"""CCDash FastAPI Backend — main application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.routers.api import (
    sessions_router,
    documents_router,
    tasks_router,
    analytics_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ccdash")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("CCDash backend starting up")
    logger.info(f"  Sessions dir: {config.SESSIONS_DIR}")
    logger.info(f"  Documents dir: {config.DOCUMENTS_DIR}")
    logger.info(f"  Progress dir: {config.PROGRESS_DIR}")

    # Validate data directories exist
    for name, path in [
        ("Sessions", config.SESSIONS_DIR),
        ("Documents", config.DOCUMENTS_DIR),
        ("Progress", config.PROGRESS_DIR),
    ]:
        if path.exists():
            logger.info(f"  ✓ {name} directory found")
        else:
            logger.warning(f"  ✗ {name} directory not found: {path}")

    yield
    logger.info("CCDash backend shutting down")


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


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "sessions_dir": str(config.SESSIONS_DIR),
        "documents_dir": str(config.DOCUMENTS_DIR),
        "progress_dir": str(config.PROGRESS_DIR),
    }
