---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: hardening_plan
status: in-progress
category: infrastructure
title: Live Ingest Source Path Canonicalization Hardening V1 - Implementation Plan
description: Hardening plan to stop worker-watch container path drift from causing duplicate session ingestion and excessive Postgres startup churn.
summary: Canonicalize filesystem-derived session source identity across host and container runtimes, migrate duplicate sync state safely, and add operator validation for startup CPU, memory, and Postgres write amplification.
author: codex
created: 2026-05-04
updated: 2026-05-04
audience:
  - ai-agents
  - developers
  - backend-platform
  - devops
tags:
  - implementation
  - hardening
  - performance
  - live-ingest
  - worker-watch
  - postgres
  - source-paths
feature_slug: live-ingest-source-path-canonicalization-hardening
feature_version: v1
priority: high
risk_level: high
effort_estimate: 24 story points
prd_ref: null
plan_ref: null
related:
  - docs/project_plans/implementation_plans/enhancements/enterprise-live-session-ingest-v1.md
  - docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md
  - docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md
  - docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md
related_documents:
  - deploy/runtime/README.md
  - deploy/runtime/compose.yaml
  - projects.json
  - backend/db/sync_engine.py
  - backend/db/file_watcher.py
  - backend/db/repositories/postgres/runtime_state.py
  - backend/db/repositories/postgres/sessions.py
  - backend/db/repositories/postgres/session_messages.py
commit_refs:
  - 60d5b4a
  - 79ad357
  - 462019e
  - 9196922
  - 7e57c7f
  - 0577e4c
  - f0c106a
pr_refs: []
files_affected:
  - backend/db/sync_engine.py
  - backend/services/source_identity.py
  - backend/tests/test_file_watcher.py
  - backend/tests/test_sync_engine_linking.py
  - backend/tests/test_source_identity.py
  - .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-1-progress.md
  - .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-2-progress.md
  - .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-3-progress.md
  - .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-4-progress.md
  - .claude/progress/live-ingest-source-path-canonicalization-hardening-v1/phase-5-progress.md
  - docs/project_plans/implementation_plans/infrastructure/live-ingest-source-path-canonicalization-hardening-v1.md
---

# Implementation Plan: Live Ingest Source Path Canonicalization Hardening V1

Plan ID: `IMPL-2026-05-04-LIVE-INGEST-SOURCE-PATH-CANONICALIZATION`

Complexity: Medium-high

Total estimated effort: 24 story points

Target timeline: 1 week

## Executive Summary

Live `worker-watch` validation on 2026-05-04 showed high CPU and Postgres churn during startup ingestion. The primary issue was not a confirmed memory leak. It was path identity drift: the same SkillMeat session corpus existed in Postgres under host paths and container paths. Host sync had stored entries such as `/Users/miethe/.claude/projects/...`, while `worker-watch` inside the container saw the same corpus at `/home/ccdash/.claude/projects/...`. Because `sync_state.file_path` and `sessions.source_file` are path-keyed, the container startup sync treated already-ingested files as new work.

This plan hardens filesystem-derived source identity so host and container runtimes converge on a stable canonical source key. It also adds a migration/backfill path for duplicate historical rows, operator guardrails around polling mode, and a repeatable docker-compose validation script for CPU, memory, and Postgres write amplification.

## Live Evidence

Observed while the stack was running through `docker-compose` with `deploy/runtime/.env`:

| Signal | Evidence | Interpretation |
| --- | --- | --- |
| Watcher startup remained active | `worker-watch /detailz` reported `startupSync=running`, backlog `startupSync=1` | Startup sync was still reconciling, not idle watching. |
| Worker CPU was high | `worker-watch` ranged from 27-97% CPU; Python process reported up to 75% in `docker-compose top` | Expected while parsing and persisting thousands of sessions. |
| Postgres CPU and I/O were high | Postgres ranged from 52-142% CPU; block I/O grew past 2 GiB read and 2 GiB written | Startup sync shifted into DB write/index/WAL work. |
| Memory did not show leak shape | `worker-watch` moved from 155 MiB to 415 MiB; Postgres peaked near 884 MiB then dropped near 268 MiB | Heavy working set and cache behavior, not enough evidence for monotonic leakage. |
| Duplicate source identity exists | `sessions`: 4106 container-path SkillMeat rows and 1809 host-path SkillMeat rows; `sync_state`: 4077 container-path entries and 5603 host-path entries | Same corpus is represented under multiple path identities. |
| Watched corpus is large | SkillMeat Claude sessions: 5607 `.jsonl` files, 1.2 GiB; total watched artifact candidates: 9877 files | Polling and startup scans are expensive even after canonicalization. |
| Direct host port was misleading | `127.0.0.1:8000` was also bound by a BoxBrain uvicorn process; `127.0.0.1:3131/api/health/ready` returned in ~27 ms | Validate API through the frontend proxy or container-internal address when port conflicts exist. |

