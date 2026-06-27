"""Auto-load repo-root .env files for non-test runtimes.

Loaded once at backend.config import time. override=False so real process env,
Docker --env-file, and CI always win. No-op in containers (no .env at repo root)
and during pytest runs.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# repo root = parent of the backend/ package dir
_REPO_ROOT = Path(__file__).resolve().parents[1]
_loaded = False


def dotenv_autoload_enabled(environ: "os._Environ | dict" = os.environ) -> bool:
    """True unless running under pytest or explicitly disabled."""
    if environ.get("CCDASH_DISABLE_DOTENV", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    if "pytest" in sys.modules or "_pytest" in sys.modules:
        return False
    return True


def load_local_env(root: Path | None = None) -> list[str]:
    """Load .env then .env.local from `root` (default repo root), override=False.

    Precedence achieved: process env > .env.local > .env (first value set wins
    under override=False, so load .env.local before .env). Returns the list of
    files actually loaded. Safe no-op if python-dotenv is unavailable or files
    are missing.
    """
    base = root or _REPO_ROOT
    loaded: list[str] = []
    try:
        from dotenv import load_dotenv
    except ImportError:
        return loaded
    # .env.local first so it wins over .env (override=False => first wins)
    for name in (".env.local", ".env"):
        path = base / name
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(str(path))
    return loaded


def autoload_local_env() -> list[str]:
    """Idempotent guarded auto-load. Call from backend.config at import time."""
    global _loaded
    if _loaded:
        return []
    _loaded = True
    if not dotenv_autoload_enabled():
        return []
    return load_local_env()
