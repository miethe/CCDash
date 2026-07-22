---
leg: scope
mvp_tier: 1
full_vision_tier: 3
confidence: 0.8
title: "Scope Leg — Value Slice & MVP Carve"
feature_slug: ccdash-automated-aar-review
created: 2026-07-21
---

# Scope Leg — Value Slice & MVP Carve

## Bottom line

The full vision is a **Tier 3** cross-system autonomy loop (AAR↔session pairing → deterministic
triage → conditional ARC/swarm deep-review → gated SkillMeat/op writeback → scheduled worker over
all sessions). The MVP that delivers user-visible value on its own is a **Tier 1** slice
(single autonomous sprint, ~10–13 pts): **a new `aar_review` agent-query service that pairs an AAR to
its session(s), computes 4 deterministic surface flags from data already in the DB, and emits a
structured triage verdict — exposed read-only via REST + MCP + CLI. No autonomous swarm, no ARC
dispatch, no writeback, no scheduling.**

This confirms the charter hypothesis with one refinement: correlation is **not** greenfield. The
session→feature correlation engine already exists (`session_correlation.py`: explicit `entity_links`,
phase/task hints, command tokens, lineage). The only genuinely new correlation is the AAR-doc→session
hop, and it rides transitively on the existing path (AAR doc → feature → sessions) plus frontmatter
session refs. That shrinks the MVP materially.

## Grounding (what already exists — do not rebuild)

| Capability the intent assumes | Already shipped in CCDash | Location |
|---|---|---|
| Session→feature correlation (5 strategies) | Yes | `agent_queries/session_correlation.py` |
| Generated AAR from feature telemetry | Yes (`generate_aar`, feature-keyed) | `agent_queries/reporting.py` + MCP `ccdash_generate_aar` |
| Workflow failure patterns | Yes | `agent_queries/workflow_intelligence.py` |
| Feature forensics + token/subagent rollup | Yes | `agent_queries/feature_forensics.py` |
| Context-balloon signal (tokens, `context_window`) | Yes (columns exist) | `sessions` detection columns |
| Agent/skill/model signal (`skill_name`, `subagent_parent_id`, `model_slug`) | Yes (columns exist) | `sessions` detection columns |
| Doc↔feature↔session linkage | Yes | `document_linking.py`, `entity_links`, `repositories/links.py` |
| Transport-neutral fan-out (REST/CLI/MCP) | Yes (the standing pattern) | `routers/agent.py`, `cli/`, `mcp/server.py` |
| Derived-entity + correlation delivery template | Yes (RF run telemetry, 9594fcc) | `run_intelligence.py`, `entity_graph.py`, `/api/agent/research-runs` |

**Gap the MVP closes**: `generate_aar` synthesizes an AAR *from* telemetry keyed by feature. The intent
is the inverse — take an **agent-written AAR document** and pair it back to the session log(s) it
describes, then judge those sessions. That inverse-pairing + deterministic flagging + triage verdict
does not exist. That is the MVP's reason to exist.

## Delivery-shape anchor (H5)

RF run telemetry (commit 9594fcc) is the closest already-shipped analogue and the sequencing anchor.
Its **P2 wave** (entity minting + run↔session correlation via `entity_graph.py`, ~8 pts, zero changes
to `aos_correlation.py`, additive-only) is the **H5 reference story** for calibration: the MVP's
correlation helper is comparable in shape and slightly smaller (it reuses `session_correlation.py`
rather than adding a new entity kind). RF telemetry as a whole (4 waves, new ingest endpoint + 2 new
tables + FE analytics tab) is the **full-vision Tier-3 shape** anchor.

## Capability-slice table

| # | Slice | Value | Risk | Depends-on | Tier | Phase |
|---|---|---|---|---|---|---|
| S1 | **AAR↔session correlation** (doc→feature→sessions + frontmatter refs) | Foundation; nothing works without it | Low — reuses `session_correlation.py`; deal-killer risk if no key (see risk leg) | existing correlation + `document_linking` | 1 | **MVP-P1** |
| S2 | **Deterministic surface flags** (missing-artifacts, context-ballooning, generic-agent-vs-specialist, stack-ineffectiveness) | Immediate, explainable, no model calls | Low — all inputs are existing columns; only heuristics/thresholds are new | S1 | 1 | **MVP-P2** |
| S3 | **Triage verdict DTO** (`surface_only` vs `deep_review_recommended` + reasons + score) | The actionable output an agent/human consumes | Low | S1, S2 | 1 | **MVP-P3** |
| S4 | **Transport wiring** (REST `/api/agent/aar-review*` + MCP tool + CLI cmd) | Makes MVP usable by op/ARC/human today | Low — standing pattern | S1–S3 | 1 | **MVP-P4** |
| S5 | 5th flag: **need-for-new-skill/agent** (speculative recommendation) | Higher-value but softest signal | Med — near the model/opinion boundary; deterministic version is weak | S2 | 2 | Inc-2 |
| S6 | **Derived rollup table + backfill** (`aar_reviews`, dual-DDL) for scan/history | Enables autonomous scanning + trend analytics | Med — new table, dual-DDL parity, ADR-007 write path | S1–S3 | 2 | Inc-2 |
| S7 | **Enhancement-recommendation output routed to op/SkillMeat** (draft, gated) | Closes the Signal→System loop | High — writeback blast radius; must be behind HITL gate (risk leg owns) | S3, op story | 3 | Inc-3 (gated) |
| S8 | **ARC/swarm deep-review dispatch** on triage verdict | Deep analysis of flagged sessions | High — cost explosion, LLM-on-recall, recursion (risk leg owns) | S3, S6 | 3 | Inc-3 (gated) |
| S9 | **Autonomous scheduled worker** over all imported sessions | Hands-off operation | High — cost/volume; needs S6 + cost gates | S6, S8 | 3 | Inc-4 (gated) |

