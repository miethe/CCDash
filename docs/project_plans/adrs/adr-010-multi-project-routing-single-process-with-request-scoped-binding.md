---
title: "ADR-010: Multi-Project Routing — Single Process with Request-Scoped Binding"
type: "adr"
status: "accepted"
created: "2026-05-10"
parent_prd: "docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md"
depends_on_spike: "docs/project_plans/SPIKEs/remote-ccdash-streaming.md"
tags: ["adr", "multi-project", "routing", "runtime", "container"]
---

# ADR-010: Multi-Project Routing — Single Process with Request-Scoped Binding

## Status

Accepted (SPIKE-resolved 2026-05-10)

## Context

`RuntimeContainer` binds **one project per process** at startup (`backend/runtime/container.py:67`, `backend/runtime/runtime.py:107-127`). For a remote CCDash deployment that serves multiple workspaces and projects from one cluster, two routing models exist:

- **(A) One process per project.** N projects → N pods/containers behind a load balancer that routes by `x-ccdash-project-id`. Trivial code change (project-id is a routing key); large infrastructure change (N processes, N DB connections, N memory baselines).
- **(B) Single process with request-scoped project binding.** One process serves all projects; the active binding is resolved from `AuthContext.project_id` (ADR-008) on every request. Requires refactoring `RuntimeContainer` to expose a per-request resolver instead of a global `bound_project`. Smaller infra footprint; larger code change.

## Decision

**Adopt option (B): single process with request-scoped project binding for the `api` runtime profile.** The `worker` runtime profile retains startup-time binding for now (one worker per project) because background sync engines are tied to filesystem watchers per project; multi-project workers are out of scope for v1.

`RuntimeContainer` is refactored as follows:

- `bound_project: ProjectBinding` (today, single value, set at startup) →
- `resolve_binding(project_id: str) -> ProjectBinding` (new, called per request from a FastAPI dependency that reads `AuthContext.project_id`).

`ProjectBinding` is a small immutable dataclass (project metadata, `ProjectPathResolver`, scoped storage facade). Bindings are cached in an LRU keyed by `project_id` — a binding is cheap to construct and naturally amortizes across requests.

The `x-ccdash-project-id` request header is **deprecated as a routing input**. Project routing is driven exclusively by `AuthContext.project_id` (which itself comes from the workspace token, ADR-008). The header is honored only as a tie-break when `AuthContext` permits multiple projects (a v2 concern); in v1 every token is bound to exactly one project so the header is a no-op.

## Decision Drivers

1. **Operational footprint.** A team of 10 with 1 project each → option (A) needs 10 pods. Option (B) needs 1. v1 targets small/medium teams where the per-pod overhead would dominate the actual ingest cost.
2. **Auth integration.** `AuthContext.project_id` (ADR-008) already exists; using it as the routing key is one DI dependency, not new infrastructure.
3. **Cold-start economics.** Option (A) means every new project means scheduling a new pod (10–30s cold start). Option (B) is a sub-millisecond LRU lookup.
4. **Daemon multi-tenancy at the door.** A single ingest endpoint accepts events for any workspace because the bearer determines scope (ADR-014). Forcing daemons to know which pod hosts their project would push routing complexity into every workstation. Single-process routing keeps the operational story simple: one DNS name, one TLS cert, one ingestion endpoint.

## Decision Matrix

Scored against E5 hard gates plus operational concerns.

| Criterion (weight) | Single process + request-scoped binding (B) | One process per project (A) |
|---|---|---|
| Cold-start ≤ baseline + 10% (×3) | **5** (LRU lookup is sub-ms) | 1 (new pod ⇒ ~20s cold start per new project) |
| Steady-state RSS ≤ 2× single-project baseline at 10 projects (×3) | **4** (per-binding caches; ~150MB at 10) | 1 (~10× baseline by definition) |
| p99 latency ≤ baseline + 25% (×2) | 4 (DI overhead trivial; same DB pool) | 5 (each pod is single-tenant, no contention) |
| Code-change surface (×2) | 2 (refactor `RuntimeContainer`, audit binding resolution) | **5** (no app code change; routing is at L7) |
| Operational footprint at 10 projects (×3) | **5** (1 pod) | 1 (10 pods + LB rules) |
| Daemon-side simplicity (×1) | **5** (one endpoint, one DNS) | 3 (LB strips header, OK; observability gets harder) |
| Forward path to scale (>50 projects) (×1) | 3 (eventually need horizontal scaling) | 4 (already horizontal) |
| **Weighted total** | **65** | 38 |

