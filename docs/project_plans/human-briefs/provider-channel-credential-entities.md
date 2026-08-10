---
schema_name: ccdash_document
schema_version: 2

doc_type: human_brief
doc_subtype: feature_brief
root_kind: project_plans

id: "BRIEF-provider-channel-credential-entities"
title: "Provider, Channel & Credential Entities — Human Brief"
status: draft
category: human-briefs

feature_slug: provider-channel-credential-entities
feature_family: provider-channel-credential-entities
feature_version: v1

prd_ref: docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/provider-channel-credential-entities-v1.md
intent_ref: null
epic_ref: null

related_documents: []

owner: nick
contributors: []

audience: [humans]

priority: medium
confidence: 0.65

created: 2026-08-10
updated: 2026-08-10
target_release: ""

tags: [human-brief, provider-identity, entity-model, credentials, cost-attribution]
---

# Provider, Channel & Credential Entities — Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-08-10

---

## 1. Context Pointers

- **PRD**: `docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md`
- **Plan**: `docs/project_plans/implementation_plans/enhancements/provider-channel-credential-entities-v1.md`
- **Design Specs**: None
- **SPIKEs**: None — deliberately skipped (see §2 below)
- **Related tracker nodes**:
  - `node_01KZKZC504A3G77J6Y5VGNEDNA` — this feature's own tracker node (plan `itt_node_id`).
  - `node_01KZP4D3BN6QYJAHC4FCRNGZNW` — out-of-repo launcher activation, not yet shipped; blocks AC3's live demonstration (Risk 1 below).
  - `node_01KZEXSPEKDRCSY3FGEVZPEWMV` — adjacent open defect (provider credentials logged in URL query strings + error bodies); M2 must not regress it.
  - `node_01KZEXVPHVYAXR7QSKDT5FJ2G9` — unrelated tracker node that reserves ADR numbers 016–018, which is why this feature's ADR is numbered 019.

---

## 2. Estimation Sanity Check

**Bottom-up total**: 17 pts, Tier 3. **Top-down anchor**: v51 ICA key + spend capture (~8 pts).

H1–H7 (given, not recomputed here):
- **H1**: Two new dimension tables (provider, channel — credential is a third) at ~2 pts/table ≈ 4 pts.
- **H2**: N/A — no local/enterprise split on this feature — but dual-backend (SQLite+Postgres) DDL is a real ~1.3x multiplier on the migration task, distinct from H2's usual trigger.
- **H3 fires**: rotation-lineage continuity is merge/graph-shaped (a declared-rotation join across credential rows) — floor of ≥3 pts per the algorithmic-service flag.
- **H4**: three capability areas (schema, service, API) — the per-area sum is the estimate floor, not the top-down guess.
- **H5 anchor**: v51 ICA key + spend capture (~8 pts: columns + sidecar + attribution + tests, no new tables). This feature adds 2 dimension tables, a rotation-lineage algorithm, and a cross-project rollup on top of that surface — roughly 2x the anchor, landing at 16–17 pts.
- **H6**: +2 pts hidden-plumbing budget (DTOs, `types.ts` mirror, tests). Correction: the new tables do **not** get a `COLUMN_PARITY_DRIFT_ALLOWLIST` entry — that allowlist covers known column-level drift on tables that already exist in both backends. Precedent (`backend/tests/test_routing_rollup_repo.py:99-109`) asserts the allowlist holds zero pairs for the new table; new tables must be parity-clean by construction instead.
- **H7**: check `backend/routers/analytics.py` size before wiring the new capability string there — if it exceeds ~2K lines, the huge-file-touch multiplier applies to that wiring task specifically; not yet confirmed as of plan authoring.

**Total: 17 pts, Tier 3.**

**SPIKE deliberately skipped.** Tier 3 normally wants a SPIKE first, but the H5 anchor already exists (v51) and the one genuine design unknown — where correlation lives — is resolved in-plan as ADR-019 rather than by research. A SPIKE would have re-derived a decision this brief already states plainly: CCDash already owns the fact table, the spend readings, and the cross-project registry AC3's join needs.

---

## 3. Wave & Orchestration Notes

**Critical path**: M1 → M2 → M3, strictly sequential (see plan §Sequencing) — M2's credential rows FK into M1's channel dimension; M3 aggregates over M2's credential identity.
**Parallel opportunities**: None load-bearing across milestones; within M1, dual-DDL authoring and backfill-script drafting can proceed in parallel once the dimension schema is settled.
**Merge order**: **honored** — ADR-019 was authored ahead of any DDL, so the schema was not built first in a way that would settle AC4 implicitly. Note: ADR-019's acceptance is not yet confirmed — it ships `status: proposed` pending Nick's explicit sign-off (see OQ-5 in §4).
**Cross-feature coupling**: Blocked-on (not blocking-of) the out-of-repo launcher activation (`node_01KZP4D3BN6QYJAHC4FCRNGZNW`) for AC3's live demonstration only; modelling and seeded-data tests proceed independently.

---

## 4. Open Questions Ledger

