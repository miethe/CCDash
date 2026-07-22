# Decisions Spine — CCDash Automated AAR Review Loop

> Opus-direct architecture scaffold for two downstream artifacts: (1) full-vision PRD (Tier 3,
> north-star), (2) Tier 1 MVP Feature Contract. Expanders read this + the exploration bundle;
> do NOT restate CLAUDE.md/ADR content — reference by path.

## Source of truth (read these, don't duplicate)
- Feasibility brief: `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-feasibility-brief.md`
- Accepted ADR (the seam contract): `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md`
- Leg findings: `.../spikes/{tech,reuse,risk,scope}-findings.md`

## North-star statement
CCDash is the **producer** of AAR-review evidence: pair each agent-written AAR back to the session
log(s) it describes, compute deterministic surface flags over already-ingested data, and emit a
model-free `aar_review_candidate` event. `op`/ARC/SkillMeat consume it and own ALL model-driven
synthesis, swarm dispatch, artifact creation, and gated writeback. This inverts `generate_aar`
(which synthesizes an AAR *from* telemetry); here we pair a *written* AAR back to sessions and judge.

## Hard invariants (any violation is a review failure)
- **No LLM on the recall/read path.** All CCDash-side triage is deterministic (threshold/lookup/regex over DB rows), same class as `persona_extract_rules.py` R1–R8. Semantic judgment ⇒ belongs upstream.
- **CCDash never dispatches swarm/ARC, never writes SkillMeat/skills/agents.** It emits events; every gate stays upstream (`op approve|reject`, story approve, ARC validate, IntentTree AgentRun).
- **Reuse, don't rebuild.** AAR sourcing already flows through `op story` (`ccdash report aar --feature`); correlation via `session_correlation.py` + `document_linking` + `entity_links`; no second correlation key. Do-Not-Build list is binding (brief §Do-Not-Build).
- **Every new write path** ⇒ ADR-007 (`retry_on_locked`, dual SQLite+PG DDL, direct-count assertion test). New columns ⇒ dual DDL + parity allowlist. Consume redaction-passed `session_detail`, never raw JSONL.

## Capability decomposition (the 5 charter capabilities)
1. **Correlation**: AAR-doc → session(s), reusing the two-hop `AAR→feature→sessions` fallback (conf-scored).
2. **Surface flags** (deterministic): missing-artifacts, context-ballooning, generic-agent-vs-specialist, stack-ineffectiveness, need-for-new-skill/agent (5th, speculative).
3. **Triage verdict**: `surface_only | deep_review_recommended` (+ reasons + correlation-confidence). Low correlation-confidence ⇒ route to human triage, never auto-escalate.
4. **Recommendation output**: model-free `aar_review_candidate` event (mirror RF→CCDash `ccdash_event.yaml` inverse); `op` consumes and routes at its gate.
5. **Autonomous operation**: scheduled worker over imported sessions, reusing the `(project_id, trigger)` coalescing guard.

## Phase roadmap (PRD phases; tiers per scope leg)
| Phase | Tier | Scope | Gate |
|-------|------|-------|------|
| P1 (MVP) | 1 | Correlation helper + 4 deterministic flags (defer 5th) + triage verdict DTO + read-only REST+MCP+CLI + emit `aar_review_candidate` event. NO swarm, NO writeback, NO scheduling. | task-completion-validator |
| P2 | 2 | 5th flag (new-skill/agent need) + persisted `aar_reviews` rollup table (ADR-007) + FE review surface (panel/tab). | validator per phase |
| P3 | 3 | **op-side consumer** (out-of-CCDash-repo, but specified here): `op` reads the event, routes surface-note vs `op council`/ARC at its existing plan gate; gated recommendation drafts. | op HITL gate |
| P4 | 3 | HITL-gated writeback into SkillMeat/skills-agents via `op approve`; autonomous scheduled worker (coalescing guard) + 3 self-recursion guards enforced. | op approve + ARC validate |

## Self-recursion guards (P4-critical, design from P1)
1. **Provenance self-exclusion** via `skill_name`/`workflow_id` capture columns (never content-sniff — that's an LLM on recall path).
2. **Idempotent dedup ledger** keyed `(aar_doc_id, session_id)` (mirror `emit_artifact_outcomes` `dedup_key`).
3. **Hard escalation quota** (env-configured) checked before any handoff; CCDash only hands off through `op`'s gated dispatch.

## Data contracts (specify precisely in PRD)
- **Flag inputs** (tech leg): context-ballooning ⇐ `contextUtilizationPct`/token cols (now); retry/failure churn ⇐ `detect_failure_patterns` (now); missing-artifacts ⇐ `session_artifacts` (produced) vs AAR-body claim (derivation); generic-agent-fit ⇐ agent usage cols (trivial) + rule map (derivation); stack-ineffectiveness ⇐ tool/file→stack map (derivation).
- **Triage verdict DTO** + **`aar_review_candidate` event schema**: define both in PRD Data Contracts. Event is model-free, consumed by `op`.
- **Integration point**: new `backend/application/services/agent_queries/aar_review.py` (transport-neutral), wired to `routers/agent.py` + `cli/commands/report.py` + `backend/mcp/`. Direct precedent: `reporting.py` / `generate_aar` wiring.

## Estimation anchors (H5)
- Full vision ≈ RF run telemetry (commit `9594fcc`, Tier 3, ~26pt) → ~34–45pt here (adds op-side consumer + writeback gates).
- MVP core ≈ RF P2 correlation wave (~8pt, additive) → MVP total ~10–13pt (Tier 1); reuses `session_correlation.py`, no new entity kind, no new ingest, no FE.

## MVP Feature Contract scope boundary (for the contract writer)
IN: `aar_review.py` service; correlation helper (reuse existing); 4 deterministic flags; triage verdict DTO; read-only REST+MCP+CLI surface; emit `aar_review_candidate` event; unit + direct-count tests; runtime smoke (CLI/MCP — no FE this slice).
OUT: 5th flag, persisted rollup table, FE, op-side consumer, ARC/swarm dispatch, any writeback, scheduling. All deferred to P2–P4 in the PRD.
Acceptance criteria must be testable & enumerable; resilience AC for every optional field (missing = contract state per R-P2).

## Changelog
`changelog_required: true` on both PRD and MVP contract (new user/operator-facing capability: `ccdash report aar-review` / MCP tool).
