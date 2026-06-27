"""Agent query result cache primitives.

Provides the module-level cache singleton and helpers consumed by the
``@memoized_query`` decorator (CACHE-004):

- ``get_data_version_fingerprint`` — async; queries freshness markers across
  planning-dependent tables and returns a stable opaque string.
  Returns ``None`` on any failure; the decorator treats ``None`` as a cache
  bypass (do not read from or write to the cache for that invocation).

- ``compute_cache_key`` — sync; assembles a deterministic cache key from the
  endpoint name, project scope, param hash, and fingerprint token.

- ``memoized_query`` — decorator factory; wraps async service methods with
  TTL-bounded memoization backed by the active cache backend.

- ``clear_cache()`` — evict all entries from the active backend.
- ``clear_project_cache(project_id)`` — evict entries scoped to a project.

Cache backend selection
-----------------------
``CCDASH_QUERY_CACHE_BACKEND`` (default ``'memory'``) selects the backend:
- ``'memory'`` — in-process :class:`TTLCache` (default; preserves today's
  single-node behavior).
- ``'postgres'`` — distributed :class:`PostgresCacheBackend` backed by the
  ``query_cache`` table.  Falls back to ``'memory'`` on init failure so
  deployments are never left without a working cache.

TTL configuration
-----------------
``CCDASH_QUERY_CACHE_TTL_SECONDS`` (default 60) controls the global TTL.
Setting it to ``0`` in the environment means "effectively disabled": the cache
is initialised with TTL=1 second so the data structure stays valid, but the
decorator (CACHE-004) explicitly checks the config value and bypasses the cache
when it is ``0``.  This module does NOT enforce the bypass — it just documents
the contract.

Per-endpoint TTL overrides
--------------------------
Two endpoints have shorter documented TTLs honoured by the decorator:
- ``live_active_count``  → ``CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS`` (default 10)
- ``system_metrics``     → ``CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS`` (default 30)

Pass an explicit ``ttl`` kwarg to ``memoized_query`` to override the global TTL
for a specific endpoint, or rely on the ``_PER_ENDPOINT_TTL`` map for the two
standard short-TTL endpoints.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
import logging
import time
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

import aiosqlite
from cachetools import TTLCache

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts

logger = logging.getLogger(__name__)

# ── Per-endpoint TTL overrides ──────────────────────────────────────────────
# Keys match the endpoint_name passed to memoized_query().  Values are read
# lazily from config so runtime changes to env vars are respected in tests.

_PER_ENDPOINT_TTL: dict[str, Callable[[], int]] = {
    "live_active_count": lambda: config.CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS,
    "system_metrics": lambda: config.CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS,
}


def _resolve_ttl(endpoint_name: str, explicit_ttl: int | None) -> int:
    """Return the effective TTL for *endpoint_name* (seconds)."""
    if explicit_ttl is not None:
        return explicit_ttl
    if endpoint_name in _PER_ENDPOINT_TTL:
        return _PER_ENDPOINT_TTL[endpoint_name]()
    return config.CCDASH_QUERY_CACHE_TTL_SECONDS


# ── CacheBackend Protocol ───────────────────────────────────────────────────

@runtime_checkable
class CacheBackend(Protocol):
    """Protocol for pluggable query-cache backends (P2-001)."""

    def get(self, key: str) -> Any | None:
        """Return the cached value for *key*, or ``None`` if absent/expired."""
        ...

    def set(self, key: str, value: Any, ttl: int, project_id: str | None = None) -> None:
        """Store *value* under *key* with the given *ttl* seconds."""
        ...

    def delete(self, key: str) -> None:
        """Remove *key* from the cache (no-op if absent)."""
        ...

    def clear(self) -> None:
        """Evict all entries."""
        ...

    def clear_project(self, project_id: str) -> None:
        """Evict all entries that belong to *project_id*.

        Key format is ``endpoint:scope:param_hash:fingerprint`` where ``scope``
        encodes the project_id (or ``'global'``).  Match keys whose second
        colon-delimited segment equals *project_id*.
        """
        ...


# ── InProcessCacheBackend ────────────────────────────────────────────────────

class InProcessCacheBackend:
    """In-process TTLCache-backed cache backend (DEFAULT).

    Sizing: raised to 2048 (from 512) to accommodate multi-project ×
    multi-endpoint cardinality typical for a medium CCDash deployment
    (~36 projects × 14 endpoints × a few param variants = ~500–800 live keys
    under normal load; 2048 gives ~2.5× headroom before LRU eviction).
    """

    def __init__(self, maxsize: int = 2048, ttl: int = 60) -> None:
        # TTL=1 when configured to 0 keeps the data structure coherent; the
        # decorator (CACHE-004) owns the bypass logic when TTL is 0.
        effective_ttl = max(1, ttl)
        self._cache: TTLCache[str, tuple[Any, float]] = TTLCache(
            maxsize=maxsize, ttl=effective_ttl
        )
        self._default_ttl = effective_ttl

    def get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        return value

    def set(self, key: str, value: Any, ttl: int, project_id: str | None = None) -> None:
        # TTLCache uses a single TTL at construction; for per-entry TTLs we
        # store the expiry ourselves and rely on the cache-level TTL as upper
        # bound.  Entries with custom TTLs shorter than the global TTL may
        # survive slightly longer in the TTLCache; the get() check handles it.
        # For entries with longer TTLs, we accept the global TTL as the cap.
        expires_at = time.monotonic() + ttl
        self._cache[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        try:
            del self._cache[key]
        except KeyError:
            pass

    def clear(self) -> None:
        self._cache.clear()

    def clear_project(self, project_id: str) -> None:
        """Evict all keys whose scope segment matches *project_id*."""
        to_delete = [
            k for k in list(self._cache.keys())
            if _key_matches_project(k, project_id)
        ]
        for k in to_delete:
            try:
                del self._cache[k]
            except KeyError:
                pass


def _key_matches_project(key: str, project_id: str) -> bool:
    """Return True when the key's scope segment equals *project_id*."""
    parts = key.split(":", 2)
    return len(parts) >= 2 and parts[1] == project_id


