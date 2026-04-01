# Data-Platform Rollout And Handoff

Updated: 2026-04-01

This guide closes Phase 6 of `data-platform-modularization-v1`. It records the supported rollout posture for local and enterprise storage profiles, the operator-facing validation contract, and the stable seams that downstream shared-auth and session-intelligence work should inherit without reopening storage fundamentals.

## Rollout Summary

The current platform contract is:

- `local` remains the default SQLite-first, filesystem-derived posture.
- `enterprise` means Postgres is the canonical hosted store.
- shared-enterprise means `enterprise` plus an explicit schema or tenant isolation boundary.
- runtime bootstrap chooses adapters once; request paths do not inspect backend type to decide persistence behavior.
- migration governance is explicit and machine-checkable through the supported storage composition matrix.

## Local SQLite Upgrade Path

Existing local operators can upgrade in place.

1. Keep the deployment on the `local` storage profile backed by SQLite.
2. Start the local runtime and allow startup migrations to run.
3. Allow startup sync to refresh derived cache state and compatibility projections.
4. Validate the runtime with `GET /api/health`.

Expected local health posture:

- `storageComposition=local-sqlite`
- `storageMode=local`
- `storageBackend=sqlite`
- `syncProvisioned=true`
- `migrationGovernanceStatus=verified`
- `auditStore=not_supported_in_v1_local_mode`

Notes:

- No enterprise-only identity, membership, or audit backfill is required in local mode.
- Existing local app metadata and derived cache value remain valid under the local adapter.
- Moving from local SQLite to hosted enterprise Postgres should be treated as a fresh hosted bootstrap plus re-ingest/rebuild step, not an in-place promotion.

## Enterprise Bootstrap Contract

Hosted operators should treat startup as a storage-contract validation boundary.

Required configuration shape:

- `CCDASH_STORAGE_PROFILE=enterprise`
- `CCDASH_DB_BACKEND=postgres`
- `CCDASH_DATABASE_URL`
- optionally `CCDASH_STORAGE_SHARED_POSTGRES=true` plus `CCDASH_STORAGE_ISOLATION_MODE=schema|tenant`

Expected hosted health posture:

- `storageComposition=enterprise-postgres` or `shared-enterprise-postgres`
- `storageCanonicalStore=postgres_dedicated` or `postgres_shared_instance`
- `migrationGovernanceStatus=verified`
- `auditStore` reports the enterprise audit foundation boundary
- `syncProvisioned=false` for API runtimes unless enterprise filesystem ingestion is intentionally enabled

If the runtime/storage combination is unsupported, bootstrap should fail instead of silently degrading.

## Observability Contract

Use `GET /api/health` as the primary runtime contract check during rollout.

Fields to monitor:

- `storageComposition`
- `storageMode`
- `storageProfile`
- `storageBackend`
- `storageIsolationMode`
- `storageSchema`
- `sharedPostgresEnabled`
- `storageCanonicalStore`
- `auditStore`
- `auditWriteStatus`
- `migrationGovernanceStatus`
- `migrationStatus`
- `syncEnabled`
- `syncProvisioned`
- `requiredStorageGuarantees`

Interpretation:

- `syncEnabled` is what the runtime profile can do.
- `syncProvisioned` is what this process actually composed.
- `auditStore` is the canonical destination for audit/security records under the active storage contract.
- `auditWriteStatus` tells you whether the active profile can actually author authoritative audit writes.
- `migrationGovernanceStatus=verified` means the supported storage composition and migration table rules still hold.
- `migrationStatus=applied` means this runtime finished its startup migration step successfully.

## Stable Seams For Follow-On Plans

The following assumptions are now fixed and should not be reopened by downstream plans:

1. Shared auth/RBAC inherits enterprise-only identity and audit storage rather than inventing new local parity tables.
2. Session intelligence inherits `session_messages` as an ownership-inheriting transcript seam under the `sessions` root.
3. Direct ownership primitives remain reserved only for directly ownable canonical entity roots.
4. Shared Postgres remains valid only with an explicit schema or tenant isolation boundary.
5. API runtimes must not assume local filesystem watch/sync behavior.

## Follow-On Artifacts

Use these implementation plans as the next execution anchors:

- [docs/project_plans/implementation_plans/enhancements/shared-auth-rbac-sso-v1.md](/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/implementation_plans/enhancements/shared-auth-rbac-sso-v1.md)
- [docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md](/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md)

Supporting storage-contract references:

- [docs/guides/storage-profiles-guide.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/storage-profiles-guide.md)
- [docs/guides/data-domain-ownership-matrix.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/data-domain-ownership-matrix.md)
- [docs/guides/data-domain-schema-layout.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/data-domain-schema-layout.md)
