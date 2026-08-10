---
schema_name: ccdash_document
schema_version: 2
doc_type: human_brief
title: "Anthropic/ICA lane + egress consent gating — human brief"
status: draft
created: 2026-08-10
audience: [humans]
feature_slug: hosted-llm-anthropic-ica-lane
category: human-briefs
owner: nick
priority: P1
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md
intent_ref: null
epic_ref: null
---

# Anthropic/ICA lane + egress consent gating — Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-08-10

---

## 1. Context Pointers

- **Plan**: `docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md`
- **SPIKE** (requirement record, 913 lines, completed): `docs/project_plans/spikes/hosted-llm-provider-strategy.md`
- **Open questions**: `docs/project_plans/spikes/hosted-llm-provider-strategy-open-questions.md`
- **IntentTree node**: `node_01KZEXTPYXYB4TKGFE111ZRXPE` (P3, parent work package `node_01KZCA2MAA0K0TWEPW0KZGC4WF`)
- **PRD**: None, by deliberate decision — the SPIKE carries requirements.

---

## 2. Estimation Sanity Check

Bottom-up total: **11 pts**. Trust bottom-up (Tier 2).

| Heuristic | Applied | Points contribution |
|-----------|---------|----------------------|
| H1 — noun-counting | ONE new nullable column on an existing `projects` table (`llm_egress_consent`); no new table, no RBAC. Not the ≥2 pts a new CRUD-with-RBAC table would cost. | 1 pt |
| H2 — dual-implementation multiplier | Applies, but as dual **database backend** (sqlite + postgres migration modules must move in the same change set), not local+enterprise repos. ~1.8x on the DDL subtotal. | 1 pt → ~2 pts |
| H3 — algorithmic service flag | Does not fire. Consent resolution is a boolean gate, not dependency/graph/conflict resolution. No SPIKE needed (one is already complete). | 0 pts |
| H4 — bundle-vs-sum | 3 capability areas: defect remediation (~2), consent+DDL (~5), adapter+config (~4). Sum = 11 = the floor for the plan total. | 11 pts (floor) |
| H5 — anchor | Closest completed comparable: v51 ICA key + per-session spend capture (5 nullable columns, dual DDL, new capture path, attribution vocabulary). This feature is smaller on DDL (1 col vs 5) but larger on new-code surface (whole new provider adapter + config surface + consent resolver) — parity to slightly above. Delta within 30%, no justification needed. | ~parity |
| H6 — hidden plumbing budget | ~15–20% for config helper, CHANGELOG, ADR-017/018 acceptance, docs/guides update. | ~1.5–2 pts, already inside the 11 |
| H7 — huge-file touch multiplier | **Fires.** `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py` are each >2K lines (`SCHEMA_VERSION` at line 85 and 61 respectively; ALTER call sites near lines 3194 and 4159). Any leg touching them carries ≥2x on that task's estimate and must not also be asked to hold the adapter work. Single biggest context-burn driver — why the plan is `context_class C3`. | reflected in M2 sizing |

**Conclusion**: bottom-up 11 pts, Tier 2, trust bottom-up.

---

## 3. Wave & Orchestration Notes

**Critical path**: 3 sequential milestones, no concurrency — M1 (safe to extend) → M2 (consent gate) → M3 (Anthropic lane).

**Non-obvious ordering choice**: the consent gate lands and is **proven against the existing Gemini lane** in M2, before the new Anthropic adapter exists in M3. Reason: the safety property then ships even if M3 slips, and the new adapter is born into an already-gated world instead of being the thing that proves the gate.

**Merge order / folding**: M1 folds in two previously-separate P2 defect nodes — `node_01KZEXSPEKDRCSY3FGEVZPEWMV` (creds-in-URL + error-body logging) and `node_01KZEXSFSH4AGBFYGY5D5YTG9F` (undeclared httpx) — because they sit on the exact files M3 extends.

**Cross-feature coupling**: M2 contains a schema migration → Mode-D, halts for explicit human approval before proceeding.

**Gate lenses**: M1 `[security/authz-boundary]`, M2 `[security+validator/irreversible-outward]`, M3 `[security/irreversible-outward]`.

---

## 4. Open Questions Ledger

| ID | Source | Question | Status | Resolved By |
|----|--------|----------|--------|-------------|
| (a) | SPIKE open-questions | Which ICA key does the deployed adapter use — only the default `~/.dotfiles/ICA_CLAUDE` key was probed; a named `ICA_KEY` block may scope models differently | open | — |
| (b) | SPIKE open-questions | Whether `CCDASH_LLM_ANTHROPIC_MODEL` should have a default at all | open | SPIKE deliberately gives it none — a wrong default is a silent cost decision |
| OQ-2 | SPIKE | Anthropic Messages API endpoint/header/rates | resolved | Confirmed in SPIKE — do not re-probe |
| OQ-3 | SPIKE | ICA wire compat | resolved | 4 live probes, all 200 — do not re-probe |
| OQ-8 | SPIKE | `[1m]`-suffixed model ids on ICA | resolved | Return 403 `team_model_access_denied`; adapter MUST send bare ids |
| RQ-1 | SPIKE | Does CCDash ever compute an embedding vector | resolved | No — CCDash never computes an embedding vector |
| OQ-5 | SPIKE | `CCDASH_OLLAMA_TIMEOUT_SECONDS` premise | stale | SPIKE claims 15s; actual is 60s as of 2026-08-09 (`config.py:270`) — OQ-5's premise is stale |

---

## 5. Deferred Items Rationale

None — see plan's Scope boundary "Out" list for explicitly deferred work, each with its owning node.

---

## 6. Risk Narrative

- **Silent fail-open**: A silent fail-open is the entire risk of this plan; every other failure mode is visible. The consent gate must be a structural no-op (data simply isn't sent) rather than a call-site conditional that a future edit can accidentally bypass.
- **Half-applied migration crash-loop**: `api` and `worker` run migrations concurrently on deploy, and a drifted column has taken both down before. M2's schema change must be idempotent and safe under concurrent apply.
- **ICA-green ≠ Anthropic-correct**: ICA returns 200 on unknown top-level request fields where Anthropic direct returns 400, so a passing probe against ICA proves reachability, not wire-format correctness against the real Anthropic API.

---

## 7. What to Watch For

- An executor "helpfully" giving `CCDASH_LLM_ANTHROPIC_MODEL` a default.
- A consent check captured at construction time rather than re-resolved per sweep tick.
- A `[1m]` model id appearing anywhere in the adapter.
- A `COLUMN_PARITY_DRIFT_ALLOWLIST` entry being added to make a parity test pass — the bar is ZERO entries.

---

## 8. Expected Success Behaviors

- [ ] With consent off, a naming sweep logs a no-op and nothing leaves the box.
- [ ] With consent on for one project only, only that project's sessions are named via the hosted lane.
- [ ] A real ICA call names one session and the response id starts with `msg_bdrk_`.

---

## 9. Running Log

- 2026-08-10 — brief created at plan authoring; no execution yet.
