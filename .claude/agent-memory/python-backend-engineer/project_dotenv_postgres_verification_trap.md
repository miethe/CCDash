---
name: project-dotenv-postgres-verification-trap
description: Bare `python script.py` verification scripts silently connect to the real node Postgres instead of an isolated SQLite temp DB — always verify via pytest.
metadata:
  type: project
---

Root `.env` in CCDash pins `CCDASH_DB_BACKEND=postgres` + `CCDASH_DATABASE_URL` at the
node (`10.42.10.76:5440`). `backend/env_bootstrap.py::dotenv_autoload_enabled()` auto-loads
that `.env` (`override=False`) at `backend.config` import time — **unless `"pytest"` is
already in `sys.modules`**. `backend.db.connection.py`'s `DB_PATH`/branch-selection reads
`config.DB_BACKEND`, a plain module-level attribute frozen at first import of
`backend.config` — it is NOT re-read per call (unlike `_resolve_db_path()`, which does
re-read `os.getenv` live).

**Why this matters**: a throwaway verification script that does
`from backend.adapters.auth.context import AuthContext` (or any other `backend.*` import)
at file/module top level, run as `python script.py` (not `pytest`), imports `backend.config`
*before* any test-local `patch.dict(os.environ, {"CCDASH_DB_BACKEND": "sqlite", ...})` takes
effect. The app then silently opens an `asyncpg` pool to the real remote node Postgres
instead of the intended isolated SQLite temp file. It still looks like it's working — a
made-up test `project_id` legitimately returns zero rows on the real DB too — so
"enabled but empty" assertions pass for the wrong reason, and a raw
`sqlite3.connect(tmp_path)` insert into your "seeded" temp file raises
`OperationalError: no such table` because the app was never touching that file at all.

**How to apply**: always verify new REST/CLI/MCP transport code against an isolated DB via
`backend/.venv/bin/python -m pytest <file_or_module> -v`, never a bare
`backend/.venv/bin/python script.py` — `pytest` being in `sys.modules` is exactly the guard
`dotenv_autoload_enabled()` checks, so `.env` never loads and `CCDASH_DB_BACKEND` correctly
defaults to `sqlite` unless a test's own `patch.dict` overrides it. The
`test_client_v1_aar_review.py`-style class-based `unittest.TestCase` harness (imports at file
top, `patch.dict(os.environ, ...)` inside `setUpClass`) is safe specifically *because* it's
always invoked through `pytest`. See [[project_dpm_phase2.md]] for other CCDash Postgres-vs-
SQLite operative-store gotchas.
