---
schema_version: 2
doc_type: implementation_plan
title: "Implementation Plan: SkillMeat Artifact Usage Intelligence Exchange V1"
description: "Phased plan for snapshot exchange, artifact rankings, optimization recommendations, and project/user/collection rollup export between CCDash and SkillMeat."
status: completed
created: 2026-05-07
updated: 2026-05-07
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
feature_version: v1
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: null
scope: "Add SkillMeat project artifact snapshot exchange, multi-dimensional artifact rankings, 7-type advisory recommendations, project/user/collection rollup export, and 5 UI/skill surfaces to CCDash."
effort_estimate: "34 pts"
architecture_summary: "Extends existing telemetry_exporter + skillmeat_client stack with new snapshot/rollup schemas, identity-resolution layer, ranking/recommendation engine, and analytics surfaces."
related_documents:
  - docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
  - docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
  - docs/project_plans/implementation_plans/integrations/ccdash-telemetry-exporter-v1.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md
references:
  context:
    - backend/services/integrations/telemetry_exporter.py
    - backend/services/integrations/skillmeat_client.py
    - backend/services/session_usage_analytics.py
    - backend/services/workflow_effectiveness.py
    - backend/services/stack_observations.py
    - backend/routers/analytics.py
    - backend/routers/agent.py
    - backend/mcp/server.py
    - types.ts
  specs:
    - .claude/skills/planning/references/ac-schema.md
  related_prds:
    - docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
spike_ref: null
adr_refs: []
deferred_items_spec_refs:
  - docs/project_plans/design-specs/skillmeat-per-user-rollup-local-mode.md
  - docs/project_plans/design-specs/skillmeat-recommendation-training-signals.md
  - docs/project_plans/design-specs/skillmeat-collection-rankings-non-deployed.md
findings_doc_ref: null
charter_ref: null
changelog_ref: CHANGELOG.md
changelog_required: true
test_plan_ref: null
plan_structure: independent
progress_init: auto
owner: platform-engineering
contributors: []
priority: high
risk_level: high
category: integrations
tags: [implementation, integrations, skillmeat, artifacts, rankings, recommendations, rollup, export]
milestone: null
commit_refs:
  - 10c6f70
  - 7a32e0e
  - 53d990b
  - c564a7e
  - e09530d
  - bfebfd4
  - 60483bd
  - c08d1e2
  - 8b96c7f
  - 2a8e72c
  - 97ca544
  - 408ab06
  - 003dff9
  - 170e31f
  - 958e1b2
  - 2ee6dbf
