# Ultrathink Debugger Memory

- [CCDash DB connection module-level singleton](db-connection-module-level-path.md) — `DB_PATH` in `connection.py` is set at import time; env patches applied after import do not change it
- [SQLite UNIQUE INDEX dedup migration pattern](sqlite-unique-index-dedup-migration.md) — before `CREATE UNIQUE INDEX`, always DELETE duplicate rows in a guard block when the index doesn't yet exist
- [v31 composite-FK session child writers](sqlite-composite-fk-child-writers.md) — every session child writer must pass project_id matching the parent; NULL project_id silently creates orphans, non-NULL mismatch raises FK
- [PG datetime bound to TEXT timestamp cols](pg-datetime-bind-text-timestamp-cols.md) — timestamp cols are TEXT/ISO in both backends; asyncpg rejects a datetime $1 bind, SQLite computes cutoffs in-SQL and masks it; fix with .isoformat()
