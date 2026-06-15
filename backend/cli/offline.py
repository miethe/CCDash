"""Offline bootstrap + synchronous scoped sync for the repo-local CLI.

Closes the two verified gaps between ``bootstrap_cli`` and a worker-populated
runtime: it (1) runs migrations against a local offline cache DB and (2) drives
a synchronous, read-only ``SyncEngine.sync_project`` from the project's raw
session logs.  The existing command/``agent_queries`` stack then runs unchanged
against the seeded DB.

Design source of truth:
``.claude/worknotes/ccdash-offline-cli-direct-source/context.md`` section
"Refined implementation design (verified 2026-06-15)".  Two gotchas honored:

  1. Never reuse the module singleton ``db_project_manager`` — its ``_db_path``
     is frozen from ``connection.DB_PATH`` at import time.  A *fresh*
     ``DbProjectManager`` is constructed against the offline DB and injected via
     ``build_core_ports(..., workspace_registry=...)``.
  2. ``--ephemeral`` uses a temp *file*, never ``:memory:`` — the registry's
     separate synchronous ``SqliteProjectRepository`` connection would otherwise
     see a different in-memory DB than the async ``aiosqlite`` connection.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import typer

from backend import config
from backend.adapters.workspaces import ProjectManagerWorkspaceRegistry
from backend.db import connection
from backend.db import migrations
from backend.db.sync_engine import SyncEngine
from backend.project_manager import DbProjectManager
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile

logger = logging.getLogger("ccdash.cli.offline")

OFFLINE_PROFILE = get_runtime_profile("test")

# Cached process-singletons (one CLI invocation == one process).
_offline_container: RuntimeContainer | None = None
_offline_manager: DbProjectManager | None = None
_ephemeral_db_path: Path | None = None


def resolve_offline_config_path(override: str | None) -> Path | None:
    """Resolve the offline registry (``projects.json`` shape) path.

    Precedence: ``--config`` → ``CCDASH_PROJECTS_FILE`` → ``~/.ccdash/projects.json``
    → ``./projects.json``.  Returns the first existing candidate, or ``None`` when
    none exist.
    """
    candidates: list[Path] = []
    if override and override.strip():
        candidates.append(Path(override).expanduser())
    env_value = os.getenv("CCDASH_PROJECTS_FILE", "").strip()
    if env_value:
        candidates.append(Path(env_value).expanduser())
    candidates.append(Path.home() / ".ccdash" / "projects.json")
    candidates.append(Path.cwd() / "projects.json")

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def resolve_offline_db_path(ephemeral: bool) -> Path:
    """Resolve the offline cache DB path.

    Persistent default: ``~/.ccdash/offline-cache.db`` (parents created).
    When *ephemeral*, return a fresh temp *file* path (NOT ``:memory:`` — see
    gotcha #2) tracked for deletion on shutdown.
    """
    global _ephemeral_db_path
    if ephemeral:
        fd, raw = tempfile.mkstemp(prefix="ccdash-offline-", suffix=".db")
        os.close(fd)
        path = Path(raw)
        # mkstemp creates an empty file; remove it so aiosqlite/WAL start clean.
        try:
            path.unlink()
        except OSError:
            pass
        _ephemeral_db_path = path
        return path

    path = Path.home() / ".ccdash" / "offline-cache.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_offline_manager() -> DbProjectManager:
    """Return the fresh offline project manager built by ``bootstrap_offline``."""
    if _offline_manager is None:
        raise RuntimeError("Offline manager requested before bootstrap_offline().")
    return _offline_manager


async def bootstrap_offline(
    *,
    ephemeral: bool,
    config_path: str | None,
) -> RuntimeContainer:
    """Bootstrap a runtime container backed by a local offline cache DB.

    Runs migrations against the offline DB and builds ``CorePorts`` with a fresh,
    DB-scoped ``DbProjectManager`` so the entire query stack resolves against the
    offline DB without touching the production singleton.
    """
    global _offline_container, _offline_manager
    if _offline_container is not None:
        return _offline_container

    registry_path = resolve_offline_config_path(config_path)
    if registry_path is None:
        raise typer.BadParameter(
            "Offline registry not found. Export one via "
            "`ccdash project list --output json` to "
            "~/.ccdash/projects.json, or pass --config <path>."
        )

    db_path = resolve_offline_db_path(ephemeral)

    # Gotcha: set the module-global DB path BEFORE the first get_connection().
    connection.DB_PATH = db_path

    db = await connection.get_connection()
    await migrations.run_migrations(db)

    # Gotcha #1: a FRESH DbProjectManager scoped to the offline DB — never the
    # module singleton ``db_project_manager`` (its db_path is frozen at import).
    manager = DbProjectManager(
        storage_path=registry_path,
        db_path=db_path,
        db_backend="sqlite",
    )

    ports = __import__(
        "backend.runtime_ports", fromlist=["build_core_ports"]
    ).build_core_ports(
        db,
        runtime_profile=OFFLINE_PROFILE,
        storage_profile=config.STORAGE_PROFILE,
        workspace_registry=ProjectManagerWorkspaceRegistry(manager),
    )

    container = RuntimeContainer(profile=OFFLINE_PROFILE)
    container.db = db
    container.ports = ports

    _offline_container = container
    _offline_manager = manager
    return container


async def ensure_synced(
    manager: DbProjectManager,
    db,
    *,
    project_id: str | None,
    refresh: bool,
) -> dict:
    """Run a read-only synchronous scoped sync for the resolved project.

    Mirrors the worker pattern (``adapters/jobs/runtime.py``) but with
    ``allow_writeback=False`` and worker-grade enrichment disabled so offline
    sync stays fast and never mutates the project repo.
    """
    project = manager.get_project(project_id) if project_id else manager.get_active_project()
    if project is None:
        if project_id:
            raise typer.BadParameter(
                f"Project '{project_id}' was not found in the offline registry."
            )
        raise typer.BadParameter(
            "Could not resolve a project offline. Set an active project in the "
            "offline registry or pass --project <id>."
        )

    paths = manager.resolve_project_paths(project, refresh=refresh)
    sessions_dir, docs_dir, progress_dir = paths.as_tuple()

    if not sessions_dir.exists():
        typer.echo(
            f"[offline] Sessions directory not found for project '{project.id}': "
            f"{sessions_dir}. Skipping sync (no session data to parse).",
            err=True,
        )
        return {
            "sessions_synced": 0,
            "sessions_skipped": 0,
            "skipped_missing_sessions_dir": True,
            "sessions_dir": str(sessions_dir),
        }

    engine = SyncEngine(db)
    return await engine.sync_project(
        project,
        sessions_dir,
        docs_dir,
        progress_dir,
        force=refresh,
        allow_writeback=False,
        capture_analytics=False,
        backfill_session_intelligence=False,
        trigger="cli-offline",
    )


async def shutdown_offline() -> None:
    """Tear down offline runtime state and clean up any ephemeral DB file."""
    global _offline_container, _offline_manager, _ephemeral_db_path
    _offline_container = None
    _offline_manager = None
    await connection.close_connection()
    if _ephemeral_db_path is not None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(_ephemeral_db_path) + suffix)
            try:
                candidate.unlink()
            except OSError:
                pass
        _ephemeral_db_path = None
