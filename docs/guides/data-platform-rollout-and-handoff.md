# Data-Platform Rollout And Handoff

Updated: 2026-04-18

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

Hosted bootstrap is not a SQLite promotion path. When you move from local SQLite to hosted enterprise Postgres, start from a fresh Postgres bootstrap and rebuild/re-ingest the canonical state instead of trying to lift-and-shift the SQLite file.

## Split Runtime Smoke Flow

Use the hosted compose helpers when you want a repeatable validation pass for the shipped split runtime contract:

```bash
npm run docker:hosted:smoke:config
npm run docker:hosted:smoke:up
npm run docker:hosted:smoke:ps
npm run docker:hosted:smoke:probes
npm run docker:hosted:smoke:job
```

What this covers:

- split API, worker, and frontend startup
- API readiness plus migration state
- worker readiness plus project binding
- one representative worker-owned background-job control path through telemetry `push-now`

Precondition:

- `CCDASH_WORKER_PROJECT_ID` must resolve to a real project before the worker can pass readiness

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

For the hosted smoke flow, add these expected split-runtime checks:

- `profile=api`
- `jobsEnabled=false`
- worker `/detailz` reports `runtimeProfile=worker`
- worker `/detailz` includes a bound project id when startup has resolved `CCDASH_WORKER_PROJECT_ID`

## CLI And MCP Handoff Boundary

The current shipped operator-query posture is intentionally narrow:

- repo-local CLI commands in `backend.cli`
- stdio MCP tools in `backend.mcp.server`
- four shared cross-domain reads exposed through both adapters

Use these repo-owned checks during rollout handoff:

```bash
npm run docker:hosted:smoke:cli-contract
npm run docker:hosted:smoke:mcp-contract
```

Those commands validate the shipped adapter surface without claiming the hosted compose stack bundles the separately packaged standalone `ccdash-cli`.

Current operator-surface contract:

- CLI: `status project`, `feature report`, `workflow failures`, `report aar`
- MCP: `ccdash_project_status`, `ccdash_feature_forensics`, `ccdash_workflow_failure_patterns`, `ccdash_generate_aar`

## Common Failure Modes

| Symptom | Interpretation | Action |
| --- | --- | --- |
| API is healthy but worker never reaches ready | split runtime is incomplete because the worker has no valid project binding | set a resolvable `CCDASH_WORKER_PROJECT_ID` and restart the worker |
| `migrationStatus` is not `applied` | startup did not finish the schema migration step | fix DB connectivity or migration errors before proceeding |
| telemetry smoke job is env-locked | worker exporter config is disabled by env | set `CCDASH_TELEMETRY_EXPORT_ENABLED=true` |
| telemetry smoke job is unconfigured | exporter is missing endpoint or API key | set `CCDASH_SAM_ENDPOINT` and `CCDASH_SAM_API_KEY` |
| CLI or MCP contract check fails | the documented operator surface no longer matches the implementation | fix the adapter/test drift before handoff |

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