pr_refs: []
files_affected:
  - .claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/phase-1-progress.md
  - .claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/phase-2-progress.md
  - .claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/phase-3-progress.md
  - .claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/phase-4-progress.md
  - .claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/phase-5-progress.md
  - .claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/phase-6-progress.md
  - .claude/worknotes/skillmeat-artifact-usage-intelligence-exchange-v1/feature-guide.md
  - .env.example
  - CHANGELOG.md
  - CLAUDE.md
  - backend/adapters/jobs/__init__.py
  - backend/adapters/jobs/artifact_rollup_export_job.py
  - backend/adapters/jobs/runtime.py
  - backend/adapters/storage/base.py
  - backend/adapters/storage/enterprise.py
  - backend/adapters/storage/local.py
  - backend/application/ports/core.py
  - backend/application/services/agent_queries/__init__.py
  - backend/application/services/agent_queries/artifact_intelligence.py
  - backend/application/services/agent_queries/models.py
  - backend/cli/commands/artifact.py
  - backend/cli/main.py
  - backend/config.py
  - backend/data_domain_layout.py
  - backend/data_domains.py
  - backend/db/factory.py
  - backend/db/postgres_migrations.py
  - backend/db/repositories/__init__.py
  - backend/services/integrations/skillmeat_client.py
  - backend/services/integrations/telemetry_exporter.py
  - backend/services/artifact_ranking_service.py
  - backend/services/artifact_recommendation_service.py
  - backend/services/identity_resolver.py
  - backend/db/repositories/artifact_snapshot_repository.py
  - backend/db/repositories/base.py
  - backend/db/repositories/artifact_ranking_repository.py
  - backend/db/repositories/postgres/artifact_snapshot_repository.py
  - backend/db/repositories/postgres/artifact_ranking_repository.py
  - backend/db/sqlite_migrations.py
  - backend/mcp/tools/__init__.py
  - backend/mcp/tools/artifacts.py
  - backend/models.py
  - backend/routers/analytics.py
  - backend/routers/agent.py
  - backend/runtime/container.py
  - backend/services/agentic_intelligence_flags.py
  - backend/services/rollup_payload_builder.py
  - backend/services/telemetry_transformer.py
  - backend/tests/test_agent_queries_artifact_intelligence.py
  - backend/tests/test_agent_router.py
  - backend/tests/test_analytics_router.py
  - backend/tests/test_artifact_intelligence_feature_flag.py
  - backend/tests/test_artifact_intelligence_phase6_contracts.py
  - backend/tests/test_artifact_intelligence_privacy_audit.py
  - backend/tests/test_artifact_intelligence_schemas.py
  - backend/tests/test_artifact_ranking_calibration.py
  - backend/tests/test_artifact_ranking_repository.py
  - backend/tests/test_artifact_ranking_service.py
  - backend/tests/test_artifact_recommendation_service.py
  - backend/tests/test_artifact_rollup_exporter.py
  - backend/tests/test_artifact_snapshot_repository.py
  - backend/tests/test_ccdash_artifact_usage_rollup_contract.py
  - backend/tests/test_cli_commands.py
  - backend/tests/test_identity_resolver.py
  - backend/tests/test_mcp_server.py
  - backend/tests/test_migration_governance.py
  - backend/tests/test_rollup_payload_builder.py
  - backend/tests/test_rollup_privacy.py
  - backend/tests/test_skillmeat_artifact_snapshot_contract.py
  - backend/tests/test_skillmeat_client.py
  - backend/tests/test_skillmeat_rollup_contract.py
  - backend/tests/test_snapshot_ingestion.py
  - backend/tests/test_sqlite_migrations.py
  - backend/tests/test_storage_adapter_composition.py
  - types.ts
  - components/Analytics/AnalyticsDashboard.tsx
  - components/Analytics/ArtifactRankingsView.tsx
  - components/FeatureExecutionWorkbench.tsx
  - components/Settings.tsx
  - components/Workflows/WorkflowEffectivenessSurface.tsx
  - components/__tests__/ArtifactRankingsView.test.tsx
  - components/__tests__/ExecutionWorkbenchRecommendations.test.ts
  - components/execution/ArtifactContributionPanel.tsx
  - components/execution/ExecutionWorkbenchRecommendations.tsx
  - docs/guides/artifact-intelligence-calibration-report-v1.md
  - docs/guides/artifact-intelligence-operator-guide.md
  - docs/guides/artifact-intelligence-privacy-audit.md
  - docs/project_plans/design-specs/skillmeat-collection-rankings-non-deployed.md
  - docs/project_plans/design-specs/skillmeat-per-user-rollup-local-mode.md
  - docs/project_plans/design-specs/skillmeat-recommendation-training-signals.md
  - docs/schemas/integrations/ccdash-artifact-usage-rollup-v1.sample.json
  - docs/schemas/integrations/ccdash-artifact-usage-rollup-v1.schema.json
  - docs/schemas/integrations/skillmeat-artifact-snapshot-v1.sample.json
  - docs/schemas/integrations/skillmeat-artifact-snapshot-v1.schema.json
  - services/__tests__/apiClient.test.ts
  - services/__tests__/artifactIntelligenceTypes.test.ts
  - services/analytics.ts
  - services/apiClient.ts
