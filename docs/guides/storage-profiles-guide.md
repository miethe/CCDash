# CCDash Storage Profiles Guide

Updated: 2026-03-28

## Purpose

CCDash now treats storage as an explicit operator-facing profile instead of only a low-level database toggle. Phase 1 freezes both the storage capability matrix and the runtime-to-storage pairing matrix so the contract is enforced in code, tests, and operator docs.

| Storage profile | Primary database | Source of truth | Typical deployment |
| --- | --- | --- | --- |
| `local` | SQLite | Filesystem-derived artifacts plus local cache metadata | Desktop and single-user local-first |
| `enterprise` | Postgres | Postgres for canonical app state, filesystem as ingestion only | Hosted API + worker deployments |

`CCDASH_DB_BACKEND` remains a compatibility setting, but `CCDASH_STORAGE_PROFILE` is the architectural control point.

## Capability Matrix

`shared-enterprise` is not a separate environment variable. It is the `enterprise` storage profile with shared Postgres enabled and an explicit isolation mode.

| Storage mode | Configuration shape | Canonical store | Filesystem role | Supported isolation | Required guarantees |
| --- | --- | --- | --- | --- | --- |
| `local` | `CCDASH_STORAGE_PROFILE=local` and `CCDASH_DB_BACKEND=sqlite` | SQLite for local app metadata and derived cache state | Primary ingestion source and acceptable source of truth for derived artifacts | `dedicated` | Local-first remains zero-config, filesystem-derived rebuilds stay first-class, and hosted-only identity/audit concerns stay out of the local contract |
| `enterprise` | `CCDASH_STORAGE_PROFILE=enterprise`, `CCDASH_DB_BACKEND=postgres`, shared Postgres disabled | Postgres | Optional ingestion adapter only | `dedicated` | Postgres is the canonical hosted store, API runtimes do not depend on local watcher behavior, and enterprise-only data lands in Postgres-owned storage |
| `shared-enterprise` | `CCDASH_STORAGE_PROFILE=enterprise`, `CCDASH_DB_BACKEND=postgres`, `CCDASH_STORAGE_SHARED_POSTGRES=true` | Postgres with an explicit CCDash boundary | Optional ingestion adapter only | `schema`, `tenant` | Cross-app table coupling is forbidden, CCDash owns an explicit schema or tenancy boundary, and hosted identity/audit data stays inside that CCDash boundary |

## Configuration

### Local

- Use `CCDASH_STORAGE_PROFILE=local` or leave it unset.
- Keep `CCDASH_DB_BACKEND=sqlite`.
- Filesystem watch and sync remain first-class runtime behavior.

### Enterprise

- Set `CCDASH_STORAGE_PROFILE=enterprise`.
- Set `CCDASH_DB_BACKEND=postgres`.
- Set `CCDASH_DATABASE_URL`.
- Treat filesystem access as an ingestion concern, not an API assumption.

## Validation Rules

- `local` requires `CCDASH_DB_BACKEND=sqlite`.
- `local` supports only `CCDASH_STORAGE_ISOLATION_MODE=dedicated`.
- Dedicated `enterprise` supports only `CCDASH_STORAGE_ISOLATION_MODE=dedicated`.
- Shared-enterprise requires `CCDASH_STORAGE_SHARED_POSTGRES=true` and `CCDASH_STORAGE_ISOLATION_MODE=schema` or `tenant`.
- Invalid storage contracts fail during config resolution.

## Shared Postgres Contract

Shared Postgres is allowed only for the `enterprise` storage profile.

- `CCDASH_STORAGE_SHARED_POSTGRES=true` enables the shared-instance posture.
- `CCDASH_STORAGE_ISOLATION_MODE=schema` means CCDash owns a dedicated schema boundary.
- `CCDASH_STORAGE_ISOLATION_MODE=tenant` means tenant isolation must be enforced by the hosted deployment contract.
- `CCDASH_STORAGE_ISOLATION_MODE=dedicated` is valid only when the Postgres instance is CCDash-owned.
- Cross-application table coupling is not allowed even in shared infrastructure.

