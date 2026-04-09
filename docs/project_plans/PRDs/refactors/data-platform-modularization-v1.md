---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: research_prd
status: completed
category: refactors
title: "PRD: Data Platform Modularization V1"
description: "Evolve CCDash from a runtime-selected SQLite/Postgres cache implementation into a profile-aware data platform with explicit storage roles, stronger schema governance, and multi-user readiness."
summary: "Define how local SQLite, hosted Postgres, cache data, canonical app data, and auth-era tenancy concerns should fit together."
created: 2026-03-11
updated: 2026-04-07
commit_refs:
- https://github.com/miethe/CCDash/commit/a533799
- https://github.com/miethe/CCDash/commit/86f9ebc
- https://github.com/miethe/CCDash/commit/357b081
pr_refs:
  - https://github.com/miethe/CCDash/pull/21
  - https://github.com/miethe/CCDash/pull/22
priority: high
risk_level: high
complexity: High
track: Data
timeline_estimate: "4-6 weeks after foundation refactor"
feature_slug: data-platform-modularization-v1
feature_family: ccdash-data-platform
feature_version: v1
lineage_family: ccdash-data-platform
lineage_parent:
  ref: docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
  kind: prerequisite
lineage_children: []
lineage_type: refactor
problem_statement: "CCDash currently treats SQLite and Postgres as interchangeable through runtime factory dispatch, but hosted auth, tenancy, and operational reliability require a more explicit storage model and schema governance strategy."
owner: data-platform
owners: [data-platform, platform-engineering, backend-platform]
contributors: [ai-agents]
audience: [developers, data-platform, platform-engineering]
tags: [prd, data, sqlite, postgres, storage, migrations, tenancy]
related_documents:
  - docs/project_plans/implementation_plans/db-caching-layer-v1.md
  - docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md
  - docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
context_files:
  - backend/db/connection.py
  - backend/db/factory.py
  - backend/db/migrations.py
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - backend/db/sync_engine.py
  - backend/verify_db_layer.py
implementation_plan_ref: docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md
---

# PRD: Data Platform Modularization V1

## Executive Summary

CCDash’s current data layer is good enough for a local cache-backed dashboard, but it is still organized as one runtime-selected persistence story: connect to SQLite by default, optionally switch to Postgres, and manually keep repository and migration parity. That is not enough for the next phase, where hosted deployment, RBAC, auditability, and possibly multi-user/project isolation will need a more deliberate data platform design.

This PRD defines the storage refactor needed to keep local SQLite viable while making Postgres a first-class hosted profile with clearer boundaries between canonical application data, cache/ingestion state, and background processing metadata.

## Current State

1. `backend/db/connection.py` exposes a singleton connection or pool selected by environment.
2. `backend/db/factory.py` chooses repositories through runtime type inspection.
3. SQLite and Postgres migrations are maintained separately by hand.
4. The same persistence model tries to serve local single-user cache use and potential hosted multi-user operation.
5. Sync-engine data, user-facing data, integration cache data, and operational metadata all live in one broad storage layer.

## Problem Statement

As CCDash moves toward shared auth and hosted deployment, I need a storage architecture that makes local and hosted tradeoffs explicit. Today, the data layer hides those differences behind adapter dispatch, which makes tenancy, audit, schema governance, and operational reliability harder to reason about and evolve safely.

## Goals

1. Define explicit storage profiles for local and hosted operation.
2. Clarify the difference between canonical app data, local cache/ingestion data, and integration snapshot data.
3. Make Postgres a first-class hosted profile instead of an optional parity target.
4. Establish schema and migration governance that reduces drift between supported backends.
5. Prepare the data model for principals, memberships, permissions, and hosted audit requirements.

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Storage profiles | Implicit via env var | Explicit local and hosted storage profiles |
| Repository selection | Runtime `isinstance` dispatch | Composition-selected storage adapters |
| Migration parity confidence | Manual and drift-prone | Verified through defined governance and tests |
| Multi-user auth-era data support | None | Principal/membership-ready storage strategy |

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | Define a local storage profile centered on SQLite for single-user/local-first operation. | Must | Preserve portability and zero-config behavior. |
| FR-2 | Define a hosted storage profile centered on Postgres for shared deployments. | Must | Hosted auth and audit data must not be a secondary concern. |
| FR-3 | Move repository selection out of runtime connection inspection and into storage composition. | Must | Align with architecture foundation. |
| FR-4 | Partition or classify data domains such as canonical app entities, ingestion/cache state, integration snapshots, job metadata, and audit/security records. | Must | Logical separation is sufficient for V1; physical separation may vary by backend. |
| FR-5 | Introduce storage support for principals, memberships, role bindings, and privileged-action audit records. | Must | Needed by auth/RBAC work. |
| FR-6 | Define migration governance that keeps supported storage profiles trustworthy. | Must | May include shared metadata, test matrices, and explicit capability tables. |
| FR-7 | Establish a position on what remains local-cache-only versus what becomes canonical hosted data. | Must | Especially important for filesystem-derived artifacts and sync state. |

## Storage Strategy

### Local Profile

1. SQLite remains the default for local-first, portable use.
2. Filesystem-derived data can continue to behave as a cache synchronized from local sources.
3. Local auth bypass and per-user local project state remain acceptable.

### Hosted Profile

1. Postgres becomes the system of record for hosted/shared deployment.
2. Hosted auth, memberships, role bindings, audit trails, and job metadata live in canonical hosted storage.
3. Filesystem watch/sync behavior must be treated as an adapter concern, not a universal assumption.

### Data Domain Separation

1. Identity and access data
2. Project/workspace metadata
3. Observed product/domain entities
4. Ingestion and cache synchronization state
5. Integration snapshots and refresh metadata
6. Job scheduling/reconciliation metadata
7. Audit and security event records

## Non-Functional Requirements

1. Backward-compatible migration path for existing local users.
2. Clear data durability expectations by domain.
3. Test coverage for storage-profile differences and migration integrity.
4. Operationally safe defaults for hosted mode, especially around transactions, retries, and concurrent writes.

## In Scope

1. Storage-profile design and adapter boundaries.
2. Data-domain classification.
3. Auth-era schema additions and governance strategy.
4. Migration/test strategy for supported backends.

## Out of Scope

1. Immediate replacement of all raw SQL with a new ORM.
2. Full warehouse/OLAP strategy.
3. Database vendor support beyond SQLite and Postgres in V1.

## Dependencies and Assumptions

1. Depends on the hexagonal foundation refactor for proper storage composition.
2. Strongly coupled with shared auth/RBAC/SSO because principal and role data need a canonical home.
3. Assumes local-first mode will remain a supported product posture, so SQLite is not being removed.

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Hosted requirements force a premature abandonment of SQLite | Medium | Medium | Keep explicit local profile and define where its limits are acceptable. |
| Manual parity work continues despite new architecture | High | Medium | Add storage-profile governance and tests as part of the deliverable, not as follow-up. |
| Cache versus canonical boundaries remain vague | High | High | Require a data-domain ownership matrix in implementation planning. |
| Auth data gets mixed into legacy cache tables | High | Medium | Keep identity/access records in clearly separated schemas or table groups. |

## Acceptance Criteria

1. CCDash has a documented local-versus-hosted storage model with explicit tradeoffs.
2. Future implementation can add principal, membership, role-binding, and audit storage without reopening the entire data architecture.
3. Repository/storage adapter selection is defined through composition, not connection-type inspection.
4. Migration governance for SQLite and Postgres is explicit and testable.
5. The project has a clear statement of which data is canonical, cached, derived, or operational.
