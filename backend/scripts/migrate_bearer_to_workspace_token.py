"""DEPRECATED shim — use ``ccdash token mint`` instead.

Historical role: this script implemented ADR-008 §Migration Path (mint a
workspace-scoped ``workspace_tokens`` row from a single ``CCDASH_AUTH_TOKEN``).
Its provisioning logic has moved to the backend-aware
``backend.application.services.auth.token_provisioning.provision_workspace_token``
and is now surfaced as::

    ccdash token mint --project <project-id>          # reads CCDASH_AUTH_TOKEN
    ccdash token mint --project <project-id> --token <plaintext>

Why it moved (node_01KZVXWY2CR9V2GG04PQNFZ1EM)
----------------------------------------------
The old inline implementation was SQLite-only end-to-end: the aiosqlite cursor
idiom, ``?`` placeholders, ``INSERT OR IGNORE`` and unguarded ``db.commit()``.
Worse, a failed schema-version read fell through a bare ``except`` to
"version 0" and then ran migrations **against a live, fully-migrated Postgres
database**. The replacement is backend-aware and NEVER runs migrations — it
aborts with a clear message if the schema is not provisioned.

This shim is retained only so the ADR-008-documented invocation keeps working
until the docs are updated. It delegates to the shared function (so it is now
correct on both backends) and prints a deprecation notice. New automation should
call ``ccdash token mint``.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "DEPRECATED: use `ccdash token mint`. Mints a workspace-scoped "
            "token row (ADR-008 §Migration Path)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("CCDASH_AUTH_TOKEN", ""),
        help="Plaintext token. Defaults to CCDASH_AUTH_TOKEN.",
    )
    parser.add_argument("--workspace", default="default-local")
    parser.add_argument("--project", required=True)
    parser.add_argument("--description", default="Migrated single-bearer token")
    return parser.parse_args(argv)


async def _run(*, token: str, workspace_id: str, project_id: str, description: str) -> int:
    from backend.application.services.auth.token_provisioning import (
        SchemaNotReadyError,
        provision_workspace_token,
    )
    from backend.db.connection import close_connection, get_connection

    try:
        db = await get_connection()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not open database: {exc}", file=sys.stderr)
        return 2

    try:
        result = await provision_workspace_token(
            db,
            token=token,
            workspace_id=workspace_id,
            project_id=project_id,
            description=description,
        )
    except SchemaNotReadyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: provisioning failed: {exc}", file=sys.stderr)
        return 2
    finally:
        await close_connection()

    verb = "SUCCESS: token_id" if result.created else "NO-OP: token already present as token_id"
    print(f"{verb}={result.token_id}")
    print(f"  workspace_id = {result.workspace_id}")
    print(f"  project_id   = {result.project_id}")
    print(f"  scope        = {result.scope}")
    return 0


def main(argv: list[str] | None = None) -> int:
    print(
        "DEPRECATION: `python -m backend.scripts.migrate_bearer_to_workspace_token` "
        "is deprecated; use `ccdash token mint --project <id>` instead. "
        "Delegating to the shared provisioning path.",
        file=sys.stderr,
    )
    args = _parse_args(argv)
    if not args.token:
        print(
            "ERROR: --token is required (or set CCDASH_AUTH_TOKEN env var).",
            file=sys.stderr,
        )
        return 1
    return asyncio.run(
        _run(
            token=args.token,
            workspace_id=args.workspace,
            project_id=args.project,
            description=args.description,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
