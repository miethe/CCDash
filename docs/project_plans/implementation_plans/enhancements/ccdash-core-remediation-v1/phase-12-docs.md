---
schema_version: 2
doc_type: phase_plan
title: "CCDash Core Remediation v1 — Phase 12: Docs Finalization + CHANGELOG + karen"
status: completed
created: 2026-06-10
updated: '2026-06-12'
phase: 12
phase_title: "Docs Finalization + CHANGELOG + karen"
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
entry_criteria:
  - "Phases {4, 5, 9, 10, 11} sealed (per dependency map {4,5,9,10,11} ─▶ 12); all upstream phase quality gates green."
  - "All new flags, columns, and endpoints from Phases 0–11 landed and parity-clean on both backends."
  - "Runtime smoke evidence exists (recorded) for UI-touching phases 3, 5, 6, 11 — or re-executable in this phase."
  - "changelog_required: true confirmed in root plan frontmatter."
exit_criteria:
  - "CHANGELOG [Unreleased] populated with user-facing changes from this program; changelog-sync gap report clean."
  - "feature-surface-architecture.md updated with the session-detail surface and new cache/transport entries."
  - "CLAUDE.md Key Conventions updated (redaction config, coalescing guard, incremental-link default flip, launch-time capture, new columns/endpoints) per progressive-disclosure rules."
  - "Observability freshness probes for watcher liveness added and emitting."
  - "analytics.py:553 per-lifecycle-event in+out sum verified NOT surfaced as a workload total in any dashboard panel."
  - "Runtime smoke for all UI-touching phases (3, 5, 6, 11) recorded or re-executed (R-P4)."
  - "karen end-of-feature pass signed off; task-completion-validator pass on this phase."
---

# Phase 12: Docs Finalization + CHANGELOG + karen

**Plan ID**: `IMPL-2026-06-10-CCDASH-CORE-REMEDIATION` (Phase 12)
**Phase**: 12 of 0–12
**Wave**: 6 (final close-out)
**Related PRD**: `/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md` (§6 FR-21, §11 "Documentation + karen")
**Decisions block**: `.claude/worknotes/ccdash-core-remediation/decisions-block.md` (Phase 12 row, Agent Routing, Model Routing)

## Overview

Phase 12 is the program-closing documentation, observability, and quality-gate phase. It does not introduce new product behavior; it finalizes the operator-facing and agent-facing surfaces for everything shipped in Phases 0–11, adds the watcher-liveness freshness probes called for in the PRD's non-functional observability requirements, performs the one residual analytics display check carried over from the excluded token-undercount work (`analytics.py:553`), and closes the program with a `karen` end-of-feature review on top of `task-completion-validator`.

This phase is mostly documentation (haiku/adaptive per the Model Routing table) with two non-doc tasks: the observability freshness probe (sonnet) and the `analytics.py:553` audit/check (sonnet). Per Plan Generator Rule **R-P4**, because UI-touching phases (3, 5, 6, 11) exist in the program, this phase carries the consolidated runtime-smoke verification task for those surfaces. Quality gate is **karen end-of-feature** (the special gate noted for Phase 12) in addition to the standard `task-completion-validator`.

Context discipline: file paths below are sourced from the decisions block and PRD; source files are not re-opened to author this plan. Subagents read the files themselves at execution time.

## Entry Criteria

See frontmatter `entry_criteria`. In short: the program's behavioral phases must be sealed and parity-clean before docs can describe them accurately, and runtime-smoke evidence for UI phases must exist or be re-runnable.

## Exit Criteria

See frontmatter `exit_criteria`. The phase cannot be marked `completed` until: CHANGELOG present and gap-clean; the three doc surfaces (feature-surface-architecture.md, CLAUDE.md, user/dev guides) updated; freshness probes live; the `analytics.py:553` check signed off; UI-phase runtime smoke recorded; and **karen** signs off end-of-feature.

## Architecture / Files Affected (from decisions block — not re-read)

| Surface | Path | Touched by task |
|---|---|---|
| CHANGELOG | `CHANGELOG.md` | T12-001 |
| Feature surface architecture guide | `docs/guides/feature-surface-architecture.md` | T12-002 |
| Root project conventions | `CLAUDE.md` | T12-003 |
| User/dev guides (redaction, coalescing, external API, launch-capture) | `docs/guides/` (new/updated pages) | T12-004 |
| Observability instrumentation | `backend/observability/otel.py`; watcher liveness emit point in `backend/db/file_watcher.py` (probe wiring only — no behavior change) | T12-005 |
| Analytics double-count audit | `backend/routers/analytics.py` (≈ line 553 per-lifecycle-event in+out sum) + dashboard panels under `components/` (read-only audit) | T12-006 |
| Plan frontmatter close-out | `docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md` + this phase file | T12-007 |
| Project-level skill (`ccdash`) SPEC/workflows for new MCP session tools | `.claude/skills/ccdash/` (SKILL.md/SPEC + workflows) | T12-008 |

