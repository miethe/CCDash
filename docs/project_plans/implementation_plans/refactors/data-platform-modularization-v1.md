---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: in_progress
category: refactors
title: 'Implementation Plan: Data Platform Modularization V1'
description: Turn CCDash's new storage-profile contract into real local and enterprise
  storage composition, explicit data-domain ownership, and migration governance that
  supports auth-era hosted deployment.
summary: Replace factory-backed backend selection with explicit storage adapters,
  classify canonical versus derived data domains, add identity and audit foundations,
  and harden SQLite/Postgres governance for local-first and enterprise profiles.
author: codex
audience:
- ai-agents
- developers
- platform-engineering
- backend-platform
created: 2026-03-27
updated: '2026-03-28'
tags:
- implementation
- data-platform
- storage
- sqlite
- postgres
- migrations
- refactor
priority: high
risk_level: high
complexity: high
track: Data
timeline_estimate: 4-6 weeks across 6 phases
feature_slug: data-platform-modularization-v1
feature_family: ccdash-data-platform
feature_version: v1
lineage_family: ccdash-data-platform
lineage_parent:
  ref: docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: refactor
linked_features: []
related_documents:
- docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md
- docs/project_plans/implementation_plans/refactors/ccdash-hexagonal-foundation-v1.md
- docs/project_plans/implementation_plans/db-caching-layer-v1.md
- docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
- docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md
- docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md
context_files:
- backend/config.py
- backend/runtime/container.py
- backend/runtime_ports.py
- backend/application/ports/core.py
- backend/adapters/storage/local.py
- backend/db/connection.py
- backend/db/factory.py
- backend/db/migrations.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/sync_engine.py
- backend/verify_db_layer.py
---

# Implementation Plan: Data Platform Modularization V1

## Objective

Turn CCDash's storage-profile contract from configuration-level intent into real platform behavior. Local SQLite must remain the default local-first posture, while enterprise Postgres becomes a first-class canonical store with explicit domain ownership, tenancy-ready schema decisions, and migration governance that downstream auth and session-storage work can build on safely.

## Current Baseline

The plan starts from a partially modernized backend, not a greenfield rewrite:

1. Runtime profiles (`local`, `api`, `worker`, `test`) and operator-facing storage-profile config already exist.
2. `RuntimeContainer` already publishes storage-profile metadata such as `storageProfile`, `storageSchema`, and `canonicalSessionStore`.
3. `build_core_ports()` still resolves storage through `FactoryStorageUnitOfWork`, which delegates repository choice back to `backend/db/factory.py`.
4. SQLite and Postgres migrations still live in separate modules and are kept in parity mostly by convention.
5. The sync/cache substrate is strong, but cache state, canonical app state, integration snapshots, telemetry queues, and future auth/audit data are still not governed as explicit domains.

This plan therefore focuses on finishing the architectural shift that the hexagonal foundation and cache work began.

## Scope And Fixed Decisions

In scope:

1. Replace compatibility-style storage selection with explicit local and enterprise storage composition.
2. Define the ownership model for canonical app data, derived cache data, integration snapshots, operational/job state, and audit/security records.
3. Add the schema and repository foundation for principals, memberships, role bindings, and privileged-action audit records.
4. Introduce migration governance and verification for supported storage profiles and isolation modes.
5. Refactor filesystem sync assumptions so enterprise API runtime no longer depends on local-ingestion behavior.

Out of scope:

1. A full ORM rewrite or vendor expansion beyond SQLite and Postgres.
2. Shipping complete RBAC and SSO behavior.
3. Delivering canonical enterprise session intelligence beyond the seams needed for the follow-on PRD.
4. Moving every existing repository to a brand-new package layout in one pass.

Non-negotiables:

1. Local SQLite plus filesystem-derived workflows remain supported and low-friction.
2. Enterprise Postgres is treated as the authoritative hosted posture, not an optional parity backend.
3. Adapter choice happens at composition time, not through connection-type inspection in request code.
4. Every persisted concern is classified as canonical, derived cache, integration snapshot, operational/job, or audit/security data.
5. The result must unblock shared auth/RBAC and canonical session-storage follow-on plans without reopening storage fundamentals.

## Target Platform Shape

### Storage Profiles