## Goals

1. Stop host/container path drift from causing duplicate `sync_state`, `sessions`, `session_messages`, `telemetry_events`, and attribution churn.
2. Preserve stable read behavior for existing UI/API consumers while source identity is normalized.
3. Make startup sync idempotent across local host runs and container `worker-watch` runs.
4. Provide a migration/backfill strategy for existing duplicate rows.
5. Add focused validation that distinguishes expected startup load from sustained idle CPU or memory growth.

## Non-Goals

1. Do not redesign the entire session ingestion pipeline.
2. Do not replace Postgres canonical transcript storage or change user-facing session DTOs.
3. Do not remove `worker-watch`; this plan hardens its source identity and operator posture.
4. Do not make polling mode the default. `WATCHFILES_FORCE_POLLING=true` remains a compatibility fallback for macOS file-sharing gaps.

## Implementation Strategy

Architecture sequence:

1. Define a runtime-independent canonical source identity contract.
2. Apply canonical source keys at sync-state lookup, session persistence, and delete/replace boundaries.
3. Add migration tooling to collapse duplicate host/container rows safely.
4. Harden watcher/operator configuration to reduce accidental polling and broad startup work.
5. Validate with docker-compose startup and idle profiles.

Critical path:

1. Canonical source identity helper lands with tests.
2. Sync engine and repositories use canonical source keys before writes.
3. Duplicate cleanup tool proves no rows are lost.
4. docker-compose validation shows second startup skips already-ingested sources.

Parallel work:

1. Operator docs and smoke script can proceed once the canonical identity contract is drafted.
2. Postgres duplicate-audit queries can be built in parallel with backend helper tests.
3. Polling-mode docs can be updated independently from migration tooling.

## Phase Overview

| Phase | Title | Estimate | Primary Subagents | Outcome |
| --- | --- | ---: | --- | --- |
| 1 | Source Identity Contract | 4 pts | backend-architect, data-layer-expert | Define canonical path/source-key rules and tests. |
| 2 | Ingest Path Canonicalization | 7 pts | python-backend-engineer, data-layer-expert | Use canonical source keys for sync and session writes. |
| 3 | Duplicate Migration And Backfill | 5 pts | data-layer-expert, python-backend-engineer | Collapse existing host/container duplicate state safely. |
| 4 | Runtime Guardrails And Operator Docs | 3 pts | DevOps, documentation-writer | Reduce accidental polling/broad-sync churn and document validation. |
| 5 | Performance Validation Gate | 5 pts | performance-engineer, task-completion-validator | Prove startup idempotence, idle CPU stability, and no memory leak signal. |

## Phase 1: Source Identity Contract

Assigned Subagents: backend-architect, data-layer-expert

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
| --- | --- | --- | --- | ---: | --- |
| SRC-001 | Canonical Source Identity Design | Define a single source identity contract for filesystem-derived session, document, progress, and test files. Cover project-root paths, `~/.claude`, `~/.codex`, container home remaps, and optional mount slots. | Contract document or code comments identify canonical inputs, outputs, collision behavior, and rollout constraints. | 1 pt | None |
| SRC-002 | Path Canonicalization Helper | Add a helper that maps host and container aliases to a stable source key before repository lookup/write. Prefer project registry path config and mounted root aliases over ad hoc string replacement. | Unit tests prove `/Users/miethe/.claude/...` and `/home/ccdash/.claude/...` map to the same key for the same project. | 2 pts | SRC-001 |
| SRC-003 | Collision And Escape Tests | Cover symlinks, non-mounted paths, optional mount slots, unrelated projects, and paths outside known roots. | Unknown paths remain stable and do not collapse across projects; known aliases collapse only when they represent the same source. | 1 pt | SRC-002 |

