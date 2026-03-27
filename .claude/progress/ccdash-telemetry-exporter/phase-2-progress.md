---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-telemetry-exporter"
feature_slug: "ccdash-telemetry-exporter"
phase: 2
phase_title: "Export Worker and HTTP Client"
status: pending
created: 2026-03-24
updated: 2026-03-24
prd_ref: docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
plan_ref: docs/project_plans/implementation_plans/integrations/ccdash-telemetry-exporter-v1.md
commit_refs: []
pr_refs: []

owners: ["python-backend-engineer"]
contributors: []

tasks:
  - id: "P2-T1"
    title: "Implement SAMTelemetryClient HTTP wrapper"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P1-T1"]
    effort: "M"
    files: ["backend/services/integrations/sam_telemetry_client.py"]

  - id: "P2-T2"
    title: "Implement TelemetryExporterJob scheduled job"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P1-T3", "P1-T6", "P2-T1"]
    effort: "L"
    files: ["backend/adapters/jobs/telemetry_exporter.py"]

  - id: "P2-T3"
    title: "Register job in RuntimeContainer for worker profile"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P2-T2"]
    effort: "S"
    files: ["backend/runtime/container.py"]

  - id: "P2-T4"
    title: "Add enqueue trigger in sync engine session finalization"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P1-T4", "P1-T6"]
    effort: "M"
    files: ["backend/db/sync_engine.py"]

  - id: "P2-T5"
    title: "Integration tests with mock SAM server"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P2-T2", "P2-T3"]
    effort: "L"
    files: ["backend/tests/test_telemetry_exporter_integration.py"]

  - id: "P2-T6"
    title: "Update __init__.py files for new modules"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["P2-T1", "P2-T2"]
    effort: "S"
    files: ["backend/adapters/jobs/__init__.py", "backend/services/integrations/__init__.py"]

parallelization:
  batch_1: ["P2-T1", "P2-T4"]
  batch_2: ["P2-T2"]
  batch_3: ["P2-T3", "P2-T5", "P2-T6"]
---

# Phase 2: Export Worker and HTTP Client

## Quick Reference

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/ccdash-telemetry-exporter/phase-2-progress.md -t P2-T1 -s completed
```

## Exit Criteria

- Worker runtime pushes a batch to mock SAM endpoint
- Retries on HTTP 5xx, abandons on 4xx after logging
- Re-entrancy guard prevents parallel job execution
- Integration tests pass against mock server
