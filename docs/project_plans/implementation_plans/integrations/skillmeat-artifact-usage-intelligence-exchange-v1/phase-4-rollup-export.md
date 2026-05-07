---
schema_version: 3
doc_type: phase_plan
title: "Phase 4: Rollup Export & SkillMeat Persistence"
status: draft
created: 2026-05-07
updated: 2026-05-07
phase: 4
phase_title: "Rollup Export & SkillMeat Persistence"
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
entry_criteria:
  - Phase 3 complete: ranking rows computed, recommendations generated, karen review passed
  - Existing telemetry_exporter.py artifact outcome ingestion tests pinned as regression suite
exit_criteria:
  - Rollup export sends project/user/collection artifact usage rollups to SkillMeat
  - SkillMeat stores project-level and collection-level artifact usage metrics
  - Existing artifact outcome ingestion behavior unaffected (regression tests green)
  - Privacy guard assertion: no raw prompts, transcripts, paths, or unhashed usernames in export payloads
  - Export integration test and SkillMeat contract test pass
integration_owner: python-backend-engineer
ui_touched: false
---

# Phase 4: Rollup Export & SkillMeat Persistence

## Phase Overview

**Estimate**: 5 pts
**Duration**: ~3–4 days
**Dependencies**: Phase 3 complete (ranking rows and recommendations must exist before export builds rollup payloads)
**Assigned Subagent(s)**: python-backend-engineer (primary and secondary — both batch tasks are python-backend-engineer)

### Scope

Extend the existing outbound telemetry pipeline to send project/user/collection-aware artifact usage rollups back to SkillMeat:

1. **Rollup payload builder** — a new service component that transforms `artifact_ranking` rows into `ccdash-artifact-usage-rollup-v1` payloads, with privacy guard enforcement
2. **Extend `telemetry_exporter.py`** — add `export_artifact_usage_rollups()` method that collects rollup payloads and sends them via a new SkillMeat additive ingestion endpoint
3. **SkillMeat ingestion contract stubs** — define the expected SkillMeat endpoint behavior for additive project/collection metrics storage (not replacing existing artifact outcome behavior)
4. **Privacy guard extension** — extend `AnonymizationVerifier` (or equivalent) to cover all new rollup fields; explicit field-level allowlist
5. **Export job integration** — wire rollup export into the background scheduler alongside existing telemetry export

### Parallelization

```yaml
parallelization:
  batch_1:
    # Rollup builder and privacy guard can proceed in parallel
    - task: T4-001
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
    - task: T4-002
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
  batch_2:
    # Telemetry exporter extension depends on rollup builder and privacy guard
    - task: T4-003
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T4-001, T4-002]
  batch_3:
    # Contract stubs and export job wiring after exporter is updated
    - task: T4-004
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T4-003]
    - task: T4-005
      assigned_to: python-backend-engineer
      model: sonnet
      effort: medium
      depends_on: [T4-003]
```

---

## Task Table

