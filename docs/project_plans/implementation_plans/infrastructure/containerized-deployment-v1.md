---
title: "Implementation Plan: Containerized Deployment Infrastructure"
schema_version: 2
doc_type: implementation_plan
status: draft
created: 2026-04-20
updated: 2026-04-20
feature_slug: containerized-deployment-v1
feature_version: "v1"
prd_ref: /docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: null
scope: "Consolidate backend Dockerfiles, harden frontend image, unify compose.yaml with local/enterprise/postgres profiles, validate Podman compatibility, and document container deployment paths for operators."
effort_estimate: "28 pts"
architecture_summary: "Single backend image with entrypoint dispatch on CCDASH_RUNTIME_PROFILE; multi-stage frontend nginx image; unified compose.yaml replacing compose.hosted.yml with three composable profiles. No config architecture changes; thin wrapper over existing runtime/profile dispatch."
related_documents:
  - deploy/runtime/compose.hosted.yml
  - deploy/runtime/api/Dockerfile
  - deploy/runtime/worker/Dockerfile
  - deploy/runtime/frontend/Dockerfile
  - deploy/runtime/frontend/default.conf.template
  - docs/guides/runtime-storage-and-performance-quickstart.md
references:
  user_docs:
    - docs/setup-user-guide.md
    - docs/guides/runtime-storage-and-performance-quickstart.md
  context:
    - backend/runtime/profiles.py
    - backend/config.py
  specs: []
  related_prds:
    - docs/project_plans/meta_plans/performance-and-reliability-v1.md
spike_ref: null
adr_refs: []
deferred_items_spec_refs: []
findings_doc_ref: null
charter_ref: null
changelog_ref: null
changelog_required: true
test_plan_ref: null
plan_structure: unified
progress_init: auto
owner: null
contributors: []
priority: high
risk_level: medium
category: infrastructure
tags: [implementation, infrastructure, docker, podman, deployment, containers, compose]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - deploy/runtime/Dockerfile
  - deploy/runtime/entrypoint.sh
  - deploy/runtime/compose.yaml
  - deploy/runtime/frontend/Dockerfile
  - deploy/runtime/frontend/default.conf.template
  - deploy/runtime/.env.example
  - docs/guides/containerized-deployment-quickstart.md
  - docs/setup-user-guide.md
  - CHANGELOG.md
---

# Implementation Plan: Containerized Deployment Infrastructure

**Plan ID**: `IMPL-2026-04-20-containerized-deployment`
**Date**: 2026-04-20
**Author**: Implementation Planning Orchestrator
**Related Documents**:
- **PRD**: `/docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md`
- **Existing compose**: `deploy/runtime/compose.hosted.yml`
- **Existing Dockerfiles**: `deploy/runtime/api/Dockerfile`, `deploy/runtime/worker/Dockerfile`, `deploy/runtime/frontend/Dockerfile`

**Complexity**: Medium
**Total Estimated Effort**: 28 story points
**Target Timeline**: 2–3 weeks (infrastructure; sequential phases with limited parallelization)

---

## Executive Summary

This implementation plan transforms CCash from a three-terminal multi-process setup into a first-class containerized platform with one-command deployment. A single unified backend image with entrypoint dispatch on `CCDASH_RUNTIME_PROFILE` replaces the separate `api/` and `worker/` Dockerfiles. A hardened frontend nginx image supersedes the existing frontend Dockerfile with non-root user and envsubst templating. A new `compose.yaml` with three composable profiles (`local`, `enterprise`, `postgres`) replaces the existing smoke-only `compose.hosted.yml` as the canonical deployment manifest. Rootless Podman compatibility is validated through non-root UID/GID build args, SELinux `:Z` bind-mount labeling, and CI smoke testing. Documentation (quickstart, operator guide, CHANGELOG) completes the operator experience.

**Key Milestones**:
1. Unified backend Dockerfile + entrypoint dispatch (5 pts)
2. Frontend Dockerfile hardening (2 pts)
3. Unified `compose.yaml` with all three profiles (5 pts)
4. Postgres profile + volume/health wiring (2 pts)
5. Rootless Podman validation (3 pts)
6. Documentation + CHANGELOG (4 pts)
7. Smoke validation across all profiles and runtimes (7 pts)

---

## Implementation Strategy

### Architecture Sequence

This is **infrastructure work**, not the standard MP layered architecture (DB → Repo → Service → API → UI → Testing → Docs → Deploy). Instead, phases follow the container build and compose orchestration flow:

