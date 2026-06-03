---
name: db-connection-module-level-path
description: DB_PATH in backend/db/connection.py is set at module import time; os.environ patches applied after import have no effect on it
metadata:
  type: feedback
---

`backend/db/connection.py` line 25: `DB_PATH = Path(os.getenv("CCDASH_DB_PATH", str(DB_DIR / "ccdash_cache.db")))` is evaluated at **import time**. Tests that `patch.dict(os.environ, {"CCDASH_DB_PATH": tmpdb.name})` after the module is imported will NOT change where `get_connection()` connects to. In practice, tests that do this connect to the real `data/ccdash_cache.db`.

**Why:** This caused P1-001's `CREATE UNIQUE INDEX` migration to fail in CI because the tests were silently connecting to the production DB (schema v28, existing duplicates) instead of their temp DB.

**How to apply:** When tests fail with migration errors on startup, check if `DB_PATH` is being properly overridden. Consider using `monkeypatch.setattr(connection, "DB_PATH", ...)` instead of env patches, or patching `get_connection` itself.
