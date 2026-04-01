# CCDash Storage Profiles Guide

Updated: 2026-04-01

## Purpose

CCDash now treats storage as an explicit operator-facing profile instead of only a low-level database toggle. Phase 1 freezes both the storage capability matrix and the runtime-to-storage pairing matrix, and Phase 4 extends that contract with enterprise-only identity/access and audit/security foundations.

| Storage profile | Primary database | Source of truth | Typical deployment |
| --- | --- | --- | --- |
| `local` | SQLite | Filesystem-derived artifacts plus local cache metadata | Desktop and single-user local-first |
| `enterprise` | Postgres | Postgres for canonical app state, identity/access, and audit/security state; filesystem remains ingestion only | Hosted API + worker deployments |

`CCDASH_DB_BACKEND` remains a compatibility setting, but `CCDASH_STORAGE_PROFILE` is the architectural control point. Runtime composition now resolves that control point into explicit `LocalStorageUnitOfWork` and `EnterpriseStorageUnitOfWork` adapters instead of routing through a factory-backed compatibility shell.

## Capability Matrix

`shared-enterprise` is not a separate environment variable. It is the `enterprise` storage profile with shared Postgres enabled and an explicit isolation mode.

| Storage mode | Configuration shape | Canonical store | Filesystem role | Supported isolation | Required guarantees |
| --- | --- | --- | --- | --- | --- |
| `local` | `CCDASH_STORAGE_PROFILE=local` and `CCDASH_DB_BACKEND=sqlite` | SQLite for local app metadata and derived cache state | Primary ingestion source and acceptable source of truth for derived artifacts | `dedicated` | Local-first remains zero-config, filesystem-derived rebuilds stay first-class, and hosted-only identity/audit concerns stay out of the local contract |
| `enterprise` | `CCDASH_STORAGE_PROFILE=enterprise`, `CCDASH_DB_BACKEND=postgres`, shared Postgres disabled | Postgres | Optional ingestion adapter only | `dedicated` | Postgres is the canonical hosted store, API runtimes do not depend on local watcher behavior, and enterprise-only identity/access plus audit/security data land in Postgres-owned storage |
| `shared-enterprise` | `CCDASH_STORAGE_PROFILE=enterprise`, `CCDASH_DB_BACKEND=postgres`, `CCDASH_STORAGE_SHARED_POSTGRES=true` | Postgres with an explicit CCDash boundary | Optional ingestion adapter only | `schema`, `tenant` | Cross-app table coupling is forbidden, CCDash owns an explicit schema or tenancy boundary, and hosted identity/access plus audit/security data stay inside that CCDash boundary |

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
- Enterprise identity/access tables and audit tables live in explicit CCDash-owned Postgres boundaries; they do not have a local-first equivalent.

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

The `/api/health` payload reports the resolved storage mode, storage profile, backend, storage composition, supported storage profiles, supported isolation modes, canonical store, audit store, shared-Postgres posture, isolation mode, schema, canonical session-store mode, migration-governance status, and runtime capability flags such as `watchEnabled`, `syncEnabled`, `syncProvisioned`, `jobsEnabled`, and `telemetryExports` so operators can verify the runtime contract quickly.

## Local Upgrade Path

Existing local SQLite installs should upgrade in place under the `local` storage profile.

1. Keep `CCDASH_STORAGE_PROFILE=local` and `CCDASH_DB_BACKEND=sqlite`.
2. Back up the SQLite file if you manage a custom path, then start the updated app normally.
3. Let startup run migrations; local mode does not backfill enterprise-only identity, membership, role-binding, or audit tables into SQLite.
4. Keep using filesystem-derived sync as before. Phase 5 only changes hosted runtime provisioning; it does not remove local sync/watch behavior.
5. If you later move to hosted enterprise mode, treat that as a fresh Postgres bootstrap plus re-ingest/rebuild step rather than an in-place SQLite promotion.

Compatibility notes:

- Existing local app metadata and derived cache state remain valid under the local adapter.
- Direct-ownership primitives reserved for enterprise canonical entities do not require a SQLite backfill.
- Local repositories for enterprise identity/audit concerns remain bounded compatibility shims, not authoritative local stores.

## Operator Rollout Checklist

- Confirm `CCDASH_STORAGE_PROFILE` and `CCDASH_DB_BACKEND` match the intended deployment posture.
- Use `local` + SQLite for the desktop/local-first workflow.
- Use `enterprise` + Postgres for hosted deployments.
- Set `CCDASH_STORAGE_SHARED_POSTGRES=true` only when CCDash shares Postgres infrastructure with another app.
- Set `CCDASH_STORAGE_ISOLATION_MODE=schema` or `tenant` for shared Postgres; do not rely on implicit isolation.
- Verify `GET /api/health` shows the expected storage mode, canonical store, and runtime capability flags.
- In the Ops panel, confirm storage composition, canonical/audit stores, migration-governance status, isolation mode/schema, sync provisioning, jobs, and telemetry export state.

## Follow-On Handoff

These seams are now considered stable for downstream implementation plans:

