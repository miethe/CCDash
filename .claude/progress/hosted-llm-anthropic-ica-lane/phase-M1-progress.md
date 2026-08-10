---
type: progress
schema_version: 2
doc_type: progress
prd: hosted-llm-anthropic-ica-lane
feature_slug: hosted-llm-anthropic-ica-lane
phase: M1
status: completed
created: 2026-08-10
updated: '2026-08-10'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md
itt_node_id: node_01KZP8ZDJ2NVMF9CK9PHB6RAP1
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
commit_refs: [db5aedd]
pr_refs: []
owners:
- python-backend-engineer
contributors: []
parallelization:
  batch_1:
  - TM1-001
  - TM1-002
  - TM1-003
  - TM1-004
tasks:
- id: TM1-001
  title: Declare httpx in backend/requirements.txt
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  started: 2026-08-10T16:50Z
  completed: 2026-08-10T17:15Z
  evidence:
  - commit: db5aedd
  verified_by:
  - gate-validator
  - gate-security
- id: TM1-002
  title: Move gemini API key from URL query string to a request header (backend/adapters/llm/gemini.py)
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  started: 2026-08-10T16:50Z
  completed: 2026-08-10T17:15Z
  evidence:
  - commit: db5aedd
  verified_by:
  - gate-validator
  - gate-security
- id: TM1-003
  title: Stop provider error bodies reaching logs across backend/adapters/llm/
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  started: 2026-08-10T16:50Z
  completed: 2026-08-10T17:15Z
  evidence:
  - commit: db5aedd
  verified_by:
  - gate-validator
  - gate-security
- id: TM1-004
  title: Tests - no key= in gemini URL; provider error body absent from captured logs
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  started: 2026-08-10T16:50Z
  completed: 2026-08-10T17:15Z
  evidence:
  - commit: db5aedd
  verified_by:
  - gate-validator
  - gate-security
total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
progress: 100
overall_progress: 100
---

# Milestone M1 — The egress path is safe to extend

## Exit Criteria

- `httpx` is declared in `backend/requirements.txt`
- No provider credential is passed in a URL query string; no provider error body reaches a log

## Gate

- `gate_lens: [security]`
- `gate_lens_reason: authz-boundary`