Reference `CLAUDE.md` (Key Conventions, Documentation Policy, transport-neutral pattern) and `docs/guides/feature-surface-architecture.md` (cache tiers) by path; do not restate them here.

## Task Table

**Column conventions** (per template): `Estimate` = task size (story points). `Model` = executor. `Effort` = reasoning budget (claude: `adaptive`|`extended`). Routing from decisions block: docs → `documentation-writer`/`changelog-generator` (haiku/adaptive); non-doc executors → sonnet/adaptive. Provider `claude` throughout. Quality gate per task: `task-completion-validator`; phase gate adds **karen** (T12-010).

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| T12-001 | CHANGELOG [Unreleased] | Populate `CHANGELOG.md` `[Unreleased]` with user-facing changes from Phases 0–11 following Keep A Changelog categorization (`.claude/specs/changelog-spec.md`). Cover: cross-project session reads, full session-detail via MCP/CLI/REST + redaction, live link freshness default-on, model/workflow detection columns, unpriced-model flag + Fable pricing, sync coalescing/recent-first, cross-project reconcile/self-heal, Postgres+container readiness, external IntentTree API + OpenAPI, launch-time profile/effort capture. Then run `changelog-sync` gap audit over the program commit range. | AC R12.1 | 1 pt | changelog-generator | haiku | adaptive |
| T12-002 | feature-surface-architecture.md | Update `docs/guides/feature-surface-architecture.md` to document the session-detail surface: `agent_queries/session_detail.py` as single source of truth; REST/MCP/CLI as thin transports; cursor-pagination envelope `{items,cursor,limit,nextCursor}`; redaction-layer placement; cache-tier note for the new bundle endpoints (server `@memoized_query` TTL + client TQ staleTime). | AC R12.2 | 0.5 pts | documentation-writer | haiku | adaptive |
| T12-003 | CLAUDE.md conventions | Add pointer-layer Key-Conventions entries (≤3 lines each, progressive disclosure) for: redaction config env vars; sync coalescing guard (project_id-keyed, in-proc + durable); `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` default flip to True; launch-time capture sidecar convention; new detection/pricing/capture columns + dual-DDL+parity rule reminder; new `/api/v1/sessions/{id}/detail` + transcript endpoints; capability-advertisement endpoint. Each entry points to the detailed guide, not inline detail. | AC R12.3 | 0.5 pts | documentation-writer | haiku | adaptive |
| T12-004 | User/dev guides | Create/refresh focused guides under `docs/guides/` for operator surfaces lacking a home: redaction tuning (env patterns, local-trust scope); sync coalescing/recent-first behavior; external `/api/v1` (CORS/bind/auth model, OpenAPI location, example-client pointer); launch-time capture setup (`~/ica-claude.sh` wrapper / sidecar). Concise, usage-focused. | AC R12.4 | 1 pt | documentation-writer | haiku | adaptive |
| T12-005 | Observability freshness probes | Add watcher-liveness freshness probes via `backend/observability/otel.py`: emit a gauge/log for last-watcher-event age per project and a reconcile-heartbeat signal (consuming Phase 8's reconcile/self-heal). Probe wiring only — no watcher behavior change. Confirm redaction-event log shape (count only, no payload) consistent with PRD §6.2 Observability. | AC R12.5 | 1 pt | python-backend-engineer | sonnet | adaptive |
| T12-006 | analytics.py:553 double-count check | Audit `backend/routers/analytics.py` (≈ line 553 per-lifecycle-event in+out sum) and all dashboard panels consuming analytics output; verify this per-event in+out sum is NOT surfaced as a workload/total token metric in any panel. If surfaced, file a finding and add the minimal display correction; otherwise record the negative result. Token-undercount fix itself is out of scope (shipped 2026-03-09). | AC R12.6 | 0.5 pts | python-backend-engineer | sonnet | adaptive |
| T12-007 | Plan + phase frontmatter close-out | Set root plan `status: completed`; populate `commit_refs`, `files_affected`, `updated`; set `changelog_ref: CHANGELOG.md`; advance this phase file to reflect completion. Confirm `deferred_items_spec_refs` and `findings_doc_ref` correct (N/A if none). | AC R12.7 | 0.5 pts | documentation-writer | haiku | adaptive |
| T12-008 | `ccdash` skill SPEC + workflows | Update the project-level `ccdash` skill (`.claude/skills/ccdash/`) for the new MCP session tools (`session_search`/`session_detail`/`session_transcript`) and cross-project detail capability: SPEC Capability-Coverage matrix, SPEC Changelog + `updated` date, affected workflow docs, skills-index version bump if applicable. Skip with "N/A" only if no `ccdash` skill domain is touched (it is). | AC R12.8 | 1 pt | ai-artifacts-engineer | sonnet | adaptive |
| T12-009 | Runtime smoke (UI phases 3, 5, 6, 11) | R-P4 consolidated runtime-smoke verification. With dev server up, browser-smoke each UI surface delivered by Phases 3/5/6/11 and confirm recorded evidence exists or re-execute. If runtime unavailable, this phase cannot be `completed` without an explicit `runtime_smoke: skipped` field + reason (per CLAUDE.md Runtime smoke gate); unit-test pass is not a substitute. | AC R12.9 | 0.5 pts | task-completion-validator | sonnet | adaptive |
| T12-010 | karen end-of-feature pass | Run `karen` end-of-feature review across the whole program: validate CHANGELOG/guides/CLAUDE.md/skill SPEC reflect shipped reality (no aspirational claims), every PRD §11 Definition-of-Done item is checkable, and no doc overstates capability. Sign-off blocks phase `completed`. | AC R12.10 | 0.5 pts | karen | sonnet | adaptive |

**Total Phase 12 estimate**: ~7.5 pts (PRD anchor ~3 pts covers the doc core; +observability probe, +analytics audit, +skill SPEC, +runtime-smoke/karen gates as H6 plumbing).

## Acceptance Criteria

Structured ACs (per `ac-schema.md`) are used for cross-surface / resilience / runtime-smoke criteria; prose ACs cover single-surface doc tasks.

#### AC R12.1: CHANGELOG [Unreleased] complete and gap-clean
- CHANGELOG.md `[Unreleased]` contains entries covering every user-facing change from Phases 0–11, correctly categorized (Added/Changed/Fixed) per `.claude/specs/changelog-spec.md`.
- `changelog-sync` gap audit over the program commit range returns no uncovered non-trivial commits (exit clean).
- `changelog_ref` frontmatter set to `CHANGELOG.md` (handled in T12-007).
- verified_by:
    - T12-010
    - T12-009

#### AC R12.2: feature-surface-architecture.md documents the session-detail surface
- `docs/guides/feature-surface-architecture.md` names `agent_queries/session_detail.py` as single source of truth and documents REST/MCP/CLI as thin transports, the `{items,cursor,limit,nextCursor}` envelope, redaction placement, and cache-tier behavior for the new bundle endpoint.
- Doc claims match shipped behavior (no analytics-only stub language remains for the detail path).
- verified_by:
    - T12-010

#### AC R12.3: CLAUDE.md conventions updated under progressive disclosure
- target_surfaces:
    - CLAUDE.md
- propagation_contract: >
    Each new convention (redaction env vars, coalescing guard, incremental-link default flip,
    launch-time capture sidecar, new columns + dual-DDL parity reminder, new /api/v1 detail+transcript
    endpoints, capability-advertisement endpoint) is added as a ≤3-line pointer entry in Key Conventions,
    each linking to the detailed guide rather than inlining detail.
- resilience: >
    Not a runtime field — documentation-only AC. N/A.
- visual_evidence_required: false
- verified_by:
    - T12-010

#### AC R12.4: User/dev guides cover new operator surfaces
- Guides exist under `docs/guides/` for redaction tuning, sync coalescing/recent-first, external `/api/v1` (CORS/bind/auth + OpenAPI + example-client pointer), and launch-time capture setup.
- Each guide is usage-focused and concise; cross-links from CLAUDE.md pointers (R12.3) resolve.
- verified_by:
    - T12-010

#### AC R12.5: Watcher-liveness freshness probes emit
- target_surfaces:
    - backend/observability/otel.py
    - backend/db/file_watcher.py
- propagation_contract: >
    A per-project last-watcher-event-age gauge/log and a reconcile-heartbeat signal are emitted through
    backend/observability/otel.py; the reconcile heartbeat consumes the Phase 8 reconcile/self-heal loop
    without modifying watcher behavior. Redaction-event logs emit count only (no payload contents).
- resilience: >
    If a project has no watcher activity yet, the probe emits a defined "no events observed" state
    (null/sentinel age) rather than failing or omitting the metric; reconcile heartbeat still fires on cadence.
- visual_evidence_required: false
- verified_by:
    - T12-009
    - T12-010

#### AC R12.6: analytics.py:553 not surfaced as a workload total
- The per-lifecycle-event in+out sum at `backend/routers/analytics.py` (≈ line 553) is confirmed NOT presented as a workload/total token metric in any dashboard panel; result recorded (negative finding acceptable).
- If a panel surfaces it, a finding is filed and a minimal display correction lands in this phase.
- Token-undercount fix is explicitly out of scope (already shipped 2026-03-09).
- verified_by:
    - T12-009
    - T12-010

#### AC R12.7: Plan and phase frontmatter finalized
- Root plan frontmatter: `status: completed`, `updated` bumped, `commit_refs`/`files_affected` populated, `changelog_ref: CHANGELOG.md`.
- `deferred_items_spec_refs` and `findings_doc_ref` are correct (explicit N/A if none).
- verified_by:
    - T12-010

#### AC R12.8: ccdash skill SPEC + workflows current
- `.claude/skills/ccdash/` SPEC Capability-Coverage matrix and Changelog reflect the new MCP session tools (`session_search`/`session_detail`/`session_transcript`) and cross-project detail capability; `updated` date bumped; affected workflows refreshed; skills-index version bumped if applicable.
- verified_by:
    - T12-010

#### AC R12.9: Runtime smoke recorded for UI phases 3, 5, 6, 11 (R-P4)
- target_surfaces:
    # Surfaces delivered by upstream UI phases; smoke each via browser with dev server up.
    - components/  # Phase 5 detection-column FE fallback states
    - components/  # Phase 6 unpriced-cost indicator state
    - components/  # Phase 11 profile/effort field FE fallbacks
- propagation_contract: >
    Dev server is started; each UI surface from Phases 3 (MCP-backed detail verified via client smoke),
    5, 6, 11 is exercised in a browser and its recorded smoke evidence is confirmed present, or the smoke
    is re-executed in this phase. Evidence is attached to the relevant phase progress files.
- resilience: >
    For each optional backend field introduced in Phases 5/6/11, the corresponding surface renders a defined
    fallback (disabled-with-tooltip or "unpriced"/"profile unknown" placeholder) when the field is null/absent —
    missing is a contract state, not an error. If runtime is unavailable, the phase records
    runtime_smoke: skipped with a reason; a unit-test pass is NOT a substitute.
- visual_evidence_required: browser smoke evidence per surface (screenshot or recorded note) at desktop ≥1440px
- verified_by:
    - T12-009

#### AC R12.10: karen end-of-feature sign-off
- `karen` reviews the full program close-out and confirms docs/CHANGELOG/CLAUDE.md/skill SPEC describe only shipped reality, every PRD §11 Definition-of-Done item is checkable, and no surface overstates capability.
- karen sign-off is recorded; phase `completed` is blocked without it.
- verified_by:
    - T12-010

## Quality Gates

- [ ] `task-completion-validator` pass on all Phase 12 tasks.
- [ ] **karen end-of-feature** pass (special gate for Phase 12 per decisions block Agent Routing).
- [ ] CHANGELOG `[Unreleased]` present and `changelog-sync` gap-clean (R12.1).
- [ ] feature-surface-architecture.md, CLAUDE.md, and user/dev guides updated (R12.2–R12.4).
- [ ] Watcher freshness probes emitting (R12.5).
- [ ] `analytics.py:553` audit recorded (R12.6).
- [ ] Plan + skill frontmatter finalized (R12.7, R12.8).
- [ ] Runtime smoke for UI phases 3, 5, 6, 11 recorded or re-executed, or `runtime_smoke: skipped` with reason (R12.9, R-P4).

## Dependencies

- **Upstream**: `{4, 5, 9, 10, 11} ─▶ 12` (decisions block dependency map). Phase 12 is wave 6, after all behavioral phases seal.
- **Downstream**: None — this phase closes the program. Wrap-up (feature guide + PR) follows per the plan template's post-implementation close-out.

## Notes

- Model Routing (decisions block): docs tasks haiku/adaptive; non-doc executors sonnet/adaptive; no external-model tasks in this phase. karen and task-completion-validator carry their own model via agent definitions.
- Documentation Policy (CLAUDE.md): allowed targets only (`/docs/`, CHANGELOG.md, CLAUDE.md pointer entries, skill SPEC/workflows, plan/phase frontmatter). No standalone debugging/summary/report markdown files.
- Progress tracking: `.claude/progress/ccdash-core-remediation/phase-12-progress.md`.