| ID | Source | Question | Status | Resolved By |
|----|--------|----------|--------|-------------|
| OQ-1 | PRD `open_questions` | Manual-declare vs. inferred rotation lineage? | **resolved 2026-08-10** | Manual declaration only. An explicit CLI/API action names the predecessor credential; the rollup trusts only that stored pointer. Inference from activity gaps is rejected for v1 — a wrong inferred merge asserts a continuity that never happened and is invisible in the output. |
| OQ-2 | PRD `open_questions` | Does the rollup API need a debug escape hatch for unattributed spend? | **resolved 2026-08-10** | Exclude unattributed spend by default; always report the excluded-session count in the response; accept `?include_unattributed=true` as a debug escape hatch. Not left to implementation judgment. |
| OQ-3 | PRD `open_questions` | Lazy vs. eager dimension-row backfill? | **resolved 2026-08-10** | Eager, but as an idempotent worker/CLI job **separate** from the v51→v52 DDL migration — not inside the migration. Api and worker run migrations concurrently on the node, so a long scan inside the migration would widen that known DuplicateColumn race. DDL stays fast; the backfill is re-runnable and observable. |
| OQ-4 | PRD AC4 / ADR-019 | Is CCDash the correlation home, or should this live elsewhere? | resolved (planning decision) | Decided by Nick: CCDash is the correlation home; the alternative to revisit is an external warehouse, gated on needing provider-side billing/rate-limit data CCDash does not capture. This is distinct from ADR-019's formal acceptance status — see OQ-5. |
| OQ-5 | Plan / ADR-019 | Has ADR-019 received Nick's explicit accept sign-off (AC4)? | **open** | Not yet. ADR-019 is authored, shipping `status: proposed`. AC4 is not met until Nick gives explicit sign-off; do not treat it as approved in the interim. |

---

## 5. Deferred Items Rationale

None identified. No `DI-` items were pulled into this plan; the PRD's out-of-scope list (FE/UI surfacing, budgets/headroom, provider reliability records) are follow-on features, not deferred pieces of this one.

---

## 6. Risk Narrative

- **AC3 isn't demonstrable on live data yet.** The launcher activation that populates `sessions.ica_key` (`node_01KZP4D3BN6QYJAHC4FCRNGZNW`) hasn't shipped. Every per-credential series is empty on real traffic until it does. Watch for pressure to "just close M3" against an empty live series — the plan is explicit that seeded-fixture evidence is sufficient and closing on empty live data is not. Shipping the launcher hooks is cheap; consider sequencing it opportunistically alongside this feature rather than after.
- **Parallel-vocabulary drift.** The PRD is blunt that a second naming scheme for provider/channel/credential is worse than no dimension at all. Watch M1 implementation for any temptation to add a "cleaner" enum instead of reusing `providerId` verbatim — that is the failure mode AC2 exists to prevent.
- **Single-backend DDL.** This repo's most recurring defect class. The plan makes the parity check an M1 exit criterion rather than a review-time courtesy, but it is still worth a human glance at the diff for both migration files before approving M1.
- **Silent spend division.** v51 already made "never silently divide" a structural guarantee (`decide_attribution` stores `NULL` rather than dividing). M3 rolls that guarantee up to the credential level. This is now a resolved contract requirement (OQ-2), not just a review-time risk: unattributed spend must be excluded by default, the excluded-session count must always be reported, and `?include_unattributed=true` must be honored as the debug escape hatch — watch that the rollup doesn't quietly undo any of the three by summing over `NULL` or dropping the count.

---

## 7. What to Watch For

- M1 is Mode-D gated (schema migration) — expect an explicit halt for human approval before the DDL runs; do not let an agent auto-approve past it.
- ADR-019 is authored but **not yet accepted** — it ships `status: proposed` pending Nick's explicit sign-off (OQ-5, §4). AC4 is not satisfied until that sign-off lands; do not let M1 schema work proceed on the assumption it already has. The other watch-item on this surface is the AC3 launcher-activation gap (`node_01KZP4D3BN6QYJAHC4FCRNGZNW`): until it ships, every per-credential series is empty and M3 must not be closed on live data.
- Before declaring M3 "done," check whether the launcher activation (`node_01KZP4D3BN6QYJAHC4FCRNGZNW`) has shipped in the interim — if it has, re-run the rollup against real data as a bonus check, even though the plan's AC only requires the seeded fixture.

---

## 8. Expected Success Behaviors

- [ ] Ask "what has CC3 cost across all projects this month" and get back a number, with an explicit count of sessions excluded for non-attributed spend.
- [ ] Declare a rotation from an old credential name to a new one and see the rollup read as one continuous series, not two.
- [ ] Query a channel or credential directly (not via a session-table `GROUP BY`) and get an object back.
- [ ] Confirm zero new provider/channel/credential string literals exist outside `model_identity.py`'s closed vocabularies (`git grep` check from the plan's AC2 row).

---

## 9. Running Log

- [2026-08-10] Brief created alongside the implementation plan and PRD.
- [2026-08-10] Nick resolved OQ-1 (manual-declare rotation), OQ-2 (exclude-by-default + always-report-count + `include_unattributed=true`), and OQ-3 (eager backfill as a separate idempotent job, not in-migration). Corrected two factual errors: new tables must not enter `COLUMN_PARITY_DRIFT_ALLOWLIST`, and ADR-019 acceptance is not confirmed — downgraded to pending sign-off (OQ-5).