1. **Backend Image** — Unified Dockerfile consolidating api + worker; entrypoint dispatch
2. **Frontend Image** — Hardened nginx with non-root user and envsubst templating
3. **Compose Configuration** — `compose.yaml` with local/enterprise/postgres profiles
4. **Postgres Wiring** — Bundled Postgres service, health checks, env-var handoff
5. **Podman Compatibility** — Non-root UID/GID build args, named volumes, SELinux labeling
6. **Documentation Finalization** — Quickstart, operator guide, setup-user-guide update, CHANGELOG
7. **Smoke Validation** — End-to-end tests of all profiles on Docker and Podman

### Parallel Work Opportunities

- **Phase 1 & 2 in parallel**: Backend and frontend Dockerfiles can be authored simultaneously (no dependencies).
- **Phase 4 with Phase 3**: Postgres service definition can be wired into `compose.yaml` alongside the enterprise profile (depends on Phase 3 starting).
- **Phase 6 & 7 can overlap**: Documentation can be drafted in parallel with initial smoke testing (Phase 7).

### Critical Path

1. Phase 1 (Backend Dockerfile) → Phase 3 (compose.yaml) → Phase 4 (Postgres) → Phase 5 (Podman validation) → Phase 7 (Smoke validation)
2. Phase 2 (Frontend Dockerfile) is independent but feeds Phase 3.
3. Phase 6 (Documentation) blocks Phase 7 smoke validation (docs must be complete before final testing).

**Timeline**: ~15–18 days of critical-path work, with frontend work, Podman validation, and documentation running in parallel.

### Phase Summary

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|-------------------|----------|-------|
| 1 | Backend Dockerfile Consolidation | 5 pts | devops-architect, python-backend-engineer | sonnet | Unified image with entrypoint dispatch; non-root UID/GID build args |
| 2 | Frontend Dockerfile Hardening | 2 pts | devops-architect, python-backend-engineer | sonnet | Multi-stage, non-root nginx, envsubst template support |
| 3 | Unified compose.yaml with Profiles | 5 pts | devops-architect, platform-engineer | sonnet | local/enterprise/postgres profiles; UID/GID env var support; depends_on with conditions |
| 4 | Postgres Profile Wiring | 2 pts | devops-architect | sonnet | postgres:17-alpine service; named volume; health check; env-var handoff |
| 5 | Rootless Podman Compatibility | 3 pts | devops-architect, platform-engineer | sonnet | UID build args validation; named volume UID mapping; CI podman-compose smoke |
| 6 | Documentation Finalization | 4 pts | documentation-writer, changelog-generator | haiku (sonnet for CHANGELOG structure) | Quickstart, operator guide, setup-guide update, CHANGELOG `[Unreleased]` entry |
| 7 | Smoke Validation & Rollout | 7 pts | devops-architect, task-completion-validator | sonnet | All AC 1–8 pass; image size gates; integration testing |
| **Total** | — | **28 pts** | — | — | — |

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items

Per PRD § 7, the following items are **explicitly out of scope** and deferred to future work:

| Item ID | Category | Item | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|------|-----------------|----------------------|-----------------|
| DEFER-K8s | scope-cut | Kubernetes manifests and Helm charts | Future platform initiative; CCDash is local-first | Separate PRD for k8s/Helm story | N/A |
| DEFER-multiarch | scope-cut | Multi-arch beyond linux/amd64 + linux/arm64 | Requires separate build/push pipelines; limited demand | Platform expansion phase | N/A |
| DEFER-cicd | scope-cut | CI/CD pipeline automation for registry publication | Outside scope; manual registry push by maintainers | DevOps infrastructure upgrade | N/A |
| DEFER-digest-rotation | scope-cut | Automated base image digest rotation tooling | Requires release process integration | Quarterly release automation | N/A |

**Policy**: These items are documented in the plan for completeness but require NO design-spec authoring. They are intentional scope cuts, not research-needed items. If any in-flight findings during execution require one of these areas, a new design-spec task will be added to Phase 6 at that time.

### In-Flight Findings

No findings are pre-created. The findings doc (`.claude/findings/containerized-deployment-v1-findings.md`) will be created **lazily** on the first real finding during execution. If a finding impacts scope, architecture, or acceptance criteria, a design-spec authoring task (DOC-006) will be added to Phase 6.

### Quality Gate

Phase 6 (Documentation Finalization) is complete when:
- `deferred_items_spec_refs` remains `[]` (no new deferred items requiring specs, only intentional scope cuts)
- `findings_doc_ref` is `null` (no findings) OR findings doc is finalized and status is `accepted`

---

## Phase Breakdown

### Phase 1: Backend Dockerfile Consolidation

**Duration**: 2–3 days
**Dependencies**: None
**Assigned Subagent(s)**: devops-architect, python-backend-engineer
**Model**: sonnet
**Risk**: Medium (entrypoint dispatch logic must correctly route all three profiles; runtime bootstrap must not be duplicated)

