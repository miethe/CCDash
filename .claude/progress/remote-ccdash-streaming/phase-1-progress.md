---
schema_version: 2
doc_type: progress
type: progress
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
phase: 1
phase_title: "SPIKE Execution"
status: in_progress
created: 2026-04-19
updated: 2026-04-19
prd_ref: docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
commit_refs: []
pr_refs: []
owners: ["nick"]
contributors: []
execution_model: batch-parallel

overall_progress: 0
completion_estimate: on-track
total_tasks: 19
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0

tasks:
  # === SPIKE-A: Remote CCDash Operation + Local Daemon Session Streaming ===
  - id: "SPIKE-A.1"
    description: "ADR — Ingest transport decision (NDJSON vs SSE vs WebSocket vs gRPC). Decision matrix + E1 benchmark table. Resolves OQ-1."
    status: pending
    assigned_to: ["python-backend-engineer", "backend-architect"]
    dependencies: []

  - id: "SPIKE-A.2"
    description: "ADR — Daemon packaging + lifecycle (standalone binary vs ccdash CLI subcommand vs worker daemon profile). Lifecycle diagrams + E2 prototype on one OS. Resolves OQ-2."
    status: pending
    assigned_to: ["python-backend-engineer"]
    dependencies: []

  - id: "SPIKE-A.3"
    description: "ADR — Auth model v1 (workspace-scoped token strategy; migration path from single-tenant bearer). E3 prototype passing cross-workspace isolation test. Resolves OQ-3."
    status: pending
    assigned_to: ["backend-architect", "data-layer-expert"]
    dependencies: []

  - id: "SPIKE-A.4"
    description: "ADR — Sync engine port abstraction (SessionIngestSource Protocol shape; FilesystemSource wrapper; ingest_cursors table; cursor/watermark contract). E4 spike branch: zero test changes gate. Resolves OQ-4."
    status: pending
    assigned_to: ["python-backend-engineer", "data-layer-expert"]
    dependencies: []

  - id: "SPIKE-A.5"
    description: "ADR — Multi-project routing model (single-process request-scoped routing vs per-project worker fanout). E5 benchmark table. Resolves OQ-7."
    status: pending
    assigned_to: ["backend-architect", "data-layer-expert"]
    dependencies: []

  - id: "SPIKE-A.6"
    description: "Benchmark E1: NDJSON ingest throughput/latency. Must meet go/no-go: >=500 events/sec sustained, p99 <200ms, reconnect <=5s."
    status: pending
    assigned_to: ["python-backend-engineer"]
    dependencies: ["SPIKE-A.1"]

  - id: "SPIKE-A.7"
    description: "Benchmark E5: Multi-project routing memory and cold-start. Must meet go/no-go at 10 concurrent projects: cold-start <=+10%, RSS <=2x baseline, p99 <=+25%."
    status: pending
    assigned_to: ["backend-architect"]
    dependencies: ["SPIKE-A.5"]

  - id: "SPIKE-A.8"
    description: "Failure-mode matrix (RQ-6): enumerate daemon offline, server 5xx, partial batch, schema skew, clock skew. Document detection, retry/backoff, dead-letter, and operator-visible health signal per row. One chaos test run against E1+E2."
    status: pending
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["SPIKE-A.6"]

  - id: "SPIKE-A.9"
    description: "Migration plan memo (RQ-8): default no-op behavior, opt-in flag (CCDASH_INGEST_SOURCE), dual-source dedup policy, upgrade instructions for local-mode users."
    status: pending
    assigned_to: ["python-backend-engineer"]
    dependencies: ["SPIKE-A.4"]

  - id: "SPIKE-A.10"
    description: "Findings synthesis doc at docs/project_plans/SPIKEs/remote-ccdash-streaming.md. Includes frontend UX inventory + cadence decision memo (RQ-7). All SPIKE-A deliverables consolidated."
    status: pending
    assigned_to: ["backend-architect", "python-backend-engineer"]
    dependencies: ["SPIKE-A.1", "SPIKE-A.2", "SPIKE-A.3", "SPIKE-A.4", "SPIKE-A.5", "SPIKE-A.6", "SPIKE-A.7", "SPIKE-A.8", "SPIKE-A.9"]

  # === SPIKE-B: Entire.io OSS CLI Integration ===
  - id: "SPIKE-B.1"
    description: "Canonical Entire checkpoint schema doc covering >=3 agents (Claude Code, Gemini CLI, Cursor). Every field marked required/optional/agent-specific. Resolves RQ-1, informs E3."
    status: pending
    assigned_to: ["data-layer-expert"]
    dependencies: []

  - id: "SPIKE-B.2"
    description: "ADR — Ingest path decision (branch-parse via libgit2/dulwich vs CLI-wrap vs hybrid). Decision matrix scoring >=5 criteria. Resolves RQ-2."
    status: pending
    assigned_to: ["python-backend-engineer"]
    dependencies: ["SPIKE-B.1"]

  - id: "SPIKE-B.3"
    description: "ADR — Session identity unification (source_ref URI scheme; source_type enum; external_id index; backfill plan; zero-downtime migration story). Resolves RQ-4."
    status: pending
    assigned_to: ["data-layer-expert"]
    dependencies: ["SPIKE-B.1"]

  - id: "SPIKE-B.4"
    description: "ADR — Live-update loop mechanism (fs-watch on .git/refs vs periodic git-fetch polling vs upstream hook). p50 latency target <30s. Resolves RQ-3."
    status: pending
    assigned_to: ["python-backend-engineer"]
    dependencies: ["SPIKE-B.2"]

  - id: "SPIKE-B.5"
    description: "Prototype branch with EntireCheckpointSource skeleton (E4). Implements SessionIngestSource port from SPIKE-A; pushes one real checkpoint end-to-end; verifies zero port changes required."
    status: pending
    assigned_to: ["python-backend-engineer", "data-layer-expert"]
    dependencies: ["SPIKE-A.4", "SPIKE-B.2", "SPIKE-B.3"]

  - id: "SPIKE-B.6"
    description: "Upstream-feedback memo: document any issues/PRs filed with entireio/cli. Hook registration investigation result (RQ-7 / E5). Go/no-go on push-based live ingest."
    status: pending
    assigned_to: ["python-backend-engineer"]
    dependencies: []

  - id: "SPIKE-B.7"
    description: "Coexistence / dedup policy memo (RQ-8): enumerate overlap scenarios (native JSONL + Entire checkpoint same session), provenance labeling spec, soft-dedup heuristics, UI policy sketch."
    status: pending
    assigned_to: ["architect"]
    dependencies: ["SPIKE-B.1", "SPIKE-B.3"]

  - id: "SPIKE-B.8"
    description: "Findings synthesis doc at docs/project_plans/SPIKEs/entire-io-integration.md. All SPIKE-B deliverables consolidated including privacy/redaction memo (RQ-9) and commit linkage schema sketch (RQ-6)."
    status: pending
    assigned_to: ["data-layer-expert", "python-backend-engineer"]
    dependencies: ["SPIKE-B.1", "SPIKE-B.2", "SPIKE-B.3", "SPIKE-B.4", "SPIKE-B.5", "SPIKE-B.6", "SPIKE-B.7"]

  # === PHASE 1 GATE ===
  - id: "PHASE-1-GATE"
    description: "Hold design review meeting; re-baseline Phases 2–7 scope and effort estimates against SPIKE findings; promote PRD status from draft to approved; create Phase 2–7 progress files."
    status: pending
    assigned_to: ["nick"]
    dependencies:
      - "SPIKE-A.1"
      - "SPIKE-A.2"
      - "SPIKE-A.3"
      - "SPIKE-A.4"
      - "SPIKE-A.5"
      - "SPIKE-A.6"
      - "SPIKE-A.7"
      - "SPIKE-A.8"
      - "SPIKE-A.9"
      - "SPIKE-A.10"
      - "SPIKE-B.1"
      - "SPIKE-B.2"
      - "SPIKE-B.3"
      - "SPIKE-B.4"
      - "SPIKE-B.5"
      - "SPIKE-B.6"
      - "SPIKE-B.7"
      - "SPIKE-B.8"