| Profile | Primary Store | Canonical Data Posture | Filesystem Role | Notes |
|------|-------|------------------------|-----------------|-------|
| Local | SQLite | Canonical for local app metadata; filesystem remains acceptable source of truth for derived artifacts | Primary ingestion source | Portable, zero-config, single-user-first |
| Enterprise | Postgres | Canonical for hosted app, identity, membership, audit, and operational state | Optional ingestion adapter | Shared deployment target |
| Enterprise (shared instance) | Postgres with schema or tenant isolation | Same as enterprise, but with explicit CCDash isolation contract | Optional ingestion adapter | Must be safe when co-located with SkillMeat |

### Data Domain Ownership

| Domain | Examples | Default Owner | Durability |
|------|----------|---------------|------------|
| Identity and access | principals, memberships, role bindings | Enterprise Postgres | Canonical |
| Workspace and project metadata | project/workspace records, settings, source bindings | Local SQLite or Enterprise Postgres by profile | Canonical |
| Observed product entities | sessions, documents, tasks, features, links | Local SQLite cache in local mode; Postgres in enterprise mode as platform evolves | Mixed |
| Ingestion and cache state | sync state, parser checkpoints, filesystem fingerprints | Profile-specific storage adapter | Derived |
| Integration snapshots | SkillMeat definitions, external refresh metadata | Profile-specific storage adapter | Refreshable |
| Operational and job data | telemetry queue, background job checkpoints, reconciliation state | Enterprise Postgres preferred; local adapter allowed for local mode | Operational |
| Audit and security records | privileged actions, access decisions, membership changes | Enterprise Postgres | Canonical |

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Storage Profile Capability Contract | 8 pts | 3-4 days | Yes | Freeze profile semantics, supported combinations, and domain ownership rules |
| 2 | Adapter Composition and Unit-of-Work Split | 10 pts | 4-5 days | Yes | Replace factory-backed selection with explicit local and enterprise storage adapters |
| 3 | Domain Ownership and Schema Layout | 10 pts | 4-5 days | Yes | Classify existing data and define domain-specific schema boundaries |
| 4 | Identity, Membership, and Audit Foundation | 12 pts | 1 week | Yes | Add auth-era canonical storage foundations for enterprise mode |
| 5 | Migration Governance and Sync Boundary Refactor | 10 pts | 4-5 days | Yes | Make migration parity and ingestion behavior explicit and testable |
| 6 | Rollout, Validation, and Handoff | 8 pts | 3-4 days | Final gate | Land upgrade paths, observability, and stable seams for follow-on plans |

**Total**: ~58 story points over 4-6 weeks

## Implementation Strategy

### Critical Path

1. Freeze the storage-profile capability matrix before changing adapters.
2. Split storage composition away from `FactoryStorageUnitOfWork` before reorganizing domains.
3. Define domain ownership and schema boundaries before adding auth-era tables.
4. Land migration governance and sync-boundary changes before enterprise rollout decisions.
5. Finish with upgrade validation, observability, and handoff to dependent plans.

### Parallel Work Opportunities

1. Phase 4 schema design can start once Phase 3 defines domain boundaries and tenancy keys.
2. Phase 5 migration-governance work can begin once Phase 2 makes storage composition explicit.
3. Documentation and capability-matrix tests can land incrementally after each phase rather than waiting for the end.

### Migration Order

1. Composition-root storage adapter split
2. Data-domain matrix and schema grouping
3. Enterprise identity/audit canonical tables
4. Filesystem ingestion and sync boundary cleanup
5. Upgrade, verification, and dependent-plan handoff

## Phase 1: Storage Profile Capability Contract

**Assigned Subagent(s)**: backend-architect, data-layer-expert

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DPM-001 | Capability Matrix | Define a concrete capability matrix for `local`, `enterprise`, and shared-enterprise modes covering canonical stores, ingestion sources, supported isolation modes, and required guarantees. | Storage profile behavior is documented in code/docs with no remaining ambiguity about canonical ownership or supported combinations. | 3 pts | backend-architect, data-layer-expert | None |
| DPM-002 | Runtime-to-Storage Mapping | Define which runtime profiles may pair with which storage profiles and what each pairing implies for sync, jobs, auth, and integrations. | `local`, `api`, `worker`, and `test` pairings are explicit and invalid combinations are rejected early. | 2 pts | backend-architect | DPM-001 |
| DPM-003 | Domain Ownership Matrix | Freeze the domain classification for existing persisted concerns, including current tables and future auth/audit records. | Every known persisted concern is mapped to a domain, durability class, and target profile owner. | 3 pts | data-layer-expert | DPM-001 |

**Phase 1 Quality Gates**

