---
schema_version: 2
doc_type: progress
phase: 2
phase_title: Watcher fan-out SPIKE / design (W2)
feature_slug: ccdash-runtime-deploy-remediation
status: completed
created: 2026-06-12
updated: '2026-06-13'
overall_progress: 100
completion_estimate: "100%"
parallelization:
  strategy: sequential
  batch_1:
  - T2-001
  batch_2:
  - T2-002
---

# Phase 2 Progress — Watcher fan-out SPIKE / design (W2)

## Objective

Author and approve the watcher fan-out design document answering all 5 open questions
(OQ-2, OQ-3, OQ-5, dynamic add/remove scope, bounded concurrency ceiling). The approved
doc gates P3 implementation; under-specified design at this phase causes P3 rework.

---

## Task Table

```yaml
tasks:
  - id: T2-001
    name: "SPIKE design doc"
    status: pending
    assigned_to: backend-architect
    assigned_model: sonnet
    model_effort: extended
    description: >
      Author .claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md.
      Must answer all 5 OQs: (OQ-2) watch all registered vs is_active=true with
      resource-budget rationale; (OQ-3) backward-compat for non-empty
      WORKER_WATCH_PROJECT_ID; (OQ-5) aggregate /readyz + per-project /detailz;
      dynamic add/remove scope decision; bounded concurrency ceiling; enumerated
      test scenarios. status: draft on creation; >=400 words.

  - id: T2-002
    name: "SPIKE approval gate"
    status: pending
    assigned_to: backend-architect
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Operator reviews T2-001; doc advances to status: approved; decision on T3-004
      (reconcile loop in-scope vs D-002 deferred) recorded in progress notes;
      P3 unblocked. w2-watcher-fanout-design.md status == approved required.
```

---

## AC Coverage

| AC ID | Description | Verified By | Verdict |
|-------|-------------|-------------|---------|
| AC-T2-001 | All 5 OQs answered; test scenarios enumerable; ≥400 words | T2-002 (operator approval) | pending |
| AC-T2-002 | T3-004 scope decision recorded (in-P3 or defer D-002) | Progress notes | pending |

---

## Quick Reference

**Batch dispatch hints for orchestrator:**

- **batch_1** → `Task(backend-architect, "T2-001: Author w2-watcher-fanout-design.md — answer OQ-2, OQ-3, OQ-5, dynamic scope, concurrency ceiling, test scenarios. See backend/runtime/container.py ~lines 1227-1236 and backend/config.py ~line 1007.")`
- **batch_2** → *(Operator review of T2-001 — advance doc to `status: approved`, record T3-004 scope decision in P2 progress notes, unblock P3)*

**Quality gates before phase close:**
- `w2-watcher-fanout-design.md` exists, answers all 5 OQs, `status: approved`
- T3-004 scope decision recorded (in-P3 or defer D-002)

**Key files:** `.claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md`