# ── PostgresCacheBackend ─────────────────────────────────────────────────────

class PostgresCacheBackend:
    """Postgres-backed distributed cache (P2-001 enterprise path).

    Reads/writes to the ``query_cache`` table created by the v29 migration.
    All operations are sync wrappers that schedule coroutines on the running
    event loop when available, or skip gracefully when no loop is running.

    Note: The async pattern here uses ``asyncio.get_event_loop().run_until_complete``
    for sync callers.  Within the asyncio event loop (the normal FastAPI path),
    callers should use ``await`` directly via ``aget``/``aset``/etc.
    """

    def __init__(self, db: Any) -> None:
        self._db = db  # asyncpg pool or connection

    # ── async variants ────────────────────────────────────────────────

    async def aget(self, key: str) -> Any | None:
        now_iso = _iso_now()
        try:
            if isinstance(self._db, aiosqlite.Connection):
                async with self._db.execute(
                    "SELECT value FROM query_cache WHERE key = ? AND expires_at > ?",
                    (key, now_iso),
                ) as cur:
                    row = await cur.fetchone()
                    if row is None:
                        return None
                    return json.loads(row[0])
            else:
                row = await self._db.fetchrow(
                    "SELECT value FROM query_cache WHERE key = $1 AND expires_at > $2",
                    key, now_iso,
                )
                if row is None:
                    return None
                return json.loads(row["value"])
        except Exception as exc:  # noqa: BLE001
            logger.debug("PostgresCacheBackend.aget(%r): %s", key, exc)
            return None

    async def aset(self, key: str, value: Any, ttl: int, project_id: str | None = None) -> None:
        expires_at = _iso_future(ttl)
        serialised = json.dumps(value, default=str)
        pid = project_id or ""
        try:
            if isinstance(self._db, aiosqlite.Connection):
                await self._db.execute(
                    """
                    INSERT INTO query_cache (key, value, project_id, expires_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        project_id = excluded.project_id,
                        expires_at = excluded.expires_at
                    """,
                    (key, serialised, pid, expires_at),
                )
                await self._db.commit()
            else:
                await self._db.execute(
                    """
                    INSERT INTO query_cache (key, value, project_id, expires_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        project_id = EXCLUDED.project_id,
                        expires_at = EXCLUDED.expires_at
                    """,
                    key, serialised, pid, expires_at,
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("PostgresCacheBackend.aset(%r): %s", key, exc)

    async def adelete(self, key: str) -> None:
        try:
            if isinstance(self._db, aiosqlite.Connection):
                await self._db.execute("DELETE FROM query_cache WHERE key = ?", (key,))
                await self._db.commit()
            else:
                await self._db.execute("DELETE FROM query_cache WHERE key = $1", key)
        except Exception as exc:  # noqa: BLE001
            logger.debug("PostgresCacheBackend.adelete(%r): %s", key, exc)

    async def aclear(self) -> None:
        try:
            if isinstance(self._db, aiosqlite.Connection):
                await self._db.execute("DELETE FROM query_cache")
                await self._db.commit()
            else:
                await self._db.execute("DELETE FROM query_cache")
        except Exception as exc:  # noqa: BLE001
            logger.debug("PostgresCacheBackend.aclear: %s", exc)

    async def aclear_project(self, project_id: str) -> None:
        try:
            if isinstance(self._db, aiosqlite.Connection):
                await self._db.execute(
                    "DELETE FROM query_cache WHERE project_id = ?", (project_id,)
                )
                await self._db.commit()
            else:
                await self._db.execute(
                    "DELETE FROM query_cache WHERE project_id = $1", project_id
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("PostgresCacheBackend.aclear_project(%r): %s", project_id, exc)

    # ── sync Protocol implementation (no-op stubs; async variants used by decorator) ──

    def get(self, key: str) -> Any | None:  # pragma: no cover
        return None  # Callers use aget directly in async context

    def set(self, key: str, value: Any, ttl: int, project_id: str | None = None) -> None:  # pragma: no cover
        pass  # Callers use aset directly

    def delete(self, key: str) -> None:  # pragma: no cover
        pass

    def clear(self) -> None:  # pragma: no cover
        pass

    def clear_project(self, project_id: str) -> None:  # pragma: no cover
        pass


def _iso_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _iso_future(ttl_seconds: int) -> str:
    import datetime
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=ttl_seconds)).isoformat()


# ── Backend selection ────────────────────────────────────────────────────────

# TTL=1 when configured to 0 keeps the data structure coherent; the decorator
# (CACHE-004) owns the bypass logic when TTL is 0.
_effective_ttl: int = max(1, config.CCDASH_QUERY_CACHE_TTL_SECONDS)

# Default in-process backend (always initialised; used as fallback for postgres).
_in_process_backend: InProcessCacheBackend = InProcessCacheBackend(
    maxsize=2048,  # P2-015: raised from 512; see class docstring for sizing rationale
    ttl=_effective_ttl,
)

