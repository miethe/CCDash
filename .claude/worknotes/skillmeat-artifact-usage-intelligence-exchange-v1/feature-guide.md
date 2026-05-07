---
title: SkillMeat Artifact Usage Intelligence Exchange Feature Guide
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
doc_type: feature_guide
status: active
created: 2026-05-07
updated: 2026-05-07
---

# SkillMeat Artifact Usage Intelligence Exchange

## What Was Built

CCDash now exchanges SkillMeat project artifact snapshots, stores and resolves artifact identities, computes artifact rankings and advisory optimization recommendations, exports aggregate artifact usage rollups, and exposes the results through Analytics, Workflow Effectiveness, Execution Workbench, Settings, CLI, and MCP surfaces.

## Architecture Overview

- Snapshot ingestion starts in `backend/services/integrations/skillmeat_client.py`, persists through `ArtifactSnapshotRepository`, and maps observed CCDash artifacts with `ArtifactIdentityMapper`.
- Ranking and recommendation reads are computed by `backend/services/artifact_ranking_service.py` and `backend/services/artifact_recommendation_service.py`, then exposed through transport-neutral agent queries in `backend/application/services/agent_queries/artifact_intelligence.py`.
- Rollup export is worker-side and additive: `backend/services/rollup_payload_builder.py` builds aggregate payloads, `AnonymizationVerifier` checks privacy, and `backend/services/integrations/telemetry_exporter.py` posts through the SkillMeat client.
- UI and operator access use the same backend contracts through Analytics rankings, Workflow Effectiveness artifact contribution, Execution Workbench recommendations, Settings snapshot health, `ccdash artifact` commands, and the `artifact_recommendations` MCP tool.

## How to Test

```bash
backend/.venv/bin/python -m pytest backend/tests/test_artifact_intelligence_phase6_contracts.py backend/tests/test_artifact_intelligence_privacy_audit.py backend/tests/test_rollup_privacy.py -q
python .claude/skills/artifact-tracking/scripts/validate_artifact.py -f .claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/phase-6-progress.md
python .claude/skills/artifact-tracking/scripts/validate_artifact.py -f docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
git diff --check -- .claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/phase-6-progress.md docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md CLAUDE.md .claude/worknotes/skillmeat-artifact-usage-intelligence-exchange-v1/feature-guide.md
```

## Test Coverage Summary

- Contract coverage verifies snapshot fetch/store/query, ranking filters, recommendation types, rollup export shape, and artifact outcome backward compatibility.
- Privacy coverage verifies rollup allowlists, prohibited field names and aliases, sensitive allowed-field values, local user scope pseudonym/omit behavior, and snapshot/rollup log redaction.
- Calibration coverage is fixture-based: the v1 report reviews 10 seeded recommendation scenarios and documents confidence and staleness behavior.
- Phase 6 focused validation result: `38 passed, 15 subtests passed in 0.91s`.

## Known Limitations

- Recommendations are advisory only; CCDash does not mutate SkillMeat artifacts or project load modes.
- Production precision is not yet established because calibration uses synthetic seeded fixtures rather than labeled production outcomes.
- Per-user local rollups, recommendation review outcomes as training signals, and non-deployed collection rankings are deferred to shaping design specs.
- Phase 5 runtime browser smoke was intentionally skipped in the earlier command-line closeout and remains a release-readiness caveat for UI confidence.
