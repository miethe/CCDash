# CCDash DB Caching Layer V1 Execution Checklist

Updated: 2026-03-27
Status: Ready for phased execution
Source plan: `docs/project_plans/implementation_plans/db-caching-layer-v1.md`

## Objective

Execute the remaining data-platform work after the cache/sync baseline and hexagonal foundation landed.

This checklist is for:

- finishing storage composition migration
- defining explicit `local` vs `enterprise` storage profiles
- laying session canonical-storage groundwork
- adding governance, verification, and rollout guardrails

This checklist is not for rebuilding the original cache layer from scratch.

## Related Plan Sequencing

Use this checklist as the execution bridge across the related architecture and data plans.

### Plan Status Snapshot

| Plan | Current Status | Execution Readiness | How To Use It |
|---|---|---|---|
| `ccdash-hexagonal-foundation-v1` | Completed | Baseline only | Treat as already-landed architecture context and guardrail source |
| `db-caching-layer-v1` | Updated implementation plan | Ready now | Execute this checklist directly |
| `deployment-runtime-modularization-v1` | Pending PRD, no implementation plan | Partial | Execute only the parts already covered by current runtime code or by this checklist; create a dedicated implementation plan before larger platform rollout |
| `data-platform-modularization-v1` | Pending PRD, no implementation plan | Partial | Use as architecture target while executing Phases 1-2 here; create a dedicated implementation plan before auth/audit or broader hosted data changes |
| `session-intelligence-canonical-storage-v1` | Draft PRD | Not ready for full execution | Use Phase 3 here as prerequisite groundwork; do not begin full product delivery until a dedicated implementation plan exists |

### Cross-Plan Dependency Rules

Follow these rules when moving from one plan to the next:

1. Treat the hexagonal foundation as complete enough to build on, but assume cleanup remains where routers still use direct DB and project-manager access.
2. Execute this checklist first for the storage and cache boundary work that the later plans depend on.
3. Do not start full deployment-runtime work beyond current scope until the storage-profile model is explicitly decided in Phase 2.
4. Do not start full session-intelligence implementation until Phase 3 here is complete and a dedicated implementation plan is written.
5. Treat data-platform modularization as the architectural umbrella for Phases 1-4 here, not as a separate immediate coding stream.

## What Executes Now Vs Later

### Execute Now

These are ready to execute immediately from this checklist:

- [ ] Use Phase 1 to finish the storage-composition and router/workspace migration left over after the foundation refactor.
- [ ] Use Phase 2 to decide and document the local-vs-enterprise storage profile model.
- [ ] Use Phase 3 only for groundwork and additive seams, not the full session-intelligence feature set.
- [ ] Use Phase 4 to lock in governance, health reporting, and rollout documentation.

### Needs Further Planning First

These should not start as open-ended implementation work yet:

- [ ] Full `deployment-runtime-modularization-v1` execution beyond the already-landed runtime split.
  Needed first:
  - a dedicated implementation plan reflecting current runtime code
  - a decision on enterprise deployment posture and storage profile contract from Phase 2

- [ ] Full `data-platform-modularization-v1` execution.
  Needed first:
  - a dedicated implementation plan
  - the Phase 2 data-domain ownership matrix
  - an explicit decision on shared Postgres with SkillMeat vs CCDash-owned Postgres

- [ ] Full `session-intelligence-canonical-storage-v1` execution.
  Needed first:
  - completion of Phase 3 in this checklist
  - a dedicated implementation plan for canonical transcript storage, embeddings, churn analytics, and scope-drift analytics
  - a product decision on what remains local-cache-only vs enterprise-canonical

## Cross-Plan Follow-On Order

Use this as the higher-level program sequence:

1. Complete `db-caching-layer-v1` Phase 1.
   Outcome:
   - storage composition cleanup
   - router/workspace migration materially advanced

2. Complete `db-caching-layer-v1` Phase 2.
   Outcome:
   - explicit local-vs-enterprise storage model
   - shared-instance posture with SkillMeat decided

3. Create a dedicated implementation plan for `data-platform-modularization-v1`.
   Required because:
   - the PRD is still pending
   - Phase 2 decisions must be translated into concrete schema, ownership, and governance tasks