## Sequencing

**MVP (Tier 1, one Feature Contract sprint) = S1 + S2 + S3 + S4.** Ships as a single additive
`agent_queries/aar_review.py` service reading existing tables (no new ingest, no new table, no FE),
surfaced read-only through the three transports. Output is a queryable triage verdict; the consumer
(op / ARC / a human) decides what to do with it. This is entirely inside the AOS constraint set:
deterministic, cheap-extract, no LLM on the recall path, CLIs-as-contract.

Then, gated increments:

1. **Inc-2 (Tier 2)** — S5 (5th flag) + S6 (derived `aar_reviews` rollup table + dual-DDL + backfill).
   Gate: MVP flags validated as useful/low-false-positive against real AARs before persisting history.
2. **Inc-3 (Tier 3, HITL-gated)** — S7 (op/SkillMeat draft-writeback via `op story`, never bypassing
   its gates) + S8 (ARC/swarm dispatch on `deep_review_recommended`). Gate: cost ceiling + explicit
   human/approval run-record state before any dispatch or writeback fires (risk leg defines the gates).
3. **Inc-4 (Tier 3)** — S9 (scheduled worker over all sessions). Gate: Inc-3 proven safe at bounded
   volume + cost caps enforced as run-record state.

**Deliberately deferred behind gates**: swarm/ARC deep-review (S8), SkillMeat/op writeback (S7),
autonomous scheduling (S9). These carry the cost-explosion and blast-radius risks the risk leg is
scoped to; none belong in the first shippable slice.

## Why this is the right MVP (test of the charter hypothesis)

- **Confirmed**: MVP = correlation + deterministic surface-flags + triage verdict, via
  agent_queries/MCP/CLI, no swarm, no writeback. ✔
- **Refinement**: correlation is cheaper than assumed (reuse `session_correlation.py` + doc linkage),
  so the MVP can afford all 4 deterministic flags + the verdict in one Tier-1 sprint rather than
  splitting correlation into its own phase.
- **Standalone value**: even with zero downstream automation, an operator/ARC can immediately ask
  "which recent sessions warrant a deep review, and on what evidence?" over already-ingested data —
  the exact triage decision that today is manual. That value does not depend on S7/S8/S9.
- **Seam-clean**: CCDash owns evidence + deterministic triage; `op`/ARC keep ownership of model-driven
  synthesis + gated writeback (aligns with charter Out-of-Scope and the reuse leg's ownership line).

## Tier classification & rough sizing

| Scope | Tier | Rough pts | Rationale |
|---|---|---|---|
| **MVP (S1–S4)** | **1** (Feature Contract, single sprint) | ~10–13 | 1 new query service + small correlation helper + 4 heuristics + triage DTO + 3-transport wiring + tests; additive-only; no new table/ingest/FE. Borders Tier 2 only if a rollup table is pulled in (it isn't). |
| **+ Inc-2 (S5,S6)** | 2 | +8–10 | New dual-DDL table, backfill, ADR-007 write path, 5th flag. |
| **Full vision (S1–S9)** | **3** | ~34–45 total | Cross-system, HITL gates as run-record state, ARC/swarm dispatch, writeback blast radius, scheduled worker — matches the RF-telemetry-scale (4-wave) shape. |

**H5 anchor**: RF run telemetry P2 (entity + run↔session correlation, ~8 pts, additive, reused
existing correlation) — the MVP's correlation+flag core is ~this size, calibrating the MVP at the
low end of Tier 1's band.

## Confidence & caveats

Confidence **0.8**. High confidence on: reuse of existing correlation, flag-input availability, and
the transport pattern (all verified in-repo). The one dependency I did not fully verify (defer to the
**tech** and **risk** legs): whether an agent-written AAR *document* carries a reliable frontmatter
session/feature ref, or whether the doc→feature→session transitive hop is sufficient on its own. If
neither yields a correlation key, the charter **deal-killer** trips and even S1 is blocked — this is
the single assumption that could shift MVP tier upward (a bounded "AAR-linkage ingest increment"
prerequisite, matching the charter's `conditional` verdict path).
