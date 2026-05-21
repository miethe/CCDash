"""Database connection factory.

Provides singleton async connection to SQLite (default) with WAL mode.
Backend selection via CCDASH_DB_BACKEND env var.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Union, Any

import aiosqlite
try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore

from backend import config

logger = logging.getLogger("ccdash.db")

# Database file location.
#
# NOTE: DB_PATH is intentionally re-resolved inside _resolve_db_path() on every
# get_connection() call so tests (and other callers) can override CCDASH_DB_PATH
# via patch.dict(os.environ, ...) AFTER the module is imported. Module-level
# evaluation would freeze the path at import time and silently route every
# test class to the shared dev DB — a latent isolation bug that surfaces as
# "database is locked" when multiple test runs collide.
DB_DIR = config.PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("CCDASH_DB_PATH", str(DB_DIR / "ccdash_cache.db")))
SQLITE_BUSY_TIMEOUT_MS = max(1000, int(os.getenv("CCDASH_SQLITE_BUSY_TIMEOUT_MS", "30000")))

# Type alias for DB connection/pool
DbConnection = Union[aiosqlite.Connection, Any] # Any to support asyncpg.Pool

_connection: DbConnection | None = None


def _resolve_db_path() -> Path:
    """Resolve the SQLite DB path from the environment on each call.

    Tests use ``patch.dict(os.environ, {"CCDASH_DB_PATH": tmp})`` to isolate
    their state; that override only matters if we read the env var here rather
    than at module import time.
    """
    return Path(os.getenv("CCDASH_DB_PATH", str(DB_DIR / "ccdash_cache.db")))


async def get_connection() -> DbConnection:
    """Return the singleton database connection/pool, creating it if needed."""
    global _connection
    if _connection is not None:
        return _connection

    if config.DB_BACKEND == "postgres":
        if not asyncpg:
            raise ImportError("asyncpg is required for Postgres backend.")

        logger.info(f"Connecting to PostgreSQL: {config.DATABASE_URL}")
        _connection = await asyncpg.create_pool(config.DATABASE_URL)
        return _connection
    else:
        db_path = _resolve_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        # Enable WAL mode for better concurrent read performance
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        logger.info(f"Database connection established: {db_path}")
        _connection = conn
        return _connection


async def close_connection() -> None:
    """Close the database connection."""
    global _connection
    if _connection is not None:
        if config.DB_BACKEND == "postgres":
            await _connection.close() # asyncpg Pool has close()
        else:
            await _connection.close()
        _connection = None
        logger.info("Database connection closed")
