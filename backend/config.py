"""CCDash Backend Configuration."""
import os
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

# Project root (one level up from backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default data paths (relative to project root)
DATA_DIR = PROJECT_ROOT / "examples" / "skillmeat"
SESSIONS_DIR = DATA_DIR / "claude-sessions"
DOCUMENTS_DIR = DATA_DIR / "project_plans"
PROGRESS_DIR = DATA_DIR / "progress"

# Database
DB_PATH = os.getenv("CCDASH_DB_PATH", ".ccdash.db")
DB_BACKEND = os.getenv("CCDASH_DB_BACKEND", "sqlite")
DATABASE_URL = os.getenv("CCDASH_DATABASE_URL", "postgresql://user:password@localhost/ccdash")
LINKING_LOGIC_VERSION = os.getenv("CCDASH_LINKING_LOGIC_VERSION", "1")
OTEL_ENABLED = _env_bool("CCDASH_OTEL_ENABLED", False)
OTEL_ENDPOINT = os.getenv("CCDASH_OTEL_ENDPOINT", "http://localhost:4318")
OTEL_SERVICE_NAME = os.getenv("CCDASH_OTEL_SERVICE_NAME", "ccdash-backend")
PROM_PORT = _env_int("CCDASH_PROM_PORT", 9464)

# Feature flags
CCDASH_TEST_VISUALIZER_ENABLED = _env_bool("CCDASH_TEST_VISUALIZER_ENABLED", False)
CCDASH_INTEGRITY_SIGNALS_ENABLED = _env_bool("CCDASH_INTEGRITY_SIGNALS_ENABLED", False)
CCDASH_LIVE_TEST_UPDATES_ENABLED = _env_bool("CCDASH_LIVE_TEST_UPDATES_ENABLED", False)
CCDASH_SEMANTIC_MAPPING_ENABLED = _env_bool("CCDASH_SEMANTIC_MAPPING_ENABLED", False)

# Startup sync tuning
STARTUP_SYNC_DELAY_SECONDS = _env_int("CCDASH_STARTUP_SYNC_DELAY_SECONDS", 2)
STARTUP_SYNC_LIGHT_MODE = _env_bool("CCDASH_STARTUP_SYNC_LIGHT_MODE", True)
STARTUP_DEFERRED_REBUILD_LINKS = _env_bool("CCDASH_STARTUP_DEFERRED_REBUILD_LINKS", True)
STARTUP_DEFERRED_REBUILD_DELAY_SECONDS = _env_int("CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS", 45)
STARTUP_DEFERRED_CAPTURE_ANALYTICS = _env_bool("CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS", False)

# Server settings
HOST = os.getenv("CCDASH_HOST", "0.0.0.0")
PORT = int(os.getenv("CCDASH_PORT", "8000"))

# CORS
FRONTEND_ORIGIN = os.getenv("CCDASH_FRONTEND_ORIGIN", "http://localhost:3000")
