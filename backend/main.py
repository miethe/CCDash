"""CCDash FastAPI Backend — main application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import asyncio
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.routers.api import (
    sessions_router,
    documents_router,
    tasks_router,
)
from backend.routers.analytics import analytics_router
from backend.routers.projects import projects_router
from backend.routers.features import features_router
from backend.routers.cache import cache_router, links_router
from backend.routers.session_mappings import session_mappings_router

from backend.db import connection, migrations, sync_engine
from backend.db.file_watcher import file_watcher
from backend.project_manager import project_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ccdash")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("CCDash backend starting up")
    
    # 1. Initialize DB connection
    db = await connection.get_connection()
    
    # 2. Run migrations
    await migrations.run_migrations(db)
    
    # 3. Initialize Sync Engine
    sync = sync_engine.SyncEngine(db)
    app.state.sync_engine = sync
    
    # 4. Initial Sync (background task)
    logger.info("Starting initial project sync...")
    sessions_dir, docs_dir, progress_dir = project_manager.get_active_paths()
    active_project = project_manager.get_active_project()
    
    if active_project:
        # Run initial sync in background so we don't block startup
        # Keep reference to cancel on shutdown
        app.state.sync_task = asyncio.create_task(sync.sync_project(
            active_project, sessions_dir, docs_dir, progress_dir
        ))
        
        # 5. Start File Watcher
        await file_watcher.start(
            sync, active_project.id, sessions_dir, docs_dir, progress_dir
        )
    
    yield
    
    logger.info("CCDash backend shutting down")
    
    # Cancel background sync if running
    if hasattr(app.state, "sync_task"):
        app.state.sync_task.cancel()
        try:
            await app.state.sync_task
        except asyncio.CancelledError:
            pass
            
    await file_watcher.stop()
    await connection.close_connection()


app = FastAPI(
    title="CCDash API",
    description="Backend API for the CCDash agentic analytics dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        config.FRONTEND_ORIGIN,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(sessions_router)
app.include_router(documents_router)
app.include_router(tasks_router)
app.include_router(analytics_router)
app.include_router(projects_router)
app.include_router(features_router)
app.include_router(cache_router)
app.include_router(links_router)
app.include_router(session_mappings_router)


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "db": "connected" if connection._connection else "disconnected",
        "watcher": "running" if file_watcher.is_running else "stopped",
    }