---

# Implementation Plan: SkillMeat Artifact Usage Intelligence Exchange V1

**Plan ID**: `IMPL-2026-05-07-SKILLMEAT-ARTIFACT-USAGE-INTELLIGENCE-EXCHANGE-V1`
**Date**: 2026-05-07
**Author**: implementation-planner (sonnet)
**Human Brief**: N/A — not created (feature estimated at 34 pts; brief recommended but omitted — estimation sanity check embedded below)
**Related Documents**:
- **PRD**: `docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md`
- **Decisions Block**: `.claude/worknotes/skillmeat-artifact-usage-intelligence-exchange-v1/decisions-block.md`
- **Lineage Parent**: `docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md`

**Complexity**: XL (34 pts, 6 phases, cross-system integration)
**Total Estimated Effort**: 34 story points
**Target Timeline**: 5–7 weeks

---

## Executive Summary

This plan delivers the CCDash↔SkillMeat artifact intelligence feedback loop in six serial phases: (1) contract and schema foundation, (2) snapshot ingestion and identity mapping, (3) ranking and recommendation engine, (4) rollup export back to SkillMeat, (5) five UI and skill surfaces, and (6) validation, privacy review, and documentation. The critical path is strictly serial — each phase depends on the prior — with intra-phase parallelism in P1 (BE schemas vs FE types) and P5 (Analytics vs Settings vs MCP). Success is defined as: snapshot fetched and stored, rankings queryable by all dimensions, recommendations advisory-only with evidence and confidence, rollup export non-regressive, and `ccdash` skill returning concise recommendations.

---

## Implementation Strategy

### Architecture Sequence

This feature follows the CCDash layered architecture:

1. **Contract & Schema** — JSON schemas (snapshot + rollup), Pydantic DTOs, TypeScript types, backward-compat shims
2. **Snapshot Ingestion** — `skillmeat_client.py` snapshot fetch, DB tables (`artifact_snapshot_cache`, `artifact_identity_map`), repository, sync wiring
3. **Ranking & Recommendation Engine** — `artifact_ranking_service.py`, `artifact_recommendation_service.py`, `identity_resolver.py`, confidence gating
4. **Rollup Export** — Extend `telemetry_exporter.py` with rollup payload builder and SkillMeat additive ingestion contract
5. **UI & Skill Surfaces** — Analytics rankings view, Workflow Effectiveness artifact contribution, Execution Workbench recommendations, Settings snapshot health, `ccdash` MCP/CLI query
6. **Validation & Docs** — Contract tests, seeded fixture tests, calibration, privacy audit, operator docs, CHANGELOG

### Parallel Work Opportunities

- **P1**: BE schema (python-backend-engineer) and FE TS type generation (ui-engineer-enhanced) can run in parallel — no file overlap.
- **P5**: Analytics surface, Settings panel, and MCP/CLI query can parallelize — distinct component owners, no shared state mutations.
- **P6**: Contract tests, privacy audit, and operator docs can parallelize — independent verification activities.

### Critical Path

```
P1 (Contract) → P2 (Ingestion) → P3 (Ranking/Recs) → P4 (Export) → P5 (UI) → P6 (Validation)
```

P3 is the highest-risk phase (algorithmic, 8 pts). If P3 exceeds estimate by >50%, split into P3a (ranking) and P3b (recommendations) per the decisions block escalation note.