Quality gates:

1. Canonicalization is deterministic and side-effect free.
2. The helper does not require a live container runtime.
3. Tests cover both host and container path forms.

## Phase 2: Ingest Path Canonicalization

Assigned Subagents: python-backend-engineer, data-layer-expert

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
| --- | --- | --- | --- | ---: | --- |
| ING-001 | Sync State Lookup Boundary | Update `sync_repo.get_sync_state`, `upsert_sync_state`, and delete usage sites so startup sync checks canonical source identity before deciding a file is new. | A second startup under container paths skips files already synced under host paths when content/mtime is unchanged. | 2 pts | SRC-002 |
| ING-002 | Session Source File Persistence | Normalize `sessions.source_file` at write boundaries or add an explicit canonical source column while preserving compatibility for display/debug payloads. | Existing API consumers keep source display behavior, but repository uniqueness and deletes use canonical identity. | 2 pts | SRC-002 |
| ING-003 | Delete/Replace Scope Hardening | Ensure `delete_by_source`, relationship deletes, canonical messages, telemetry replacement, and usage attribution replacement do not duplicate rows when the same physical file appears through an alias path. | Re-ingesting one aliased file does not double `session_messages`, `telemetry_events`, or `session_usage_attributions`. | 2 pts | ING-001, ING-002 |
| ING-004 | Live Fanout Idempotence | Confirm publish counts reflect real changed sessions, not alias re-ingestion. Preserve invalidation-only Postgres fanout behavior. | `worker-watch` publishes no bulk duplicate fanout events on second startup with unchanged files. | 1 pt | ING-003 |

Quality gates:

1. Existing local SQLite tests still pass.
2. Existing Postgres repository tests still pass.
3. The fix applies to both startup sync and watcher-triggered changed-file sync.

## Phase 3: Duplicate Migration And Backfill

Assigned Subagents: data-layer-expert, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
| --- | --- | --- | --- | ---: | --- |
| MIG-001 | Duplicate Audit Queries | Add repeatable SQL or a CLI/admin script that reports host/container alias duplicates in `sync_state`, `sessions`, and derived tables. | The script reports counts equivalent to the 2026-05-04 investigation and exits non-zero only on query failure. | 1 pt | SRC-002 |
| MIG-002 | Safe Collapse Strategy | Define how to choose survivor rows and update or delete duplicate rows without losing newer mtime/hash data or canonical transcript rows. | Strategy is restart-safe, dry-run first, and scoped by project id. | 1 pt | MIG-001 |
| MIG-003 | Migration Tool | Implement a project-scoped dry-run/apply command for duplicate source identity collapse. | Dry run prints affected source keys and row counts; apply is idempotent and records operation evidence. | 2 pts | MIG-002 |
| MIG-004 | Post-Migration Verification | Verify table counts, live feature/session views, and source lookup behavior after cleanup. | No duplicate host/container source identities remain for the target project; session counts remain explainable. | 1 pt | MIG-003 |

Quality gates:

1. Migration cannot run without explicit project id.
2. Migration has dry-run output suitable for review before apply.
3. Rollback plan is documented as restoring from the Postgres volume backup or transaction snapshot.

## Phase 4: Runtime Guardrails And Operator Docs

Assigned Subagents: DevOps, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
| --- | --- | --- | --- | ---: | --- |
| OPS-001 | Polling Mode Guardrail | Keep `WATCHFILES_FORCE_POLLING` scoped to `worker-watch`, but document that it increases sustained CPU and should be disabled after event delivery is confirmed. | `deploy/runtime/README.md` distinguishes startup sync load from idle polling load and lists expected validation commands. | 1 pt | None |
| OPS-002 | Port Conflict Guidance | Document that host `127.0.0.1:8000` can be occupied by another dev server and that `127.0.0.1:3131/api/health/ready` or container-internal probes are safer for stack validation. | Runtime smoke docs include a port-conflict check using `lsof -nP -iTCP:8000 -sTCP:LISTEN`. | 1 pt | None |
| OPS-003 | Watch Scope Guidance | Document how `sessionsPath`, `.claude`, `.codex`, workspace roots, and optional mounts affect watch size and startup cost. | Docs call out that broad global session roots can contain thousands of JSONL files and should be intentional. | 1 pt | SRC-001 |