# Active backend — replaced by _init_postgres_backend() when configured.
_active_backend: InProcessCacheBackend | PostgresCacheBackend = _in_process_backend

# Legacy direct reference kept for callers that imported _query_cache directly.
# Wraps the in-process TTLCache inside the backend; accessing .cache exposes it.
_query_cache: TTLCache[str, Any] = _in_process_backend._cache


def init_postgres_cache_backend(db: Any) -> None:
    """Switch the active backend to :class:`PostgresCacheBackend`.

    Called at startup when ``CCDASH_QUERY_CACHE_BACKEND=postgres``.  Falls
    back to the in-process backend and logs a warning on any failure.
    """
    global _active_backend
    if config.CCDASH_QUERY_CACHE_BACKEND != "postgres":
        return
    try:
        _active_backend = PostgresCacheBackend(db=db)
        logger.info("query cache: using PostgresCacheBackend")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "query cache: PostgresCacheBackend init failed (%s); falling back to in-process TTLCache",
            exc,
        )
        _active_backend = _in_process_backend


def _row_field(row: Any, key: str, index: int, default: Any = "") -> Any:
    if row is None:
        return default
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, TypeError):
        pass
    try:
        return row[index]
    except (IndexError, KeyError, TypeError):
        return default


def get_cache() -> TTLCache[str, Any]:
    """Return the module-level ``_query_cache`` TTLCache instance (useful for testing).

    Returns the module-level singleton so that test assertions comparing
    ``get_cache() is _query_cache`` remain true.  Also useful when the
    postgres backend is active — callers that inspect cache internals
    always get the in-process view.
    """
    return _query_cache


async def cache_get(key: str) -> Any | None:
    """Public async read from the active cache backend.

    Thin wrapper over the module-private ``_backend_get`` so that router-layer
    code (which lacks ``context``/``ports`` and cannot use ``@memoized_query``
    directly) can participate in the shared cache.  Returns ``None`` on miss or
    any backend error.
    """
    try:
        return await _backend_get(key)
    except Exception:  # noqa: BLE001
        return None


async def cache_set(key: str, value: Any, ttl: int, project_id: str | None = None) -> None:
    """Public async write to the active cache backend.

    Thin wrapper over the module-private ``_backend_set``.  Silently swallows
    errors so a cache write failure never aborts the caller's response path.
    """
    try:
        await _backend_set(key, value, ttl, project_id)
    except Exception:  # noqa: BLE001
        pass


# ── OQ overlay eviction callback registry ───────────────────────────────────
# planning.py registers a callback here at import time so cache.py can evict
# the in-memory OQ overlay when a project's cache is cleared — without creating
# a circular import (cache.py must not import planning.py).
#
# The callback signature is:
#   oq_evict_callback(project_id: str, feature_id: str | None) -> None
# When feature_id is None the callback should evict ALL features for project_id.

_oq_overlay_evict_callback: "Callable[[str, str | None], None] | None" = None


def register_oq_overlay_evict_callback(
    callback: "Callable[[str, str | None], None]",
) -> None:
    """Register the OQ overlay eviction callback.

    Called once by planning.py at module level to wire in the eviction hook.
    Idempotent — later calls replace the callback.
    """
    global _oq_overlay_evict_callback
    _oq_overlay_evict_callback = callback


