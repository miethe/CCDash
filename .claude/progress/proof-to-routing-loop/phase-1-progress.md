---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 1
title: "Contract & Envelope Foundations"
status: pending
created: "2026-07-29"
updated: "2026-07-29"
started: null
completed: null
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners: ["backend-architect", "python-backend-engineer"]
contributors: []
commit_refs: []
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T1-001"
    description: "Vendor mapping JSON — copy routing-feedback-task-map.v1.json verbatim (byte-for-byte)"
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: []
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"

  - id: "T1-002"
    description: "Envelope constants module — create routing_feedback_contract.py with all 9 frozen constants"
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["T1-001"]
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"

  - id: "T1-003"
    description: "Capability string — add routing:feedback to _V1_CAPABILITIES in client_v1.py"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T1-002"]
    priority: "high"
    estimated_effort: "0.25h"
    assigned_model: "sonnet"

  - id: "T1-004"
    description: "Config flag + tunables — add CCDASH_ROUTING_FEEDBACK_* env vars to config.py"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    priority: "high"
    estimated_effort: "0.25h"
    assigned_model: "sonnet"

  - id: "T1-005"
    description: "Digest-parity + flag-default test — create test_routing_feedback_contract_parity.py"
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["T1-001", "T1-002", "T1-004"]
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"

parallelization:
  batch_1: ["T1-001", "T1-004"]
  batch_2: ["T1-002", "T1-003"]
  batch_3: ["T1-005"]
  critical_path: ["T1-001", "T1-002", "T1-005"]
  estimated_total_time: "2h"

blockers: []

success_criteria: []

files_modified:
  - "backend/application/services/agent_queries/routing_task_map_v1.json"
  - "backend/application/services/agent_queries/routing_feedback_contract.py"
  - "backend/routers/client_v1.py"
  - "backend/config.py"
  - "backend/tests/test_routing_feedback_contract_parity.py"

---

# Phase 1: Contract & Envelope Foundations

**Total Tasks**: 5  
**Estimated Effort**: 2 points  
**Key Files**: `routing_feedback_contract.py`, `routing_task_map_v1.json`, `client_v1.py`, `config.py`

## Objective

Establish the feature's frozen contract surface with zero behavior change. Vendor the pinned cross-repo mapping, expose its identity via frozen constants, advertise the capability string, and add the default-off feature flag.

## Implementation Notes

### Architectural Decisions

- **Seam precision**: This phase is deliberately kept on primary Claude (Sonnet), not offloaded to ICA. Cross-repo/seam phases require precise digest handling and contract fidelity.
- **Single source of truth**: All downstream phases import from `routing_feedback_contract.py`, never re-declaring any contract-identity constants.
- **Default-off posture**: `CCDASH_ROUTING_FEEDBACK_ENABLED` defaults `False` (opt-in), unlike the `AARReviewSweepJob` precedent which defaults `True` (opt-out).

### Patterns and Best Practices

- Mirrors the Automated AAR Review Loop's envelope-and-flag scaffolding pattern exactly
- Uses existing `_env_bool`/`_env_int` helpers from `backend/config.py`
- Capability advertisement precedes any route landing (Phase 5)

### Known Gotchas

- **Byte-for-byte copying**: Any editor auto-formatting of `routing_task_map_v1.json` will silently break T1-005's digest-parity test
- **Two different digest conventions**: Constants carry `sha256:` prefix; `hashlib.sha256(...).hexdigest()` does not — normalization must be consistent
- **Don't conflate identity with runtime**: `routing_feedback_contract.py` (frozen) vs. `backend/config.py` (environment-configurable) are deliberately separate

### Development Setup

- Access to `agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json` for copying
- Familiarity with `backend/config.py` helper pattern: `_env_bool(..., default_value)`, `_env_int(..., default_value)`
- Knowledge of `backend/routers/client_v1.py` capability-list pattern

## Completion Notes

*Fill in when phase is complete*

- What was built
- Key learnings
- Unexpected challenges
- Recommendations for next phase
