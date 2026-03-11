---
schema_name: ccdash_document
schema_version: 3
doc_type: report
doc_subtype: analysis
status: pending
category: product
title: "CCDash Platform Evolution Progression Report"
description: "Expected progression, per-step success criteria, and overall expected outcomes for the CCDash architecture, auth, deployment, and data-platform evolution sequence."
summary: "Synthesizes the new PRDs into one staged roadmap with completion signals for each step."
created: 2026-03-11
updated: 2026-03-11
priority: high
risk_level: medium
report_kind: progression
scope: ccdash-platform-foundation
owner: platform-engineering
owners: [platform-engineering, backend-platform, data-platform]
contributors: [ai-agents]
audience: [developers, platform-engineering, engineering-leads]
tags: [report, progression, architecture, auth, deployment, data-platform]
related_documents:
  - docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
  - docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md
  - docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md
  - docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md
evidence:
  - backend/main.py
  - backend/db/factory.py
  - backend/project_manager.py
  - contexts/DataContext.tsx
recommendations:
  - Execute the foundation refactor before implementation of shared auth, hosted deployment, or major storage changes.
  - Keep local-first mode as an explicit supported runtime profile throughout the sequence.
  - Treat hosted Postgres and shared identity as coordinated platform moves, not isolated technical upgrades.
impacted_features:
  - ccdash-hexagonal-foundation-v1
  - shared-auth-rbac-sso-v1
  - deployment-runtime-modularization-v1
  - data-platform-modularization-v1
---

# CCDash Platform Evolution Progression Report

## Executive Summary

The expected progression is:

1. establish the hexagonal/application foundation
2. introduce shared auth, RBAC, and SSO
3. modularize deployment and runtime responsibilities
4. formalize the data platform for local and hosted profiles

This order matters. The first step creates the seams that the other three steps depend on. If the sequence is reversed, CCDash will likely accumulate more router-level logic, more startup coupling, and more one-off exceptions for auth and hosted mode.

## Why This Progression Is Expected

The current architecture still centers on:

1. a mixed FastAPI startup path that owns API and background concerns
2. direct router awareness of DB access and adapter selection
3. global project state instead of request-scoped workspace context
4. a frontend data provider that is also the likely future auth boundary

Those traits are manageable in a trusted local tool, but they are the wrong shape for shared identity, hosted deployment, and stronger persistence guarantees. The expected progression therefore starts with architecture, not features.

## Step-by-Step Progression

### Step 1: Complete the Hexagonal Foundation

**Target document:** `docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md`

**Purpose**

Create explicit composition roots, application services, request context, and ports/adapters so later work can be added without reopening the same architecture problems.

**Success Criteria**

1. API, worker, local, and test runtime composition paths are explicit.
2. Migrated routers no longer fetch DB connections or repositories directly.
3. Request context can carry principal, workspace, project, and tracing data.
4. Background behaviors such as sync/watch/refresh are no longer assumed to be part of every API boot.
5. Frontend data access and app-shell/session concerns are clearly separated.

**What Changes After This Step**

1. CCDash becomes extensible in a controlled way.
2. New cross-cutting concerns can be introduced at service and adapter boundaries.
3. Auth, deployment, and storage work can proceed without brittle one-off wiring.

### Step 2: Complete Shared Auth, RBAC, and SSO

**Target document:** `docs/project_plans/PRDs/enhancements/shared-auth-rbac-sso-v1.md`

**Purpose**

Introduce a first-class identity boundary and a shared SSO posture with SkillMeat using a common OIDC-capable issuer.

**Success Criteria**

1. Hosted CCDash accepts authenticated users through a shared external issuer.
2. Service-layer authorization checks protect sensitive read/write/admin/execute paths.
3. Role bindings exist for workspace/project scoped access.
4. Audit attribution exists for privileged operations.
5. Local no-auth mode still works through a deliberate local adapter path.

**What Changes After This Step**

1. CCDash can be exposed to more than one user without relying on trust-by-network.
2. CCDash and SkillMeat begin to feel like parts of one operational environment.
3. Execution approvals, settings changes, and sensitive data access gain enforceable controls.

### Step 3: Complete Deployment and Runtime Modularization

**Target document:** `docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md`

**Purpose**

Turn CCDash from a combined dev stack into a platform with deployable runtime profiles and independently operable background work.

**Success Criteria**

1. Hosted API runtime no longer depends on local filesystem-watch behavior.
2. Worker responsibilities are independently runnable and observable.
3. Health and readiness reporting reflect real runtime state, not just process liveness.
4. Packaging contracts exist for frontend, API, and worker responsibilities.
5. Local mode remains ergonomic instead of being degraded by hosted-first assumptions.

**What Changes After This Step**

1. CCDash becomes materially easier to operate in shared or long-lived environments.
2. Failure domains become smaller and more diagnosable.
3. Auth, execution, sync, and analytics workloads can evolve without all living in one process lifecycle.

### Step 4: Complete Data Platform Modularization

**Target document:** `docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md`

**Purpose**

Make storage roles explicit so local SQLite and hosted Postgres both have a coherent place in the product strategy.

**Success Criteria**

1. Local and hosted storage profiles are explicitly documented and implemented.
2. Repository/storage adapter selection happens through composition, not connection-type inspection.
3. Identity, membership, role binding, and audit data have a canonical home.
4. Migration governance exists for supported backends.
5. Canonical data versus cache/derived/operational data boundaries are explicit.

**What Changes After This Step**

1. CCDash can support both local portability and hosted rigor without pretending they are identical runtime shapes.
2. Auth-era and audit-era data concerns stop being “bolt-ons” to a cache-oriented persistence layer.
3. The data platform becomes a strategic part of the product instead of a hidden implementation detail.

## Expected Completion Pattern

The practical completion pattern should look like this:

1. **Foundation complete:** architecture stops fighting the roadmap.
2. **Auth complete:** hosted access becomes safe and cross-app identity becomes coherent.
3. **Deployment complete:** runtime operations become reliable and modular.
4. **Data complete:** local-first and hosted modes both have a durable storage story.

If a step is “partially complete” but does not satisfy its success criteria, the expected outcome should be treated as deferred rather than assumed.

## Overall Expected Outcomes

When the full sequence is completed, CCDash should be expected to deliver the following outcomes.

### Product Outcomes

1. Shared sign-in across CCDash and SkillMeat.
2. Role-protected access to projects, execution controls, integrations, and sensitive analytical data.
3. A cleaner mental model for users moving between local and hosted usage.

### Engineering Outcomes

1. A backend organized around application services and ports/adapters rather than route-local orchestration.
2. A frontend that can support authenticated app shells and more modular data access.
3. Lower implementation friction for future platform capabilities.

### Operational Outcomes

1. Deployable API and worker runtimes with clearer health semantics.
2. Better observability and smaller failure domains.
3. A more credible hosted story for teams, not just individual local users.

### Data Outcomes

1. Explicit local-versus-hosted storage posture.
2. A canonical home for auth, audit, and membership data.
3. Stronger confidence in migration and backend support over time.

## Bottom Line

The expected progression is not four independent upgrades. It is one coordinated platform evolution.

1. The foundation step makes the roadmap feasible.
2. The auth step makes the product shareable.
3. The deployment step makes the product operable.
4. The data step makes the product durable.

If executed in this order, CCDash should move from a strong local-first engineering dashboard to a modular platform that can safely support shared identity, hosted operation, and future cross-app workflows.
