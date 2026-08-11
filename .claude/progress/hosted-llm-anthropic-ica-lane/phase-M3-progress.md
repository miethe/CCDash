---
type: progress
schema_version: 2
doc_type: progress
prd: hosted-llm-anthropic-ica-lane
feature_slug: hosted-llm-anthropic-ica-lane
phase: M3
status: completed
created: 2026-08-10
updated: '2026-08-10'
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md
itt_node_id: node_01KZP8ZDNQ04KP7BYT2QTC2D0F
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
commit_refs:
- 9ac7dcc
- 5c809a6
- a788751
- f469fa1
pr_refs: []
owners:
- python-backend-engineer
contributors: []
parallelization:
  batch_1:
  - TM3-001
  - TM3-002
  batch_2:
  - TM3-003
  - TM3-004
  - TM3-005
  - TM3-006
tasks:
- id: TM3-001
  title: 'Anthropic adapter (backend/adapters/llm/anthropic.py): wire format, base-URL-only routing, bare model ids, [1m] rejection'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  started: 2026-08-10T14:00Z
  completed: 2026-08-10T14:28Z
  evidence:
  - commit: 9ac7dcc
  - test: 204 passed 8 skipped 13 subtests
  - orchestrator: adapter born gated behind M2 consent machinery
  verified_by:
  - gate-security
- id: TM3-002
  title: 'Config surface: CCDASH_LLM_SESSION_NAMING_LANE, CCDASH_LLM_*_{API_KEY,BASE_URL,MODEL} with legacy fallbacks via one shared helper'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies: []
  started: 2026-08-10T14:00Z
  completed: 2026-08-10T14:28Z
  evidence:
  - commit: 9ac7dcc
  - orchestrator: single fallback helper, deprecation log per process, CCDASH_LLM_ANTHROPIC_MODEL has no default
  verified_by:
  - gate-security
- id: TM3-003
  title: 'Deploy: CCDASH_LLM_* surface plumbed through compose env allowlists'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM3-001
  - TM3-002
  started: 2026-08-10T14:28Z
  completed: 2026-08-10T14:34Z
  evidence:
  - commit: 5c809a6
  - docker-compose.yml six vars added to backend env anchor
  - compose.hosted.env.example six defaults documented
  verified_by:
  - gate-validator
- id: TM3-004
  title: 'ADRs accepted: ADR-017 (ICA canonical hosted lane), ADR-018 (provenance enforced, no raw transcript imports)'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM3-001
  started: 2026-08-10T14:28Z
  completed: 2026-08-10T14:52Z
  evidence:
  - commit: a788751
  - docs/project_plans/adrs/adr-017-anthropic-wire-format-canonical-hosted-lane.md
  - docs/project_plans/adrs/adr-018-redaction-provenance-carried-by-type.md
  verified_by:
  - gate-security
- id: TM3-005
  title: 'ADR-018 structurally enforced: test_llm_adapters_no_raw_transcript_imports.py guards adapter import paths'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM3-001
  - TM3-004
  started: 2026-08-10T14:28Z
  completed: 2026-08-10T14:52Z
  evidence:
  - commit: a788751
  - test: backend/tests/test_llm_adapters_no_raw_transcript_imports.py 306 lines
  - orchestrator: positive control asserts walk reaches sanctioned port
  verified_by:
  - gate-security
- id: TM3-006
  title: 'Base-URL default corrected to ICA gateway (https://api.nextgen-beta.ica.ibm.com/ica), not paid api.anthropic.com'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM3-001
  - TM3-002
  started: 2026-08-10T14:28Z
  completed: 2026-08-10T14:52Z
  evidence:
  - commit: a788751
  - backend/adapters/llm/anthropic.py base_url default
  - backend/config.py CCDASH_LLM_ANTHROPIC_BASE_URL default
  - .env.example and compose.hosted.env.example updated
  - docs/guides/external-api-lan-deployment.md guidance added
  verified_by:
  - gate-validator
