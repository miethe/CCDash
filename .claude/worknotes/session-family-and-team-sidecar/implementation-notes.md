# Session Family Endpoint — Implementation Notes

## 2026-08-03 — subagent-exclusion fix + SessionRef field gap

### Fix: subagents excluded from `GET /api/v1/sessions/{id}/family`

`get_session_family_v1` (`backend/routers/_client_v1_sessions.py`) called
`session_repo.list_paginated(..., filters={"root_session_id": root_id})`
without `include_subagents`. `SqliteSessionRepository.list_paginated`
(`backend/db/repositories/sessions.py` ~L425) defaults
`filters.get("include_subagents", False)` to `False`, appending
`(session_type IS NULL OR session_type != 'subagent')` to the WHERE clause —
this silently dropped every subagent child from the family response. Fixed
by adding `"include_subagents": True` to the filters dict passed into
`list_paginated`. Proven live: family of
`S-21ae87ed-4bb2-4aa5-b763-ece90f685168` went from `session_count: 1` to
including its 8+ subagent children.

### Gap: `SessionRef.tool_names` cannot be populated from the row alone

`SessionRef` (`backend/application/services/agent_queries/models.py`) declares
`workflow_refs`, `tool_names`, and `source_ref`. Of these:

- `source_ref` and `workflow_id` are plain columns on the `sessions` row
  returned by `list_paginated` (`SELECT * FROM sessions`), so they are now
  populated directly in `get_session_family_v1` (`workflow_refs` is the
  single-element-list wrap of `workflow_id`, matching the existing pattern
  in `backend/application/services/agent_queries/workflow_intelligence.py`).
- `tool_names` is **not** a column on the sessions row. Every other call site
  that populates it (e.g. `feature_forensics.py` ~L180-196) runs a *separate*
  query against tool-usage/transcript data per session. Per the task's scope
  boundary ("do not invent a new query to fetch them"), `tool_names` is left
  as its default empty list on `SessionFamilyDTO` members returned by the
  family endpoint. Populating it would require a follow-up task that adds a
  batched tool-usage lookup for the family's session_ids.
