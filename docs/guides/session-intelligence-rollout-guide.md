# Session-Intelligence Rollout Guide

Updated: 2026-04-06

This guide closes Phase 7 of `session-intelligence-canonical-storage-v1`. It documents the supported rollout posture for canonical transcript intelligence, the checkpointed enterprise backfill path, and the approval-gated SkillMeat memory-draft workflow.

If you need the full enterprise operator path, including storage setup, the supported API + worker topology, `/api/health` verification, and post-rollout usage guidance, start with [`enterprise-session-intelligence-runbook.md`](/Users/miethe/dev/homelab/development/CCDash/docs/guides/enterprise-session-intelligence-runbook.md).

## Scope

Phase 7 freezes three rollout expectations:

1. `local` SQLite remains a supported cache-oriented posture with canonical transcript projection and limited optional intelligence.
2. `enterprise` Postgres is the canonical session-intelligence store and supports checkpointed historical backfill plus full analytics.
3. SkillMeat publication remains review-gated. CCDash may draft memory candidates automatically, but it does not auto-publish them.

## Prerequisites

Before an enterprise rollout:

- complete startup migrations successfully
- verify Postgres is the active database backend
- verify the runtime reports the expected storage profile and isolation posture
- confirm the deployment already includes the Phase 2 `session_embeddings` substrate and the Phase 3/4 intelligence fact and API surfaces
- confirm operators understand the SkillMeat review flow before enabling any memory-draft publishing

Required enterprise configuration shape:

- `CCDASH_STORAGE_PROFILE=enterprise`
- `CCDASH_DB_BACKEND=postgres`
- `CCDASH_DATABASE_URL`
- optionally `CCDASH_STORAGE_SHARED_POSTGRES=true`
- if shared Postgres is enabled: `CCDASH_STORAGE_ISOLATION_MODE=schema|tenant`

Local SQLite operators should stay on `CCDASH_STORAGE_PROFILE=local` and should not expect enterprise embedding or hosted backfill behavior.

## Health And Validation Contract

Use `GET /api/health` before and after rollout.

Minimum fields to validate:

- `storageComposition`
- `storageMode`
- `storageBackend`
- `storageFilesystemRole`
- `sessionIntelligenceProfile`
- `sessionIntelligenceAnalyticsLevel`
- `sessionIntelligenceBackfillStrategy`
- `sessionIntelligenceMemoryDraftFlow`
- `sessionIntelligenceIsolationBoundary`
- `sessionEmbeddingWriteStatus`
- `storageProfileValidationMatrix`
- `canonicalSessionStore`
- `migrationGovernanceStatus`
- `migrationStatus`

Expected posture by profile:

| Profile | Expected posture |
| --- | --- |
| `local-sqlite` | `sessionIntelligenceProfile=local_cache`, `sessionEmbeddingWriteStatus=unsupported`, `sessionIntelligenceBackfillStrategy=local_rebuild_from_filesystem` |
| `enterprise-postgres` | `sessionIntelligenceProfile=enterprise_canonical`, `sessionEmbeddingWriteStatus=authoritative`, `sessionIntelligenceBackfillStrategy=checkpointed_enterprise_backfill` |
| `shared-enterprise-postgres` | `sessionIntelligenceProfile=enterprise_canonical_shared_boundary`, `sessionEmbeddingWriteStatus=authoritative`, `sessionIntelligenceIsolationBoundary=schema_or_tenant_boundary` |

`storageProfileValidationMatrix` is the operator-facing comparison payload for those three supported postures. Treat it as the canonical validation table instead of reconstructing capability expectations from environment variables alone.

## Historical Enterprise Backfill

Use the rollout script to backfill canonical transcript rows, derived facts, and canonical embedding blocks for existing enterprise sessions.

### Command

```bash
python backend/scripts/agentic_intelligence_rollout.py \
  --project <project-id> \
  --session-intelligence-backfill \
  --session-intelligence-limit 200 \
  --session-intelligence-checkpoint-key session_intelligence_historical_backfill_v1 \
  --fail-on-warning
```