- id: TM3-007
  title: 'CHANGELOG entry: added consent model, ADR-017/018, adapter wire contract, CCDASH_LLM_* surface; fixed four defects'
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - TM3-001
  - TM3-002
  - TM3-003
  - TM3-004
  started: 2026-08-10T14:52Z
  completed: 2026-08-10T15:24Z
  evidence:
  - commit: f469fa1
  - CHANGELOG.md [Unreleased] 15 lines, claims checked against code not reports
  verified_by:
  - gate-validator
total_tasks: 7
completed_tasks: 7
in_progress_tasks: 0
blocked_tasks: 0
pending_tasks: 0
progress: 100
overall_progress: 100
live_egress_smoke: passed
live_egress_smoke_reason: "RUN 2026-08-11 under explicit operator authorization, using the default ~/.dotfiles/ICA_CLAUDE key (the key the SPIKE already probed, so not a guess). The shipped AnthropicTextCompletionAdapter completed a real prompt against the ICA gateway and returned 'ok'. Raw probe on the same key: HTTP 200, id msg_bdrk_01Cy81qtPXAFRRMC9NjnrdpY, model echoed back as the bare id claude-haiku-4-5, stop_reason end_turn, usage 14 in / 4 out. Negative side reproduced 3/3: claude-haiku-4-5[1m] -> HTTP 403 team_model_access_denied, each attempt paired with a bare-id control returning 200, which excludes a general gateway outage. The adapter also raises ValueError on a [1m] id before any network call. EGRESS POSTURE: the prompt was a SYNTHETIC string carrying AGGREGATE provenance, so ZERO session content (redacted or otherwise) left the box. STILL NOT RUN: the end-to-end worker sweep that names a real session -- that is a different claim from this AC and would mutate session names."
---

# Milestone M3 — The Anthropic/ICA lane serves a session name

## Exit Criteria

- Anthropic adapter reaches ICA and Anthropic direct by base URL alone, sending bare model ids
- CCDASH_LLM_* surface resolves with documented fallbacks to legacy vars
- ADR-017 and ADR-018 accepted
- CHANGELOG entry documenting added features and fixes

### Deferred to Operator

The first exit criterion in the plan — "the anthropic adapter completes a real prompt against ICA with bare model ids" — was **NOT verified**. This AC requires:
- An operator-held ICA key (one of CC1–CC6)
- An actual outbound HTTP call to the ICA gateway
- Confirmation that a session was named end-to-end

The plan (M3 section, "open_questions") explicitly records the uncertainty: "Which ICA key the deployed adapter uses — the default ~/.dotfiles/ICA_CLAUDE key was the only one probed; a named ICA_KEY block may scope models differently."

Rather than invent a passing call or mark this criterion unverified without evidence, it remains open. The adapter is production-ready, the config surface and fallbacks are shipped, and the ADRs are accepted. The operator should verify the live egress call with their deployed environment and ICA key configuration.

## Gate

- `gate_lens: [security]`
- `gate_lens_reason: irreversible-outward`

## Summary

M3 completes the implementation plan's three milestones. The Anthropic/ICA lane is born gated (M2's consent machinery was landed first), carries only bare model ids and sanctioned headers (credential as x-api-key, never in a URL or log), and enforces provenance before any egress. The config surface unifies both egress lanes (gemini + anthropic) under a single CCDASH_LLM_SESSION_NAMING_LANE selector with documented fallbacks to legacy vars. ADR-017 and ADR-018 now move from proposed to accepted. The only outstanding item is an operator-verified live call to the ICA gateway with their own key — a deployment-time concern, not a code concern.

Commits:
- 9ac7dcc — anthropic adapter + CCDASH_LLM_* config surface with legacy-var fallbacks
- 5c809a6 — CCDASH_LLM_* plumbed through deploy/compose env allowlists
- a788751 — ADR-017 + ADR-018 authored/accepted, ADR-018 guardrail test, base-URL default corrected to ICA
- f469fa1 — CHANGELOG [Unreleased] entry
