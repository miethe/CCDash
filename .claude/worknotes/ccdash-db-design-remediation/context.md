---
type: context
schema_version: 2
doc_type: context
prd: "ccdash-db-design-remediation"
feature_slug: "ccdash-db-design-remediation"
title: "CCDash DB Design Remediation — Development Context"
status: active
created: 2026-06-03
updated: 2026-06-03

critical_notes_count: 4
implementation_decisions_count: 3
active_gotchas_count: 2
agent_contributors: []

agents: []
---

# CCDash DB Design Remediation — Development Context

**Status**: Active (pre-execution — P1 not yet started)
**Created**: 2026-06-03
**Last Updated**: 2026-06-03

> Shared worknotes for all agents executing this remediation. Add brief observations, decisions, gotchas, and handoff notes as execution proceeds.

---

## Originating Incident

**Finding F-01 — Registry silent flush**: `ProjectManager._flush_snapshot_to_db` (`project_manager.py:447–460`) swallows all exceptions and always returns `True`, even when zero rows were written. This caused the project registry DB to remain empty after every cold restart: the in-memory snapshot was considered "loaded" but never actually persisted. On restart, projects were re-read from `projects.json` into memory only — the DB table stayed at 0 rows.

**Discovery**: Manual inspection of `data/ccdash_cache.db` revealed `projects` table was empty despite 5 active projects in `projects.json`. Confirmed by `PRAGMA table_info(projects)` + `SELECT COUNT(*) FROM projects`.

**Impact**: All tools that query the DB-backed registry (health endpoint, CLI `ccdash project list`) returned empty or inconsistent results. Affected upstream queries in `application/services/agent_queries/` that assumed DB parity.

---

## SPIKE Verdict

SPIKE audit (`docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md`) returned a **conditional GO**:

- Confirmed 5 root-cause findings (F-01 through F-10) across registry, write reliability, migration concurrency, storage, and config.
- Recommended Option B (DB-authoritative registry) over Option A (JSON-primary), now ratified as ADR-006.
- ADR-007 ratified alongside: every DB write path must retry via a shared helper and surface failures in health + Prometheus.
- Destructive multi-GB storage reclaim (`session_logs`, `telemetry_events`) scoped OUT to `ccdash-enterprise-liveness-storage-v1` PRD.

**Charter**: `docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md`
**Findings**: `docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md`

---

## ADR Status

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| ADR-006 | DB-Authoritative Project Registry | ratified (pre-P1) | 2026-06-03 |
| ADR-007 | DB-Write Failure Surfacing Standard | ratified (pre-P1) | 2026-06-03 |

ADR files: `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`, `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`

Both ADRs are ratified but their `status` fields will be updated to `accepted` in P5 (T5-001, T5-002) once the concrete implementations land.

---

## 5-Phase Critical Path

```
ADR-006/007 ratified ──> P1 (Registry Correctness)  [ships first; fully independent]
                              │
                              ├──> P2 (Reliability + Observability)  [P1 must verify; sequential]
                              │
                              ├──> P3 (Migration Integrity)          [parallel with P4 after P1]
                              │
                              └──> P4 (Storage Hygiene)              [parallel with P3; snapshot-gated]
P2 + P3 + P4 ──────────────────────────────────────> P5 (Docs / ADRs)  [convergence]
```

**Wave plan**:
- Wave 1: P1 alone (unblocked)
- Wave 2: P2 alone (blocked on P1)
- Wave 3: P3 + P4 in parallel (blocked on P1; P4 additionally needs operator snapshot)
- Wave 4: P5 alone (blocked on P2 + P3 + P4)

**Hard gate for P4**: P1 cold-start smoke (T1-010) must pass AND operator must confirm a restorable DB snapshot before P4 executes any task. Record snapshot timestamp in `phase-4-progress.md` under Operator Approvals.

---

## Key Implementation Decisions

### ADR-006 Option B: DB-Authoritative Registry

The dual `ProjectManager` (JSON-backed) and `DbProjectManager` (DB-backed) are collapsed. `DbProjectManager` becomes the sole runtime manager. `projects.json` is demoted to import-seed / export artifact only. `import_from_json()` and `export_to_json()` are added as static helpers to `DbProjectManager`. No production call site may pass the JSON-backed manager as `manager=`.

### Shared retry helper location: `repositories/base.py`

The `_commit_with_retry` / `_is_locked` pattern from `execution.py:33–69` is generalized into `repositories/base.py:retry_on_locked`. P1 applies a local copy to `SqliteProjectRepository._flush_to_db`; P2 (T2-001) extracts it to the shared location and P2 (T2-002) replaces P1's local copy with the shared helper.

### P4 scope boundary (destructive reclaim is NOT here)

