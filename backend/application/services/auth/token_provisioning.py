"""Backend-aware workspace-token provisioning (ADR-008 §Migration Path).

This is the ONE place workspace tokens are minted. It replaces the SQLite-only
logic that used to live inline in
``backend/scripts/migrate_bearer_to_workspace_token.py`` (which is now a thin
deprecated shim over this module) and is the implementation behind
``ccdash token mint``.

Why it exists (node_01KZVXWY2CR9V2GG04PQNFZ1EM)
-----------------------------------------------
The old script used the aiosqlite cursor idiom (``async with db.execute(...)``),
``?`` placeholders and ``INSERT OR IGNORE`` — all SQLite-only. On the Postgres
backend the first line raised, a bare ``except`` resolved the schema version as
``0``, and it then called ``run_migrations()`` **against a live, fully-migrated
production database**. It aborted on the first ``PRAGMA`` by luck, not design.

Design rules encoded here (do not "relax" them — each maps to an AC):
  * AC2 — provisioning NEVER runs migrations. It ASSERTS the schema is present
    and ABORTS with a clear, actionable error if the ``workspace_tokens`` table
    is missing. A failed existence/version read raises ``SchemaNotReadyError``;
    it is never silently treated as "schema 0".
  * AC3 — every statement is dispatched on the actual connection type
    (``isinstance(db, aiosqlite.Connection)`` vs asyncpg Pool), with ``$1``
    placeholders and ``ON CONFLICT DO NOTHING`` on the Postgres arm.
  * AC1/AC4 — a fresh DB gets exactly one workspace row + one token row; a
    second run with the same plaintext token is a no-op (argon2id dedup by
    ``ph.verify``, since salted hashes are not value-comparable).

The argon2id hashing and the dedup loop are backend-agnostic pure Python; only
the three DB touches (schema probe, workspace upsert, token read + insert) fork
on backend.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiosqlite
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

logger = logging.getLogger("ccdash.auth.token_provisioning")


class SchemaNotReadyError(RuntimeError):
    """Raised when the workspace_tokens schema is absent or unreadable.

    Provisioning must ABORT here, never run migrations (AC2). The message tells
    the operator exactly how to bring the schema up (a separate concern from
    minting a token).
    """


@dataclass(frozen=True)
class ProvisionResult:
    """Outcome of a provisioning call."""

    created: bool
    """True if a new token row was inserted; False if an existing active row
    already verified against this plaintext (no-op)."""

    token_id: str
    workspace_id: str
    project_id: str
    scope: str


def _is_sqlite(db: Any) -> bool:
    return isinstance(db, aiosqlite.Connection)


async def _assert_schema_ready(db: Any) -> None:
    """Confirm the workspace_tokens table exists. Raise SchemaNotReadyError if
    not — NEVER run migrations, NEVER assume "version 0" (AC2).

    A probe SELECT is used rather than reading a schema_version row so this works
    identically on both backends and is robust to the exact migration bookkeeping
    shape. A driver error (table missing, connection dead) is surfaced as
    SchemaNotReadyError with the underlying class name, never swallowed.
    """
    probe = "SELECT 1 FROM workspace_tokens LIMIT 1"
    try:
        if _is_sqlite(db):
            async with db.execute(probe) as cur:
                await cur.fetchone()
        else:
            await db.fetch(probe)
    except Exception as exc:  # noqa: BLE001 — deliberately broad: any failure to
        # read the table means we must not proceed. We re-raise as a typed error
        # instead of falling through to a migration run (the original bug).
        raise SchemaNotReadyError(
            "workspace_tokens is not readable "
            f"({type(exc).__name__}: {exc}). The schema is not provisioned. "
            "Run migrations first (start the api/worker runtime once, or run the "
            "migration runner), then re-run token provisioning. Provisioning will "
            "NOT run migrations for you against a live database."
        ) from exc


async def _upsert_workspace(db: Any, workspace_id: str, now_iso: str) -> None:
    """Ensure the workspace row exists (idempotent, backend-appropriate)."""
    if _is_sqlite(db):
        await db.execute(
            "INSERT OR IGNORE INTO workspaces (workspace_id, name, status, created_at)"
            " VALUES (?, ?, 'active', ?)",
            (workspace_id, workspace_id, now_iso),
        )
        await db.commit()
    else:
        await db.execute(
            "INSERT INTO workspaces (workspace_id, name, status, created_at)"
            " VALUES ($1, $2, 'active', $3) ON CONFLICT (workspace_id) DO NOTHING",
            workspace_id,
            workspace_id,
            now_iso,
        )


async def _active_token_rows(
    db: Any, workspace_id: str, project_id: str
) -> list[tuple[str, str]]:
    """Return [(token_id, hashed_token)] for active rows in this workspace+project."""
    if _is_sqlite(db):
        async with db.execute(
            "SELECT token_id, hashed_token FROM workspace_tokens"
            " WHERE workspace_id = ? AND project_id = ? AND revoked_at IS NULL",
            (workspace_id, project_id),
        ) as cur:
            rows = await cur.fetchall()
    else:
        rows = await db.fetch(
            "SELECT token_id, hashed_token FROM workspace_tokens"
            " WHERE workspace_id = $1 AND project_id = $2 AND revoked_at IS NULL",
            workspace_id,
            project_id,
        )
    return [(str(r[0]), str(r[1])) for r in rows]


async def _insert_token(
    db: Any,
    *,
    token_id: str,
    workspace_id: str,
    project_id: str,
    hashed: str,
    scope: str,
    description: str,
    now_iso: str,
) -> None:
    if _is_sqlite(db):
        await db.execute(
            "INSERT INTO workspace_tokens"
            " (token_id, workspace_id, project_id, hashed_token, scope, description, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token_id, workspace_id, project_id, hashed, scope, description, now_iso),
        )
        await db.commit()
    else:
        await db.execute(
            "INSERT INTO workspace_tokens"
            " (token_id, workspace_id, project_id, hashed_token, scope, description, created_at)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7)",
            token_id,
            workspace_id,
            project_id,
            hashed,
            scope,
            description,
            now_iso,
        )


async def provision_workspace_token(
    db: Any,
    *,
    token: str,
    workspace_id: str = "default-local",
    project_id: str,
    description: str = "Provisioned workspace token",
    scope: str = "admin",
    password_hasher: PasswordHasher | None = None,
) -> ProvisionResult:
    """Mint (or confirm) a workspace-scoped bearer token. Backend-aware.

    Idempotent: if an active row in ``workspace_id``/``project_id`` already
    verifies against ``token``, no row is inserted and ``created=False`` is
    returned. Raises ``SchemaNotReadyError`` if the schema is not provisioned
    (never runs migrations). Raises ``ValueError`` on an empty token/project.
    """
    if not token:
        raise ValueError("token must be a non-empty plaintext string")
    if not project_id:
        raise ValueError("project_id is required")

    ph = password_hasher or PasswordHasher()

    await _assert_schema_ready(db)

    now_iso = datetime.now(timezone.utc).isoformat()
    await _upsert_workspace(db, workspace_id, now_iso)

    # Dedup: argon2id hashes embed a salt, so two hashes of the same secret are
    # distinct strings — we must verify(), not compare values.
    for existing_token_id, existing_hash in await _active_token_rows(
        db, workspace_id, project_id
    ):
        try:
            ph.verify(existing_hash, token)
        except VerifyMismatchError:
            continue
        except VerificationError:
            # Corrupted / parameter-mismatch hash — skip, do not block the mint.
            logger.warning(
                "token_provisioning: skipping token_id=%s (argon2 verification "
                "error; possible corrupted hash)",
                existing_token_id,
            )
            continue
        else:
            return ProvisionResult(
                created=False,
                token_id=existing_token_id,
                workspace_id=workspace_id,
                project_id=project_id,
                scope=scope,
            )

    token_id = str(uuid.uuid4())
    await _insert_token(
        db,
        token_id=token_id,
        workspace_id=workspace_id,
        project_id=project_id,
        hashed=ph.hash(token),
        scope=scope,
        description=description,
        now_iso=now_iso,
    )
    return ProvisionResult(
        created=True,
        token_id=token_id,
        workspace_id=workspace_id,
        project_id=project_id,
        scope=scope,
    )