## Runtime Mapping

Runtime profiles and storage profiles are related but distinct:

| Runtime profile | `local` | Dedicated `enterprise` | Shared-enterprise | Runtime implications |
| --- | --- | --- | --- | --- |
| `local` | Supported | Unsupported | Unsupported | Watch + sync + in-process jobs; no hosted auth assumption |
| `api` | Unsupported | Supported | Supported | Stateless HTTP runtime; no incidental watcher or startup sync; hosted auth expected |
| `worker` | Unsupported | Supported | Supported | Background sync, refresh, and scheduled jobs; request auth not expected |
| `test` | Supported | Supported | Supported | Background work disabled by default; may validate either storage posture without watcher/job startup |

### Unsupported Pairings

- `api` + `local` is rejected before DB connection or migrations begin.
- `worker` + `local` is rejected before worker startup reaches DB setup.
- `local` runtime + any enterprise storage mode is rejected because the local runtime contract is local-first only.

The `/api/health` payload reports the resolved storage mode, storage profile, backend, supported storage profiles, supported isolation modes, canonical store, shared-Postgres posture, isolation mode, schema, and canonical session-store mode so operators can verify the runtime contract quickly.

## Domain Ownership Matrix

Phase 1 freezes the ownership vocabulary for the existing persisted concerns. This is a classification contract, not a claim that every future enterprise domain already has tables.

| Domain | Current artifacts in code | Local owner | Enterprise owner | Durability |
| --- | --- | --- | --- | --- |
| Workspace and project metadata | `projects.json`, workspace registry state, `app_metadata`, `alert_configs` | Local filesystem plus SQLite-backed app metadata | Postgres-backed canonical app metadata as hosted posture matures | Canonical |
| Observed product entities | `sessions`, `session_logs`, `session_messages`, `documents`, `document_refs`, `tasks`, `features`, `feature_phases`, `entity_links`, `tags`, `entity_tags`, `session_relationships`, `session_usage_*`, `commit_correlations` | SQLite cache and local metadata | Postgres canonical or mixed-mode hosted storage, depending on follow-on session-storage work | Mixed |
| Ingestion and cache state | `sync_state` and rebuild/checkpoint metadata around filesystem sync | Profile-local storage adapter | Profile-local storage adapter | Derived |
| Integration snapshots | `external_definition_sources`, `external_definitions`, `pricing_catalog_entries` | SQLite-backed refreshable cache | Postgres-backed refreshable snapshot store | Refreshable |
| Operational and job data | `telemetry_events`, `outbound_telemetry_queue`, `execution_runs`, `execution_run_events`, `execution_approvals`, `test_runs`, `test_definitions`, `test_results`, `test_domains`, `test_feature_mappings`, `test_integrity_signals`, `test_metrics`, `session_stack_observations`, `session_stack_components`, `effectiveness_rollups` | Local adapter allowed for local mode | Postgres preferred and expected for hosted mode | Operational |
| Identity and access | Future `principals`, `memberships`, `role_bindings`, scope identifiers | Not part of the local-first storage contract | Enterprise Postgres canonical home | Canonical |
| Audit and security records | Future privileged-action audit records and access-decision logs | Not part of the local-first storage contract | Enterprise Postgres canonical home | Canonical |

### Phase 1 Boundary Notes

- Identity, membership, role-binding, and privileged-action audit tables do not exist yet in the current schema. Phase 1 freezes them as enterprise-owned domains so Phase 4 can add them without reopening ownership decisions.
- Session and document data remains mixed in V1: local mode keeps SQLite plus filesystem-derived workflows, while enterprise mode reserves Postgres as the canonical direction without forcing the full session-intelligence redesign into Phase 1.
- Shared Postgres is an isolation posture, not permission to reuse SkillMeat tables directly.
