---
type: progress
schema_version: 2
doc_type: progress
prd: proof-to-routing-loop
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
phase: 3
title: "Rollup Compute Service"
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
  - id: "T3-001"
    description: "RoutingRollupQueryService skeleton — pure-SQL GROUP BY aggregation at grain key"
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: []
    priority: "critical"
    estimated_effort: "2h"
    assigned_model: "sonnet"
    model_effort: "extended"

  - id: "T3-002"
    description: "Apply pinned mapping + protected-class policy — derive task_class, handle _unclassified"
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["T3-001"]
    priority: "critical"
    estimated_effort: "2h"
    assigned_model: "sonnet"
    model_effort: "extended"

  - id: "T3-003"
    description: "Provider + coverage counters — derive provider via derive_model_identity(), compute mapped/unclassified counts"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T3-002"]
    priority: "high"
    estimated_effort: "1h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

  - id: "T3-004"
    description: "D5 metric payload — sample_count, success_rate, cost_index, regression_rate, confidence, eligible_for_adjustment, windows, freshness"
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["T3-003"]
    priority: "critical"
    estimated_effort: "2h"
    assigned_model: "sonnet"
    model_effort: "extended"

  - id: "T3-005"
    description: "Determinism + no-LLM guard — AST-walk transitive imports, two-invocation fixture test"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T3-004"]
    priority: "high"
    estimated_effort: "1h"
    assigned_model: "sonnet"
    model_effort: "adaptive"

parallelization:
  batch_1: ["T3-001"]
  batch_2: ["T3-002"]
  batch_3: ["T3-003", "T3-004"]
  batch_4: ["T3-005"]
  critical_path: ["T3-001", "T3-002", "T3-004", "T3-005"]
  estimated_total_time: "8h"

blockers: []

success_criteria: []

files_modified:
  - "backend/application/services/agent_queries/routing_rollup.py"
  - "backend/application/services/agent_queries/models.py"
  - "backend/tests/test_routing_rollup_determinism.py"
  - "backend/tests/test_routing_rollup_no_llm_imports.py"

---

# Phase 3: Rollup Compute Service

**Total Tasks**: 5  
**Estimated Effort**: 4 points  
**Key Files**: `routing_rollup.py` service, `models.py` DTOs, determinism test, no-LLM guard

## Objective

Implement `RoutingRollupQueryService` — the **only genuinely algorithmic phase** in the entire feature. Aggregate sessions at `(project_id, source_skill_name, model)` grain, apply the pinned v1 skill_name→task_class mapping, compute metrics, and prove determinism + no-LLM invariant.

## Implementation Notes

### Architectural Decisions

- **Pure SQL aggregation**: One GROUP BY query, zero N+1, zero ORM lazy-loading
- **Hard invariant (AOS Constraint 4)**: Zero LLM/model-client imports anywhere in transitive closure
- **Mapping application at write time**: `task_class` is a derived, denormalized column — never raw `skill_name` (D3/FR-6)
- **Protected-class policy**: `_unclassified` (always emitted, eligible_for_adjustment hardcoded False); protected classes (orchestration, mode_d) gated by `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`
- **Sub-threshold visibility**: Every distinct key present in response, never suppressed; only `eligible_for_adjustment` flips to False

### Patterns and Best Practices

- Clones `aar_review.py` and `system_metrics.py` query-service conventions
- Uses `aiosqlite` direct queries, not ORM
- Module-level docstring explicitly states no-LLM invariant
- Imports deferred locally in key methods to avoid import cycles

### Known Gotchas

- **Row-grain discipline**: Never collapse (source_skill_name, model) rows sharing a task_class — that merge is the router's job (out of scope)
- **Two independent gates**: `_unclassified` bypasses the protected-class gate entirely (always emitted); protected classes are gated by config flag
- **Provider sourcing**: Always via `derive_model_identity(model)["modelProvider"]` — never independently derived
- **Confidence saturation**: Pick a simple, documented, monotonic formula (e.g., min(1.0, sample_count / (sample_count + k)))
- **This is H3 anchor phase**: The only algorithmic phase — budget plan-level karen review at completion, not just task-completion-validator

### Development Setup

- Familiarity with SQL GROUP BY aggregation patterns
- Knowledge of `routing_feedback_contract.py` mapping loader pattern
- Understanding of D5 metric payload design (PRD §6.3 JSON example)
- Ability to author AST-walk import-graph guards

## Completion Notes

*Fill in when phase is complete*

- Determinism test green (two invocations produce field-identical rows)
- No-LLM guard green (transitive import graph clean)
- Full RoutingRollupResponseDTO shape matches PRD §6.3 example
- Mapping fidelity verified against fixture