parallelization:
  batch_1:
    - "SPIKE-A.1"
    - "SPIKE-A.2"
    - "SPIKE-A.3"
    - "SPIKE-A.4"
    - "SPIKE-A.5"
    - "SPIKE-B.1"
    - "SPIKE-B.6"
  batch_2:
    - "SPIKE-A.6"
    - "SPIKE-A.7"
    - "SPIKE-A.8"
    - "SPIKE-A.9"
    - "SPIKE-B.2"
    - "SPIKE-B.3"
    - "SPIKE-B.4"
    - "SPIKE-B.7"
  batch_3:
    - "SPIKE-A.10"
    - "SPIKE-B.5"
    - "SPIKE-B.8"
    - "PHASE-1-GATE"

blockers: []

success_criteria:
  - "All 5 SPIKE-A ADRs approved and present in architecture docs directory"
  - "All 3 SPIKE-B ADRs approved and present in architecture docs directory"
  - "Benchmark E1 meets go/no-go: >=500 events/sec, p99 <200ms, reconnect <=5s"
  - "Benchmark E5 meets go/no-go at 10 concurrent projects"
  - "E4 spike branch: zero existing test changes required (FilesystemSource local-mode parity)"
  - "SPIKE-A findings doc at docs/project_plans/SPIKEs/remote-ccdash-streaming.md"
  - "SPIKE-B findings doc at docs/project_plans/SPIKEs/entire-io-integration.md"
  - "Design meeting held; PRD re-baselined and promoted to approved"
  - "Phase 2–7 progress files created"