### Phase Summary

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| 1 | Contract & Schema Foundation | 5 pts | python-backend-engineer, ui-engineer-enhanced | sonnet | Parallel: BE schemas ∥ FE TS types |
| 2 | Snapshot Ingestion & Storage | 6 pts | python-backend-engineer, data-layer-expert | sonnet | Identity mapping tables; integration_owner: python-backend-engineer |
| 3 | Ranking & Recommendation Engine | 8 pts | python-backend-engineer, backend-architect | sonnet | Algorithmic (H3); karen review at phase exit |
| 4 | Rollup Export & SkillMeat Persistence | 5 pts | python-backend-engineer | sonnet | Extends existing telemetry exporter |
| 5 | UI & Skill Surfaces | 6 pts | ui-engineer-enhanced, frontend-developer | sonnet | R-P4: runtime smoke required; integration_owner: ui-engineer-enhanced |
| 6 | Validation, Privacy & Docs | 4 pts | task-completion-validator, documentation-writer | sonnet / haiku | Parallel: tests ∥ privacy audit ∥ docs |
| **Total** | — | **34 pts** | — | — | — |

---

### Estimation Sanity Check

**Noun count (H1)**: ~4 new first-class domain concepts (`artifact_snapshot_cache`, `artifact_identity_map`, `artifact_ranking`, `artifact_recommendation`) → ≥8 pt floor before services and UI.

**Dual-impl multiplier (H2)**: N/A — CCDash uses a single async DB backend abstracted by connection.py; no dual-repository pattern applies here.

**Algorithmic flag (H3)**: Three flagged services:
- `artifact_ranking_service.py` — multi-dimensional aggregation with ranking algebra (ranking + weighted dimensions)
- `artifact_recommendation_service.py` — 7-type classifier with confidence gating and staleness logic
- `identity_resolver.py` — 3-tier resolution (UUID match → alias fuzzy match → unresolved quarantine)
Budgeted at 8 pts (P3) + ~2 pts embedded in P2 (identity mapping).

**Bundle decomposition (H4)**:

| Capability Area | Independent Estimate | Notes |
|----------------|---------------------|-------|
| Snapshot exchange (P1+P2) | 11 pts | Schema + fetch + store + identity mapping |
| Ranking & recommendations (P3) | 8 pts | Algorithmic core, 3 algorithmic services |
| Rollup export (P4) | 5 pts | Extends existing exporter, additive payloads |
| UI & skill surfaces (P5) | 6 pts | 5 surfaces (Analytics, WF, Execution, Settings, MCP/CLI) |
| Validation & docs (P6) | 4 pts | Contract tests, privacy audit, operator docs |
| **Σ** | **34 pts** | |

**Anchor (H5)**: `ccdash-telemetry-exporter` (PRD: `docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md`) cost ~28 pts over 4 phases. This plan adds 3 algorithmic services, 5 UI surfaces, and a cross-system identity resolution layer beyond the exporter scope — 34 pts (+21%) is within range given wider surface area.

**Plumbing budget (H6)**: ~5 pts (~15% of 34) embedded across phases for DTOs, DI wiring, feature flags (`CCDASH_ARTIFACT_INTELLIGENCE_ENABLED`), OpenAPI schema updates, config entries, CHANGELOG, and `context_files` updates.

**Bottom-up total**: 34 pts
**Top-down intuition**: 30–35 pts (5–7 week timeline per PRD)
**Locked estimate**: 34 pts

---

## Architecture Decisions

### OQ-1: Snapshot Endpoint Strategy

**Resolution**: Use a new dedicated `/api/v1/project-artifact-snapshot` endpoint on the SkillMeat side rather than composing from multiple existing endpoints. Rationale: composing from artifact/workflow/context/bundle endpoints would require N round-trips, risk partial failures, and produce an incoherent freshness timestamp. A single snapshot endpoint allows SkillMeat to return a consistent, atomically-generated artifact inventory with a single `generatedAt` timestamp, which is required for staleness tracking. CCDash should treat this endpoint as the canonical snapshot contract.

If SkillMeat cannot expose the dedicated endpoint in V1, CCDash should fall back to composing from existing project detail APIs and set `snapshot_source: composed` in the freshness metadata. This fallback adds ~1 pt to P2 scope.

### OQ-2: `context_pressure` Calculation

