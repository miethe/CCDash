---
schema_version: 2
doc_type: context
type: context
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
title: "Remote CCDash Streaming + Entire.io Integration - Development Context"
status: pending
created: 2026-04-19
updated: 2026-04-19
owners: ["nick"]
prd_ref: docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
critical_notes_count: 0
implementation_decisions_count: 0
active_gotchas_count: 5
agent_contributors: []
agents: []
phase_status:
  - phase: 1
    status: in-progress
    reason: "SPIKE-A and SPIKE-B charters finalized; execution not yet started."
blockers: []
decisions: []
---

# Remote CCDash Streaming + Entire.io Integration - Development Context

**Status**: Draft — SPIKE execution phase
**Created**: 2026-04-19
**Last Updated**: 2026-04-19

---

## Feature Summary

CCDash today is a local-first tool with a filesystem-coupled sync engine, single-tenant auth, and no mechanism to receive session data from a remote source. This feature delivers two complementary tracks — remote team operation (N developer daemons streaming to one shared CCDash server via a transport-neutral `SessionIngestSource` port) and Entire.io integration (treating `entire/checkpoints/v1` git-branch checkpoints as a first-class session source) — on a single shared foundation of port abstraction and cursor-based resumable ingest.

---

## Key Documents

- **Design spec**: `docs/project_plans/design-specs/remote-ccdash-streaming.md`
- **PRD**: `docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md`
- **Implementation plan**: `docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md`
- **SPIKE-A charter** (remote streaming): `docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md`
- **SPIKE-B charter** (Entire.io integration): `docs/project_plans/SPIKEs/entire-io-integration-charter.md`
- **Grounding brief**: `.claude/findings/remote-ccdash-grounding-brief.md`

---

## Architectural Decisions Pending

All ADRs below are **TBD** pending SPIKE findings. No implementation begins until these are locked.

**SPIKE-A ADRs (5):**
1. ADR: Ingest transport selection (NDJSON vs SSE vs WebSocket vs gRPC) — TBD
2. ADR: Daemon packaging + lifecycle (standalone binary vs CLI subcommand vs worker profile) — TBD
3. ADR: Auth model v1 (workspace-scoped token strategy; migration from single-tenant bearer) — TBD
4. ADR: Sync engine port abstraction (`SessionIngestSource` interface shape; cursor/watermark model) — TBD
5. ADR: Multi-project routing model (single-process routing vs per-project worker fanout) — TBD

**SPIKE-B ADRs (3):**
6. ADR: Ingest path decision for Entire checkpoints (branch-parse vs CLI-wrap vs hybrid) — TBD
7. ADR: Session identity unification (`source_ref` scheme; ON CONFLICT upsert key; migration) — TBD
8. ADR: Live-update loop mechanism (fs-watch on ref vs periodic git-fetch polling) — TBD

---

## Active Risks

From PRD §9 (top 5):

| # | Risk | Severity |
|---|------|----------|
| R-1 | `SyncEngine` refactor breaks local-mode deployments | High impact, medium likelihood — mitigated by `FilesystemSource` pass-through + E4 zero-test-change gate |
| R-4 | Absent cursor table causes duplicate rows on daemon restart | Medium impact, high likelihood if skipped — cursor table is a hard prerequisite for any external ingest (FR-3 blocks FR-1) |
| R-3 | Per-workspace ingest token credential leakage via daemon config | High impact, low-medium likelihood — token stored only in OS keychain or env var; write-only scope |
| R-9 | SPIKE outcomes materially reshape transport or auth decisions, invalidating PRD sections 6–8 | High impact, medium likelihood — explicit re-baseline of PRD after both SPIKEs land; promote from `draft` only post re-baseline |
| R-2 | Entire `entire/checkpoints/v1` schema changes without notice | Medium impact, medium likelihood — schema snapshot in SPIKE-B; skip + warn on unknown fields |

---

## Current Focus

Phase 1: SPIKE execution. Phases 2–7 plan rebaseline gated on SPIKE deliverables.

Both SPIKE charters are finalized and ready to execute. SPIKE-A and SPIKE-B can run in parallel (1.5–2 weeks each). A design meeting is scheduled after SPIKE completion to lock ADRs and re-baseline Phases 2–7 scope and estimates.

---

## Glossary

- **SessionIngestSource**: The transport-neutral Python `Protocol` / ABC that decouples the sync engine from any specific ingest medium (filesystem, remote HTTP, git branch). Both `FilesystemSource` and `RemoteIngestSource` implement this port. Adding a new source requires only a new implementation class, no core sync engine changes.
- **EntireCheckpointSource**: The concrete `SessionIngestSource` implementation that reads `entire/checkpoints/v1` branch checkpoint JSON via git plumbing (libgit2 / dulwich) and maps Entire 12-hex checkpoint IDs to CCDash sessions.
- **workspace-scoped auth**: An extension to `backend/adapters/auth/bearer.py` that maps per-workspace ingest tokens to a `workspace_id`. All data-access paths enforce a workspace predicate so Workspace A can never read Workspace B's sessions. Replaces (but is backward-compatible with) the current single-static-bearer model.
- **daemon**: A lightweight process (standalone binary or `ccdash daemon` subcommand — shape TBD per SPIKE-A ADR) that runs on a developer workstation, tails local JSONL session files, and POSTs NDJSON batches to the remote CCDash ingest endpoint. Carries per-event idempotency keys and implements reconnect/backoff.