1. Storage profiles are defined by capability and ownership, not by environment variables alone.
2. Runtime/storage combinations are explicit enough for bootstrap validation and docs.
3. Canonical versus derived domains are stable enough that downstream schema work does not reopen the model.

## Phase 2: Adapter Composition and Unit-of-Work Split

**Assigned Subagent(s)**: backend-architect, python-backend-engineer, data-layer-expert

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DPM-101 | Explicit Storage Adapters | Introduce explicit local and enterprise `StorageUnitOfWork` adapters that implement the existing port contract without delegating selection through `backend/db/factory.py`. | `CorePorts.storage` is composed from profile-aware adapters rather than the factory compatibility shell. | 4 pts | data-layer-expert, python-backend-engineer | DPM-002 |
| DPM-102 | Composition Root Wiring | Update `backend/runtime_ports.py` and related bootstraps so storage selection happens once in the runtime composition layer. | Runtime composition chooses storage adapters without leaking connection-type checks into routers or services. | 3 pts | backend-architect, python-backend-engineer | DPM-101 |
| DPM-103 | Compatibility Sunset Plan | Reduce `FactoryStorageUnitOfWork` and `backend/db/factory.py` to a transitional internal bridge or remove them where no longer needed. | Remaining factory usage is isolated, documented, and no longer the architectural control point. | 3 pts | backend-architect, data-layer-expert | DPM-102 |

**Phase 2 Quality Gates**

1. Storage adapter selection is profile-aware and composition-driven.
2. Router and service code do not depend on connection-type inspection for repository choice.
3. The compatibility path, if temporarily retained, is clearly bounded and scheduled for removal.

## Phase 3: Domain Ownership and Schema Layout

**Assigned Subagent(s)**: data-layer-expert, backend-architect

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DPM-201 | Table and Repository Classification | Audit current tables and repositories, then classify them by domain, canonical owner, and profile-specific behavior. | Existing SQLite and Postgres structures are mapped into the approved domain matrix with no uncategorized tables. | 3 pts | data-layer-expert | DPM-003 |
| DPM-202 | Schema Boundary Design | Define how Postgres schemas or table groups separate identity/access, canonical app data, integration snapshots, operational state, and audit records; document the SQLite-local equivalent where physical separation is limited. | Schema grouping and isolation rules are concrete enough to guide migrations and repository ownership. | 4 pts | data-layer-expert, backend-architect | DPM-201 |
| DPM-203 | Repository Ownership Realignment | Update repository/module ownership so domain responsibilities are explicit and future auth/session work does not land in cache-only abstractions. | Repository boundaries line up with domain ownership rather than one broad cache layer. | 3 pts | backend-architect | DPM-202 |

**Phase 3 Quality Gates**

1. Every persisted concern has a domain owner and target store.
2. Postgres isolation strategy is explicit for dedicated and shared-instance deployments.
3. Repository ownership no longer assumes one undifferentiated persistence layer.

## Phase 4: Identity, Membership, and Audit Foundation

**Assigned Subagent(s)**: data-layer-expert, python-backend-engineer, backend-architect

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DPM-301 | Principal and Membership Schema | Add canonical enterprise schema support for principals, memberships, role bindings, and scope identifiers that align to the shared-auth PRD. | Enterprise Postgres has a stable home for identity and membership data with clear keys and ownership. | 4 pts | data-layer-expert | DPM-202 |
| DPM-302 | Audit Record Foundation | Add storage for privileged-action audit records, including actor, scope, action, decision/result, and timestamp semantics. | Hosted mode can persist privileged-action audit data without mixing it into legacy cache tables. | 4 pts | data-layer-expert, python-backend-engineer | DPM-301 |
| DPM-303 | Tenancy and Scope Contract | Define how enterprise, team, workspace, and project scopes map into the new storage model and request context. | Scope and tenancy keys are stable enough for downstream auth enforcement and multi-user work. | 4 pts | backend-architect, python-backend-engineer | DPM-301 |

**Phase 4 Quality Gates**

1. Identity and audit data have a canonical hosted home.
2. Tenancy and scope keys are explicit enough for follow-on RBAC work.
3. Local mode preserves a bounded compatibility story without pretending to be equivalent to enterprise auth storage.

## Phase 5: Migration Governance and Sync Boundary Refactor

