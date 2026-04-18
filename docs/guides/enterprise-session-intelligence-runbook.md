# Enterprise Session-Intelligence Runbook

Updated: 2026-04-07

This runbook is for operators who want the full hosted storage posture for CCDash and need to turn on canonical enterprise session intelligence end to end.

Use it when you need to:

1. configure CCDash for enterprise Postgres storage
2. validate the runtime/storage contract
3. run the checkpointed historical session-intelligence backfill
4. and start using transcript search, intelligence analytics, and approval-gated SkillMeat memory drafts in production

## Outcome

When this runbook is complete:

- Postgres is the canonical transcript-intelligence store
- `GET /api/health` reports the expected enterprise posture
- historical enterprise sessions have been backfilled incrementally with restart-safe checkpoints
- session intelligence is available through the existing session and execution surfaces
- SkillMeat memory drafts can be reviewed and approved from CCDash, but are never auto-published

## 1. Choose The Enterprise Posture

CCDash supports two hosted enterprise postures:

| Posture | Use when | Required isolation |
| --- | --- | --- |
| dedicated enterprise Postgres | CCDash owns the Postgres instance or database boundary | `dedicated` |
| shared-enterprise Postgres | CCDash shares infrastructure with another app | `schema` or `tenant` |

Do not use local SQLite for this runbook. Local mode is supported, but it is intentionally cache-oriented and does not provide the authoritative enterprise transcript-intelligence contract.

## 2. Required Environment Configuration

### Dedicated enterprise Postgres

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_DATABASE_URL=postgresql://<user>:<pass>@<host>:<port>/<db>
CCDASH_STORAGE_ISOLATION_MODE=dedicated
CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=false
```

### Shared-enterprise Postgres with schema isolation

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_DATABASE_URL=postgresql://<user>:<pass>@<host>:<port>/<db>
CCDASH_STORAGE_SHARED_POSTGRES=true
CCDASH_STORAGE_ISOLATION_MODE=schema
CCDASH_STORAGE_SCHEMA=ccdash
CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=false
```

### Shared-enterprise Postgres with tenant isolation

```bash
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_DATABASE_URL=postgresql://<user>:<pass>@<host>:<port>/<db>
CCDASH_STORAGE_SHARED_POSTGRES=true
CCDASH_STORAGE_ISOLATION_MODE=tenant
CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=false
```

Notes:

- `CCDASH_STORAGE_PROFILE=enterprise` is the architectural switch. `CCDASH_DB_BACKEND=postgres` is still required, but it is now a compatibility input behind the storage contract.
- Shared enterprise requires explicit isolation. If `CCDASH_STORAGE_SHARED_POSTGRES=true` is set without `schema` or `tenant`, treat the deployment as invalid.
- Filesystem ingestion in enterprise mode is optional. Keep it off unless you intentionally want CCDash to ingest from a filesystem boundary in the hosted environment.

Recommended rollout gates:

```bash
CCDASH_SKILLMEAT_INTEGRATION_ENABLED=true
CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED=true
CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED=true
CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED=true
CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED=true
```

Notes:

- `CCDASH_SKILLMEAT_INTEGRATION_ENABLED` is the global gate for SkillMeat sync/cache endpoints and the review/publish draft flow.
- SkillMeat base URL, project mapping, and API key are configured in `Settings > Integrations > SkillMeat`, not by a dedicated environment variable in this repo.
- There is no runtime-profile environment variable for enterprise. Runtime profile is chosen by the process entrypoint.

## 3. Runtime Topology

Enterprise mode assumes a split runtime:

- API runtime serves HTTP and reads canonical state
- worker runtime owns sync, refresh, and scheduled jobs

Canonical runtime matrix for hosted validation:

| Runtime | Canonical entrypoint | Hosted use |
| --- | --- | --- |
| `api` | `backend.runtime.bootstrap_api:app` | required |
| `worker` | `python -m backend.worker` | required |
| `local` | `backend.main:app` and `npm run dev` | never use for hosted validation |
| `test` | `backend.runtime.bootstrap_test:app` | test-only |

Supported enterprise entrypoints:

```bash
backend/.venv/bin/python -m uvicorn backend.runtime.bootstrap_api:app --host 0.0.0.0 --port 8000
backend/.venv/bin/python -m backend.worker
```

Optional frontend and worker helpers:

```bash
npm run start:frontend
npm run start:worker
```

Operator rules:

- `backend.runtime.bootstrap_api:app` is the stateless hosted API runtime.
- `backend.worker` is the background-only runtime for sync, refresh, and scheduled jobs.
- `backend.main:app` and `npm run dev` are local-convenience entrypoints and are not the hosted API posture.
- `npm run dev:backend` and `npm run start:backend` are wrappers around `backend.runtime.bootstrap_api:app`; they are useful local helpers, but the canonical hosted entrypoint remains the bootstrap module itself.
- If you are validating locally against enterprise Postgres, keep the same API/worker split. Do not rely on the desktop `local` runtime profile for enterprise validation.

