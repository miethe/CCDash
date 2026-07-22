---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-automated-aar-review
feature_slug: ccdash-automated-aar-review
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
execution_model: batch-parallel
phase: 2
title: "Full-Metadata Evidence Enrichment"
status: pending
created: 2026-07-22
updated: 2026-07-22
started: null
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: on-track

total_tasks: 9
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners:
- backend-architect
- python-backend-engineer
contributors: []

model_usage:
  primary: sonnet
  external: []

tasks:
- id: T2-001
  description: "Design the deterministic doc->feature->plan/progress->task frontmatter
    traversal and the shape of the enrichment evidence contract (what fields each
    flag's evidence_refs/triage_reasons may cite). Document the ruleset explicitly —
    no free-text judgment fields."
  status: pending
  assigned_to: [backend-architect]
  dependencies: ["Phase 1 sealed"]
  estimated_effort: "1.5 pt"
  assigned_model: sonnet
  model_effort: extended
- id: T2-002
  description: "Implement the enrichment service's reads over session_detail (tokens,
    context_window, detection/capture columns, subagents, artifacts, links) —
    consuming the redaction-passed output exclusively, never raw JSONL."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T2-001]
  estimated_effort: "1.5 pt"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P2.2]
- id: T2-003
  description: "Implement the doc->feature->plan/progress->task traversal, extracting
    acceptance_criteria, assigned_to, assigned_model, effort, phase from linked
    plan/progress frontmatter via existing document_linking.py/entity_links reads
    (D6 — no new port)."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T2-001]
  estimated_effort: "1.5 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T2-004
  description: "Sharpen context_ballooning with plan/task evidence: attach
    plan-declared effort/phase context to the flag's evidence when linked task
    frontmatter is available; deterministic threshold logic unchanged from P1."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T2-002, T2-003]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T2-005
  description: "Sharpen missing_artifacts with plan/task acceptance_criteria: compare
    AAR-claimed artifacts against the linked task's acceptance_criteria/files_affected
    frontmatter (set-difference), in addition to the existing session_artifacts diff."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T2-002, T2-003]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T2-006
  description: "Sharpen generic_agent_vs_specialist with assigned_to/assigned_model:
    compare the session's actual agentsUsed/skill_name against the linked task's
    assigned_to/assigned_model frontmatter (set-membership comparison). Static
    keyword->specialist lookup from P1 remains the fallback."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T2-002, T2-003]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T2-007
  description: "Sharpen stack_ineffectiveness with phase/effort correlation: correlate
    the linked task's declared phase/effort against observed failure/retry density
    (threshold comparison, unchanged derivation) to add context to evidence, not new
    logic."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T2-002, T2-003]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
- id: T2-008
  description: "No-LLM compute-path assertion test (Hard Invariant #1): statically
    assert no LLM/model-client import (Anthropic SDK, OpenAI SDK, any Task/Agent
    dispatch helper) exists anywhere in aar_review.py or its enrichment-module
    dependency graph."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T2-004, T2-005, T2-006, T2-007]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive
  ac_refs: [AC-P2.1]
- id: T2-009
  description: "Enrichment fixture suite: doc with a linked plan/task vs doc with no
    link; each flag's sharpened-evidence path vs its P1 fallback path."
  status: pending
  assigned_to: [python-backend-engineer]
  dependencies: [T2-004, T2-005, T2-006, T2-007]
  estimated_effort: "1 pt"
  assigned_model: sonnet
  model_effort: adaptive

parallelization:
  batch_1: [T2-001]
  batch_2: [T2-002, T2-003]
  batch_3: [T2-004, T2-005, T2-006, T2-007]
  batch_4: [T2-008, T2-009]
  critical_path: [T2-001, T2-002, T2-004, T2-008]
  estimated_total_time: "5-7 pts (4 sequential batches)"

blockers: []

success_criteria:
- id: SC-1
  description: "All 4 flags carry sharpened, plan/task-anchored evidence when a link
    is resolvable."
  status: pending
- id: SC-2
  description: "All 4 flags fall back cleanly to P1 behavior when no plan/task link
    exists (never an error)."
  status: pending
- id: SC-3
  description: "No-LLM compute-path test (T2-008) green."
  status: pending
- id: SC-4
  description: "Fixture suite (T2-009) green, covering linked and unlinked cases."
  status: pending
- id: SC-5
  description: "task-completion-validator review passes."
  status: pending

files_modified:
- backend/application/services/agent_queries/aar_review.py
- backend/application/services/agent_queries/session_detail.py

notes: >
  Entry criteria: Phase 1 sealed (reconciled DTO + aar_reviews persistence live;
  contract test + parity + direct-count green). Every enrichment comparison MUST be
  set-membership, threshold, or static-ruleset lookup — any comparison requiring semantic
  judgment is out of scope for this phase (Hard Invariant #1); descope and record the
  finding. Phase 3's task-level scaffolding may start once T2-001's evidence contract is
  frozen, but Phase 3 does not formally close until this phase is sealed.
---

# ccdash-automated-aar-review - Phase 2: Full-Metadata Evidence Enrichment

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Quick Reference

```bash
# Update single task status
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-2-progress.md \
  -t T2-001 -s completed

# Batch update
python .claude/skills/artifact-tracking/scripts/update-batch.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-2-progress.md \
  --updates "T2-001:completed,T2-002:completed"

# Arbitrary field update
python .claude/skills/artifact-tracking/scripts/update-field.py \
  -f .claude/progress/ccdash-automated-aar-review/phase-2-progress.md \
  --field overall_progress --value 25
```

---

## Objective

Build a deterministic enrichment layer over `session_detail` plus a doc->feature->plan/task
frontmatter traversal that sharpens the 4 shipped flags with richer, plan/task-anchored evidence —
without introducing new semantic verdicts (D2).

---

## Implementation Notes

### Architectural Decisions

- D2 (locked): enrichment sharpens evidence/reasons on the existing 4 flags; it does not add new
  semantic verdicts.
- D6 (locked): traversal reuses existing CorePorts + `session_detail`/`feature_forensics`/
  `artifact_intelligence` services; no new correlation key, no new port.

### Patterns and Best Practices

- All enrichment reads route through `session_detail.py`'s public, redaction-applied output —
  never raw JSONL (Hard Invariant #4b).
- Plan/task traversal reuses `document_linking.py`/`entity_links`, matching the
  transport-neutral `agent_queries` layered pattern.

### Known Gotchas

- If a session's `session_detail` output has redacted/absent fields, treat the absence as
  "insufficient data for this evidence point" — never an error, never a fallback to raw-file
  access.
- Any comparison an implementer finds requires semantic judgment ("was this the *right* choice")
  is out of scope — descope and record the finding; it belongs upstream in op/ARC synthesis.

### Development Setup

No special setup beyond the standard backend venv; this phase's fixture suite (T2-009) should be
run via `backend/.venv/bin/python -m pytest backend/tests/ -k aar_review`.

---

## Completion Notes

_To be filled in when this phase is complete: what was built, key learnings, unexpected
challenges, recommendations for Phase 3._