**Resolution**: `context_pressure` is computed from observed token attribution only in V1. Observed tokens are ground truth — they reflect what the model actually consumed from this artifact in recorded sessions. Static artifact size metadata from the SkillMeat snapshot is not yet a reliable proxy for actual context window contribution (compression, caching, and partial loads make static size misleading). A future V2 enhancement can incorporate `static_context_bytes` from the snapshot as a secondary signal once the correlation is validated empirically. The `context_pressure` field definition is: `exclusive_tokens / avg_context_window_tokens_per_session` where the denominator is derived from session telemetry.

### OQ-3: Cold-Start Handling

**Resolution**: When a project has a valid snapshot but fewer than `CCDASH_RANKING_MIN_SAMPLE_SIZE` (default: 3) sessions attributing to a given artifact, that artifact's ranking row should be populated with `sample_size: N` and `confidence: null`, and all recommendation types except `insufficient_data` and `identity_reconciliation` should be suppressed. The `insufficient_data` recommendation fires automatically for artifacts with 0 attributed sessions in the configured lookback period (default: 30d). This ensures cold-start projects see the snapshot coverage without generating premature recommendations.

### OQ-4: P3 Phase Split Decision

**Resolution**: Keep P3 as a single phase but define two internal batches: `batch_1` (ranking computation: identity resolver + ranking service) and `batch_2` (recommendation classifier: recommendation service + API exposure). This intra-phase split preserves the phase boundary structure while allowing the backend-architect reviewer to checkpoint between algorithmic components. If P3 batch_1 comes in >50% over estimate during execution, the orchestrator should escalate to a full phase split.

### OQ-5: Snapshot Freshness Thresholds by Recommendation Type

**Resolution**:

| Recommendation Type | Max Snapshot Age | Rationale |
|--------------------|-----------------|-----------|
| `disable_candidate` | 7 days | Destructive — requires very fresh inventory to avoid false positives |
| `workflow_specific_swap` | 7 days | Comparisons across versions require current version availability |
| `load_on_demand` | 14 days | Advisory but affects workflow design — moderate freshness required |
| `version_regression` | 14 days | Version comparison needs current deployment data |
| `optimization_target` | 30 days | Improvement target doesn't require near-real-time inventory |
| `identity_reconciliation` | 30 days | Identity issues persist across snapshot ages |
| `insufficient_data` | 30 days | Data sufficiency check is not inventory-sensitive |

These thresholds should be configurable via `CCDASH_SNAPSHOT_FRESHNESS_*` env vars per type.

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items Triage Table

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| DF-001 | design | OQ-2 (PRD): per-user rollups in local mode — privacy-preserving pseudonymous scope is partial; full per-user rollup needs user identity design | Per-user identity design approved for local mode | docs/project_plans/design-specs/skillmeat-per-user-rollup-local-mode.md |
| DF-002 | design | OQ-4 (PRD): recommendation review outcomes as training signals — requires SkillMeat-side write-back API and review workflow | SkillMeat review-outcome ingestion endpoint available; privacy contract defined | docs/project_plans/design-specs/skillmeat-recommendation-training-signals.md |
| DF-003 | design | OQ-5 (PRD): collection-level rankings for artifacts not deployed in project — scope and filtering semantics undefined for non-deployed artifacts | Collection ranking scope decision recorded in ADR | docs/project_plans/design-specs/skillmeat-collection-rankings-non-deployed.md |

*Design-spec authoring tasks for DF-001, DF-002, and DF-003 were completed during Phase 6 (T6-006). The three paths above are now populated in `deferred_items_spec_refs`.*

### In-Flight Findings

**Lazy-creation rule**: Findings doc is not pre-created. Create `.claude/findings/skillmeat-artifact-usage-intelligence-exchange-v1-findings.md` on the first real finding during execution and set `findings_doc_ref` in this plan's frontmatter.

### Quality Gate