- Shared auth/RBAC should build on the enterprise-only `identity` and `audit` schema boundaries from Phase 4, plus the request-context scope bindings and tenancy keys already exposed in the runtime container.
- Session intelligence should keep `session_messages` and derived transcript facts as inherited-from-parent entities. Do not add direct ownership columns to transcript rows or derived intelligence facts.
- Local mode remains a cache-oriented SQLite posture; enterprise mode remains the canonical Postgres posture. Follow-on plans should not reopen that split.
- Hosted API runtimes stay stateless. Worker-owned ingestion is optional and explicit, and health now reports whether sync is merely supported or actually provisioned.
- Shared Postgres remains valid only behind an explicit schema or tenant boundary. No follow-on plan may couple CCDash tables directly to external app schemas.

## Domain Ownership Matrix

Phase 1 freezes the ownership vocabulary for the existing persisted concerns. This is a classification contract, not a claim that every future enterprise domain already has tables.
The post-completion Phase 3 delta now also marks each persisted concern as `scope-owned`, `directly-ownable`, or `inherits-parent-ownership`.

| Domain | Current artifacts in code | Local owner | Enterprise owner | Durability |
| --- | --- | --- | --- | --- |
| Workspace and project metadata | `projects.json`, workspace registry state, `app_metadata`, `alert_configs` | Local filesystem plus SQLite-backed app metadata | Postgres-backed canonical app metadata as hosted posture matures | Canonical |
| Observed product entities | `sessions`, `session_logs`, `session_messages`, `documents`, `document_refs`, `tasks`, `features`, `feature_phases`, `entity_links`, `tags`, `entity_tags`, `session_relationships`, `session_usage_*`, `commit_correlations` | SQLite cache and local metadata | Postgres canonical or mixed-mode hosted storage, depending on follow-on session-storage work | Mixed |
| Ingestion and cache state | `sync_state` and rebuild/checkpoint metadata around filesystem sync | Profile-local storage adapter | Profile-local storage adapter | Derived |
| Integration snapshots | `external_definition_sources`, `external_definitions`, `pricing_catalog_entries` | SQLite-backed refreshable cache | Postgres-backed refreshable snapshot store | Refreshable |
| Operational and job data | `telemetry_events`, `outbound_telemetry_queue`, `execution_runs`, `execution_run_events`, `execution_approvals`, `test_runs`, `test_definitions`, `test_results`, `test_domains`, `test_feature_mappings`, `test_integrity_signals`, `test_metrics`, `session_stack_observations`, `session_stack_components`, `effectiveness_rollups` | Local adapter allowed for local mode | Postgres preferred and expected for hosted mode | Operational |
| Identity and access | Future `principals`, `memberships`, `role_bindings`, scope identifiers | Not part of the local-first storage contract | Enterprise Postgres canonical home | Canonical |
| Audit and security records | Future privileged-action audit records and access-decision logs | Not part of the local-first storage contract | Enterprise Postgres canonical home | Canonical |

### Phase 1 and Phase 4 Boundary Notes

- Identity, membership, role-binding, and privileged-action audit tables do not exist yet in the current schema. Phase 1 freezes them as enterprise-owned domains so Phase 4 can add them without reopening ownership decisions.
- Session and document data remains mixed in V1: local mode keeps SQLite plus filesystem-derived workflows, while enterprise mode reserves Postgres as the canonical direction without forcing the full session-intelligence redesign into Phase 1.
- In enterprise mode, the API should stay stateless and the worker should own startup sync, refresh, and scheduled/background jobs.
- Shared Postgres is an isolation posture, not permission to reuse SkillMeat tables directly.
- Phase 4 keeps principals, memberships, role bindings, scope identifiers, and privileged-action audit records in enterprise-only Postgres boundaries rather than backfilling local parity tables.

### Enterprise Ownership Guardrails

- Reserve `tenant_id` or `enterprise_id`, `owner_subject_type`, `owner_subject_id`, and `visibility` only on directly ownable canonical roots.
- The current directly ownable enterprise roots are `alert_configs`, `sessions`, `documents`, `tasks`, and `features`.
- Child rows such as transcript messages, document refs, feature phases, correlations, and operational/snapshot derivatives inherit ownership from the governing canonical entity or scope instead of storing direct ownership primitives.
- Membership, role-binding, scope-identifier, and audit rows remain scope-governed and do not become directly ownable content objects.
- Use [docs/guides/data-domain-ownership-matrix.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/data-domain-ownership-matrix.md) for concern-level posture and [docs/guides/data-domain-schema-layout.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/data-domain-schema-layout.md) for boundary/repository placement.

## Ownership Readiness

Phase 3 now distinguishes between `scope-owned`, `directly-ownable`, and `inherits-parent-ownership` concerns.

- `docs/guides/data-domain-ownership-matrix.md` mirrors the concern-level ownership posture in `backend/data_domains.py`.
- `docs/guides/data-domain-schema-layout.md` records where ownership primitives are reserved and which repositories must become owner-aware in Phase 4.
- Reserve `tenant_id`, `enterprise_id`, `owner_subject_type`, `owner_subject_id`, and `visibility` only on directly ownable canonical entities. In the current Phase 3 contract, that means `alert_configs`, `sessions`, `documents`, `tasks`, and `features`.
- Derived cache, integration snapshot, operational, and audit rows remain scope-rooted or inherit ownership from a governing canonical entity; they should not gain direct ownership columns just because the deployment is enterprise.