| Task ID | Name | Description | Acceptance Criteria | Points | Subagent(s) | Model | Effort | Dependencies |
|---------|------|-------------|--------------------|---------|----|-------|--------|------|
| T4-001 | Rollup payload builder | Create `backend/services/rollup_payload_builder.py`. Reads from `artifact_ranking` repository. Transforms ranking rows into `ArtifactUsageRollup` Pydantic objects. Applies user_scope logic: hosted mode uses OTel principal, local mode uses `CCDASH_LOCAL_USER_SCOPE_PSEUDONYM` (default: "local-user") or omits user_scope dimension if `CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE=omit`. Includes embedded recommendations from `ArtifactRecommendationService`. Groups by (project, collection, artifact, period). | Rollup payloads correctly built from seeded ranking rows. user_scope logic: hosted mode populates principal, local mode uses pseudonym or omits. Embedded recommendations included with correct fields. Schema validates against `ccdash-artifact-usage-rollup-v1`. No raw prompts, transcripts, code, paths, or unhashed usernames in any field. | 1.5 pts | python-backend-engineer | sonnet | medium | Phase 3 complete |
| T4-002 | Privacy guard extension | Extend the `AnonymizationVerifier` (in `backend/services/integrations/` or equivalent) to cover all new rollup fields. Create an explicit field-level allowlist for `ArtifactUsageRollup` (permitted fields: usage stats, effectiveness scores, recommendation metadata, artifact identity; prohibited: raw_prompt, transcript_text, code, absolute_path, unhashed_username). Add a `verify_rollup_payload(rollup: ArtifactUsageRollup) -> bool` method that raises `PrivacyViolationError` if any prohibited field is populated. | Privacy guard correctly identifies prohibited fields. Test: populate a rollup with a mock `raw_prompt` field → raises `PrivacyViolationError`. Test: clean rollup passes verification. Field-level allowlist documented as a code-level comment and in inline docstring. | 1 pt | python-backend-engineer | sonnet | medium | None |
| T4-003 | Extend telemetry_exporter.py | Add `export_artifact_usage_rollups(project_id, period)` method to `backend/services/integrations/telemetry_exporter.py`. Calls `RollupPayloadBuilder`, runs each payload through `AnonymizationVerifier`, and sends to SkillMeat via `SkillMeatClient.post_artifact_usage_rollup(rollup)`. Uses existing retry/backoff patterns from telemetry exporter. Existing `export_artifact_outcomes()` method and tests must remain unchanged. | Rollup export method sends correct payloads. Privacy guard called for every payload. Verified-failed payloads are logged and skipped (not raised). Existing artifact outcome export method unaffected — regression test suite green. Network failures log and do not crash the worker. | 1.5 pts | python-backend-engineer | sonnet | medium | T4-001, T4-002 |
| T4-004 | SkillMeat ingestion contract stubs | Add `post_artifact_usage_rollup(rollup: ArtifactUsageRollup)` to `backend/services/integrations/skillmeat_client.py`. Route: `POST /api/v1/analytics/artifact-usage-rollups`. Additive contract: SkillMeat must persist project-level and collection-level metrics without overwriting existing artifact/version metrics. Define a `SkillMeatRollupIngestionContractTest` that asserts: new endpoint accepts rollup payload, existing artifact outcome endpoint still accepts outcome payload, no data overlap. Note: SkillMeat-side endpoint implementation is out of scope for CCDash — this task authors the client stub and contract test that CCDash will call against the SkillMeat team's implementation. | Client stub method defined and wired. Contract test file authored at `backend/tests/test_skillmeat_rollup_contract.py`. Contract test uses httpretty/respx to mock SkillMeat endpoint. Existing artifact outcome client method unaffected. | 0.5 pts | python-backend-engineer | sonnet | medium | T4-003 |
| T4-005 | Export job wiring | Wire `export_artifact_usage_rollups` into the background scheduler in `backend/adapters/jobs/`. Add `CCDASH_ARTIFACT_ROLLUP_EXPORT_INTERVAL_SECONDS` config (default: 3600). Ensure job only runs when `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED=true`. Add job to `backend/runtime/container.py` alongside existing telemetry export jobs. Log export summary (rollup count, success count, skipped count) per run. | Job registered in scheduler. Config var present with default. Job skips silently when flag disabled. Export summary logged per run. Integration test: job runs and calls `export_artifact_usage_rollups` with correct args. | 0.5 pts | python-backend-engineer | sonnet | medium | T4-003 |

---

## Structured ACs

#### AC T4-002-Privacy-Allowlist: Rollup payload contains no sensitive fields
- target_surfaces:
    - backend/services/integrations/telemetry_exporter.py
    - backend/services/rollup_payload_builder.py
    - backend/tests/test_rollup_privacy.py
- propagation_contract: >
    Every rollup payload passes through AnonymizationVerifier.verify_rollup_payload() before
    being sent to SkillMeat. PrivacyViolationError is raised (and caught/logged) if any
    prohibited field is populated. Prohibited fields defined as an explicit allowlist constant.
- resilience: >
    If AnonymizationVerifier is not initialized (misconfiguration), telemetry_exporter.py
    must refuse to send and log a CRITICAL-level error. The payload must not bypass the guard.
- visual_evidence_required: false
- verified_by:
    - T4-002
    - T4-003

#### AC T4-003-Regression: Existing artifact outcome export unaffected
- target_surfaces:
    - backend/services/integrations/telemetry_exporter.py
- propagation_contract: >
    export_artifact_outcomes() method signature, behavior, and test fixtures must be unchanged.
    New export_artifact_usage_rollups() is a separate method. No shared mutable state between methods.
- resilience: >
    If rollup export fails or is disabled, artifact outcome export continues normally.
    The two export paths are independent code branches.
- visual_evidence_required: false
- verified_by:
    - T4-003

---

## Key Files Affected

- `backend/services/rollup_payload_builder.py` (new)
- `backend/services/integrations/telemetry_exporter.py` — add `export_artifact_usage_rollups`
- `backend/services/integrations/skillmeat_client.py` — add `post_artifact_usage_rollup`
- `backend/adapters/jobs/artifact_rollup_export_job.py` (new) — scheduled export job
- `backend/runtime/container.py` — register artifact rollup export job
- `backend/config.py` — `CCDASH_ARTIFACT_ROLLUP_EXPORT_INTERVAL_SECONDS`, `CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE`, `CCDASH_LOCAL_USER_SCOPE_PSEUDONYM`
- `backend/tests/test_rollup_privacy.py` (new)
- `backend/tests/test_skillmeat_rollup_contract.py` (new)

---

## Quality Gates

- [ ] Rollup payloads correctly built from seeded ranking rows and validate against schema
- [ ] Privacy guard correctly identifies and rejects prohibited fields
- [ ] All clean rollup payloads pass privacy guard verification
- [ ] Existing `export_artifact_outcomes()` method and tests unchanged (regression suite green)
- [ ] Rollup export method sends correct payloads with retry/backoff
- [ ] SkillMeat client stub and contract test authored
- [ ] Background job registered, config var present, job skips when flag disabled
- [ ] Privacy assertion test: mock-populated prohibited fields raise PrivacyViolationError
