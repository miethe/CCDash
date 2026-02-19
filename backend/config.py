"""CCDash Backend Configuration."""
import os
from pathlib import Path

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

# Server settings
HOST = os.getenv("CCDASH_HOST", "0.0.0.0")
PORT = int(os.getenv("CCDASH_PORT", "8000"))

# CORS
FRONTEND_ORIGIN = os.getenv("CCDASH_FRONTEND_ORIGIN", "http://localhost:3000")