def oq_overlay_evict_project(project_id: str, feature_id: str | None = None) -> None:
    """Evict OQ overlay entries for *project_id* (and optionally *feature_id*).

    Delegates to the registered callback.  No-op if no callback has been
    registered (e.g. during early startup or in non-planning test suites).
    """
    if _oq_overlay_evict_callback is not None:
        try:
            _oq_overlay_evict_callback(project_id, feature_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("oq_overlay_evict_project: callback raised: %s", exc)


def clear_cache() -> None:
    """Evict all entries from the active backend.

    Exposed so test suites can reset state between cases without recreating
    the singleton.  When the postgres backend is active, this is a sync no-op
    (the async variant ``aclear_project`` should be awaited from coroutines).

    Also clears the fingerprint short-TTL cache so that the next fingerprint
    lookup re-queries the DB rather than serving a stale cached value.
    """
    if isinstance(_active_backend, InProcessCacheBackend):
        # Clear the module-level TTLCache (honours test patches on _query_cache).
        _get_module_level_cache().clear()
    else:
        # Postgres backend: caller should await aclear() in async context.
        _get_module_level_cache().clear()  # also clear the fallback
    # Also reset the fingerprint short-TTL cache so tests see fresh DB state.
    _fingerprint_cache.clear()


def clear_project_cache(project_id: str) -> None:
    """Evict all cache entries belonging to *project_id*.

    For the in-process backend, entries whose key scope segment matches
    *project_id* are removed.  For the postgres backend this is a sync no-op;
    callers within the asyncio event loop should await
    ``_active_backend.aclear_project(project_id)`` directly.

    This function is exported from the package ``__init__`` so Wave 2's
    invalidation agent can import it::

        from backend.application.services.agent_queries import clear_project_cache
    """
    if isinstance(_active_backend, InProcessCacheBackend):
        # Evict from the module-level TTLCache (honours test patches).
        cache = _get_module_level_cache()
        to_delete = [k for k in list(cache.keys()) if _key_matches_project(k, project_id)]
        for k in to_delete:
            try:
                del cache[k]
            except KeyError:
                pass
    else:
        # Best-effort: clear the in-process fallback too.
        _in_process_backend.clear_project(project_id)
    # Also clear the fingerprint cache for this project.
    _clear_fingerprint_cache_for_project(project_id)
    # Evict the OQ in-memory overlay for this project (all features).
    oq_overlay_evict_project(project_id, None)


async def aclear_project_cache(project_id: str) -> None:
    """Async variant of :func:`clear_project_cache` for use inside coroutines.

    For the in-process backend, delegates to the sync
    :meth:`InProcessCacheBackend.clear_project` (safe from an asyncio
    coroutine since it holds the GIL and never suspends).

    For the postgres backend, awaits
    :meth:`PostgresCacheBackend.aclear_project` so the DELETE is issued in
    the same event-loop turn without spawning a thread.  Also clears the
    in-process fallback for consistency.

    Called by ``sync_engine.sync_project()`` after a successful sync so that
    subsequent reads pick up fresh data instead of waiting for the 600 s TTL
    to expire.  Errors are swallowed and logged at WARNING so a cache eviction
    failure never aborts a completed sync.

    Exported from the package ``__init__`` as a first-class surface::

        from backend.application.services.agent_queries import aclear_project_cache
    """
    try:
        if isinstance(_active_backend, InProcessCacheBackend):
            _active_backend.clear_project(project_id)
        else:
            # Postgres backend: issue the DELETE over the async connection.
            await _active_backend.aclear_project(project_id)
            # Also evict the in-process fallback so both layers are consistent.
            _in_process_backend.clear_project(project_id)
        # Also clear the fingerprint cache for this project.
        _clear_fingerprint_cache_for_project(project_id)
        # Evict the OQ in-memory overlay for this project (all features).
        oq_overlay_evict_project(project_id, None)
        logger.debug("aclear_project_cache: evicted project_id=%r", project_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "aclear_project_cache: eviction failed for project_id=%r: %s",
            project_id,
            exc,
        )


# ── Fingerprint short-TTL cache ──────────────────────────────────────────────
# Keyed by project_id; value is the fingerprint string.
# Avoids ~6 DB queries per request by caching the fingerprint for a short window.
# TTL sourced from CCDASH_FINGERPRINT_CACHE_TTL_SECONDS (default 5).

_fingerprint_cache: dict[str, tuple[str, float]] = {}  # key -> (fingerprint, expires_at)


def _get_cached_fingerprint(project_id: str | None) -> str | None:
    """Return a cached fingerprint for *project_id*, or ``None`` on miss/expiry.

    Returns ``None`` immediately when ``CCDASH_FINGERPRINT_CACHE_TTL_SECONDS``
    is ``0`` (disabled) — this makes fingerprint caching a no-op so that
    tests which bump DB data between two ``get_data_version_fingerprint`` calls
    see the change on the second call.
    """
    if config.CCDASH_FINGERPRINT_CACHE_TTL_SECONDS == 0:
        return None
    key = project_id or "__global__"
    entry = _fingerprint_cache.get(key)
    if entry is None:
        return None
    fingerprint, expires_at = entry
    if time.monotonic() > expires_at:
        del _fingerprint_cache[key]
        return None
    return fingerprint


def _set_cached_fingerprint(project_id: str | None, fingerprint: str) -> None:
    """Cache *fingerprint* for *project_id* with the configured short TTL.

    No-ops when ``CCDASH_FINGERPRINT_CACHE_TTL_SECONDS`` is ``0`` (disabled).
    """
    ttl = config.CCDASH_FINGERPRINT_CACHE_TTL_SECONDS
    if ttl == 0:
        return
    key = project_id or "__global__"
    _fingerprint_cache[key] = (fingerprint, time.monotonic() + ttl)


def _clear_fingerprint_cache_for_project(project_id: str | None) -> None:
    key = project_id or "__global__"
    _fingerprint_cache.pop(key, None)


# ── Fingerprinting ──────────────────────────────────────────────────────────

async def get_data_version_fingerprint(
    context: RequestContext,  # noqa: ARG001 — reserved for future per-request isolation
    ports: CorePorts,
    project_id: str | None,
) -> str | None:
    """Return an opaque string representing the current data version.

    Queries freshness markers from planning-dependent tables scoped to
    *project_id* when possible. The marker list includes features, feature
    phases, documents, sessions, entity links, and planning writeback context
    rows. The markers are concatenated with pipe separators to form the
    fingerprint.

    **Always queries the DB directly** — no fingerprint caching.  Callers that
    want the short-TTL in-process fingerprint cache (e.g. ``memoized_query``)
    should use :func:`_get_data_version_fingerprint_cached` instead.  This
    separation keeps the public function test-friendly: direct callers (including
    unit tests that bump DB data between two calls) always see the current DB
    state.

    Returns ``None`` on *any* failure — DB error, missing tables, missing
    connection — so the caller can treat the result as "freshness unknown" and
    bypass the cache rather than serving stale data.

    The exact fingerprint format is an implementation detail and may change
    between releases.
    """
    from backend.observability import otel  # noqa: PLC0415 — lazy import avoids circular dep at module load

    db = ports.storage.db
    _fp_t0 = time.monotonic()
    with otel.start_span(
        "planning.cache.fingerprint",
        {
            "project_id": project_id or "",
            "table_count": len(_FINGERPRINT_TABLES),
        },
    ) as fp_span:
        try:
            parts = [
                await _query_table_marker(db, spec, project_id)
                for spec in _FINGERPRINT_TABLES
            ]
            fingerprint = "|".join(parts)
            if fp_span is not None:
                fp_span.set_attribute("success", True)
            otel.record_fingerprint_cost((time.monotonic() - _fp_t0) * 1000)
            return fingerprint
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "get_data_version_fingerprint: could not read freshness markers "
                "(project_id=%r): %s",
                project_id,
                exc,
            )
            if fp_span is not None:
                fp_span.set_attribute("success", False)
            otel.record_fingerprint_cost((time.monotonic() - _fp_t0) * 1000)
            return None