P4 owns: activating `RETENTION_PRUNE_ENABLED` flag + VACUUM runbook validated on snapshot. P4 does NOT own: `session_logs` drop, `telemetry_events` bounding — those belong to `ccdash-enterprise-liveness-storage-v1`.

---

## Active Gotchas

### Dual-manager grep before collapse (T1-004, T1-007)

Before retiring the JSON-backed `ProjectManager` instantiation at `project_manager.py:658`, grep all production call sites for `manager=` argument. Some callers may pass the JSON-backed manager explicitly. Any remaining caller that passes the JSON manager in a non-test context must be migrated first; annotate test-only overrides with a comment.

### P4 VACUUM — NEVER on live DB without Opus go/no-go (T4-003)

The live DB has `freelist_count=543,926` (2.23 GB). Running VACUUM on an 11 GB DB with an improperly configured WAL may lock for minutes. The runbook must be validated on a snapshot copy first. Opus (not sonnet) issues the go/no-go decision; record it in `phase-4-progress.md` before T4-004 or T4-006 executes.

---

## Document Pointers

| Document | Path |
|----------|------|
| PRD | `docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md` |
| Implementation Plan | `docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md` |
| Phase 1 progress | `.claude/progress/ccdash-db-design-remediation/phase-1-progress.md` |
| Phase 2 progress | `.claude/progress/ccdash-db-design-remediation/phase-2-progress.md` |
| Phase 3 progress | `.claude/progress/ccdash-db-design-remediation/phase-3-progress.md` |
| Phase 4 progress | `.claude/progress/ccdash-db-design-remediation/phase-4-progress.md` |
| Phase 5 progress | `.claude/progress/ccdash-db-design-remediation/phase-5-progress.md` |
| Decisions block | `.claude/worknotes/ccdash-db-design-remediation/decisions-block.md` |
| SPIKE findings | `docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md` |
| SPIKE charter | `docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md` |
| ADR-006 | `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md` |
| ADR-007 | `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md` |
| Liveness PRD (owns destructive storage) | `docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md` |
| Lazy findings doc (create on first P3 drift) | `.claude/findings/ccdash-db-design-remediation-findings.md` |
| VACUUM runbook (created in P4) | `docs/guides/db-vacuum-runbook.md` |
| AAR (created in P5) | `.claude/worknotes/ccdash-db-design-remediation/aar.md` |

---

## Agent Handoff Notes

> Fill in as phases complete.

---

## Phase 1 Exit Findings (2026-06-03)

### Findings Remediated

- **F-01** (silent flush): `_flush_snapshot_to_db` now re-raises on exception; `_snapshot_loaded` stays `False` on failure so next access retries. Commit `4ef37ac`.
- **F-02** (dual-manager): Legacy `ProjectManager` demoted to compat-alias only; `db_project_manager` is the sole runtime registry. All production routers (`features.py`, `integrations.py`, `test_visualizer.py`) and scripts (`agentic_intelligence_rollout.py`, `telemetry_backfill.py`) redirected to `db_project_manager`. Commit `7d04401` (approx; see T1-004/T1-007 changes).
- **F-10** (dead `config.DB_PATH` default `.ccdash.db`): Consolidated — `db/connection.py` now derives from `config.DB_PATH`. Commit `3254722`.
- Smoke verification: 5 projects on cold DB (bootstrap from `projects.json` → flush to `projects` table); registry-before-sync log ordering confirmed by `RuntimeContainer._bootstrap_registry` placement ahead of `_build_sync_engine()` call.

### Deferred to P2

- **Generalize `_commit_with_retry`**: A local copy of the retry helper lives in `db/repositories/projects.py`. P2 (T2-001) extracts it to `repositories/base.py:retry_on_locked`; P2 (T2-002) replaces the local copy with the shared helper.
- **Demoted legacy `ProjectManager` read-only / lazy**: The legacy `ProjectManager` instance (`project_manager` global) still calls `_load()` at import time, which can write a default `projects.json` if none exists (karen G2 flag). Tracked for P2: make `ProjectManager` truly read-only or suppress the side-effecting `_load()` call on the compat instance.

### Pre-existing, Out of Scope

- **`session_messages` UNIQUE-constraint `IntegrityError`** during watcher-triggered incremental sync — observed in T1-010 smoke logs; intermittent, not registry-related. File as a separate bug (`db/sync_engine.py` watcher path).
- **`backend/tests/test_runtime_bootstrap.py` + `test_sse_wire_boundary.py` hang at import** — UE-state unkillable processes; environment-wide issue that predates Phase 1. These test files must never be collected by pytest (see CLAUDE.md warning). Not addressed in this phase.
