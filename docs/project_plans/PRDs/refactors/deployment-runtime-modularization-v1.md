---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: product_requirements
status: completed
category: refactors
title: "PRD: Deployment and Runtime Modularization V1"
description: "Split CCDash into deployable runtime profiles and service boundaries suitable for local-first use and hosted/shared environments."
summary: "Decouple API, workers, and local-watch behaviors so CCDash can be deployed reliably beyond the current single-process development model."
created: 2026-03-11
updated: 2026-04-28
priority: high
risk_level: high
complexity: High
track: Platform
timeline_estimate: "3-5 weeks after foundation refactor"
feature_slug: deployment-runtime-modularization-v1
feature_family: ccdash-runtime-platform
feature_version: v1
lineage_family: ccdash-runtime-platform
lineage_parent:
  ref: docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
  kind: prerequisite
lineage_children: []
lineage_type: refactor
problem_statement: "CCDash deployment behavior is still shaped around a combined dev stack with API startup owning background jobs, local filesystem watch, and sync responsibilities."
owner: platform-engineering
owners: [platform-engineering, devops, backend-platform]
contributors: [ai-agents]
audience: [developers, platform-engineering, engineering-leads]
tags: [prd, deployment, runtime, workers, platform, observability]
related_documents:
  - docs/setup-user-guide.md
  - docs/project_plans/PRDs/refactors/ccdash-hexagonal-foundation-v1.md
  - docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md
  - docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-phase-3-platform-connectors-v1.md
context_files:
  - backend/main.py
  - deploy/observability/docker-compose.yml
  - scripts/dev.mjs
  - scripts/backend.mjs
implementation_plan_ref: docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
---

# PRD: Deployment and Runtime Modularization V1

## Executive Summary

CCDash currently documents a “production-style” startup, but the application still fundamentally behaves like a combined local development runtime. The API process owns work that should be optional, schedulable, or delegated to workers. That creates operational risk for hosted deployments and makes auth, execution, and background processing harder to harden.

This PRD defines the runtime split required to support both local-first and hosted deployments cleanly. The target is a small set of explicit runtime profiles with predictable responsibilities, health semantics, and observability.

## Current State

1. `backend/main.py` starts API, sync pipeline, file watcher, analytics snapshots, and SkillMeat refresh together.
2. Deployment guidance ends at “run under a process manager or Docker,” but there is no CCDash runtime packaging beyond dev scripts.
3. Local filesystem watch is assumed to be part of application boot, which is not appropriate for all hosted environments.
4. Health reporting is minimal and does not expose readiness of dependent subsystems.
5. There is no explicit worker runtime for ingestion, reconciliation, or scheduled jobs.

## Problem Statement

As an operator, when I want to deploy CCDash in a durable shared environment, I cannot separate user-facing API responsibilities from background ingestion and maintenance work. That makes scaling, monitoring, failure recovery, and secure hosted operation unnecessarily fragile.

## Goals

1. Define clear runtime profiles for local desktop, hosted API, background worker, and test harness operation.
2. Remove mandatory local-watch and sync behavior from hosted API startup.
3. Provide deployment artifacts and contracts that support repeatable packaging and observability.
4. Make long-running or scheduled operations independently scalable and restartable.
5. Establish readiness, liveness, and degradation signals suitable for real operations.

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Runtime profiles with documented responsibility boundaries | 1 implicit mixed mode | 4 explicit profiles |
| Background tasks tied to API boot | Many | Only truly API-local tasks remain |
| Hosted deployment guidance | High level only | Reproducible packaging + runtime contract |
| Subsystem health visibility | Basic `status/db/watcher` | Readiness and degraded-state signaling for key dependencies |

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | Define runtime profiles for `local`, `api`, `worker`, and `test`. | Must | Profiles select adapters and enabled job classes. |
| FR-2 | Move sync/watch/scheduled tasks behind worker or job-runner abstractions. | Must | Local mode may still co-run them for convenience. |
| FR-3 | Provide a deployment packaging strategy for backend, worker, and frontend assets. | Must | Containers are expected; local process-manager support may remain. |
| FR-4 | Add health/readiness/degraded-state endpoints or payloads for API and worker runtimes. | Must | Must cover DB, auth provider reachability where relevant, and job subsystem state. |
| FR-5 | Define environment and secret contracts separately for local and hosted modes. | Must | Avoid accidental local defaults in hosted environments. |
| FR-6 | Ensure execution workbench, integration refresh, and analytics jobs can be disabled or routed to worker runtimes by profile. | Must | Hosted API should remain stateless where possible. |
| FR-7 | Add structured deployment observability covering request traces, job traces, and runtime metadata. | Should | Build on current OTel/Prometheus work. |

## Runtime Model

### Local Runtime

1. Optimized for single-user development.
2. May include in-process watch/sync convenience behaviors.
3. Supports explicit no-auth mode.

### Hosted API Runtime

1. Serves HTTP traffic only.
2. Does not depend on a local filesystem watcher.
3. Exposes readiness and auth/session-aware health signals.

### Worker Runtime

1. Runs sync, refresh, scheduled analytics, reconciliation, and other background jobs.
2. Can be disabled, scaled, or restarted independently.
3. Emits job-level observability and backpressure signals.

### Test Runtime

1. Supports isolated deterministic boot without incidental background jobs.
2. Makes integration tests easier to reason about.

## Non-Functional Requirements

1. Hosted mode must support TLS termination behind a reverse proxy.
2. API runtime should be horizontally scalable once stateful job concerns move out.
3. Background jobs must be idempotent or safely retryable.
4. Operational docs must include failure modes and degraded behavior, not just happy-path startup.

## In Scope

1. Runtime profile design and service decomposition.
2. Packaging/deployment contracts for API, worker, and frontend.
3. Operational health and observability expectations.
4. Compatibility path for local-first workflows.

## Out of Scope

1. Full Kubernetes-specific implementation.
2. Multi-region or HA database architecture.
3. CDN or edge-specific frontend deployment optimizations.

## Dependencies and Assumptions

1. Depends on the hexagonal foundation refactor for runtime composition and job ports.
2. Assumes auth work may introduce hosted-mode requirements for secure cookies, reverse proxy headers, and issuer reachability.
3. Assumes some local-first features will continue to use filesystem-based adapters in local profile.

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Worker split introduces operational complexity too early | Medium | Medium | Start with a DB-backed job model and one worker profile before adding more infrastructure. |
| Hosted API still accumulates background work via convenience paths | High | Medium | Enforce runtime-profile capability checks in composition. |
| Local mode regresses due to hosted-first assumptions | Medium | Medium | Keep local runtime as a first-class profile, not an afterthought. |
| Packaging becomes container-only and hurts contributors | Low | Medium | Document both container and process-manager equivalents. |

## Acceptance Criteria

1. CCDash has explicit runtime profiles with documented responsibility boundaries.
2. Hosted API startup no longer requires local sync/watch behavior to be enabled.
3. Background work can be run independently from the user-facing API process.
4. Deployment docs and packaging contracts cover frontend, API, and worker responsibilities.
5. Health/readiness reporting gives operators actionable visibility into runtime state.