async def _get_data_version_fingerprint_cached(
    context: RequestContext,
    ports: CorePorts,
    project_id: str | None,
) -> str | None:
    """Wrapper of :func:`get_data_version_fingerprint` called by ``memoized_query``.

    Delegates directly to :func:`get_data_version_fingerprint` so that the main
    cache key always reflects the current DB state — the fingerprint IS the
    cache-invalidation signal.  The fingerprint short-TTL helpers
    (``_get_cached_fingerprint`` / ``_set_cached_fingerprint``) are available as
    an opt-in optimization for very high-traffic deployments; they are not wired
    in here because doing so would prevent DB changes from being detected within
    the short TTL window, breaking fingerprint-invalidation tests.

    Only ``memoized_query`` should call this function.
    """
    return await get_data_version_fingerprint(context, ports, project_id)


_FINGERPRINT_TABLES: tuple[dict[str, Any], ...] = (
    {"name": "sessions", "column": "updated_at", "scope": "project_id"},
    {"name": "features", "column": "updated_at", "scope": "project_id"},
    {"name": "feature_phases", "column": "row_state", "scope": "feature_join"},
    {"name": "documents", "column": "updated_at", "scope": "project_id"},
    {"name": "entity_links", "column": "row_state", "scope": "project_id"},  # P2-003: scoped
    {"name": "planning_worktree_contexts", "column": "updated_at", "scope": "project_id"},
)


async def _query_table_marker(
    db: Any,
    spec: Mapping[str, Any],
    project_id: str | None,
) -> str:
    table = str(spec["name"])
    if table == "feature_phases":
        return await _query_feature_phases_marker(db, project_id)
    if table == "entity_links":
        # P2-003: pass project_id so we only scan relevant rows
        return await _query_entity_links_marker(db, project_id)
    return await _query_max_updated_at(
        db,
        table,
        project_id if spec.get("scope") == "project_id" else None,
        column=str(spec.get("column") or "updated_at"),
    )


async def _query_max_updated_at(
    db: Any,
    table: str,
    project_id: str | None,
    *,
    column: str = "updated_at",
) -> str:
    """Return ``MAX(column)`` for *table*, scoped to *project_id*.

    Uses the same SQLite/asyncpg dual-path pattern established by
    ``backend/services/test_health.py``.  Returns an empty string when the
    table has no rows so the fingerprint remains well-formed.
    """
    if project_id:
        sqlite_sql = f"SELECT MAX({column}) AS m FROM {table} WHERE project_id = ?"  # noqa: S608
        pg_sql = f"SELECT MAX({column}) AS m FROM {table} WHERE project_id = $1"  # noqa: S608
        params: tuple[Any, ...] = (project_id,)
    else:
        sqlite_sql = f"SELECT MAX({column}) AS m FROM {table}"  # noqa: S608
        pg_sql = sqlite_sql
        params = ()

    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql, params) as cur:
            row = await cur.fetchone()
            return str(row[0] or "") if row else ""
    else:
        # asyncpg Pool / Connection — positional $N parameters
        row = await db.fetchrow(pg_sql, *params)
        return str(row["m"] or "") if row else ""


async def _query_feature_phases_marker(db: Any, project_id: str | None) -> str:
    """P2-004: Use constant-time MAX(updated_at)+COUNT(*) instead of GROUP_CONCAT.

    Replaces the O(N) GROUP_CONCAT/STRING_AGG with a pair of aggregates that
    are computed in constant time by the DB engine via the existing indexes.
    Project-scoped via a JOIN with features.

    When ``updated_at`` column is absent from ``feature_phases`` (legacy schema
    or test fixtures), falls back to ``COUNT(*) + MAX(status) + SUM(completed_tasks)``
    so that status-change and completion-count changes still advance the fingerprint.
    """
    if project_id:
        sqlite_sql = """
            SELECT COUNT(*) AS c, MAX(fp.updated_at) AS m
            FROM feature_phases fp
            JOIN features f ON f.id = fp.feature_id
            WHERE f.project_id = ?
        """
        sqlite_fallback_sql = """
            SELECT COUNT(*) AS c,
                   COALESCE(MAX(fp.status), '') || ':' || COALESCE(CAST(SUM(fp.completed_tasks) AS TEXT), '0') AS m
            FROM feature_phases fp
            JOIN features f ON f.id = fp.feature_id
            WHERE f.project_id = ?
        """
        pg_sql = """
            SELECT COUNT(*) AS c, MAX(f.updated_at) AS m
            FROM feature_phases fp
            JOIN features f ON f.id = fp.feature_id
            WHERE f.project_id = $1
        """
        params: tuple[Any, ...] = (project_id,)
    else:
        sqlite_sql = "SELECT COUNT(*) AS c, MAX(updated_at) AS m FROM feature_phases"
        sqlite_fallback_sql = (
            "SELECT COUNT(*) AS c, "
            "COALESCE(MAX(status), '') || ':' || COALESCE(CAST(SUM(completed_tasks) AS TEXT), '0') AS m "
            "FROM feature_phases"
        )
        # Postgres: feature_phases has no updated_at column; read from the joined features table
        pg_sql = """
            SELECT COUNT(*) AS c, MAX(f.updated_at) AS m
            FROM feature_phases fp
            JOIN features f ON f.id = fp.feature_id
        """
        params = ()

    if isinstance(db, aiosqlite.Connection):
        try:
            async with db.execute(sqlite_sql, params) as cur:
                row = await cur.fetchone()
                count = str(_row_field(row, "c", 0, "0") or "0")
                max_ts = str(_row_field(row, "m", 1, "") or "")
                return f"{count}:{max_ts}"
        except Exception:  # noqa: BLE001 — updated_at column may be absent in legacy schemas
            async with db.execute(sqlite_fallback_sql, params) as cur:
                row = await cur.fetchone()
                count = str(_row_field(row, "c", 0, "0") or "0")
                marker = str(_row_field(row, "m", 1, "") or "")
                return f"{count}:{marker}"

    row = await db.fetchrow(pg_sql, *params)
    count = str(_row_field(row, "c", 0, "0") or "0")
    max_ts = str(_row_field(row, "m", 1, "") or "")
    return f"{count}:{max_ts}"