## Implementation Sketch

```python
# backend/runtime/container.py (refactored)

class ProjectBinding:
    project_id: str
    project_meta: ProjectMeta
    paths: ProjectPathResolver
    storage: ScopedStorageFacade

class RuntimeContainer:
    def __init__(self, ...):
        self._bindings: LRU[str, ProjectBinding] = LRU(maxsize=64)
        # Note: NOT pre-populated. Bindings are lazy.

    def resolve_binding(self, project_id: str) -> ProjectBinding:
        if cached := self._bindings.get(project_id):
            return cached
        meta = self._project_manager.get(project_id)        # raises 404 if unknown
        binding = ProjectBinding(
            project_id=project_id,
            project_meta=meta,
            paths=ProjectPathResolver(meta),
            storage=ScopedStorageFacade(meta, self._db),
        )
        self._bindings[project_id] = binding
        return binding

# FastAPI dependency
def get_project_binding(
    auth: AuthContext = Depends(get_auth_context),
    container: RuntimeContainer = Depends(get_container),
) -> ProjectBinding:
    return container.resolve_binding(auth.project_id)

# Router usage
@router.get("/sessions")
async def list_sessions(binding: ProjectBinding = Depends(get_project_binding), ...):
    return await session_service.list(binding=binding, ...)
```

## Hard Gates (from E5)

The implementation must hit these before v1 ships. They are not measured in this SPIKE; they are the floor that downstream load testing (Phase 4 of the implementation plan) must validate.

| Metric | Target |
|---|---|
| Cold start (process boot to ready) | ≤ existing baseline + 10% |
| Steady-state RSS at 10 concurrently active projects | ≤ 2× single-project baseline (target: ≤ 1.5×) |
| p99 request latency at 10 concurrent projects | ≤ baseline + 25% |
| Cross-project read attempt (forged `x-ccdash-project-id`, valid token for a different project) | 403 (header is ignored; scope follows token) |

If any gate is missed in the actual implementation, the fallback is **option (A) for the affected dimension only** — e.g., if RSS scales linearly with project count beyond 2× at 10 projects, ship v1 single-process and add a horizontal scaling story in v1.1 (one process per project-set, project-set sized to fit the RSS budget). Do not silently degrade.

## Consequences

### Positive

- One pod for typical small-team deployments; trivial install on a single VM.
- One ingestion endpoint and one DNS name; daemons do not care about project topology.
- Project bindings are lazy; cold-start cost stays at process-boot, not per-project.
- The forward path to horizontal scaling is unblocked: nothing about the binding model breaks if a future deployment runs N processes and routes by `project_id` at L7.

### Negative

- The `worker` profile retains startup-time binding (out of scope for v1). A team that wants multi-project ingest workers must run N worker processes. Documented in operator guide.
- A single `api` process is a noisier-neighbor risk: a slow query in project A can starve project B. Mitigated by the existing query timeout in `backend/db/connection.py` and by the agent-query cache. v2 may add per-project rate limits.
- The LRU cache for bindings adds cognitive load. Mitigated by keeping `ProjectBinding` immutable and easily reconstructible.

### Risks

| Risk | Mitigation |
|---|---|
| Cross-project leak via stale binding | Bindings are immutable; cache key is `project_id` only; on revocation/deletion the project_manager evicts the binding explicitly |
| LRU thrash at >64 active projects | LRU size is configurable; at 64+ active projects v1.1 should ship horizontal scaling |
| Per-project DB connection pool contention | Default DB connection pool is process-wide and shared; per-binding storage facades reuse the pool. Audit on every storage call |
| Hidden mutable state in `RuntimeContainer` | Lint rule + structural test asserting `ProjectBinding` and `RuntimeContainer.resolve_binding` are pure |

## Related

- ADR-014 (transport — single endpoint serves all projects)
- ADR-008 (auth — provides `AuthContext.project_id`)
- ADR-009 (sync port — sources are scoped per (project, workspace))
- Container today: `backend/runtime/container.py:67`
- Project resolution today: `backend/runtime/runtime.py:107-127`
