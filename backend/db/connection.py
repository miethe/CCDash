"""Database connection factory.

Provides singleton async connection to SQLite (default) with WAL mode.
Backend selection via CCDASH_DB_BACKEND env var.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import aiosqlite

from backend import config

logger = logging.getLogger("ccdash.db")

# Database file location
DB_DIR = config.PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("CCDASH_DB_PATH", str(DB_DIR / "ccdash_cache.db")))

_connection: aiosqlite.Connection | None = None


async def get_connection() -> aiosqlite.Connection:
    """Return the singleton database connection, creating it if needed."""
    global _connection
    if _connection is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _connection = await aiosqlite.connect(str(DB_PATH))
        _connection.row_factory = aiosqlite.Row
        # Enable WAL mode for better concurrent read performance
        await _connection.execute("PRAGMA journal_mode=WAL")
        await _connection.execute("PRAGMA foreign_keys=ON")
        await _connection.execute("PRAGMA busy_timeout=5000")
        logger.info(f"Database connection established: {DB_PATH}")
    return _connection


async def close_connection() -> None:
    """Close the database connection."""
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None
        logger.info("Database connection closed")