Quality gates:

1. Docs use `docker-compose` for this environment and do not assume standalone `docker`.
2. Docs include expected CPU/RAM interpretation rather than only commands.
3. Docs do not present polling mode as a default performance setting.

## Phase 5: Performance Validation Gate

Assigned Subagents: performance-engineer, task-completion-validator

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Dependencies |
| --- | --- | --- | --- | ---: | --- |
| VAL-001 | Startup Idempotence Smoke | Start the stack, wait for `worker-watch` startup sync to complete, stop/start again, and compare sync/fanout/write counts. | Second startup does not bulk re-ingest already-synced session files under alias paths. | 2 pts | ING-004, MIG-004 |
| VAL-002 | Idle CPU And Memory Window | After startup completes, sample `docker-compose stats --no-stream` every 30 seconds for 10 minutes with no file changes. | `worker-watch` CPU stays low outside polling/event bursts; RSS does not grow monotonically across the sample. | 1 pt | VAL-001 |
| VAL-003 | Postgres Churn Check | Capture relation stats for `sessions`, `session_messages`, `telemetry_events`, `session_usage_attributions`, and `sync_state` before and after second startup. | Rows and dead tuples do not grow materially on unchanged second startup. | 1 pt | VAL-001 |
| VAL-004 | Regression Suite | Run focused backend tests for file watcher, runtime bootstrap, Postgres live fanout, sync engine session writes, and new canonicalization/migration tests. | Focused tests pass; any known environment caveats are documented with exact command output. | 1 pt | ING-004, MIG-004 |

Quality gates:

1. Validation uses the same `docker-compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres --profile live-watch` surface.
2. CPU/RAM evidence includes startup and idle windows.
3. Postgres evidence includes table stats and active query sampling.

## Risks And Mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Canonicalization collapses distinct files that only look similar by path suffix. | High | Include project id and configured mount/root identity in the source key; test unrelated roots. |
| Migration deletes useful historical rows. | High | Dry-run first, project-scoped apply, transactional operations, backup/restore runbook. |
| UI/debug surfaces lose useful source path display. | Medium | Preserve display path separately from canonical identity when needed. |
| Local SQLite and enterprise Postgres diverge. | Medium | Add parity tests for both repository paths where feasible. |
| Polling remains high CPU after canonicalization. | Medium | Validate idle CPU separately with polling on/off; document polling as compatibility mode. |

## Validation Commands

Use these commands during implementation validation:

```bash
docker-compose --env-file deploy/runtime/.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch ps

docker-compose --env-file deploy/runtime/.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch stats --no-stream

curl -fsS http://127.0.0.1:9466/detailz | jq '.detail.worker.jobs.startupSync, .detail.liveFanout'

curl -fsS http://127.0.0.1:3131/api/health/ready | jq .

docker-compose --env-file deploy/runtime/.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch exec -T postgres \
  psql -U ccdash -d ccdash -c "select relname, n_live_tup, n_dead_tup, n_tup_ins, n_tup_del from pg_stat_user_tables where relname in ('sessions','session_messages','telemetry_events','session_usage_attributions','sync_state') order by relname;"
```

## Success Criteria

1. Host and container runtime aliases resolve to the same source identity for the same physical session file.
2. A second unchanged `worker-watch` startup does not duplicate session rows or produce bulk live fanout.
3. Startup CPU and Postgres I/O remain explainable by real changed work.
4. Idle `worker-watch` CPU is low when polling is disabled and bounded when polling is enabled.
5. Operator docs distinguish port conflicts, startup sync load, polling load, and actual leak signals.

## Deferred Items

1. A broader ingestion service extraction is deferred to future architecture work. This plan only hardens source identity and duplicate cleanup.
2. Changing the default deployment port away from `8000` is deferred unless port conflicts become a frequent operator issue.
3. Rewriting telemetry event insertion to use batched Postgres `executemany` or copy protocol is deferred unless post-canonicalization validation still shows unacceptable startup duration.