Repo-shipped non-container launch examples live in [`deploy/runtime/README.md`](../../deploy/runtime/README.md). Use those systemd or supervisor examples when you need the same API/worker/frontend topology on a single host without inventing a separate runtime contract.

## 4. Initial Health Validation

Before running any backfill, confirm the runtime contract:

```bash
curl -sS http://127.0.0.1:8000/api/health
```

Minimum fields to inspect:

- `profile`
- `storageComposition`
- `storageMode`
- `storageBackend`
- `storageCanonicalStore`
- `storageIsolationMode`
- `storageSchema`
- `storageFilesystemRole`
- `canonicalSessionStore`
- `migrationGovernanceStatus`
- `migrationStatus`
- `sessionEmbeddingWriteStatus`
- `sessionIntelligenceProfile`
- `sessionIntelligenceAnalyticsLevel`
- `sessionIntelligenceBackfillStrategy`
- `sessionIntelligenceMemoryDraftFlow`
- `sessionIntelligenceIsolationBoundary`
- `storageProfileValidationMatrix`
- `watchEnabled`
- `syncEnabled`
- `syncProvisioned`
- `jobsEnabled`

Expected dedicated-enterprise posture:

- `profile=api`
- `storageComposition=enterprise-postgres`
- `storageMode=enterprise`
- `storageBackend=postgres`
- `storageCanonicalStore=postgres_dedicated`
- `storageIsolationMode=dedicated`
- `canonicalSessionStore=postgres`
- `sessionEmbeddingWriteStatus=authoritative`
- `sessionIntelligenceProfile=enterprise_canonical`
- `sessionIntelligenceAnalyticsLevel=full`
- `sessionIntelligenceBackfillStrategy=checkpointed_enterprise_backfill`
- `sessionIntelligenceMemoryDraftFlow=approval_gated_enterprise_publish`
- `sessionIntelligenceIsolationBoundary=dedicated_instance`
- `watchEnabled=false`
- `syncEnabled=false`
- `syncProvisioned=false`
- `jobsEnabled=false`

Expected shared-enterprise posture:

- `storageComposition=shared-enterprise-postgres`
- `storageCanonicalStore=postgres_shared_instance`
- `storageIsolationMode=schema` or `tenant`
- `storageSchema=<configured schema>` when schema isolation is used
- `sessionIntelligenceProfile=enterprise_canonical_shared_boundary`
- `sessionIntelligenceIsolationBoundary=schema_or_tenant_boundary`

Stop here if the health contract does not match the intended posture. Fix the deployment before starting backfill.

Worker probe validation:

```bash
curl -sS http://127.0.0.1:9465/readyz
curl -sS http://127.0.0.1:9465/detailz
```

Expected worker posture:

- `runtimeProfile=worker`
- readiness succeeds only after the worker binding contract is satisfied
- the worker probe host/port come from `CCDASH_WORKER_PROBE_HOST` and `CCDASH_WORKER_PROBE_PORT` when overridden

## 5. Pre-Backfill Checklist

Make sure all of the following are true:

- startup migrations completed successfully
- the worker is running
- session-intelligence code from the recent rollout is deployed
- the target project or projects already have enterprise session history to process
- operators understand that backfill is incremental and restart-safe
- operators understand that SkillMeat publish remains approval-gated even after backfill completes

Recommended validation commands before rollout:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_session_intelligence_repository.py backend/tests/test_session_intelligence_service.py backend/tests/test_sync_engine_session_intelligence.py -q
backend/.venv/bin/python -m pytest backend/tests/test_runtime_bootstrap.py backend/tests/test_storage_profiles.py -q
```

## 6. Run The Historical Backfill

### Single project

```bash
backend/.venv/bin/python backend/scripts/agentic_intelligence_rollout.py \
  --project <project-id> \
  --session-intelligence-backfill \
  --session-intelligence-limit 200 \
  --session-intelligence-checkpoint-key session_intelligence_historical_backfill_v1 \
  --fail-on-warning
```

### All projects

```bash
backend/.venv/bin/python backend/scripts/agentic_intelligence_rollout.py \
  --all-projects \
  --session-intelligence-backfill \
  --session-intelligence-limit 200 \
  --session-intelligence-checkpoint-key session_intelligence_historical_backfill_v1 \
  --fail-on-warning
```

What this does:

1. walks enterprise sessions in stable `(started_at, session_id)` order
2. rebuilds canonical transcript rows from session logs when available
3. falls back to existing canonical transcript rows if needed
4. recomputes sentiment, churn, and scope-drift facts
5. materializes canonical embedding blocks where the storage adapter supports embeddings
6. stores and advances a restart-safe checkpoint in `app_metadata`

## 7. Resume, Retry, And Reset Behavior

The backfill is designed for bounded batches.

Normal retry behavior:

- rerun the same command with the same checkpoint key
- CCDash resumes strictly after the last committed `(started_at, session_id)` cursor
- the checkpoint is written after each processed session and again at batch end

When to reset:

- only reset when you intentionally want to rebuild from the oldest eligible session again

Reset command:

```bash
backend/.venv/bin/python backend/scripts/agentic_intelligence_rollout.py \
  --project <project-id> \
  --session-intelligence-backfill \
  --reset-session-intelligence-checkpoint