**Assigned Subagent(s)**: data-layer-expert, python-backend-engineer, qa-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DPM-401 | Migration Governance Manifest | Add shared migration metadata, capability tables, or verification hooks that make SQLite/Postgres support explicit instead of parity-by-convention. | Supported schema features and backend exceptions are machine-checkable and documented. | 3 pts | data-layer-expert | DPM-203 |
| DPM-402 | Verification Matrix | Expand `backend/verify_db_layer.py` and automated tests to validate local SQLite, dedicated enterprise Postgres, and shared-instance enterprise posture. | Storage profile verification covers supported profiles and fails clearly on drift or unsupported combinations. | 3 pts | qa-engineer, python-backend-engineer | DPM-401 |
| DPM-403 | Filesystem Ingestion Boundary | Refactor sync and ingestion assumptions so `backend/db/sync_engine.py` is an adapter capability, not a universal API runtime assumption. | Enterprise API runtime can boot cleanly without local-filesystem ingestion while local profile still supports current sync behavior. | 4 pts | python-backend-engineer, data-layer-expert | DPM-102 |

**Phase 5 Quality Gates**

1. Migration support and backend differences are explicit, not tribal knowledge.
2. Enterprise runtime no longer depends on local-filesystem assumptions.
3. Verification covers both profile behavior and schema-governance correctness.

## Phase 6: Rollout, Validation, and Handoff

**Assigned Subagent(s)**: qa-engineer, backend-architect, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DPM-501 | Local Upgrade Path | Define and validate the migration path for existing local SQLite users, including any backfill or compatibility requirements introduced by the new domain ownership model. | Existing local installs can upgrade without losing derived cache value or app metadata. | 3 pts | qa-engineer, data-layer-expert | DPM-402 |
| DPM-502 | Enterprise Bootstrap and Observability | Add bootstrap documentation and observability for schema selection, migration status, audit writes, and misconfigured storage-profile combinations. | Operators can tell which profile is active, which schema/isolation mode is in effect, and whether migrations/audit pipelines are healthy. | 3 pts | backend-architect, documentation-writer | DPM-402 |
| DPM-503 | Follow-on Plan Handoff | Document the stable seams and explicit assumptions for shared-auth/RBAC and session-intelligence canonical storage follow-on work. | Downstream implementation plans can begin without reopening storage-profile or domain-ownership decisions. | 2 pts | documentation-writer, backend-architect | DPM-302 |

**Phase 6 Quality Gates**

1. Local and enterprise rollout paths are documented and testable.
2. Operators and developers can inspect active storage posture and migration health.
3. Follow-on auth and session-storage plans inherit stable data-platform seams.

## Validation and Test Strategy

1. Add unit coverage for storage-profile resolution, runtime/storage pairing validation, and explicit adapter selection.
2. Add integration coverage for local SQLite, enterprise Postgres dedicated, and enterprise Postgres shared-schema modes.
3. Extend migration verification so schema drift, unsupported backend gaps, and profile-specific exceptions fail explicitly.
4. Add request/runtime tests proving enterprise API boot does not require local sync ingestion while local profile retains current behavior.
5. Add repository and migration coverage for principals, memberships, role bindings, and audit records.

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Storage-profile work stops at config semantics and does not remove factory-era coupling | High | Medium | Make explicit storage adapters and composition-root wiring a hard gate in Phase 2. |
| Domain ownership remains descriptive but not enforceable in code or migrations | High | Medium | Require table/repository classification and schema-boundary decisions before auth-era schema work begins. |
| Enterprise requirements erode the local-first workflow | High | Medium | Keep local SQLite and filesystem ingestion as a first-class profile with its own upgrade and verification path. |
| Identity and audit data leak into legacy cache abstractions | High | Medium | Give identity/access and audit records explicit hosted ownership and schema boundaries in Phase 4. |
| Separate SQLite/Postgres migrations continue to drift | High | High | Add migration manifest, backend capability table, and verification matrix as deliverables, not follow-up ideas. |

## Exit Criteria

This implementation plan is complete when:

1. Local and enterprise storage profiles are implemented through explicit storage adapters and composition-root selection.
2. Every persisted CCDash concern is assigned to a stable data domain with an explicit canonical or derived ownership model.
3. Enterprise Postgres provides a canonical home for principals, memberships, role bindings, and audit records.
4. Migration governance and verification make supported SQLite/Postgres behavior explicit and testable.
5. Enterprise API and worker runtimes no longer rely on local-filesystem sync assumptions, while local mode preserves current convenience behavior.
6. Shared auth/RBAC and session-intelligence follow-on plans can build on the platform without reopening storage-model fundamentals.