4. Execute `db-caching-layer-v1` Phase 3 in parallel with the early, non-disruptive part of the data-platform implementation plan.
   Constraint:
   - only additive groundwork is allowed here

5. Create a dedicated implementation plan for `deployment-runtime-modularization-v1` if broader hosted rollout is still needed after current runtime work.
   Required because:
   - the PRD is still pending
   - the original current-state section is partially stale relative to the codebase

6. Execute `db-caching-layer-v1` Phase 4 and the relevant deployment/data-platform rollout tasks together.
   Outcome:
   - supported operator model
   - health and governance guardrails

7. Create the implementation plan for `session-intelligence-canonical-storage-v1`.
   Prerequisites:
   - Phase 3 complete
   - storage-profile model settled
   - canonical transcript seams defined

8. Execute `session-intelligence-canonical-storage-v1` after the above prerequisites are met.

## Planning Deliverables To Create Next

When this checklist reaches the indicated gate, create the following planning artifacts:

- [ ] After Phase 2: implementation plan for `data-platform-modularization-v1`
- [ ] After Phase 2 or alongside Phase 4: refreshed implementation plan for `deployment-runtime-modularization-v1` if hosted rollout remains in scope
- [ ] After Phase 3: implementation plan for `session-intelligence-canonical-storage-v1`

## Fixed Assumptions

- `local` remains first-class and defaults to SQLite plus filesystem-derived ingestion.
- `enterprise` is Postgres-first and must not be treated as optional parity.
- A shared Postgres deployment with SkillMeat is allowed only with explicit schema or tenant isolation.
- Existing REST contracts should stay stable unless a task explicitly documents an additive change.
- Runtime/container composition is the correct control point for adapter selection, not `isinstance` checks inside repository factories.

## Baseline Already Landed

Verify these are present before starting implementation work:

- [ ] Runtime profiles exist for `local`, `api`, `worker`, and `test`.
- [ ] Runtime container bootstraps DB, ports, sync engine, and jobs.
- [ ] SQLite and Postgres migrations/repositories exist.
- [ ] Cache status and sync APIs exist.
- [ ] Frontend data shell is already split into session/runtime/entity/client layers.

If any of these regress, stop and repair the baseline before starting later phases.

## Phase 1: Complete Storage Composition Migration

Goal: finish the migration away from direct router-level DB and workspace singleton usage.

### Tasks

- [ ] `DB-P1-01` Replace compatibility storage wiring.
  Acceptance:
  - runtime composition can choose storage adapters explicitly
  - dependence on `FactoryStorageUnitOfWork` is reduced or removed for migrated flows
  - repository selection no longer depends on connection-type inspection in migrated paths

- [ ] `DB-P1-02` Finish router migration.
  Acceptance:
  - targeted routers no longer import `backend.db.connection`, `backend.db.factory`, or `backend.project_manager` directly
  - sessions, documents, analytics, projects, cache, and remaining read-heavy paths use injected ports/services where appropriate
  - HTTP handlers primarily map requests and responses

- [ ] `DB-P1-03` Tighten architecture guardrails.
  Acceptance:
  - tests or lint checks fail when migrated routers regress to direct singleton DB imports
  - existing architecture-boundary tests are extended to the newly migrated routers

- [ ] `DB-P1-04` Normalize workspace resolution.
  Acceptance:
  - migrated request paths resolve project/workspace scope through the workspace registry
  - direct `project_manager` reads are removed from migrated request paths

### Phase Gate

- [ ] Phase 1 complete.
  Exit criteria:
  - router composition is materially cleaner than today
  - remaining compatibility shims are explicitly documented
  - local and Postgres-backed migrated flows still pass smoke coverage

## Phase 2: Define Local Vs Enterprise Storage Profiles

Goal: turn backend selection into an explicit deployment/storage model.

### Tasks

- [ ] `DB-P2-01` Create a data-domain ownership matrix.
  Acceptance:
  - every major table group is classified as one of: derived cache, canonical app state, integration snapshot, operational/job metadata, or future auth/audit data
  - the matrix identifies what stays local-cache-friendly vs what should become canonical in enterprise mode