#### Overview

Consolidate `deploy/runtime/api/Dockerfile` and `deploy/runtime/worker/Dockerfile` into a single unified `deploy/runtime/Dockerfile` (backend image). Add a shell entrypoint script `deploy/runtime/entrypoint.sh` that reads `CCDASH_RUNTIME_PROFILE` and dispatches to the appropriate bootstrap command. The image must run as a non-root UID (configurable via `BUILD_UID`/`BUILD_GID` build args, default 1000:1000) and be < 400 MB compressed.

#### Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| BE-001 | Unified Dockerfile | Create `deploy/runtime/Dockerfile` as multi-stage Python 3.12-slim image consolidating existing api + worker Dockerfiles | Image builds successfully; < 400 MB; runs as non-root UID 1000 by default | 3 pts | devops-architect, python-backend-engineer | sonnet | adaptive | None |
| BE-002 | Entrypoint script | Write `deploy/runtime/entrypoint.sh` to dispatch on `CCDASH_RUNTIME_PROFILE` env var (local/api/worker) or print usage and exit non-zero | Script correctly invokes bootstrap_local/bootstrap_api/bootstrap_worker; exits non-zero on unknown profile; handles SIGTERM signal propagation | 1.5 pts | python-backend-engineer | sonnet | adaptive | BE-001 |
| BE-003 | Non-root UID/GID | Add `BUILD_UID` and `BUILD_GID` build args (default 1000:1000) to Dockerfile; verify image runs as specified UID (test via `docker run --rm image id`) | Build args accepted; image runs with correct UID/GID; no permission errors on mounted volumes | 0.5 pts | devops-architect | sonnet | adaptive | BE-001 |
| BE-004 | Runtime bootstrap testing | Execute `backend.tests.test_runtime_bootstrap` inside the running container for all three profiles (local, api, worker) | Tests pass for all three profiles; bootstrap logic not duplicated in entrypoint.sh (shell script only dispatches) | 1 pt | python-backend-engineer | sonnet | adaptive | BE-002, BE-003 |

#### Quality Gates

- [ ] `docker build -t ccdash-backend:test .` succeeds
- [ ] `docker run --rm ccdash-backend:test id` shows UID 1000
- [ ] `docker run --rm ccdash-backend:test python -m backend.runtime.bootstrap_local` starts backend in local mode
- [ ] `docker run --rm ccdash-backend:test python -m backend.runtime.bootstrap_api` starts backend in api mode
- [ ] `docker run --rm ccdash-backend:test python -m backend.runtime.bootstrap_worker` starts backend in worker mode
- [ ] `backend.tests.test_runtime_bootstrap` passes inside container for all three profiles
- [ ] Image size < 400 MB (verify via `docker image ls`)
- [ ] `docker history --no-trunc ccdash-backend:test | grep -i secret` returns nothing (no secrets in layers)

---

### Phase 2: Frontend Dockerfile Hardening

**Duration**: 0.5–1 day
**Dependencies**: None (can run in parallel with Phase 1)
**Assigned Subagent(s)**: devops-architect, python-backend-engineer
**Model**: sonnet
**Risk**: Low (mostly hardening an existing pattern)

#### Overview

Update `deploy/runtime/frontend/Dockerfile` to add non-root user to the nginx runtime stage (nginx user, UID 101) and ensure `default.conf.template` uses `envsubst` for dynamic variable substitution (e.g., `CCDASH_API_UPSTREAM`, `CCDASH_FRONTEND_PORT`). Image must be < 50 MB compressed and serve static assets correctly with reverse-proxy to backend API.

#### Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| FE-001 | Non-root nginx user | Add `RUN useradd -r -s /sbin/nologin nginx` to runtime stage; switch to `USER nginx` before exposing port | Image runs as UID 101 (nginx user); no permission errors on config mount | 0.5 pts | devops-architect | sonnet | adaptive | None |
| FE-002 | envsubst templating | Verify `default.conf.template` uses `${CCDASH_API_UPSTREAM}` and `${CCDASH_FRONTEND_PORT}` placeholders; add entrypoint script or CMD to invoke `envsubst < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf` | Config substitution works; `/api` proxies correctly to backend; port binding respected | 0.5 pts | python-backend-engineer | sonnet | adaptive | None |
| FE-003 | Image size validation | Build and measure final image size | Image < 50 MB; confirmed via `docker image ls` | 0.5 pts | devops-architect | sonnet | adaptive | FE-001, FE-002 |

#### Quality Gates

