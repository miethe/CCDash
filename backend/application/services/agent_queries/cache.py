"""Agent query result cache primitives.

Provides the module-level TTLCache singleton and helpers consumed by the
``@memoized_query`` decorator (CACHE-004):

- ``get_data_version_fingerprint`` — async; queries freshness markers across
  planning-dependent tables and returns a stable opaque string.
  Returns ``None`` on any failure; the decorator treats ``None`` as a cache
  bypass (do not read from or write to the cache for that invocation).

- ``compute_cache_key`` — sync; assembles a deterministic cache key from the
  endpoint name, project scope, param hash, and fingerprint token.

- ``memoized_query`` — decorator factory; wraps async service methods with
  TTL-bounded memoization backed by the module-level TTLCache singleton.

TTL configuration
-----------------
``CCDASH_QUERY_CACHE_TTL_SECONDS`` (default 60) controls the TTLCache TTL.
Setting it to ``0`` in the environment means "effectively disabled": the cache
is initialised with TTL=1 second so the data structure stays valid, but the
decorator (CACHE-004) explicitly checks the config value and bypasses the cache
when it is ``0``.  This module does NOT enforce the bypass — it just documents
the contract.
"""
from __future__ import annotations

import functools
import hashlib
import inspect
import json
import logging
from typing import Any, Callable, Mapping

import aiosqlite
from cachetools import TTLCache

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts

logger = logging.getLogger(__name__)

# ── Module-level cache singleton ────────────────────────────────────────────

# TTL=1 when configured to 0 keeps the data structure coherent; the decorator
# (CACHE-004) owns the bypass logic when TTL is 0.
_effective_ttl: int = max(1, config.CCDASH_QUERY_CACHE_TTL_SECONDS)

_query_cache: TTLCache[str, Any] = TTLCache(maxsize=512, ttl=_effective_ttl)


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
    """Return the module-level cache instance (useful for testing)."""
    return _query_cache


def clear_cache() -> None:
    """Evict all entries from the cache.

    Exposed so test suites can reset state between cases without recreating
    the singleton.
    """
    _query_cache.clear()


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

    Returns ``None`` on *any* failure — DB error, missing tables, missing
    connection — so the caller can treat the result as "freshness unknown" and
    bypass the cache rather than serving stale data.

    The exact fingerprint format is an implementation detail and may change
    between releases.
    """
    from backend.observability import otel  # noqa: PLC0415 — lazy import avoids circular dep at module load

    db = ports.storage.db
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
            return None


_FINGERPRINT_TABLES: tuple[dict[str, Any], ...] = (
    {"name": "sessions", "column": "updated_at", "scope": "project_id"},
    {"name": "features", "column": "updated_at", "scope": "project_id"},
    {"name": "feature_phases", "column": "row_state", "scope": "feature_join"},
    {"name": "documents", "column": "updated_at", "scope": "project_id"},
    {"name": "entity_links", "column": "row_state", "scope": None},
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
        return await _query_entity_links_marker(db)
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
    if project_id:
        sqlite_sql = """
            SELECT COUNT(*) AS c, GROUP_CONCAT(marker, '|') AS m
            FROM (
                SELECT fp.id || ':' || fp.feature_id || ':' || fp.phase || ':' ||
                       COALESCE(fp.status, '') || ':' || COALESCE(fp.progress, 0) || ':' ||
                       COALESCE(fp.total_tasks, 0) || ':' || COALESCE(fp.completed_tasks, 0) AS marker
                FROM feature_phases fp
                JOIN features f ON f.id = fp.feature_id
                WHERE f.project_id = ?
                ORDER BY fp.id
            )
        """
        pg_sql = """
            SELECT COUNT(*) AS c,
                   STRING_AGG(
                       fp.id || ':' || fp.feature_id || ':' || fp.phase || ':' ||
                       COALESCE(fp.status, '') || ':' || COALESCE(fp.progress::text, '0') || ':' ||
                       COALESCE(fp.total_tasks::text, '0') || ':' || COALESCE(fp.completed_tasks::text, '0'),
                       '|' ORDER BY fp.id
                   ) AS m
            FROM feature_phases fp
            JOIN features f ON f.id = fp.feature_id
            WHERE f.project_id = $1
        """
        params: tuple[Any, ...] = (project_id,)
    else:
        sqlite_sql = """
            SELECT COUNT(*) AS c, GROUP_CONCAT(marker, '|') AS m
            FROM (
                SELECT id || ':' || feature_id || ':' || phase || ':' ||
                       COALESCE(status, '') || ':' || COALESCE(progress, 0) || ':' ||
                       COALESCE(total_tasks, 0) || ':' || COALESCE(completed_tasks, 0) AS marker
                FROM feature_phases
                ORDER BY id
            )
        """
        pg_sql = """
            SELECT COUNT(*) AS c,
                   STRING_AGG(
                       id || ':' || feature_id || ':' || phase || ':' ||
                       COALESCE(status, '') || ':' || COALESCE(progress::text, '0') || ':' ||
                       COALESCE(total_tasks::text, '0') || ':' || COALESCE(completed_tasks::text, '0'),
                       '|' ORDER BY id
                   ) AS m
            FROM feature_phases
        """
        params = ()

    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql, params) as cur:
            row = await cur.fetchone()
            count = str(_row_field(row, "c", 0, "0") or "0")
            marker = str(_row_field(row, "m", 1, "") or "")
            return f"{count}:{hashlib.sha256(marker.encode()).hexdigest()[:16]}"

    row = await db.fetchrow(pg_sql, *params)
    count = str(_row_field(row, "c", 0, "0") or "0")
    marker = str(_row_field(row, "m", 1, "") or "")
    return f"{count}:{hashlib.sha256(marker.encode()).hexdigest()[:16]}"


async def _query_entity_links_marker(db: Any) -> str:
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
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql) as cur:
            row = await cur.fetchone()
            count = str(_row_field(row, "c", 0, "0") or "0")
            marker = str(_row_field(row, "m", 1, "") or "")
            return f"{count}:{hashlib.sha256(marker.encode()).hexdigest()[:16]}"

    row = await db.fetchrow(pg_sql)
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

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # ── TTL=0 fast-path: bypass entirely ────────────────────────
            if config.CCDASH_QUERY_CACHE_TTL_SECONDS == 0:
                return await func(*args, **kwargs)

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
            fingerprint: str | None = None
            if context is not None and ports is not None:
                try:
                    fingerprint = await get_data_version_fingerprint(context, ports, project_id)
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
            if not bypass_cache and cache_key in _query_cache:
                _emit_hit(endpoint_name)
                return _query_cache[cache_key]

            # ── Cache miss: call through, store, emit counter ─────────────
            result = await func(*args, **kwargs)
            _query_cache[cache_key] = result
            _emit_miss(endpoint_name)
            return result

        return wrapper

    return decorator


def _emit_hit(endpoint: str) -> None:
    """Increment the OTel cache-hit counter; silently skip if unavailable."""
    try:
        from backend.observability.otel import record_cache_hit  # noqa: PLC0415
        record_cache_hit(endpoint)
    except Exception:  # noqa: BLE001
        pass


def _emit_miss(endpoint: str) -> None:
    """Increment the OTel cache-miss counter; silently skip if unavailable."""
    try:
        from backend.observability.otel import record_cache_miss  # noqa: PLC0415
        record_cache_miss(endpoint)
    except Exception:  # noqa: BLE001
        pass
