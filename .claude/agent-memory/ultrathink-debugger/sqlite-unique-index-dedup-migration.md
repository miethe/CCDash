---
name: sqlite-unique-index-dedup-migration
description: Pattern for safely adding UNIQUE index to existing table with potential duplicate rows; deduplicate first inside an existence guard
metadata:
  type: feedback
---

When adding `CREATE UNIQUE INDEX` to an existing table that may have duplicate rows (e.g., analytics data with multiple same-day rows), SQLite raises `UNIQUE constraint failed: index '<name>'` even with `IF NOT EXISTS` because the error occurs when existing data violates the uniqueness, not from re-creation.

**Correct pattern (in `_ensure_index`-style migration):**

```python
async with db.execute(
    "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_name' LIMIT 1"
) as cur:
    exists = await cur.fetchone() is not None
if not exists:
    await db.execute(
        "DELETE FROM table WHERE id NOT IN (SELECT MAX(id) FROM table GROUP BY dedup_cols)"
    )
    await db.commit()
await _ensure_index(db, "CREATE UNIQUE INDEX IF NOT EXISTS idx_name ON table(dedup_cols)")
```

**Why:** Production DBs may have existing duplicate rows from before the dedup constraint was introduced. `IF NOT EXISTS` only skips if the index already exists; it does NOT skip the uniqueness validation on existing data.

**How to apply:** Any new UNIQUE index added to a table that had unrestricted inserts before must dedup existing data first. Always gate the dedup DELETE on `sqlite_master` check to avoid running it on every startup.