Phase 6 cannot be sealed until: all three deferred items have design-spec paths in `deferred_items_spec_refs`, OR are explicitly re-marked N/A with rationale; and findings doc (if created) is advanced to `status: accepted`.

---

## Risk Mitigation

| Risk | Severity | Mitigation |
|------|----------|------------|
| Artifact identity resolution mismatches produce incorrect rankings | High | Three-tier resolution (UUID/hash → alias fuzzy → unresolved quarantine). Seeded fixture tests with known mismatch scenarios in P2 and P3. |
| Privacy leakage in rollup export payloads | High | `AnonymizationVerifier` guard extended to cover rollup fields. Explicit field-level allowlist. Privacy assertion tests on every export payload shape in P4 and P6. |
| Recommendation aggression harms users | Medium | V1 is strictly advisory — no automatic mutations. Evidence, confidence ≥ threshold, adequate sample size, and fresh snapshot all required. Stale-snapshot recommendations suppressed (OQ-5 thresholds). |
| Snapshot staleness creates false "unused" artifact recommendations | Medium | Freshness metadata on every ranking/recommendation. Configurable thresholds by recommendation type (OQ-5). Stale snapshots suppress destructive types. Diagnostics surface in Settings. |
| Existing telemetry exporter regression in P4 | Medium | Additive contract — new rollup fields are optional. Existing artifact outcome tests pinned as regression suite. Backward-compat assertion in P1 schema work. |
| P3 ranking algebra complexity exceeds estimate | Medium | Backend-architect review checkpoint between P3 batch_1 and batch_2. Escalation path to opus for ranking algebra if blocked. karen review at P3 exit. |

---

## Phase Breakdown Index

| Phase | File | Estimate |
|-------|------|----------|
| Phase 1: Contract & Schema Foundation | [phase-1-contract-schema.md](./skillmeat-artifact-usage-intelligence-exchange-v1/phase-1-contract-schema.md) | 5 pts |
| Phase 2: Snapshot Ingestion & Storage | [phase-2-snapshot-ingestion.md](./skillmeat-artifact-usage-intelligence-exchange-v1/phase-2-snapshot-ingestion.md) | 6 pts |
| Phase 3: Ranking & Recommendation Engine | [phase-3-ranking-recommendations.md](./skillmeat-artifact-usage-intelligence-exchange-v1/phase-3-ranking-recommendations.md) | 8 pts |
| Phase 4: Rollup Export & SkillMeat Persistence | [phase-4-rollup-export.md](./skillmeat-artifact-usage-intelligence-exchange-v1/phase-4-rollup-export.md) | 5 pts |
| Phase 5: UI & Skill Surfaces | [phase-5-ui-skill-surfaces.md](./skillmeat-artifact-usage-intelligence-exchange-v1/phase-5-ui-skill-surfaces.md) | 6 pts |
| Phase 6: Validation, Privacy & Docs | [phase-6-validation-docs.md](./skillmeat-artifact-usage-intelligence-exchange-v1/phase-6-validation-docs.md) | 4 pts |

---

## Reviewer Gates

Per Tier 3 requirements:

- **P3 exit** (algorithmic core complete): `karen` mandatory review before P4 begins.
- **P6 exit** (feature complete): `karen` mandatory review before PR is opened.
- **Each phase exit**: `task-completion-validator` confirms quality gates before next phase.

---

## Wrap-Up: Feature Guide & PR

After all six phases seal:

1. Delegate to `documentation-writer` (haiku) to create `.claude/worknotes/skillmeat-artifact-usage-intelligence-exchange-v1/feature-guide.md` with: What Was Built, Architecture Overview, How to Test, Test Coverage Summary, Known Limitations.
2. Open PR using `gh pr create` with summary bullets derived from this plan's Executive Summary and the CHANGELOG entry from P6.

---

**Progress Tracking**: `.claude/progress/skillmeat-artifact-usage-intelligence-exchange-v1/`