- [ ] `docker run --rm frontend:test id` shows UID 101
- [ ] `docker run --rm --env CCDASH_API_UPSTREAM=http://backend:8000 --env CCDASH_FRONTEND_PORT=3000 frontend:test nginx -t` passes
- [ ] Static assets served on `:3000` from `/usr/share/nginx/html`
- [ ] `/api/*` proxies to `CCDASH_API_UPSTREAM`
- [ ] Image size < 50 MB (verify via `docker image ls`)

---

### Phase 3: Unified compose.yaml with Profiles

**Duration**: 2–3 days
**Dependencies**: Phase 1 & 2 complete (images must be defined)
**Assigned Subagent(s)**: devops-architect, platform-engineer
**Model**: sonnet
**Risk**: Medium (compose profiles and `depends_on` conditions must work with both Docker Compose v2 and podman-compose)

#### Overview

Write `deploy/runtime/compose.yaml` as the canonical compose file, replacing `compose.hosted.yml`. Define three composable profiles:
- **`local`**: Single backend container (profile=local, SQLite), frontend nginx, no Postgres
- **`enterprise`**: api + worker as separate containers, frontend, no Postgres (external CCDASH_DATABASE_URL)
- **`postgres`**: Adds bundled `postgres:17-alpine` service

Services must include health checks, `depends_on` with `condition: service_healthy`, and UID/GID mapping via `user: "${CCDASH_UID:-1000}:${CCDASH_GID:-1000}"` for rootless Podman compatibility.

Write `deploy/runtime/.env.example` covering all `CCDASH_*` env vars relevant to container deployment.

#### Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| COMP-001 | compose.yaml structure | Write base `compose.yaml` with services: backend (single unified image), frontend (nginx). Define three profiles: local (backend profile=local), enterprise (api service profile=api + worker service profile=worker), postgres (adds postgres:17-alpine) | YAML is valid; `docker compose config` and `podman-compose config` both pass; profiles composable | 3 pts | devops-architect, platform-engineer | sonnet | adaptive | Phase 1, Phase 2 |
| COMP-002 | Health checks | Add `healthcheck` blocks to backend services: api uses `GET /api/health/ready` (port 8000), worker uses `GET /readyz` (port 9465) with `start_period: 30s`, `interval: 30s`, `retries: 3` | Health check endpoints accessible inside container; probes respond within 30 s of startup | 1 pt | devops-architect | sonnet | adaptive | COMP-001 |
| COMP-003 | depends_on with conditions | Wire `depends_on: api: condition: service_healthy` for worker (enterprise profile); `depends_on: postgres: condition: service_healthy` for api + worker (postgres profile) | Services start in correct order; worker does not start before api; API migrations run before worker startup | 1 pt | platform-engineer | sonnet | adaptive | COMP-002 |
| COMP-004 | .env.example | Write `deploy/runtime/.env.example` documenting all `CCDASH_*` vars for local, enterprise, and postgres profiles (CCDASH_DB_BACKEND, CCDASH_DB_PATH, CCDASH_DATABASE_URL, CCDASH_UID, CCDASH_GID, CCDASH_API_UPSTREAM, CCDASH_FRONTEND_PORT, CCDASH_RUNTIME_PROFILE, CCDASH_POSTGRES_*, CCDASH_OTEL_*, etc.) | `.env.example` is complete; operator can copy to `.env` and run without reading source code; no secrets baked in | 1 pt | devops-architect | sonnet | adaptive | COMP-001 |

#### Quality Gates

- [ ] `docker compose config --profiles local,enterprise,postgres -f deploy/runtime/compose.yaml` produces valid output
- [ ] `podman-compose config --profiles local,enterprise,postgres -f deploy/runtime/compose.yaml` produces valid output (or noted as incompatibility)
- [ ] `docker compose --profile local up --no-start` creates all expected containers (backend, frontend)
- [ ] `docker compose --profile enterprise up --no-start` creates api, worker, frontend
- [ ] `docker compose --profile postgres up --no-start` creates postgres, api, worker, frontend
- [ ] All services have health checks or noted as intentionally absent
- [ ] `.env.example` is complete and operator-ready

---

### Phase 4: Postgres Profile Wiring

**Duration**: 0.5–1 day
**Dependencies**: Phase 3 complete
**Assigned Subagent(s)**: devops-architect
**Model**: sonnet
**Risk**: Low (follows existing compose.hosted.yml pattern; mostly copy + adaptation)

#### Overview

Wire the `postgres:17-alpine` service into the `--profile postgres` compose profile. Add a named volume for Postgres data persistence, health check, and environment variables for credentials (CCDASH_POSTGRES_USER, CCDASH_POSTGRES_PASSWORD, CCDASH_POSTGRES_DB). Wire `depends_on: postgres: condition: service_healthy` for api + worker. Verify that the api service runs migrations on startup and becomes healthy only after migrations complete, so the worker can safely depend on `api: condition: service_healthy`.

#### Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| PG-001 | Postgres service definition | Add `postgres` service to `compose.yaml` under `--profile postgres` with image `postgres:17-alpine`, environment vars POSTGRES_USER/PASSWORD/DB, named volume `ccdash-postgres:/var/lib/postgresql/data`, health check `pg_isready` | Service starts; health check passes; data persists across restarts | 1 pt | devops-architect | sonnet | adaptive | COMP-001 |
| PG-002 | depends_on ordering | Verify api + worker have `depends_on: postgres: condition: service_healthy` in enterprise + postgres profiles | Postgres becomes healthy before api/worker attempt to connect; startup order correct | 0.5 pts | devops-architect | sonnet | adaptive | PG-001, COMP-003 |
| PG-003 | Smoke test: Postgres profile | Run `docker compose --profile postgres up`, wait for all health checks to pass, verify api reaches `/api/health/detail`, verify worker is ready (`/readyz`) | All three services healthy within 2 min; database accessible from both containers | 0.5 pts | devops-architect | sonnet | adaptive | PG-001, PG-002 |

#### Quality Gates

- [ ] Postgres service defined with correct image, environment, volume
- [ ] Health check returns 200 from `pg_isready` within 30 s
- [ ] api + worker depend on postgres with health condition
- [ ] Named volume `ccdash-postgres` created and mapped correctly
- [ ] Smoke test passes: all services healthy, database accessible

---

### Phase 5: Rootless Podman Compatibility Validation

**Duration**: 1 day
**Dependencies**: Phases 1–4 complete
**Assigned Subagent(s)**: devops-architect, platform-engineer
**Model**: sonnet
**Risk**: Medium (Podman and podman-compose have subtle differences; SELinux labels require special handling)

#### Overview

Validate that the unified container stack works with rootless Podman >= 4.6 and podman-compose >= 1.2. Test UID/GID build args, named volume UID mapping, and SELinux `:Z` bind-mount relabeling. Document any differences between `docker compose` and `podman-compose` (e.g., `depends_on` condition support, profile syntax). If gaps are found, create a `compose.podman.override.yaml` or documented workaround.

#### Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| PODMAN-001 | UID/GID build args validation | Test `docker build --build-arg BUILD_UID=1000 --build-arg BUILD_GID=1000` for backend and frontend images on a rootless Podman host; verify containers run with correct UID/GID | Images build successfully; containers run as UID 1000 (or specified UID); no permission errors | 1 pt | devops-architect | sonnet | adaptive | Phase 1, Phase 2 |
| PODMAN-002 | Named volume UID mapping | Test that named volumes created by podman-compose are accessible from containers running as UID 1000; document any SELinux label (`-Z` or `:Z` mismatch) issues | Volume accessible without permission errors; data persists across container restarts | 0.5 pts | devops-architect | sonnet | adaptive | PODMAN-001 |
| PODMAN-003 | Bind-mount SELinux support | Document `:Z` bind-mount label syntax for operators; test with sample `projects.json` bind-mount on SELinux host | Bind mounts work with `:Z` label; documented in operator guide | 0.5 pts | platform-engineer | sonnet | adaptive | PODMAN-001 |
| PODMAN-004 | podman-compose syntax validation | Run `podman-compose --profiles local,enterprise,postgres config` on test host; verify `depends_on: condition:` syntax is supported | Output valid; any unsupported syntax flagged and workaround documented | 0.5 pts | devops-architect | sonnet | adaptive | Phase 3, Phase 4 |

#### Quality Gates

- [ ] `podman build --build-arg BUILD_UID=1000 --build-arg BUILD_GID=1000 -t ccdash-backend:local .` succeeds
- [ ] `podman run --rm ccdash-backend:local id` returns UID 1000
- [ ] `podman-compose --profile local up` starts containers on rootless Podman 4.6+
- [ ] Health checks pass with `podman-compose`
- [ ] Named volumes accessible without permission errors
- [ ] Bind-mount `:Z` label documented for operators
- [ ] Any compose.yaml incompatibilities documented or overridden

---

### Phase 6: Documentation Finalization

**Duration**: 1–2 days
**Dependencies**: Phases 1–5 complete
**Assigned Subagent(s)**: documentation-writer, changelog-generator
**Model**: haiku (standard docs), sonnet (changelog structure review)
**Risk**: Low

#### Overview

Create comprehensive operator documentation covering local, enterprise, and Podman deployment paths. Update existing `setup-user-guide.md` to recommend the container path as the preferred onboarding route. Update `npm run docker:*` scripts to target the new `compose.yaml`. Add a `[Unreleased]` CHANGELOG entry. Finalize operator guide with rootless Podman notes and troubleshooting.

#### Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| DOC-001 | CHANGELOG entry | Add `[Unreleased]` entry under "Added" with: "Containerized deployment infrastructure: unified backend Dockerfile, hardened frontend image, compose.yaml with local/enterprise/postgres profiles, rootless Podman support. Single-command deployment via docker compose or podman-compose." | Entry follows Keep A Changelog format; present before release tag | 0.5 pts | changelog-generator | haiku | adaptive | Phases 1–5 |
| DOC-002 | Operator quickstart | Write `docs/guides/containerized-deployment-quickstart.md` covering: local profile setup (copy `.env.example`, `docker compose --profile local up`), enterprise profile (set CCDASH_DATABASE_URL, `docker compose --profile enterprise up`), postgres profile bundled example, rootless Podman notes (UID mapping, `:Z` bind-mount label) | Guide is copy-paste ready; all three profiles covered; rootless Podman steps included | 1 pt | documentation-writer | haiku | adaptive | Phases 1–5 |
| DOC-003 | Setup guide update | Update `docs/setup-user-guide.md` to recommend container path as primary onboarding route; keep manual setup as secondary/advanced path | Container path listed first; links to `containerized-deployment-quickstart.md` | 0.5 pts | documentation-writer | haiku | adaptive | DOC-002 |
| DOC-004 | Image tagging convention | Document image tag strategy in `deploy/runtime/README.md` or new section of quickstart: `ghcr.io/ccdash/backend:<version>`, `ghcr.io/ccdash/frontend:<version>` | Convention documented; not enforced yet (registry publication out of scope) | 0.5 pts | documentation-writer | haiku | adaptive | Phases 1–5 |
| DOC-005 | Script update | Update or add `npm run docker:local:*` scripts (or equivalent) to invoke new `compose.yaml` with correct profiles; update existing `npm run docker:hosted:smoke:*` to use `compose.yaml --profile enterprise --profile postgres` | Scripts match new compose.yaml layout; developer ergonomics maintained | 1 pt | documentation-writer | haiku | adaptive | Phase 3 |

#### Quality Gates

- [ ] `docs/guides/containerized-deployment-quickstart.md` is present and complete
- [ ] `docs/setup-user-guide.md` updated to reference container path
- [ ] CHANGELOG `[Unreleased]` section has entry for containerized deployment
- [ ] `npm run docker:*` scripts work with new `compose.yaml`
- [ ] Image tagging convention documented
- [ ] All operator-facing documentation reviewed and finalized

---

### Phase 7: Smoke Validation & Rollout

**Duration**: 1 day
**Dependencies**: Phases 1–6 complete
**Assigned Subagent(s)**: devops-architect, task-completion-validator
**Model**: sonnet
**Risk**: Low (if Phases 1–6 are solid, smoke tests should pass)

#### Overview

Execute comprehensive smoke validation covering all acceptance criteria (AC-1 through AC-8 from PRD). Verify image size constraints, run end-to-end tests of all profiles on both Docker and Podman, execute `test_runtime_bootstrap` inside containers, validate health checks, and confirm operator documentation works. Document any issues found and roll back or patch as needed.

#### Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|-------------|-------|--------|--------------|
| SMOKE-001 | AC-1: Docker local profile | Run `docker compose --profile local up`, wait for health checks, verify UI on `:3000`, API on `:8000`, `/api/health/ready` returns 200 within 30 s | All acceptance criteria (AC-1) from PRD met | 1.5 pts | devops-architect | sonnet | adaptive | Phase 1, Phase 2, Phase 3 |
| SMOKE-002 | AC-2: Docker enterprise + postgres | Run `docker compose --profile enterprise --profile postgres up`, all four health checks pass | AC-2 from PRD met | 1.5 pts | devops-architect | sonnet | adaptive | Phase 3, Phase 4 |
| SMOKE-003 | AC-3: Docker enterprise external Postgres | Run `docker compose --profile enterprise up` with external `CCDASH_DATABASE_URL` (e.g., localhost Postgres), api + worker + frontend healthy | AC-3 from PRD met | 1 pt | devops-architect | sonnet | adaptive | Phase 3 |
| SMOKE-004 | AC-4: Podman rootless local | Run `podman-compose --profile local up` on rootless Podman 4.6+ host, same result as AC-1 | AC-4 from PRD met | 1 pt | devops-architect | sonnet | adaptive | Phase 5, SMOKE-001 |
| SMOKE-005 | AC-5: backend.tests.test_runtime_bootstrap | Execute `docker compose exec api python -m pytest backend/tests/test_runtime_bootstrap -v` for all three profiles (local, api, worker) | Tests pass; bootstrap logic works inside container | 1 pt | task-completion-validator | sonnet | adaptive | SMOKE-001, SMOKE-002 |
| SMOKE-006 | AC-6: Worker profile readiness | Test `docker compose exec worker curl http://localhost:9465/readyz` returns 200 | AC-6 from PRD met | 0.5 pts | devops-architect | sonnet | adaptive | Phase 1 |
| SMOKE-007 | AC-7: Session log bind-mount | Mount sample session logs into container via bind-mount, verify sync engine parses without permission errors (UID mapping correct) | AC-7 from PRD met | 0.5 pts | devops-architect | sonnet | adaptive | Phase 5 |
| SMOKE-008 | AC-8: SQLite + enterprise contract failure | Set `CCDASH_DB_BACKEND=sqlite` with `--profile enterprise`, verify startup fails with clear error from `StorageProfileConfig.validate_contract()` | AC-8 from PRD met | 0.5 pts | devops-architect | sonnet | adaptive | Phase 1, Phase 3 |
| SMOKE-009 | Image size gates | Verify backend image < 400 MB, frontend image < 50 MB | Both gates pass; confirmed via `docker image ls` | 0.5 pts | task-completion-validator | sonnet | adaptive | Phase 1, Phase 2 |
| SMOKE-010 | Operator quickstart validation | Follow `docs/guides/containerized-deployment-quickstart.md` from a fresh clone, verify all three profiles work as documented | Quickstart is copy-paste correct | 1 pt | task-completion-validator | sonnet | adaptive | DOC-002 |

