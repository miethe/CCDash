"""WorkspaceTokenAuthBackend: argon2id-based workspace-scoped bearer token verification.

Architecture note — O(N) verification per request:
    argon2id hashes are not query-indexable because the KDF salt is stored as
    part of each hash. The strategy here is:

    1. Maintain an in-memory snapshot of (workspace_id, token_id, hashed_token)
       rows loaded at startup and refreshed every SNAPSHOT_TTL_SECONDS (60 s).
    2. On verify(secret): iterate the snapshot calling PasswordHasher.verify()
       until a match is found or the snapshot is exhausted — O(N tokens).
    3. An LRU cache keyed by SHA-256(secret) short-circuits repeat calls within
       TTL (60 s, maxsize 256) so the O(N) argon2 work is only paid once per
       unique token per TTL window.

    For the v1 scale (tens of tokens) argon2id verify runs in ~100-300 ms per
    token. The LRU reduces steady-state auth cost to a single SHA-256 hash plus
    a dictionary lookup.

    ADR-008 Risk row: "Argon2id verify cost".  If token count reaches hundreds
    the snapshot approach should be replaced with a pre-indexed short-hash
    (BLAKE2s-128 of the secret stored alongside the argon2id hash) as a fast
    pre-filter.  That is out of scope for v1.

Revocation guarantee (ADR-008 hard gate §2):
    On each LRU cache hit, a fast indexed lookup (`SELECT 1 FROM workspace_tokens
    WHERE token_id = :tid AND revoked_at IS NULL`) re-checks the live DB before
    returning the cached AuthContext.  If the row is now revoked, the cache entry
    is evicted and None is returned — ensuring a revoked token is rejected within
    one request cycle even within the LRU TTL window.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable, Awaitable
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cachetools import TTLCache

from backend.adapters.auth.context import AuthContext

logger = logging.getLogger("ccdash.auth.workspace_token")

# --------------------------------------------------------------------------- #
# Constants                                                                     #
# --------------------------------------------------------------------------- #
SNAPSHOT_TTL_SECONDS: int = 60
"""Seconds between full in-memory snapshot refreshes from the DB."""

LRU_MAXSIZE: int = 256
LRU_TTL_SECONDS: int = 60

_SECRET_LOG_PREFIX_LEN: int = 6
"""Maximum prefix length of a secret ever written to a log line."""


def _secret_prefix(secret: str) -> str:
    """Return a safe loggable prefix of the secret."""
    return secret[:_SECRET_LOG_PREFIX_LEN] + "..."


def _fingerprint(secret: str) -> str:
    """SHA-256 fingerprint of the plaintext secret for LRU keying."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Backend                                                                       #
# --------------------------------------------------------------------------- #


