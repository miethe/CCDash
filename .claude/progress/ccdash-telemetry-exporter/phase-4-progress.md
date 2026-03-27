---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-telemetry-exporter"
feature_slug: "ccdash-telemetry-exporter"
phase: 4
phase_title: "Hardening - Retry, Backpressure, and Monitoring"
status: pending
created: 2026-03-24
updated: 2026-03-24
prd_ref: docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
plan_ref: docs/project_plans/implementation_plans/integrations/ccdash-telemetry-exporter-v1.md
commit_refs: []
pr_refs: []

owners: ["python-backend-engineer"]
contributors: ["frontend-developer"]

tasks:
  - id: "P4-T1"
    title: "Queue-size cap enforcement with drop-and-warn"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P2-T4"]
    effort: "S"
    files: ["backend/services/telemetry_transformer.py"]

  - id: "P4-T2"
    title: "Synced-row purge with configurable retention"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P2-T2"]
    effort: "S"
    files: ["backend/adapters/jobs/telemetry_exporter.py"]

  - id: "P4-T3"
    title: "OTel counters and histograms in otel.py"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P2-T2"]
    effort: "M"
    files: ["backend/observability/otel.py"]

  - id: "P4-T4"
    title: "OTel span wrapping for export batches"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P4-T3"]
    effort: "S"
    files: ["backend/adapters/jobs/telemetry_exporter.py"]

  - id: "P4-T5"
    title: "Prometheus gauge for exporter-disabled state"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P4-T3"]
    effort: "S"
    files: ["backend/observability/otel.py"]

  - id: "P4-T6"
    title: "Load test script for CPU overhead validation"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P2-T5"]
    effort: "M"
    files: ["backend/tests/load/test_telemetry_exporter_load.py"]

  - id: "P4-T7"
    title: "End-to-end documentation"
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["P4-T3", "P3-T5"]
    effort: "M"
    files: ["docs/telemetry-export-guide.md"]

parallelization:
  batch_1: ["P4-T1", "P4-T2", "P4-T3"]
  batch_2: ["P4-T4", "P4-T5", "P4-T6"]
  batch_3: ["P4-T7"]
---

# Phase 4: Hardening - Retry, Backpressure, and Monitoring

## Quick Reference

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/ccdash-telemetry-exporter/phase-4-progress.md -t P4-T1 -s completed
```

## Exit Criteria

- All success metrics are measurable via OTel/Prometheus
- Ops panel shows staleness warnings when export stalls
- Load test confirms < 2% CPU overhead at 50-event batches
- All NFRs verified by automated or manual testing
- Documentation covers configuration, ops panel, and troubleshooting