```

Do not delete transcript/fact rows as the first recovery step. The intended recovery path is to fix the deployment posture and rerun from the stored checkpoint.

## 8. Interpret Backfill Output

The rollout script prints:

- processed transcript-session count
- processed derived-fact session count
- processed embedding-session count
- materialized embedding block count
- the current checkpoint cursor
- operator-guidance lines for resume or reset behavior

Healthy rollout pattern:

- counts continue moving forward across repeated runs
- checkpoint cursor advances
- final runs report `completed=true`

Common warning patterns:

- embedding writes skipped because storage support is unavailable
- no substantive transcript blocks in a batch
- backfill interrupted before completion

In enterprise mode, treat `sessionEmbeddingWriteStatus=unsupported` as a deployment problem unless you intentionally disabled the enterprise embedding substrate.

## 9. Post-Backfill Health Check

After the backfill:

1. call `GET /api/health` again
2. confirm the same enterprise posture is still reported
3. keep the checkpoint unless the rollout intentionally requires a full recompute

The health contract should still report:

- enterprise storage posture
- authoritative embedding support
- `checkpointed_enterprise_backfill`
- the expected isolation boundary

## 10. Start Using The New Capabilities

### Session Inspector

Use the Session Inspector to verify:

- canonical transcript rows render correctly
- transcript intelligence panels show sentiment, churn, and scope-drift evidence
- transcript search returns results from canonical transcript storage

Primary surface:

- [components/SessionInspector.tsx](/Users/miethe/dev/homelab/development/CCDash/components/SessionInspector.tsx)

### Execution Workbench

Use the Execution Workbench to verify:

- analytics and recommendation evidence now reflect the enterprise posture
- feature/workflow-level intelligence rollups are populated
- linked workflow evidence and related session intelligence surfaces behave as expected

Primary surface:

- [docs/execution-workbench-user-guide.md](/Users/miethe/dev/homelab/development/CCDash/docs/execution-workbench-user-guide.md)

### Ops / SkillMeat Memory Draft Flow

Use CCDash memory drafts as a review queue, not an auto-publish system.

Expected flow:

1. CCDash derives reviewable memory drafts from successful sessions
2. operators inspect the draft and its evidence in CCDash
3. only approved drafts call the SkillMeat write API
4. rejected drafts remain CCDash-side operational records until cleaned up later

This separation is intentional. Transcript backfill, intelligence analytics, and SkillMeat publish are related, but they are not the same operation.

Relevant API endpoints:

- `GET /api/integrations/skillmeat/memory-drafts?projectId=<project-id>`
- `POST /api/integrations/skillmeat/memory-drafts/generate?projectId=<project-id>`
- `POST /api/integrations/skillmeat/memory-drafts/{draft_id}/review?projectId=<project-id>`
- `POST /api/integrations/skillmeat/memory-drafts/{draft_id}/publish?projectId=<project-id>`

## 11. Integration Guidance

To integrate the new enterprise posture effectively:

- use `/api/health` as the canonical machine-readable contract check in deployment automation
- treat `storageProfileValidationMatrix` as the frozen comparison table for supported postures
- run backfill in bounded batches during rollout windows instead of one unbounded recompute
- keep enterprise API runtimes stateless and let workers own sync/backfill/background jobs
- make memory-draft publication part of an operator review workflow, not an unattended pipeline

If you expose this to internal users, explain three points clearly:

1. `local` and `enterprise` are intentionally different postures
2. enterprise analytics are only authoritative after backfill completes
3. SkillMeat draft publication still requires approval

## 12. Troubleshooting

### Health contract is wrong

- fix env vars first
- confirm the runtime profile matches the intended deployment
- confirm shared Postgres uses explicit schema or tenant isolation

### Backfill does not finish in one run

- this is expected
- rerun with the same checkpoint key until `completed=true`

### Embeddings are not being written

- confirm enterprise posture in `/api/health`
- confirm `sessionEmbeddingWriteStatus=authoritative`
- verify the enterprise embedding substrate from the earlier rollout is actually deployed

### Session intelligence exists but SkillMeat publish is unavailable

- transcript intelligence and memory publishing are separate
- drafts should remain reviewable in CCDash even when SkillMeat publish is unavailable

## Related References

- [docs/guides/storage-profiles-guide.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/storage-profiles-guide.md)
- [docs/guides/session-intelligence-rollout-guide.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/session-intelligence-rollout-guide.md)
- [docs/setup-user-guide.md](/Users/miethe/dev/homelab/development/CCDash/docs/setup-user-guide.md)
- [docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md](/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md)