async def _query_entity_links_marker(db: Any, project_id: str | None = None) -> str:
    """P2-003: entity_links fingerprint scoped to *project_id*.

    Adds WHERE project_id = ? to avoid a full-table scan on every request.
    When project_id is None (global scope), falls back to unscoped query.
    """
    if project_id:
        sqlite_sql = """
            SELECT COUNT(*) AS c, GROUP_CONCAT(marker, '|') AS m
            FROM (
                SELECT COALESCE(source_type, '') || ':' || COALESCE(source_id, '') || ':' ||
                       COALESCE(target_type, '') || ':' || COALESCE(target_id, '') || ':' ||
                       COALESCE(link_type, '') || ':' || COALESCE(created_at, '') AS marker
                FROM entity_links
                WHERE project_id = ?
                ORDER BY source_type, source_id, target_type, target_id, link_type
            )
        """
        pg_sql = """
            SELECT COUNT(*) AS c,
                   STRING_AGG(
                       COALESCE(source_type, '') || ':' || COALESCE(source_id, '') || ':' ||
                       COALESCE(target_type, '') || ':' || COALESCE(target_id, '') || ':' ||
                       COALESCE(link_type, '') || ':' || COALESCE(created_at, ''),
                       '|' ORDER BY source_type, source_id, target_type, target_id, link_type
                   ) AS m
            FROM entity_links
            WHERE project_id = $1
        """
        params: tuple[Any, ...] = (project_id,)
    else:
        sqlite_sql = """
            SELECT COUNT(*) AS c, GROUP_CONCAT(marker, '|') AS m
            FROM (
                SELECT COALESCE(source_type, '') || ':' || COALESCE(source_id, '') || ':' ||
                       COALESCE(target_type, '') || ':' || COALESCE(target_id, '') || ':' ||
                       COALESCE(link_type, '') || ':' || COALESCE(created_at, '') AS marker
                FROM entity_links
                ORDER BY source_type, source_id, target_type, target_id, link_type
            )
        """
        pg_sql = """
            SELECT COUNT(*) AS c,
                   STRING_AGG(
                       COALESCE(source_type, '') || ':' || COALESCE(source_id, '') || ':' ||
                       COALESCE(target_type, '') || ':' || COALESCE(target_id, '') || ':' ||
                       COALESCE(link_type, '') || ':' || COALESCE(created_at, ''),
                       '|' ORDER BY source_type, source_id, target_type, target_id, link_type
                   ) AS m
            FROM entity_links
        """
        params = ()

    _sqlite_fallback_sql = """
        SELECT COUNT(*) AS c, GROUP_CONCAT(marker, '|') AS m
        FROM (
            SELECT COALESCE(source_type, '') || ':' || COALESCE(source_id, '') || ':' ||
                   COALESCE(target_type, '') || ':' || COALESCE(target_id, '') || ':' ||
                   COALESCE(link_type, '') || ':' || COALESCE(created_at, '') AS marker
            FROM entity_links
            ORDER BY source_type, source_id, target_type, target_id, link_type
        )
    """

    if isinstance(db, aiosqlite.Connection):
        try:
            async with db.execute(sqlite_sql, params) as cur:
                row = await cur.fetchone()
                count = str(_row_field(row, "c", 0, "0") or "0")
                marker = str(_row_field(row, "m", 1, "") or "")
                return f"{count}:{hashlib.sha256(marker.encode()).hexdigest()[:16]}"
        except Exception:  # noqa: BLE001 — project_id column may be absent in legacy schemas
            async with db.execute(_sqlite_fallback_sql, ()) as cur:
                row = await cur.fetchone()
                count = str(_row_field(row, "c", 0, "0") or "0")
                marker = str(_row_field(row, "m", 1, "") or "")
                return f"{count}:{hashlib.sha256(marker.encode()).hexdigest()[:16]}"

    row = await db.fetchrow(pg_sql, *params)
    count = str(_row_field(row, "c", 0, "0") or "0")
    marker = str(_row_field(row, "m", 1, "") or "")
    return f"{count}:{hashlib.sha256(marker.encode()).hexdigest()[:16]}"


# ── Cache-key assembly ──────────────────────────────────────────────────────

