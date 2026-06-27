---
name: project-p1-010-badge-materialization
description: P1-010 session badge materialization — wave 2 writes Python for the 6 badge columns Wave 1 added to DDL
metadata:
  type: project
---

P1-010 badge materialization (T1-010) is implemented across 3 owned files. DDL columns (`command_slug`, `latest_summary`, `subagent_type`, `models_used_json`, `agents_used_json`, `skills_used_json`) were added by Wave 1 in sqlite_migrations.py + postgres_migrations.py.

**Why:** GET /api/sessions was fetching up to 250K rows per page (50 sessions × 5000-row log cap) to derive badges per session. Badge columns are now materialized.

**How to apply:** Wave 3 must migrate the remaining consumers in `_client_v1_features.py`, `feature_forensics.py`, and `skillmeat_memory_drafts.py` off the heavy log path. sync_engine.py (not owned by this agent) needs a one-line call to `session_transcript_service.compute_and_persist_badges(session_row, ports)` after writing session messages to fully automate badge population at ingest time.

**Integration point for sync_engine.py:**
After writing session messages, call:
```python
await session_transcript_service.compute_and_persist_badges(session_row, ports)
```

**Test failure note:** `test_detail_probe_endpoint_surfaces_degraded_runtime_storage_and_database_state` in test_runtime_bootstrap.py fails due to other agents' changes (container.py, bootstrap.py) — not from this agent's files. Confirmed by stash isolation.