- [ ] `DB-P2-02` Define the enterprise profile contract.
  Acceptance:
  - enterprise mode supports CCDash-owned Postgres and shared Postgres with SkillMeat
  - shared-instance rules define schema or tenant isolation explicitly
  - no implicit cross-app table coupling is allowed

- [ ] `DB-P2-03` Split adapter responsibilities cleanly.
  Acceptance:
  - filesystem watch/sync is treated as a local or ingestion adapter concern
  - hosted API runtime does not assume local filesystem watch behavior
  - worker responsibilities are documented for enterprise mode

- [ ] `DB-P2-04` Define deployment selection behavior.
  Acceptance:
  - `local` vs `enterprise` selection maps coherently to runtime profile and storage profile
  - compatibility env vars are documented as implementation details rather than architecture
  - operator-facing configuration expectations are captured

### Phase Gate

- [ ] Phase 2 complete.
  Exit criteria:
  - the team has an agreed storage-profile model
  - CCDash-owned Postgres vs shared Postgres is explicitly decided and documented
  - cache vs canonical boundaries are clear enough to start schema work safely

## Phase 3: Session Storage Modernization Groundwork

Goal: create additive seams for future canonical session intelligence without breaking current behavior.

### Tasks

- [ ] `DB-P3-01` Introduce canonical transcript seams.
  Acceptance:
  - repository or service contracts exist for message-level session storage
  - current session APIs do not need to know whether data comes from cache-oriented logs or future canonical tables

- [ ] `DB-P3-02` Stabilize provenance and lineage storage.
  Acceptance:
  - transcript ordering, source provenance, root session lineage, and conversation-family identifiers are consistently stored
  - both local and Postgres-backed modes preserve the same identity semantics

- [ ] `DB-P3-03` Prepare Postgres-ready canonical tables.
  Acceptance:
  - additive schema path is defined for `session_messages`
  - extension path is documented for embeddings, churn facts, and scope-drift facts
  - local SQLite mode remains functional without requiring canonical enterprise tables

- [ ] `DB-P3-04` Preserve compatibility read models.
  Acceptance:
  - existing session detail APIs remain stable
  - any compatibility projections from canonical tables back into current DTOs are documented

### Phase Gate

- [ ] Phase 3 complete.
  Exit criteria:
  - session intelligence work can begin without reopening storage fundamentals
  - local mode still works as a cache-oriented experience
  - enterprise mode has a credible path to canonical transcript storage

## Phase 4: Governance, Verification, and Rollout

Goal: make the storage model safe to operate and evolve.

### Tasks

- [ ] `DB-P4-01` Build the storage-profile test matrix.
  Acceptance:
  - local SQLite, dedicated Postgres enterprise, and shared-instance enterprise compositions are covered
  - test expectations identify supported differences, not just parity assumptions

- [ ] `DB-P4-02` Add migration governance.
  Acceptance:
  - schema-capability checks exist for supported backends
  - migration parity risks are documented and tested where required

- [ ] `DB-P4-03` Improve runtime health reporting.
  Acceptance:
  - API and worker modes expose runtime/storage capability health clearly
  - operators can tell whether watch, sync, jobs, and enterprise storage dependencies are healthy

- [ ] `DB-P4-04` Refresh documentation.
  Acceptance:
  - setup and deployment docs describe local vs enterprise storage selection
  - docs cover CCDash-owned Postgres and shared-instance posture
  - docs call out what remains local-only, cache-derived, or enterprise-canonical

### Phase Gate

- [ ] Phase 4 complete.
  Exit criteria:
  - the supported operating model is documented
  - storage profile behavior is testable
  - rollout risks are visible before broader enterprise adoption

## Recommended Execution Order

1. Finish Phase 1 before touching canonical enterprise schema design.
2. Complete the Phase 2 storage-profile decision before making irreversible enterprise-schema choices.
3. Start Phase 3 only after cache vs canonical ownership is agreed.
4. Use Phase 4 to lock in governance before expanding enterprise rollout.

## Explicit Out Of Scope For This Checklist

- Full RBAC and SSO delivery
- Final auth schema design beyond the storage seams needed now
- Warehouse or OLAP redesign
- Removal of SQLite local-first support
- Full implementation of semantic search, DX sentiment, or SkillMeat write-back

Those items belong to the related platform and session-intelligence plans after this groundwork is in place.