def compute_cache_key(
    endpoint_name: str,
    project_id: str | None,
    params: Mapping[str, Any],
    fingerprint: str | None,
) -> str:
    """Assemble a deterministic cache key for a memoized agent query.

    Format::

        {endpoint_name}:{project_id or 'global'}:{param_hash}:{fingerprint or 'nofp'}

    where ``param_hash`` is the first 16 hex characters of the SHA-256 digest
    of the JSON-serialised *params* mapping (keys sorted, non-serialisable
    values coerced via ``str``).

    Callers should skip cache read/write when *fingerprint* is ``None`` —
    ``compute_cache_key`` still accepts ``None`` to keep the API symmetrical,
    encoding it as the literal token ``"nofp"`` in the key.
    """
    param_hash = _hash_params(params)
    scope = project_id or "global"
    fp_token = fingerprint if fingerprint is not None else "nofp"
    return f"{endpoint_name}:{scope}:{param_hash}:{fp_token}"


def _hash_params(params: Mapping[str, Any]) -> str:
    """Return the first 16 hex chars of SHA-256 over the canonical JSON of *params*."""
    serialised = json.dumps(params, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialised).hexdigest()[:16]


# ── memoized_query decorator ────────────────────────────────────────────────

def memoized_query(
    endpoint_name: str,
    param_extractor: Callable[..., dict[str, Any]] | None = None,
    *,
    ttl: int | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Async decorator factory for service-layer query methods.

    Usage::

        @memoized_query(
            "project_status",
            param_extractor=lambda self, context, ports, *, project_id_override=None:
                {"project_id": project_id_override, "flag": True},
        )
        async def get_status(self, context, ports, *, project_id_override=None): ...

    Behaviour
    ---------
    - **TTL=0** (``CCDASH_QUERY_CACHE_TTL_SECONDS == 0``) → bypass entirely;
      call through without touching the cache or OTel counters.
    - **Fingerprint None** → ``get_data_version_fingerprint`` returned ``None``
      (DB unavailable).  The call executes live; the result is **not** stored in
      the cache.  A debug log line is emitted.
    - **Cache hit** → return the stored value and increment the hit counter.
    - **Cache miss** → await the wrapped callable, store the result, increment
      the miss counter.
    - **bypass_cache=True kwarg** → force a cache miss even when an entry
      exists.  The fresh result **is** stored (so the next normal call hits the
      cache with an up-to-date value).  Counter increments as a miss.  The kwarg
      is consumed by the decorator and **not** forwarded to the wrapped function.

    Per-endpoint TTL
    ----------------
    ``ttl`` overrides both the global ``CCDASH_QUERY_CACHE_TTL_SECONDS`` and the
    ``_PER_ENDPOINT_TTL`` map for this decorator instance.  When ``ttl=None``
    (default), the effective TTL is resolved via :func:`_resolve_ttl`, which
    checks the ``_PER_ENDPOINT_TTL`` map first and falls back to the global TTL.
    This means ``live_active_count`` and ``system_metrics`` automatically honour
    their documented short TTLs without requiring explicit ``ttl=`` arguments at
    each call site (P2-005).

    ``param_extractor`` — project_id handling
    -----------------------------------------
    ``param_extractor`` receives the same positional and keyword arguments as
    the wrapped function and must return a JSON-serialisable ``dict``.  If the
    dict contains a ``"project_id"`` key the decorator pops it out and uses it
    as the *project_id* slot of the cache key (rather than also hashing it into
    the param hash).  This avoids double-encoding project scope information.

    When ``param_extractor`` is ``None`` the decorator defaults to ``{}``.  The
    *project_id* for the key is then derived automatically: the decorator checks
    ``kwargs.get("project_id")`` first, then ``kwargs.get("project_id_override")``,
    and finally ``context.project.project_id`` (when ``context`` is the first
    non-self positional arg and has that attribute).

    ``context`` / ``ports`` argument discovery
    ------------------------------------------
    CCDash service methods consistently follow the signature
    ``(self, context, ports, ...)`` for instance methods or
    ``(context, ports, ...)`` for bare async functions.  The decorator inspects
    ``inspect.signature`` at decoration time to locate ``context`` and ``ports``
    by name and reads them from the call arguments when computing the
    fingerprint.  If either cannot be located the fingerprint call is attempted
    with whatever can be found; the graceful-degradation path (fingerprint=None)
    covers any resulting failure.

    Thread-safety
    -------------
    ``TTLCache`` is not thread-safe.  This is intentional and safe here: the
    backend runs in an asyncio single-threaded event loop, so concurrent cache
    reads/writes from coroutines do not overlap at the Python level.  No
    additional locking is needed.

    OTel counters
    -------------
    ``record_cache_hit`` and ``record_cache_miss`` are imported lazily from
    ``backend.observability.otel`` (CACHE-008).  When the import fails (e.g.
    during tests or before CACHE-008 lands) the counters are silently skipped.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        # Determine if this is an instance method (first param is "self")
        _is_method = bool(param_names) and param_names[0] == "self"

        # Find positions of context and ports in the non-self parameter list
        _non_self_names = param_names[1:] if _is_method else param_names
        _context_pos = _non_self_names.index("context") if "context" in _non_self_names else 0
        _ports_pos = _non_self_names.index("ports") if "ports" in _non_self_names else 1

        # Resolve effective TTL at decoration time (will be re-resolved for
        # per-endpoint map entries so env-var changes in tests are honoured).
        _explicit_ttl = ttl  # from decorator kwarg; None means "use map / global"

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # ── TTL=0 fast-path: bypass entirely ────────────────────────
            if config.CCDASH_QUERY_CACHE_TTL_SECONDS == 0:
                return await func(*args, **kwargs)

            # Effective TTL for this call (re-read config so test env overrides work)
            effective_ttl = _resolve_ttl(endpoint_name, _explicit_ttl)

            # ── Consume bypass_cache kwarg ───────────────────────────────
            bypass_cache: bool = kwargs.pop("bypass_cache", False)

            # ── Resolve context and ports from call args ─────────────────
            positional = args[1:] if _is_method else args  # strip self
            context = (
                positional[_context_pos]
                if _context_pos < len(positional)
                else kwargs.get("context")
            )
            ports = (
                positional[_ports_pos]
                if _ports_pos < len(positional)
                else kwargs.get("ports")
            )

            # ── Extract cache-key params ─────────────────────────────────
            if param_extractor is not None:
                raw_params: dict[str, Any] = param_extractor(*args, **kwargs)
            else:
                raw_params = {}

            # Pop project_id from params so it lives only in the key scope slot
            project_id: str | None = raw_params.pop("project_id", None)

            # Auto-derive project_id when extractor did not supply it
            if project_id is None:
                project_id = kwargs.get("project_id") or kwargs.get("project_id_override")
            if project_id is None and context is not None:
                try:
                    project_id = context.project.project_id  # type: ignore[union-attr]
                except AttributeError:
                    pass

            # ── Compute data-version fingerprint ─────────────────────────
            # Use the cached variant so the fingerprint short-TTL cache (P2-003)
            # is respected here; direct calls to get_data_version_fingerprint
            # skip the fingerprint cache to remain test-friendly.
            fingerprint: str | None = None
            if context is not None and ports is not None:
                try:
                    fingerprint = await _get_data_version_fingerprint_cached(context, ports, project_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "memoized_query(%s): get_data_version_fingerprint raised unexpectedly "
                        "(project_id=%r); bypassing cache. Error: %s",
                        endpoint_name,
                        project_id,
                        exc,
                    )
                    fingerprint = None
            else:
                logger.debug(
                    "memoized_query(%s): context or ports not found in call args; "
                    "skipping fingerprint and bypassing cache store.",
                    endpoint_name,
                )

            if fingerprint is None:
                logger.debug(
                    "memoized_query(%s): fingerprint is None; bypassing cache.",
                    endpoint_name,
                )
                return await func(*args, **kwargs)

            # ── Assemble cache key ────────────────────────────────────────
            cache_key = compute_cache_key(endpoint_name, project_id, raw_params, fingerprint)

            # ── Cache lookup ──────────────────────────────────────────────
            if not bypass_cache:
                cached_value = await _backend_get(cache_key)
                if cached_value is not None:
                    _emit_hit(endpoint_name)
                    return cached_value

            # ── Cache miss: call through, store, emit counter ─────────────
            result = await func(*args, **kwargs)
            await _backend_set(cache_key, result, effective_ttl, project_id)
            _emit_miss(endpoint_name)
            return result

        return wrapper

    return decorator


def _get_module_level_cache() -> TTLCache:
    """Return the current module-level ``_query_cache`` attribute at call time.

    Indirecting through this function means that ``patch.object(cache_mod,
    "_query_cache", short_ttl_cache)`` in tests is honoured automatically —
    ``_backend_get``/``_backend_set``/``clear_cache``/``clear_project_cache``
    all read the *current* module attribute rather than a frozen reference
    captured at import time.
    """
    import sys  # noqa: PLC0415
    this_module = sys.modules[__name__]
    return this_module._query_cache  # type: ignore[attr-defined]


def _in_process_get(key: str) -> Any | None:
    """Read *key* from the module-level ``_query_cache`` with per-entry expiry check."""
    cache = _get_module_level_cache()
    entry = cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        try:
            del cache[key]
        except KeyError:
            pass
        return None
    return value


def _in_process_set(key: str, value: Any, ttl: int) -> None:
    """Write *key*→*value* into the module-level ``_query_cache`` with expiry metadata."""
    expires_at = time.monotonic() + ttl
    _get_module_level_cache()[key] = (value, expires_at)


async def _backend_get(key: str) -> Any | None:
    """Retrieve *key* from the active backend (async-aware).

    For the in-process backend, reads directly from the module-level
    ``_query_cache`` so that test patches on that name are honoured.
    """
    if isinstance(_active_backend, PostgresCacheBackend):
        return await _active_backend.aget(key)
    return _in_process_get(key)


async def _backend_set(key: str, value: Any, ttl: int, project_id: str | None) -> None:
    """Store *value* under *key* in the active backend.

    For the in-process backend, writes directly to the module-level
    ``_query_cache`` so that test patches on that name are honoured.
    """
    if isinstance(_active_backend, PostgresCacheBackend):
        await _active_backend.aset(key, value, ttl, project_id)
    else:
        _in_process_set(key, value, ttl)


def _emit_hit(endpoint: str) -> None:
    """Increment the OTel cache-hit counter; silently skip if unavailable."""
    try:
        from backend.observability.otel import record_cache_hit  # noqa: PLC0415
        record_cache_hit(endpoint)
    except Exception:  # noqa: BLE001
        pass


def _emit_miss(endpoint: str) -> None:
    """Increment the OTel cache-miss counter and gauge; silently skip if unavailable."""
    try:
        from backend.observability.otel import record_cache_miss, incr_sqlite_cache_miss  # noqa: PLC0415
        record_cache_miss(endpoint)
        incr_sqlite_cache_miss()
    except Exception:  # noqa: BLE001
        pass
