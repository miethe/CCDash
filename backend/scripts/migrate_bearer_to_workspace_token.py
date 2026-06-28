"""Migrate a single-bearer CCDASH_AUTH_TOKEN to a workspace-scoped token row.

Usage
-----
    python -m backend.scripts.migrate_bearer_to_workspace_token \
        --token <plaintext-token> \
        --workspace default-local \
        --project <project-id> \
        [--description "Migrated single-bearer token"]

Or rely on the environment variable::

    CCDASH_AUTH_TOKEN=<token> python -m backend.scripts.migrate_bearer_to_workspace_token \
        --project <project-id>

Idempotent: if an active (revoked_at IS NULL) workspace_tokens row already
verifies against the supplied token, the script exits 0 without inserting a
duplicate row.

Exit codes
----------
0  — success or no-op (token already migrated)
1  — bad arguments (missing token or project)
2  — DB error

ADR-008 §Migration Path defines the operator steps this script implements.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ccdash.migrate_bearer")


# --------------------------------------------------------------------------- #
# Argument parsing                                                              #
# --------------------------------------------------------------------------- #

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate a single CCDASH_AUTH_TOKEN bearer to a workspace-scoped "
            "workspace_tokens row (ADR-008 §Migration Path)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "After running this script:\n"
            "  1. Keep CCDASH_AUTH_TOKEN set to the same plaintext value.\n"
            "  2. Set CCDASH_PROFILE=api (or worker) to activate WorkspaceTokenAuthBackend.\n"
            "  3. Restart the server.\n"
            "  4. Verify: GET /api/health → auth_mode == 'workspace_token'.\n"
        ),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("CCDASH_AUTH_TOKEN", ""),
        help=(
            "Plaintext bearer token to migrate. Defaults to CCDASH_AUTH_TOKEN env var. "
            "Required if the env var is not set."
        ),
    )
    parser.add_argument(
        "--workspace",
        default="default-local",
        help="Workspace ID to create or use. Defaults to 'default-local'.",
    )
    parser.add_argument(
        "--project",
        required=True,
        help=(
            "Project ID the token is scoped to. "
            "Use the project ID from your projects.json (e.g. 'my-project')."
        ),
    )
    parser.add_argument(
        "--description",
        default="Migrated single-bearer token",
        help="Human-readable description stored in the workspace_tokens row.",
    )
    return parser.parse_args(argv)


# --------------------------------------------------------------------------- #
# Core migration logic (async)                                                  #
# --------------------------------------------------------------------------- #

async def _run_migration(
    *,
    token: str,
    workspace_id: str,
    project_id: str,
    description: str,
) -> int:
    """Perform the idempotent migration. Returns exit code 0 or 2."""
    # Import here so tests can patch os.environ before module-level code runs.
    import aiosqlite
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError

    from backend.db.connection import get_connection, _connection  # noqa: F401 — used for type hint only
    from backend.db.sqlite_migrations import run_migrations, SCHEMA_VERSION

    # ------------------------------------------------------------------ #
    # Step 1 — open DB, ensure schema is at v29+                          #
    # ------------------------------------------------------------------ #
    try:
        db = await get_connection()
    except Exception as exc:
        print(f"ERROR: could not open database: {exc}", file=sys.stderr)
        return 2

    # Check schema version and run migrations if needed.
    try:
        async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
            current_version = int(row[0]) if row and row[0] is not None else 0
    except Exception:
        current_version = 0

    if current_version < SCHEMA_VERSION:
        print(
            f"Schema version {current_version} < {SCHEMA_VERSION}; running migrations ...",
            file=sys.stderr,
        )
        try:
            await run_migrations(db)
            await db.commit()
        except Exception as exc:
            print(f"ERROR: migration failed: {exc}", file=sys.stderr)
            return 2

    # ------------------------------------------------------------------ #
    # Step 2 — ensure the workspace row exists                            #
    # ------------------------------------------------------------------ #
    try:
        await db.execute(
            """
            INSERT OR IGNORE INTO workspaces (workspace_id, name, status, created_at)
            VALUES (?, ?, 'active', ?)
            """,
            (workspace_id, workspace_id, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
    except Exception as exc:
        print(f"ERROR: could not ensure workspace row: {exc}", file=sys.stderr)
        return 2

    # ------------------------------------------------------------------ #
    # Step 3 — argon2id-hash the token                                    #
    # ------------------------------------------------------------------ #
    ph = PasswordHasher()
    hashed = ph.hash(token)

    # ------------------------------------------------------------------ #
    # Step 4 — dedup: verify the candidate token against every active row #
    # ------------------------------------------------------------------ #
    # argon2id hashes include salt, so two hashes of the same secret are
    # different strings. We cannot compare by value; we must ph.verify().
    try:
        async with db.execute(
            """
            SELECT token_id, hashed_token
            FROM   workspace_tokens
            WHERE  workspace_id = ? AND project_id = ? AND revoked_at IS NULL
            """,
            (workspace_id, project_id),
        ) as cur:
            active_rows = await cur.fetchall()
    except Exception as exc:
        print(f"ERROR: could not query workspace_tokens: {exc}", file=sys.stderr)
        return 2

    for existing_token_id, existing_hash in active_rows:
        try:
            ph.verify(str(existing_hash), token)
            # Match found — this token is already migrated.
            print(
                f"NO-OP: token already present as token_id={existing_token_id} "
                f"in workspace={workspace_id}, project={project_id}."
            )
            print(
                "\nNext steps (same as a fresh migration):\n"
                f"  export CCDASH_AUTH_TOKEN=<your-token>\n"
                f"  export CCDASH_PROFILE=api\n"
                "  # restart the server\n"
                "  # verify: GET /api/health → auth_mode == 'workspace_token'"
            )
            return 0
        except VerifyMismatchError:
            continue
        except VerificationError:
            # Corrupted or parameter-mismatch hash — skip, don't block migration.
            logger.warning(
                "Skipping existing token_id=%s: argon2 verification error "
                "(possible corrupted hash).",
                existing_token_id,
            )
            continue

    # ------------------------------------------------------------------ #
    # Step 5 — insert new workspace_tokens row                            #
    # ------------------------------------------------------------------ #
    token_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        await db.execute(
            """
            INSERT INTO workspace_tokens
                (token_id, workspace_id, project_id, hashed_token, scope,
                 description, created_at)
            VALUES (?, ?, ?, ?, 'admin', ?, ?)
            """,
            (token_id, workspace_id, project_id, hashed, description, now_iso),
        )
        await db.commit()
    except Exception as exc:
        print(f"ERROR: could not insert workspace_tokens row: {exc}", file=sys.stderr)
        return 2

    # ------------------------------------------------------------------ #
    # Step 6 — print result and next-step instructions                    #
    # ------------------------------------------------------------------ #
    print(f"SUCCESS: token_id={token_id}")
    print(f"  workspace_id = {workspace_id}")
    print(f"  project_id   = {project_id}")
    print(f"  scope        = admin")
    print()
    print("Next steps:")
    print(f"  export CCDASH_AUTH_TOKEN=<your-original-token>")
    print(f"  export CCDASH_PROFILE=api")
    print("  # restart the server")
    print("  # verify: GET /api/health → auth_mode == 'workspace_token'")
    return 0


# --------------------------------------------------------------------------- #
# Entry point                                                                   #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not args.token:
        print(
            "ERROR: --token is required (or set CCDASH_AUTH_TOKEN env var).",
            file=sys.stderr,
        )
        return 1

    if not args.project:
        print("ERROR: --project is required.", file=sys.stderr)
        return 1

    return asyncio.run(
        _run_migration(
            token=args.token,
            workspace_id=args.workspace,
            project_id=args.project,
            description=args.description,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