class WorkspaceTokenAuthBackend:
    """Argon2id workspace-scoped bearer-token verifier.

    Parameters
    ----------
    get_db:
        Zero-argument async callable that returns the live aiosqlite/asyncpg
        connection.  Matches the pattern used by the existing
        StaticBearerTokenIdentityProvider — the connection is obtained lazily
        on first use rather than at construction time to avoid coupling
        to startup ordering.
    """

    def __init__(self, get_db: Callable[[], Awaitable[Any]]) -> None:
        self._get_db = get_db
        self._ph = PasswordHasher()
        # Snapshot: list of (workspace_id, token_id, project_id, scope, hashed_token)
        self._snapshot: list[tuple[str, str, str, str, str]] = []
        self._snapshot_loaded_at: float = 0.0
        # LRU cache: sha256(secret) -> AuthContext | None
        # TTLCache is not thread-safe for concurrent writes but in an async
        # single-threaded event loop it is fine.
        self._lru: TTLCache[str, AuthContext | None] = TTLCache(
            maxsize=LRU_MAXSIZE, ttl=LRU_TTL_SECONDS
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def verify(self, secret: str) -> AuthContext | None:
        """Verify a bearer secret and return the resolved AuthContext or None.

        Returns None on miss (unknown token).  Callers should distinguish
        between None (miss) and a revoked result by checking whether the
        token_id was previously valid — the dependency layer handles error
        code selection based on the 401 path.

        NOTE: never logs the full secret — only the first 6 characters.
        NOTE: never logs hashed_token values.
        """
        fp = _fingerprint(secret)

        # --- LRU cache hit path ------------------------------------------- #
        if fp in self._lru:
            cached = self._lru[fp]
            if cached is None:
                logger.debug(
                    "auth.workspace_token: LRU cache miss-cached (secret_prefix=%s)",
                    _secret_prefix(secret),
                )
                return None

            # Re-check revocation in DB using fast indexed lookup.
            if not await self._is_token_active(cached.token_id):
                logger.info(
                    "auth.workspace_token: cached token revoked (token_id=%s, secret_prefix=%s)",
                    cached.token_id,
                    _secret_prefix(secret),
                )
                del self._lru[fp]
                return None

            logger.debug(
                "auth.workspace_token: LRU cache hit (token_id=%s, workspace_id=%s)",
                cached.token_id,
                cached.workspace_id,
            )
            asyncio.create_task(self._update_last_used(cached.token_id))
            return cached

        # --- Snapshot / argon2 path --------------------------------------- #
        await self._ensure_snapshot_fresh()

        for workspace_id, token_id, project_id, scope, hashed_token in self._snapshot:
            try:
                self._ph.verify(hashed_token, secret)
            except VerifyMismatchError:
                continue
            except VerificationError:
                # Hash format / parameter mismatch — log and skip, not a hard error.
                logger.warning(
                    "auth.workspace_token: argon2 verification error for token_id=%s "
                    "(may indicate corrupted hash or parameter mismatch)",
                    token_id,
                )
                continue

            # Match found — re-confirm revocation status via live DB.
            if not await self._is_token_active(token_id):
                logger.info(
                    "auth.workspace_token: matched but revoked (token_id=%s, secret_prefix=%s)",
                    token_id,
                    _secret_prefix(secret),
                )
                # Cache as None so future requests skip the O(N) scan.
                self._lru[fp] = None
                return None

            ctx = AuthContext(
                workspace_id=workspace_id,
                project_id=project_id,
                token_id=token_id,
                scope=scope,
            )
            self._lru[fp] = ctx
            logger.info(
                "auth.workspace_token: verified (token_id=%s, workspace_id=%s, "
                "project_id=%s, scope=%s, secret_prefix=%s)",
                token_id,
                workspace_id,
                project_id,
                scope,
                _secret_prefix(secret),
            )
            asyncio.create_task(self._update_last_used(token_id))
            return ctx

        # No match in snapshot.
        self._lru[fp] = None
        logger.debug(
            "auth.workspace_token: no matching token (secret_prefix=%s)",
            _secret_prefix(secret),
        )
        return None

    def invalidate(self) -> None:
        """Evict the entire LRU cache and force a snapshot refresh on next verify.

        Call this after inserting a new token row or setting ``revoked_at`` on
        an existing row so the change propagates within one request cycle.
        """
        self._lru.clear()
        self._snapshot_loaded_at = 0.0
        logger.debug("auth.workspace_token: cache + snapshot invalidated")

    def invalidate_token(self, token_id: str) -> None:
        """Evict LRU entries cached for a specific ``token_id``.

        Walks the LRU and removes any entry whose cached AuthContext matches
        the given token_id.  Also resets the snapshot TTL so a fresh DB load
        occurs on the next verify call.
        """
        keys_to_evict = [
            fp
            for fp, ctx in list(self._lru.items())
            if isinstance(ctx, AuthContext) and ctx.token_id == token_id
        ]
        for key in keys_to_evict:
            try:
                del self._lru[key]
            except KeyError:
                pass
        self._snapshot_loaded_at = 0.0
        logger.debug(
            "auth.workspace_token: evicted %d LRU entries for token_id=%s",
            len(keys_to_evict),
            token_id,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _ensure_snapshot_fresh(self) -> None:
        """Reload the token snapshot from the DB if the TTL has expired."""
        now = time.monotonic()
        if now - self._snapshot_loaded_at < SNAPSHOT_TTL_SECONDS:
            return
        await self._reload_snapshot()

    async def _reload_snapshot(self) -> None:
        db = await self._get_db()
        try:
            async with db.execute(
                """
                SELECT workspace_id, token_id, project_id, scope, hashed_token
                FROM   workspace_tokens
                WHERE  revoked_at IS NULL
                ORDER  BY created_at ASC
                """
            ) as cur:
                rows = await cur.fetchall()
        except Exception:  # noqa: BLE001
            logger.exception("auth.workspace_token: failed to reload token snapshot")
            return

        self._snapshot = [
            (str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]))
            for r in rows
        ]
        self._snapshot_loaded_at = time.monotonic()
        logger.debug(
            "auth.workspace_token: snapshot refreshed (%d active tokens)", len(self._snapshot)
        )

    async def _is_token_active(self, token_id: str) -> bool:
        """Fast indexed lookup — returns True iff the token exists and is not revoked."""
        db = await self._get_db()
        try:
            async with db.execute(
                "SELECT 1 FROM workspace_tokens WHERE token_id = ? AND revoked_at IS NULL",
                (token_id,),
            ) as cur:
                row = await cur.fetchone()
            return row is not None
        except Exception:  # noqa: BLE001
            logger.exception(
                "auth.workspace_token: revocation re-check failed for token_id=%s; "
                "treating as active to avoid false rejections",
                token_id,
            )
            # Fail open on DB errors during revocation check to avoid
            # denying service when the DB is temporarily unavailable.
            return True

    async def _update_last_used(self, token_id: str) -> None:
        """Asynchronous fire-and-forget update of last_used_at."""
        db = await self._get_db()
        try:
            await db.execute(
                "UPDATE workspace_tokens SET last_used_at = datetime('now') WHERE token_id = ?",
                (token_id,),
            )
            await db.commit()
        except Exception:  # noqa: BLE001
            logger.warning(
                "auth.workspace_token: failed to update last_used_at for token_id=%s",
                token_id,
            )
