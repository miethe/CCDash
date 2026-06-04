---
title: "ADR-006: Project Registry Authority Model — DB-Authoritative, JSON Import/Export-Only"
type: "adr"
status: "accepted"
created: "2026-06-03"
parent_prd: "docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md"
depends_on_spike: "docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md"
tags: ["adr", "database", "registry", "sqlite", "persistence", "multi-process", "project-management"]
---

# ADR-006: Project Registry Authority Model — DB-Authoritative, JSON Import/Export-Only

## Status

**Accepted** — Ratified by operator 2026-06-03 following audit and findings review (see Finding F-02, RQ3).

## Context

CCDash maintains a registry of projects (metadata, paths, active selection) that must be consistent across multiple processes (api server + background worker) and, in the enterprise case, across replicas. The registry currently has two independent storage layers with no reconciliation:

1. **JSON file** (`projects.json`): Atomic writeback via `ProjectManager` (sync, file-based); the original single source of truth
2. **SQLite `projects` table**: Intended as authoritative per the enterprise-liveness PRD intent ("DB-backed registry so persistence survives restarts"); writes via `DbProjectManager` (async) with **no JSON writeback**

**Current behavior (Finding F-02):**
- Both managers are instantiated at import time (`backend/project_manager.py:658`, `:663`)
- They are coincidentally in sync today (both list 5 ids) only because the DB was hand-populated to match JSON on 2026-06-03
- No code enforces reconciliation
- UI-added projects via the DB path never persist to JSON
- A table wipe loses DB-only projects because bootstrap re-reads stale JSON
- Fallback logic in `build_workspace_registry` (`runtime_ports.py:134-136`) creates silent ambiguity about which store is canonical

The registry is small (typically <100 rows), rarely written (admin ops: add/remove/select project), and must be consistent across process boundaries — properties a shared DB can provide and a per-process JSON file cannot.

## Decision

**The database (`projects` table) is the authoritative store. JSON becomes an import/seed artifact and an export target, never a live runtime store.**

**Ratification (2026-06-03)**: Option B was implemented and shipped in Phase 1 (P1) of the ccdash-db-design-remediation plan, including dual-manager collapse, DB-authoritative registry, and projects.json reduced to import-seed/export-only (see `backend/project_manager.py`, `backend/db/repositories/projects.py`).

### Implementation Requirements

1. **Single manager**: Retire or demote the legacy `ProjectManager` (JSON-only sync manager instantiated at `:658`). It becomes available as an optional `import_from_json()` helper, not an active registry writer.

2. **Bootstrap must be reliable**: The DB write **must not fail silently**:
   - On flush exception, do **not** set `_snapshot_loaded=True` 
   - Log ERROR with the locked reason
   - Retry with backoff on next access (see Finding F-01 remediation and ADR-007)
   - Sequence bootstrap outside the heavy startup-sync window to reduce contention (lazy-on-first-request or pre-sync)

3. **Export capability**: Provide an explicit `export_to_json()` method for:
   - Portability across deployments
   - Backup/escape-hatch operations
   - Integration with external tooling expecting `projects.json`

4. **Config semantics**: `CCDASH_PROJECTS_FILE` (env var, `config.py:PROJECTS_FILE`) becomes the import-seed source only, not a live write target.

## Decision Drivers

1. **Multi-process consistency**: A JSON file per process cannot represent shared state; the DB is the natural integration point for api + worker processes
2. **Replica readiness**: Enterprise deployments with replicated database have a single source of truth; JSON per-machine would fragment state
3. **Small, rarely-written schema**: Registry writes are administrative (add/remove projects), not transactional volume; DB overhead is negligible, consistency gain is large
4. **Existing intent**: The enterprise-liveness PRD and `build_workspace_registry` comments already state "DB authoritative"
5. **Escape hatch**: `export_to_json()` preserves the portability benefit of the original JSON-only design

## Alternatives Considered

### Option A: JSON Authoritative, DB Derived (Write-Through Cache)

Keep JSON as the primary store. Both managers remain instantiated; `ProjectManager` owns writes; `DbProjectManager` reads and caches.

**Advantages:**
- Preserves the original single-file portability
- No bootstrap sequencing required

**Disadvantages:**
- Per-process JSON file is fundamentally inconsistent across api+worker boundaries; would require distributed consensus or frequent re-syncs to maintain consistency
- Conflicts with the stated enterprise multi-replica direction (replica clusters share a DB, not per-machine JSON)
- Does not fix the dual-manager reconciliation gap (F-02) — just shifts which manager owns writes
- Adds write-through synchronization complexity without solving the multi-process problem

**Rejected:** Keeps the per-process-file consistency problem and does not scale to replicas.

### Option C: Status Quo (Dual Managers, No Reconciliation)

Maintain the current design: both managers active, no guaranteed consistency, manual recovery on divergence.

**Advantages:**
- No code changes required

**Disadvantages:**
- Silent split-brain (F-02): UI-added projects via DB vanish if JSON is re-read
- Violates documented intent (liveness PRD §4 states "DB authoritative")
- Undetectable until a table wipe or process restart exposes the divergence
- No path to enterprise multi-replica consistency

**Rejected:** Fundamental correctness defect; blocks enterprise readiness.

## Consequences

### Positive

- **Single source of truth**: All processes and replicas read/write the same `projects` table; no reconciliation logic needed
- **Consistent add/remove**: New projects via UI or CLI immediately visible to all processes
- **Enterprise-ready**: Replicas automatically share state via shared database
- **Reversibility**: `export_to_json()` provides an always-available escape hatch for portability or manual recovery

### Negative

- **Bootstrap ordering**: Registry bootstrap must be sequenced to avoid contention with the sync engine during startup (P0-3 in the remediation backlog)
- **Retry logic required**: The DB write is on the critical path; must implement locked-retry and backoff (ADR-007 standard applies)
- **No offline-first**: A replica without DB access cannot bootstrap from local JSON alone; import must be explicit

### Risks

- **Bootstrap failure blocks startup**: If registry flush fails and is not retried, the app starts with stale/missing projects. Mitigate: fail-loud (F-01 remediation) + /api/health surfacing (F-09).
- **Contention during startup**: The registry writer and sync engine both acquire the SQLite write-lock; may deadlock or timeout if not sequenced. Mitigate: lazy-on-first-request or pre-sync ordering (P0-3).

## Related Decisions and Dependencies

- **ADR-007** defines the DB-write failure-surfacing standard that the registry writer must follow (shared locked-retry helper, Prometheus counter, health field exposure)
- **F-01 Remediation** (P0-1 through P0-3) details the bootstrap sequencing and retry logic that makes Option B safe
- **Enterprise-Liveness PRD §4/§8** documents the original intent ("DB authoritative") which this ADR formalizes
- **Migration governance** (`backend/db/migration_governance.py`, test_migration_governance.py) ensures the `projects` table schema is maintained in lockstep across SQLite and Postgres

## Implementation Checklist

- [ ] Ratify ADR-007 (DB-write failure surfacing standard)
- [ ] Implement P0-1: registry bootstrap fails loud (do not set `_snapshot_loaded=True` on exception)
- [ ] Implement P0-2: shared locked-retry helper in `repositories/base.py`; apply to registry sync writer
- [ ] Implement P0-3: sequence registry bootstrap outside the startup sync window
- [ ] Implement P0-4: retire or demote `ProjectManager`; add `export_to_json()` method; remove dual instantiation
- [ ] Implement P0-5: registry persistence test hardening (direct count + lock-injection)
- [ ] Implement P3-1: expose registry health fields in `/api/health/detail`