#### Quality Gates

- [ ] All AC-1 through AC-8 from PRD acceptance criteria pass
- [ ] Backend image < 400 MB, frontend image < 50 MB
- [ ] `test_runtime_bootstrap` passes in all container profiles
- [ ] Health checks respond correctly for all services
- [ ] Operator quickstart validated end-to-end
- [ ] No P0/P1 bugs found; any issues documented and patched
- [ ] `compose.yaml` ready for production deployment

---

## Risk Mitigation

| Risk | Impact | Likelihood | Mitigation Strategy |
|------|--------|------------|-------------------|
| podman-compose syntax gaps (e.g., `depends_on: condition:` unsupported) | High | Medium | Validate early (Phase 5); provide `compose.podman.override.yaml` if needed; document workarounds |
| Rootless UID mapping breaks bind-mounted paths (host UID != container UID) | High | High | Document `:Z` SELinux label; recommend named volumes; provide `CCDASH_UID`/`CCDASH_GID` build args; operator note in quickstart |
| SQLite file-lock contention when enterprise profile accidentally uses SQLite | High | Low | Existing `StorageProfileConfig.validate_contract()` already fails fast; add compose comment + .env.example note |
| Image size bloat (dev dependencies leak into production) | Medium | Low | Multi-stage build + `pip install --no-cache-dir` only; size gate in CI (Phase 7) |
| Base image vulnerabilities from unpinned tags | Medium | Medium | Pin digests at release time; add quarterly digest-rotation note to operator runbook (documented but tooling deferred) |
| Worker startup race before API migrations complete | Medium | Medium | `depends_on: api: condition: service_healthy` ensures API runs migrations first; health check validated in Phase 2 |
| Entrypoint script dispatch logic duplicates existing bootstrap code | Medium | Low | Use shell script for dispatch only; validation logic stays in `backend/runtime/profiles.py` |

---

## Resource Requirements

### Team Composition
- **DevOps Architect** (primary): 1 FTE across all phases (infrastructure lead)
- **Python Backend Engineer** (supporting): 0.5 FTE for Phases 1, 4–5 (entrypoint, bootstrap validation)
- **Platform Engineer** (supporting): 0.5 FTE for Phases 3, 5 (compose orchestration, Podman compatibility)
- **Documentation Writer** (Phase 6): 0.5 FTE (operator guides, updates)
- **CHANGELOG Generator** (Phase 6): 0.2 FTE (changelog entry)
- **Task Completion Validator** (Phase 7): 0.5 FTE (smoke testing, QA)

### Skills Required
- Docker, Podman, Docker Compose v2
- Shell scripting (entrypoint.sh)
- Python FastAPI, async/await patterns
- YAML composition (compose.yaml, .env.example)
- SELinux and rootless container security
- nginx configuration and templating (envsubst)
- Operator documentation and troubleshooting guides

---

## Success Metrics

### Delivery Metrics
- All 7 phases complete on schedule (±3 days)
- All AC-1 through AC-8 from PRD acceptance criteria passing
- Zero P0/P1 bugs in first week of deployment

### Operational Metrics
- Onboarding time for new operators: < 2 min via `docker compose --profile local up`
- Backend image size: < 400 MB
- Frontend image size: < 50 MB
- Rootless Podman local profile smoke: 100% pass rate on CI
- Operator satisfaction: Container path documented and copy-paste ready

