"""Cache management API.

Control the sync engine and check status.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Request, BackgroundTasks

from backend.project_manager import project_manager

logger = logging.getLogger("ccdash.cache")

cache_router = APIRouter(prefix="/api/cache", tags=["cache"])


@cache_router.get("/status")
def get_cache_status(request: Request):
    """Return status of the sync engine and file watcher."""
    sync_engine = getattr(request.app.state, "sync_engine", None)
    if not sync_engine:
        return {"status": "error", "detail": "Sync engine not initialized"}
    
    # We could expose more detailed stats here if SyncEngine tracked them
    return {
        "status": "active",
        "sync_engine": "ready",
        # We can't easily access the file watcher instance from here unless we attach it to app.state too
        # But for now, just returning basic info is fine.
    }


@cache_router.post("/rescan")
async def trigger_rescan(request: Request, background_tasks: BackgroundTasks):
    """Trigger a full re-scan of the active project."""
    sync_engine = getattr(request.app.state, "sync_engine", None)
    if not sync_engine:
        return {"status": "error", "detail": "Sync engine not initialized"}

    project = project_manager.get_active_project()
    if not project:
        return {"status": "error", "detail": "No active project"}

    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()

    # Run in background
    background_tasks.add_task(
        sync_engine.sync_project,
        project, sessions_dir, docs_dir, progress_dir, force=True
    )

    return {"status": "ok", "message": "Rescan triggered in background"}