Useful variants:

- add `--all-projects` to process every configured project
- add `--reset-session-intelligence-checkpoint` to restart from the oldest eligible session
- add `--skip-sync` and/or `--skip-recompute` if the rollout window should only execute session-intelligence backfill

### Behavior

The backfill path:

1. pages enterprise sessions in stable `(started_at, session_id)` order
2. rebuilds canonical transcript rows from session logs when available
3. falls back to existing canonical rows if the session already has projected transcript state
4. recomputes sentiment, churn, and scope-drift facts from canonical transcript and evidence sources
5. materializes canonical embedding blocks only when the active storage adapter reports embedding support
6. stores a restart-safe checkpoint in `app_metadata`

Checkpoint key:

- `session_intelligence_historical_backfill_v1`

Checkpoint payload includes:

- `lastStartedAt`
- `lastSessionId`
- cumulative processed/backfilled counters
- `completed`
- `updatedAt`

### Operator Output

The rollout script now prints:

- batch counts for transcript, fact, and embedding backfill
- the current checkpoint cursor
- operator guidance lines explaining whether the next run will resume or whether a reset is needed

Use repeated runs with the same checkpoint key to drain history in bounded batches.

## Failure Modes

Common rollout failure modes:

- `sessionEmbeddingWriteStatus=unsupported`
  - expected in local mode; enterprise backfill still succeeds for transcript and fact rows but skips embeddings on unsupported storage
- unsupported runtime/storage pairing
  - bootstrap should fail instead of silently degrading
- shared Postgres without explicit isolation
  - treat this as invalid rollout state; fix storage configuration before continuing
- partially backfilled enterprise history
  - rerun the rollout command with the same checkpoint key until `completed=true`
- SkillMeat unavailable during review or publish
  - drafts remain reviewable CCDash records and should not be discarded automatically

## Rollback And Recovery

Rollback should be operational, not destructive.

1. Stop the rollout batch if health fields no longer match the intended storage profile.
2. Leave the checkpoint in place if the backfill should resume later from the same cursor.
3. Reset the checkpoint only when you intentionally want to recompute history from the beginning.
4. Keep local operators on `CCDASH_STORAGE_PROFILE=local`; do not try to force enterprise-only embedding behavior into SQLite.
5. If SkillMeat publishing is noisy or unsafe, stop at draft generation and keep publish approval manual.

Do not delete canonical transcript rows or derived facts as a first response. The intended recovery path is to correct the deployment posture and rerun the backfill from the stored checkpoint.

## SkillMeat Approval Flow

Session intelligence and SkillMeat publishing are separate workflows.

The intended flow is:

1. CCDash derives reviewable memory drafts from successful sessions.
2. Operators review the draft plus its extracted evidence in CCDash.
3. Only approved drafts call the SkillMeat write API.
4. Rejected or stale drafts remain CCDash-side operational records until cleaned up by later operational policy.

Guardrails:

- no blind auto-publish
- publish remains approval-gated
- draft evidence must remain inspectable from CCDash
- backfill and publish are independent so transcript ingestion can proceed even when SkillMeat is unavailable

## Verification Commands

Targeted checks used for Phase 7:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_session_intelligence_repository.py backend/tests/test_session_intelligence_service.py backend/tests/test_sync_engine_session_intelligence.py -q
backend/.venv/bin/python -m pytest backend/tests/test_runtime_bootstrap.py backend/tests/test_storage_profiles.py -q
```

Related references:

- [storage-profiles-guide.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/storage-profiles-guide.md)
- [data-platform-rollout-and-handoff.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/data-platform-rollout-and-handoff.md)
- [enterprise-session-intelligence-runbook.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/enterprise-session-intelligence-runbook.md)
- [session-intelligence-canonical-storage-v1.md](/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md)
