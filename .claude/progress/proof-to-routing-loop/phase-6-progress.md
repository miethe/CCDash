---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 6
title: "Validation, Guards & Docs"
status: pending
created: "2026-07-29"
updated: "2026-07-29"
started: null
completed: null
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 14
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners: ["python-backend-engineer", "documentation-writer", "task-completion-validator", "karen"]
contributors: []
commit_refs: []
pr_refs: []
execution_model: batch-parallel
model_usage:
  primary: "sonnet"
  external: ["haiku"]

tasks:
  - id: "T6-001"
    description: "Extend no-LLM guard to worker — AST-walk routing_rollup_sweep_job.py transitive imports"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T6-002"
    description: "Digest-parity CI test (seam task) — vendored mapping file SHA-256 == MAPPING_DIGEST (AC-2)"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T6-001"]
    priority: "critical"
    estimated_effort: "0.75h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T6-003"
    description: "Envelope-completeness test (seam task) — all 11 pinned fields + 3 top-level counters (AC-1)"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T6-002"]
    priority: "critical"
    estimated_effort: "0.75h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T6-004"
    description: "Determinism re-confirmation — end-to-end worker path (AC-3 determinism)"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T6-003"]
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T6-005"
    description: "Sparse-key + protected-class fixture tests — sub-threshold visibility (AC-5), coverage-only handling (AC-6)"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T6-004"]
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T6-006"
    description: "Disabled-state + reversibility + version-field tests — all transports (AC-4, AC-7, AC-8)"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T6-005"]
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T6-007"
    description: "task-completion-validator gate — phase-end review of all tasks and ACs"
    status: "pending"
    assigned_to: ["task-completion-validator"]
    dependencies: ["T6-006"]
    priority: "critical"
    estimated_effort: "1h"
    assigned_model: "sonnet"

  - id: "T6-008"
    description: "karen feature-end review — verify claimed completion against actual behavior across all 6 phases"
    status: "pending"
    assigned_to: ["karen"]
    dependencies: ["T6-007"]
    priority: "critical"
    estimated_effort: "1h"
    assigned_model: "sonnet"

  - id: "DOC-001"
    description: "CHANGELOG entry — new capability, new surfaces, default-off"
    status: "pending"
    assigned_to: ["changelog-generator"]
    dependencies: []
    priority: "high"
    estimated_effort: "0.25h"
    assigned_model: "haiku"
    model_effort: "adaptive"

  - id: "DOC-002"
    description: "Consumer-contract doc — mirrors ccdash-aar-review-consumer-contract-v1.md structure"
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["DOC-001"]
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "haiku"
    model_effort: "adaptive"

  - id: "DOC-003"
    description: "Operator guide — mirrors docs/guides/aar-review-loop.md structure"
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["DOC-002"]
    priority: "high"
    estimated_effort: "0.5h"
    assigned_model: "haiku"
    model_effort: "adaptive"

  - id: "DOC-006"
    description: "Deferred-items design specs — DI-1 (router merge), DI-2 (model namespacing), DI-3 (window/decay defaults)"
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["DOC-003"]
    priority: "high"
    estimated_effort: "1h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

parallelization:
  batch_1: ["T6-001", "DOC-001"]
  batch_2: ["T6-002", "DOC-002"]
  batch_3: ["T6-003", "DOC-003"]
  batch_4: ["T6-004", "DOC-006"]
  batch_5: ["T6-005"]
  batch_6: ["T6-006"]
  batch_7: ["T6-007"]
  batch_8: ["T6-008"]
  critical_path: ["T6-001", "T6-002", "T6-003", "T6-007", "T6-008"]
  estimated_total_time: "8h"

blockers: []

success_criteria: []

files_modified:
  - "backend/tests/test_routing_rollup_no_llm_imports.py"
  - "backend/tests/test_routing_feedback_contract_parity.py"
  - "backend/tests/test_routing_rollup_envelope_completeness.py"
  - "backend/tests/test_routing_rollup_determinism.py"
  - "backend/tests/test_routing_rollup_sparse_protected.py"
  - "backend/tests/test_routing_rollup_disabled_state.py"
  - "docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md"
  - "docs/guides/routing-feedback-loop.md"
  - "docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md"
  - "docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md"
  - "docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md"
  - "CHANGELOG.md"

---

# Phase 6: Validation, Guards & Docs

**Total Tasks**: 14 (6 test tasks + 2 review gates + 4 doc tasks)  
**Estimated Effort**: 2 points (test/guard implementation; reviews are gates, not point-counted)  
**Key Files**: 6 new test files, 4 doc files, CHANGELOG

## Objective

Terminal validation and documentation phase. Does not add new production behavior — every module already shipped by Phases 1-5. Phase 6 proves the assembled feature satisfies PRD §11's AC-1 through AC-8 via CI-enforced tests, documents the deferred cross-repo items, and provides operator-facing documentation.

## Implementation Notes

### Architectural Decisions

- **Structural clone of AAR-review validation**: No-LLM guard, consumer-contract doc, operator guide all mirror shipped precedent
- **Two R-P3 seam tasks**: T6-002 (mapping-digest parity) and T6-003 (envelope completeness) are cross-repo risk mitigations
- **Review gates mandatory**: task-completion-validator (T6-007) and karen feature-end (T6-008) before feature seals
- **D9 documentation**: Socialization of D5 metric-payload must be documented in completion note (even if informal)

### Patterns and Best Practices

- Every AC-1..AC-8 has a corresponding `verified_by` test task
- Seam tasks defend against R-P3 (silent non-join / vocabulary drift)
- Guards re-confirm determinism and no-LLM invariant end-to-end through worker path
- All documentation mirrors shipped AAR-review loop conventions

### Known Gotchas

- **Extension, not rewrite**: Test files like `test_routing_rollup_no_llm_imports.py` are extended from Phase 3, not rewritten
- **Scope enforcement**: DOC-006 specs describe seams only, never executor-repo implementation as executable tasks
- **Deferred items update**: After DOC-006 tasks complete, append all three paths to parent plan's `deferred_items_spec_refs` frontmatter
- **Karen milestone**: Phase 3 already referenced karen review at algorithmic-core milestone; Phase 6 is the second/final review gate

### Development Setup

- Familiarity with test-authoring patterns across 6 different test files
- Knowledge of AST-walk import-graph guard structure (clone from `test_aar_review_no_llm_imports.py`)
- Understanding of parametrized tests (REST/MCP/CLI transport trio)
- Ability to write documentation mirroring shipped precedent structure

## Completion Notes

*Fill in when phase is complete*

- All 6 test files green (no-LLM guard, digest parity, envelope completeness, determinism, sparse-key/protected-class, disabled-state/reversibility/version-fields)
- task-completion-validator gate passed
- karen feature-end review passed
- All 4 documentation deliverables shipped (CHANGELOG, consumer-contract, operator guide, deferred-items specs)
- Parent plan's `deferred_items_spec_refs` updated with all three DOC-006 paths
- D9 socialization attempt documented