notes: >
  Phases 2–7 progress files deferred per plan §11; create after PHASE-1-GATE completes.
  SPIKE-A (3 tracks: transport/ingest, auth/routing, frontend UX) and SPIKE-B can
  run in parallel for the first 1–2 weeks. batch_1 tasks are all independent and can
  start on day 1. SPIKE-B.5 (EntireCheckpointSource prototype) depends on SPIKE-A.4
  landing the SessionIngestSource port shape first.
---

# remote-ccdash-streaming - Phase 1: SPIKE Execution

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate task state in markdown.

Update task status via CLI:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/remote-ccdash-streaming/phase-1-progress.md \
  -t SPIKE-A.1 -s in_progress
```

---

## Objective

Execute SPIKE-A (remote streaming: transport, daemon, auth, sync engine port, multi-project routing) and SPIKE-B (Entire.io integration: checkpoint schema, ingest path, session identity, live-update loop) in parallel. Produce 8 ADRs, benchmarks E1+E5, failure-mode matrix, migration plan memo, and two findings synthesis docs. All outputs gate Phase 2 kickoff.

---

## Notes

**Phases 2–7 progress files deferred per plan §11; create after PHASE-1-GATE completes.**

SPIKE-A has three parallel tracks (see charter §7):
- Track A — Transport + ingest + daemon (RQ-1, RQ-2, RQ-4; E1, E2, E4): `python-backend-engineer`
- Track B — Auth + routing + ops posture (RQ-3, RQ-5, RQ-6; E3, E5): `backend-architect` + `data-layer-expert`
- Track C — Frontend health UX + migration (RQ-7, RQ-8): frontend owner TBD

SPIKE-B tracks (see charter §7):
- Data/schema: `data-layer-expert` (RQ-1, RQ-4, RQ-5, RQ-6, E1, E3)
- Ingest/live-loop: `python-backend-engineer` (RQ-2, RQ-3, RQ-7, E2, E5)
- Policy/product: `architect` (RQ-8, RQ-9)
- Integration: coordinated with SPIKE-A owner (E4)

Mid-SPIKE checkpoint at end of week 1: SPIKE-A E1+E2 running end-to-end; SPIKE-A E3 enforcing workspace scoping; SPIKE-B schema doc drafted.