### Technical Metrics
- `test_runtime_bootstrap` passing inside container for all profiles
- Health checks responding correctly on all services
- Named volume UID mapping working without permission errors
- `depends_on` conditions enforcing correct startup order

---

## Communication Plan

- **Daily standups** (async): Progress on critical path phases (1, 3, 5, 7)
- **Phase gates**: Formal review at end of each phase before moving to next
- **Risk escalation**: Any `depends_on` or profile syntax incompatibilities flagged immediately (Phase 3 gate)
- **Operator feedback**: Quickstart reviewed by target operators before finalization (Phase 6)

---

## Post-Implementation

- **Smoke testing**: Automated via CI; `docker compose` and `podman-compose` tests run on each commit
- **Image push**: Manual registry publication by maintainers (automation deferred)
- **Operator feedback loop**: Monitor first-time users for friction points; iterate on quickstart
- **Digest rotation**: Quarterly manual base image digest pin review (process documented; tooling deferred)
- **Documentation maintenance**: Keep quickstart and image tags in sync as versions release

---

## Wrap-Up: Feature Guide & PR

**Triggered**: After Phase 7 quality gates pass.

### Step 1 — Feature Guide

Delegate to `documentation-writer` (haiku) to create `.claude/worknotes/containerized-deployment-v1/feature-guide.md`.

**Frontmatter**:
```yaml
---
doc_type: feature_guide
feature_slug: containerized-deployment-v1
prd_ref: /docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md
plan_ref: /docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
spike_ref: null
adr_refs: []
created: 2026-04-20
---
```

**Sections** (≤200 lines):
1. **What Was Built** — Unified backend Dockerfile, hardened frontend image, compose.yaml with three profiles, rootless Podman compatibility
2. **Architecture Overview** — Entrypoint dispatch pattern, UID/GID build args, named volume strategy, health check ordering
3. **How to Test** — `docker compose --profile local up`, `docker compose --profile enterprise --profile postgres up`, `podman-compose --profile local up`
4. **Test Coverage Summary** — All AC-1–AC-8 pass, image size gates met, bootstrap tests passing in containers
5. **Known Limitations** — Kubernetes/Helm deferred, multi-arch deferred, registry publication manual

Commit before opening PR.

### Step 2 — Open PR

```bash
gh pr create \
  --title "Container deployment infrastructure: unified images and compose.yaml" \
  --body "$(cat <<'EOF'
## Summary
- Unified backend Dockerfile with entrypoint dispatch on CCDASH_RUNTIME_PROFILE
- Hardened frontend nginx image with non-root user and envsubst templating
- Unified compose.yaml with local/enterprise/postgres profiles replacing compose.hosted.yml
- Rootless Podman compatibility validated via UID/GID build args and SELinux labels
- Operator quickstart guide and updated setup-user-guide

## Feature Guide
.claude/worknotes/containerized-deployment-v1/feature-guide.md

## Test plan
- [ ] All 7 phases complete and all AC-1–AC-8 pass
- [ ] Smoke-tested locally (all three profiles)
- [ ] Smoke-tested on rootless Podman
- [ ] Image size constraints met (backend <400 MB, frontend <50 MB)
- [ ] Operator quickstart validated end-to-end
- [ ] CHANGELOG [Unreleased] entry added

🤖 Generated with Claude Code
EOF
)"
```

---

## Model & Effort Assignment

All tasks in the phase breakdowns include **Model** and **Effort** columns per `.claude/config/multi-model.toml`:

- **sonnet** (default for implementation): Phases 1–5, 7 (Dockerfile, compose, entrypoint, validation)
- **haiku** (default for docs): Phase 6 documentation (guides, README updates, quickstart)
- **Effort**: `adaptive` (default) for all tasks; escalate to `extended` only if blocked with concrete artifacts

---

## Reference Documentation

- **PRD**: `/docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md`
- **Existing Dockerfiles**: `deploy/runtime/api/Dockerfile`, `deploy/runtime/worker/Dockerfile`, `deploy/runtime/frontend/Dockerfile`
- **Existing compose**: `deploy/runtime/compose.hosted.yml`
- **Runtime profiles**: `backend/runtime/profiles.py`
- **Env vars**: `backend/config.py`
- **Subagent reference**: `.claude/skills/planning/references/subagent-assignments.md`
- **Multi-model guidance**: `.claude/skills/planning/references/multi-model-guidance.md`

---

**Progress Tracking**: `.claude/progress/containerized-deployment-v1/all-phases-progress.md` (auto-created by artifact-tracking skill)

**Implementation Plan Version**: 1.0
**Last Updated**: 2026-04-20
