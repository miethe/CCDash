---
title: "Feature Contract: CCDash AAR Review MVP \u2014 Deterministic AAR\u2194Session\
  \ Triage"
schema_version: 2
doc_type: feature_contract
it_schema: 1
description: Pair an agent-written AAR document back to the session(s) it describes
  and emit a deterministic, model-free triage verdict via REST/CLI/MCP.
status: completed
created: '2026-07-21'
updated: '2026-07-22'
feature_slug: ccdash-aar-review-mvp
category: features
estimated_points: 12
tier: 1
owner: nick
priority: high
risk_level: medium
changelog_required: true
node_type: work_package
acceptance_criteria: []
definition_of_done: "AARReviewQueryService resolves an AAR document to its session(s),\
  \ computes the 4 deterministic surface flags plus the triage verdict DTO from data\
  \ already in the DB, and is reachable read-only via REST, CLI, and MCP \u2014 with\
  \ no model call anywhere on the compute path and no new persisted table."
execution_mode: autonomous
agent_title: Implement AAR Review MVP (deterministic triage service + 3-transport
  wiring)
agent_summary: "New transport-neutral aar_review.py service: correlate AAR doc \u2192\
  \ session(s) via existing entity_links/session_correlation, compute 4 deterministic\
  \ flags, emit a triage verdict DTO, wire to REST+CLI+MCP, log a model-free aar_review_candidate\
  \ observability event."
agent_context: 'This is the Tier 1 MVP slice of the CCDash Automated AAR Review Loop
  (see prd_ref once authored). Producer/consumer boundary is fixed by the accepted
  ADR: CCDash computes deterministic evidence only; op/ARC own all model-driven synthesis,
  swarm dispatch, and writeback. No LLM call is permitted anywhere in this contract''s
  code path.'
open_questions:
- q: "Do agent-written AARs from op story reliably carry a session/feature frontmatter\
    \ ref in practice, or does the MVP lean entirely on the two-hop doc\u2192feature\u2192\
    session fallback?"
  owner: implementer
  status: open
- q: Should the context-ballooning and generic-agent-fit thresholds be hardcoded constants
    or CCDASH_* env vars in the MVP?
  owner: implementer
  status: open
decisions:
- decision: No new DB table, no new ingest pipeline, no new correlation key for the
    MVP.
  rationale: "Tech leg confirmed entity_links already materializes document\u2192\
    session correlation; reuse is total."
  status: accepted
- decision: aar_review_candidate event is emitted as a structured observability log
    event (backend/observability/otel.py style, mirroring log_auth_event), not a DB
    row and not a push to any external system.
  rationale: Avoids a new ADR-007 write path and an unbuilt push transport for op
    in this slice; REST/CLI/MCP remain the actual v1 pull-based data path for op/ARC.
  status: accepted
scores: {}
related_documents:
- docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-feasibility-brief.md
- docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md
- docs/project_plans/exploration/ccdash-automated-aar-review/spikes/tech-findings.md
spike_ref: null
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: null
commit_refs:
- e4c38cde76ecfb4985f4bc628334369eb9c2ddc3
pr_refs: []
files_affected:
- backend/application/services/agent_queries/aar_review.py
- backend/application/services/agent_queries/models.py
- backend/application/services/agent_queries/__init__.py
- backend/config.py
- backend/observability/otel.py
- backend/routers/agent.py
- backend/cli/commands/report.py
- backend/cli/runtime.py
- backend/mcp/tools/reports.py
- backend/tests/test_agent_queries_aar_review.py
- backend/tests/test_agent_router.py
- backend/tests/test_cli_commands.py
- backend/tests/test_mcp_server.py
- CHANGELOG.md
---

# Feature Contract: CCDash AAR Review MVP — Deterministic AAR↔Session Triage

This is **Phase 1 (MVP)** of the CCDash Automated AAR Review Loop. The full vision (5th flag,
persisted rollup, FE surface, op-side consumer, ARC/swarm dispatch, HITL-gated writeback,
autonomous scheduling) is specified in the companion Tier 3 PRD (`prd_ref` above) and is explicitly
**out of scope here**. This contract delivers a self-contained, standalone-valuable slice: a
deterministic query service an operator or `op`/ARC can call *today* to ask "which sessions behind
this AAR warrant a deep review, and on what evidence?"

---

## 1. Goal

Ship a read-only, model-free CCDash service that resolves an agent-written AAR document to the
session(s) it describes, computes four deterministic surface flags from data already in the
database, and returns a triage verdict (`surface_only` vs `deep_review_recommended`) — reachable
via REST, CLI, and MCP — with zero LLM calls anywhere on the compute path.

---

## 2. User / Actor

- **Primary user**: `op`/ARC, as an automated consumer calling the REST endpoint or MCP tool to
  decide whether a completed feature's AAR warrants routing to `op council`/ARC.
- **Secondary users**: a human operator running `ccdash report aar-review` directly from the CLI to
  spot-check a feature without waiting for `op` automation.

---

## 3. Job To Be Done

When an agent-written AAR document exists for a feature, the operator (human or `op`/ARC) wants to
**deterministically identify surface issues in the underlying session(s)** — missing artifacts,
context ballooning, generic-agent-where-a-specialist-fit, and tech-stack ineffectiveness — so they
can **decide whether to route the feature to a full ARC review or file a surface note**, without
manually re-reading transcripts and without waiting on a model call.

---

## 4. Scope

### In Scope

- New transport-neutral service `backend/application/services/agent_queries/aar_review.py`
  (`AARReviewQueryService`), following the exact shape of `ReportingQueryService.generate_aar`
  (`backend/application/services/agent_queries/reporting.py:63-64`) and reusing `@memoized_query`
  (`.cache.memoized_query`).
- A correlation helper that resolves an AAR document id/path to its session(s), **reusing existing
  primitives only**:
  - `session_correlation.correlate_session` (`backend/application/services/agent_queries/session_correlation.py:317`) for the confidence-scored strategies.
  - `ports.storage.entity_links().get_links_for(...)` (same call shape as `reporting.py:81`) for the
    materialized `document → session` / `document → feature` links (`explicit_session_ref` 1.0,
    `task_session_ref` 0.96, two-hop `doc→feature→session` 0.64–1.0; strategies documented in
    `sync_engine.py:6574-6656`).
  - `document_linking.extract_frontmatter_references` (`document_linking.py:954`) for any
    `session:`/`session_id:`/`linked_sessions:` frontmatter on the AAR doc itself.
  - **No new correlation key, no new table, no new ingest pipeline.**
- **Four deterministic surface flags**, each computed from columns already in the `sessions` /
  `session_artifacts` tables (see §6 Data Requirements for the exact source columns):
  1. `missing_artifacts`
  2. `context_ballooning`
  3. `generic_agent_vs_specialist`
  4. `stack_ineffectiveness`
- A **triage verdict DTO** (`AARReviewDTO`) combining correlation confidence + flags into
  `surface_only | deep_review_recommended` + `reasons[]`.
- Read-only wiring to all three standing transports:
  - REST: `GET /agent/aar-review/{document_id}` in `backend/routers/agent.py`, mirroring the
    `GET /feature-forensics/{feature_id}` pattern (`routers/agent.py:254-255`), not the POST
    `/reports/aar` shape (that endpoint takes a request body because `feature_id` alone is
    insufficient for AAR *generation*; here `document_id` is a path parameter, same as
    `feature_id` in feature-forensics).
  - CLI: `ccdash report aar-review --document <doc-id-or-path>` subcommand in
    `backend/cli/commands/report.py`, mirroring the existing `report aar` command
    (`cli/commands/report.py:15-26`).
  - MCP: `ccdash_aar_review` tool in `backend/mcp/tools/reports.py`, mirroring
    `ccdash_generate_aar` (`mcp/tools/reports.py:13-22`).
- A model-free `aar_review_candidate` **observability event** emitted via structured logging at
  verdict-computation time (see Architecture Constraints — this is a log event, not a persisted row
  or an external push).
- Unit tests for the correlation helper and each of the 4 flags (deterministic inputs → deterministic
  outputs), plus the standard direct-count-style assertion coverage where any new code touches a
  write path (see §11 Risk Areas — there should be none in this MVP, but the test must assert that).
- Runtime smoke via CLI and MCP (no FE surface exists yet to smoke).

### Out of Scope

- The 5th flag (`need_for_new_skill_or_agent`) — deferred to PRD Phase 2 (Inc-2); it sits closer to
  the model/opinion boundary and is explicitly excluded here.
- Any persisted rollup/history table (`aar_reviews` or similar) — deferred to PRD Phase 2 (Inc-2,
  ADR-007 write path).
- Any frontend surface (panel, tab, badge) — deferred to PRD Phase 2.
- Any `op`-side consumer logic, ARC/swarm dispatch, or automatic escalation — deferred to PRD Phase 3
  (Inc-3), and per the accepted ADR, **never** owned by CCDash at all; CCDash only emits evidence.
- Any writeback into SkillMeat, skills, or agents — deferred to PRD Phase 4 (Inc-4), HITL-gated,
  never CCDash-initiated.
- Scheduling / autonomous worker invocation over all imported sessions — deferred to PRD Phase 4
  (Inc-4).
- Self-recursion guards (provenance self-exclusion, escalation quota) — these matter only once
  auto-escalation exists (Phase 3+); this MVP has no escalation path to guard, so they are noted as
  a forward-compat concern in Implementation Notes but not implemented here.

---

## 5. UX / Behavior Requirements

- Given a valid AAR document id/path with at least one correlatable session, calling any of the
  three transports returns an `AARReviewDTO` with `status: "ok"`, populated `flags[]`,
  `correlation_confidence`, and `verdict`.
- Given a document id that does not resolve to any document, all three transports return a
  structured "not found" response (`status: "error"`), never a raw exception/stack trace, matching
  the existing `generate_aar` `status: "error"` convention (`reporting.py:75-77`).
- Given a document that resolves but has **zero** correlatable sessions, the verdict is always
  `surface_only` with a reason explicitly stating "no correlated sessions found" and
  `correlation_confidence: 0.0` — the service never guesses a verdict from zero evidence.
- Given a document whose only correlation is the two-hop `doc→feature→session` fallback (confidence
  band 0.64–1.0) and that confidence falls below the configured floor
  (`CCDASH_AAR_REVIEW_MIN_CONFIDENCE`, default `0.64`), the verdict is forced to `surface_only`
  regardless of how many flags trigger, with a reason stating the low-confidence gate fired (per the
  risk leg: low-confidence correlations never auto-escalate).
- Given a document whose correlation confidence clears the floor and **at least one** flag triggers,
  the verdict is `deep_review_recommended`, and every triggered flag appears in `flags[]` with its
  own `evidence_refs` (session ids / artifact ids / column values that justify it) — no flag is
  silently dropped from the response.
- No transport ever blocks on or issues a model/LLM call. This is the hardest behavioral requirement
  in this contract; a reviewer must be able to grep the diff for any LLM/agent-invocation import and
  find none in `aar_review.py`.

---

## 6. Data Requirements

- **Entities affected**: none created or migrated. This is a pure read/derivation service over
  existing tables: `documents`, `sessions`, `session_artifacts`, `entity_links`, `features`.
- **New fields**: none on any existing table. No schema migration, no dual-DDL requirement, no
  `COLUMN_PARITY_DRIFT_ALLOWLIST` entry needed for this contract.
- **New DTOs** (Python/Pydantic, in `agent_queries/models.py` alongside `AARReportDTO`):
  - `AARReviewFlag`: `flag_id: str`, `triggered: bool`, `severity: Literal["low","medium","high"]`,
    `evidence_refs: list[str]`, `rationale: str`.
  - `AARReviewDTO`: `status: Literal["ok","error"]`, `document_id: str`, `session_refs: list[str]`,
    `correlation_confidence: float`, `correlation_strategy: str | None`, `flags: list[AARReviewFlag]`,
    `verdict: Literal["surface_only","deep_review_recommended"] | None`, `reasons: list[str]`,
    `generated_at: str`, `source_refs: list[str]` (mirrors the existing `source_refs` convention used
    by `AARReportDTO` and `collect_source_refs` in `_filters.py`).
- **Flag input columns** (all already shipped, no new column work):
  - `context_ballooning` ⇐ `contextUtilizationPct` / `currentContextTokens` / `contextWindowSize`
    (`types.ts:631-635`), `context_window_size` (`sqlite_migrations.py:175`), `tokensIn`/`tokensOut`
    plus cache-token columns (`types.ts:617-629`).
  - `missing_artifacts` ⇐ `session_artifacts` table (`sqlite_migrations.py:368-379`,
    `source_tool_name`, `type`) and `updatedFiles`/`linkedArtifacts`/`output_artifacts_json`
    (`types.ts:653-654`, `:1301`) on the produced side; the AAR document's own `files_affected`
    frontmatter field (per this repo's plan-frontmatter convention) on the claimed side.
  - `generic_agent_vs_specialist` ⇐ `agentName`/`agentsUsed`/`subagentType` (`types.ts:600,607,673`),
    `skill_name` (`sqlite_migrations.py:233`), `subagent_parent_id` (`:232`).
  - `stack_ineffectiveness` ⇐ `workflow_effectiveness.get_workflow_effectiveness` +
    `detect_failure_patterns` (`backend/services/workflow_effectiveness.py`, already consumed by
    `reporting.py:15,124,135`), tool/file-name signatures already present in `tool_summary`/
    `toolSummary` (`session_correlation.py:120`, `types.ts:602`).
- **State changes**: none. No row is ever written by this contract's code.
- **Storage implications**: none. No migration, no new table, no index change.

---

## 7. API / Integration Requirements

**New or modified endpoints:**
- `GET /agent/aar-review/{document_id}` (new, `backend/routers/agent.py`) — returns `AARReviewDTO`.
  Query params: `bypass_cache: bool = False` (mirrors `feature-forensics`'s cache-bypass convention,
  `routers/agent.py:255`).

**New CLI commands:**
- `ccdash report aar-review --document <doc-id-or-path> [--output json|markdown] [--json] [--md]`
  in `backend/cli/commands/report.py`, structurally mirroring the existing `report aar` command.

**New MCP tools:**
- `ccdash_aar_review(document_id: str, project_id: str | None = None) -> dict` in
  `backend/mcp/tools/reports.py`, structurally mirroring `ccdash_generate_aar`
  (`mcp/tools/reports.py:13-22`).

**External service calls**: none. This contract makes zero outbound network/model calls.

**Internal service dependencies:**
- `session_correlation.correlate_session` — read-only reuse.
- `ports.storage.entity_links()`, `.sessions()`, `.documents()`, `.features()` — existing ports, no
  new port required.
- `workflow_effectiveness.get_workflow_effectiveness` / `.detect_failure_patterns` — existing service,
  read-only reuse.
- `backend.observability.otel` — for the `aar_review_candidate` structured log event (new function,
  see Architecture Constraints).

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/application/services/agent_queries/reporting.py` — service shape, `@memoized_query` usage,
  `status: "error"` convention, `partial` flag when a sub-fetch fails without aborting the whole
  response.
- `backend/application/services/agent_queries/session_correlation.py` — correlation confidence tiers
  and the strategy names/values already established (`explicit_session_ref` 1.0, `task_session_ref`
  0.96, two-hop 0.64–1.0). This contract MUST reuse these values, not invent new ones.
- `backend/cli/commands/report.py` + `backend/mcp/tools/reports.py` + `backend/routers/agent.py` —
  the transport-neutral fan-out pattern (one service method, three thin adapters).
- `backend/observability/otel.py:1172` (`log_auth_event`) — the precedent for a structured,
  named-event log line via `logger.info(msg, extra={...})`. The new `aar_review_candidate` event
  MUST follow this exact shape: a **log event**, not a DB write, not an HTTP push. This is a
  deliberate architectural choice for this MVP (see Decisions in frontmatter) — it satisfies the
  decisions-spine requirement to "emit a model-free `aar_review_candidate` event" without opening a
  new ADR-007 write path or building an unowned push transport to `op` in this slice. A future
  increment (PRD Phase 3+) may promote this to a real queued/pushed event; this contract does not.

**Must not change** (protected areas):
- `session_correlation.py`'s existing correlation logic, confidence values, or fallback ordering —
  read-only consumer only.
- `entity_links` table schema or population logic (`sync_engine.py`) — read-only consumer only.
- Any existing `agent_queries` service's public method signatures (`generate_aar`,
  `correlate_session`, `get_workflow_effectiveness`, `detect_failure_patterns`).
- `AARReportDTO` and the `/reports/aar` endpoint/CLI/MCP surface — this is a **new**, parallel
  surface, not a modification of the existing AAR-generation path.

**New dependencies:**
- Allowed? **No.** No new third-party package. No LLM client. No new outbound HTTP client.
  *No new dependencies expected.*

**Hard invariant (non-negotiable, per the accepted ADR):**
- **No LLM call anywhere on this contract's compute path.** All four flags are threshold/lookup/regex
  checks over already-materialized DB rows, the same class as `persona_extract_rules.py`'s R1–R8
  deterministic rules. If implementation reveals that any flag genuinely requires semantic judgment
  to compute (e.g., "was the agent choice *wrong*," not just "was a generic agent used"), that flag
  must be **descoped from this contract** and flagged in the Completion Report as belonging to the
  synthesis tier upstream — do not approximate it with a model call to hit the acceptance criteria.

---

## 9. Acceptance Criteria

Correlation:

- [ ] **AC-1**: Given an AAR document whose frontmatter contains an explicit `session:`/
  `session_id:`/`linked_sessions:` reference, `AARReviewQueryService` resolves it via the
  `explicit_session_ref` strategy and reports `correlation_confidence: 1.0`,
  `correlation_strategy: "explicit_session_ref"`.
  - target_surfaces: [`backend/application/services/agent_queries/aar_review.py`]
  - resilience: N/A (required-path AC).
  - verified_by: [unit test on the correlation helper]
- [ ] **AC-2**: Given an AAR document with no explicit session reference but a resolvable
  `feature` frontmatter reference whose feature has ≥1 linked session, the service falls back to the
  two-hop `doc→feature→session` strategy and reports `correlation_confidence` in the `[0.64, 1.0]`
  band and `correlation_strategy` naming the two-hop path.
  - verified_by: [unit test on the correlation helper]
- [ ] **AC-3**: Given an AAR document with **no** resolvable session or feature reference of any
  kind, the service returns `session_refs: []`, `correlation_confidence: 0.0`, and
  `verdict: "surface_only"` with a reason stating no correlated sessions were found — it never raises
  an unhandled exception and never fabricates a session reference.
  - resilience: consumer/CLI/MCP handle `session_refs: []` and `correlation_confidence: 0.0` as a
    valid, well-formed response — not an error state, per R-P2 (absent evidence is a contract state).
  - verified_by: [unit test + CLI smoke]

Deterministic flags (one AC per flag, each independently testable):

- [ ] **AC-4 (`context_ballooning`)**: Given a correlated session whose `contextUtilizationPct` (or
  equivalent token-ratio columns) exceeds the configured threshold
  (`CCDASH_AAR_REVIEW_CONTEXT_BALLOON_PCT`, default documented in Implementation Notes), the flag is
  `triggered: true` with `evidence_refs` naming the session id and the observed percentage; below
  threshold, `triggered: false`.
  - resilience: if `contextUtilizationPct` and all fallback token columns are null/absent for a given
    session, the flag evaluates to `triggered: false` with a rationale noting "insufficient token
    data" — it is never silently omitted from `flags[]` and never treated as an error.
  - verified_by: [unit test with fixture sessions above/below/missing the threshold]
- [ ] **AC-5 (`missing_artifacts`)**: Given a correlated session whose `session_artifacts` /
  `output_artifacts_json` set does not fully cover the AAR document's own `files_affected`
  frontmatter list, the flag is `triggered: true` naming the specific missing paths in
  `evidence_refs`; when the sets fully overlap (or the AAR declares no `files_affected`), the flag is
  `triggered: false`.
  - resilience: if the AAR document has no `files_affected` frontmatter at all, the flag evaluates to
    `triggered: false` with rationale "no claimed artifacts to check" — absence of the claim side is
    a contract state, not an error, per R-P2.
  - verified_by: [unit test with fixture AAR docs with/without files_affected, sessions with/without matching session_artifacts]
- [ ] **AC-6 (`generic_agent_vs_specialist`)**: Given a correlated session whose `agentsUsed`/
  `subagentType` shows `general-purpose` (or equivalent) invoked against a task-domain the MVP's
  static keyword→specialist lookup table associates with a known specialist, the flag is
  `triggered: true` naming the generic invocation and the specialist the lookup expected; otherwise
  `triggered: false`.
  - resilience: if `agentsUsed`/`subagentType` is null/absent for a session, the flag evaluates to
    `triggered: false` with rationale "no agent-usage data" — never an error.
  - verified_by: [unit test with fixture sessions matching/not matching the static lookup table]
- [ ] **AC-7 (`stack_ineffectiveness`)**: Given a correlated session whose tool/file signatures map
  (via the MVP's static extension→stack lookup) to a known stack, and that session's
  `detect_failure_patterns`/`get_workflow_effectiveness` output shows failure/retry density above the
  configured threshold for that stack, the flag is `triggered: true` naming the stack and the
  observed failure signal; otherwise `triggered: false`.
  - resilience: if the session's tool/file signatures don't map to any known stack in the static
    lookup, the flag evaluates to `triggered: false` with rationale "stack unresolved" — never an
    error, never a guess.
  - verified_by: [unit test with fixture sessions matching a known stack above/below the threshold, and with an unmapped stack]

Triage verdict:

- [ ] **AC-8**: The verdict DTO combines correlation confidence and the 4 flags per the decision rule
  in §5 UX/Behavior — `deep_review_recommended` requires both `correlation_confidence >=
  CCDASH_AAR_REVIEW_MIN_CONFIDENCE` (default `0.64`) **and** at least one triggered flag; every other
  combination yields `surface_only`. `reasons[]` explicitly states which gate produced the verdict
  (low confidence / no evidence / no flags triggered / N flags triggered).
  - target_surfaces: [`backend/application/services/agent_queries/aar_review.py`]
  - verified_by: [unit test covering all four quadrants: high-confidence+flags, high-confidence+no-flags, low-confidence+flags, no-evidence]

Transports:

- [ ] **AC-9 (REST)**: `GET /agent/aar-review/{document_id}` returns `200` with a valid `AARReviewDTO`
  body for a resolvable document, and a structured `status: "error"` body (not a raw 500) for an
  unresolvable one; response includes `Cache-Control` header consistent with existing
  `agent_queries` endpoints.
  - verified_by: [integration test against routers/agent.py]
- [ ] **AC-10 (CLI)**: `ccdash report aar-review --document <id>` prints a human-readable summary by
  default and a valid JSON payload with `--json`, matching the existing `report aar` output-mode
  conventions (`OutputMode`, `get_formatter`).
  - verified_by: [CLI test + runtime smoke]
- [ ] **AC-11 (MCP)**: `ccdash_aar_review(document_id=...)` returns the same DTO shape (as a dict) as
  the REST/CLI surfaces, registered in `backend/mcp/tools/reports.py` alongside
  `ccdash_generate_aar`.
  - verified_by: [MCP regression test, `backend.tests.test_mcp_server`]

Observability:

- [ ] **AC-12**: Every successful verdict computation emits exactly one `aar_review_candidate`
  structured log event (via `backend.observability.otel`, `log_auth_event`-style) carrying
  `document_id`, `session_refs`, `verdict`, and the triggered flag ids — no PII/session-transcript
  content beyond ids and flag names, consistent with the redaction posture described in Risk Areas.
  - verified_by: [unit test asserting the log call/args; caplog-based assertion acceptable]

No-model-call invariant:

- [ ] **AC-13**: `grep`-level review of the diff confirms zero imports of any LLM/agent-invocation
  client (Anthropic SDK, OpenAI SDK, any `Task`/`Agent` dispatch helper) anywhere in
  `aar_review.py` or its new test file.
  - verified_by: [manual reviewer check during task-completion-validator pass]

---

## 10. Validation Requirements

- [ ] **Typecheck**: N/A for this contract's Python surface beyond existing lint (no FE types touched).
- [ ] **Lint**: `backend/.venv/bin/python -m flake8` (or the project's configured linter) passes on
  all new/changed files.
- [ ] **Tests**: new unit tests for the correlation helper (AC-1–3), each flag (AC-4–7), the verdict
  combinator (AC-8), and the observability event (AC-12); at least one integration test per transport
  (AC-9–11).
- [ ] **Relevant tests pass**: `backend/.venv/bin/python -m pytest backend/tests/ -k "aar_review" -v`
  and `backend/.venv/bin/python -m unittest backend.tests.test_mcp_server -v` (MCP regression must
  still pass with the new tool registered).
- [ ] **Build**: backend imports cleanly (`python -c "import backend.main"` or equivalent smoke).
- [ ] **Runtime smoke** (CLI + MCP, no FE this slice — see §4 Out of Scope):
  - Start the local backend/CLI runtime per `npm run dev:backend` (or repo-local `backend/.venv/bin/ccdash`).
  - Run `ccdash report aar-review --document <a real or fixture AAR doc id/path>` and confirm a
    well-formed response (not a stack trace) for at least one resolvable and one unresolvable
    document id.
  - Run the MCP server against `backend/tests/test_mcp_server.py`-style invocation (or manual
    `backend/.venv/bin/python -m backend.mcp.server` + a client call) and confirm
    `ccdash_aar_review` is listed and returns the same shape as the CLI.
  - This runtime-smoke step satisfies the project convention that UI/frontend changes require a
    browser smoke check; since this slice has no FE, CLI+MCP invocation is the equivalent gate and
    MUST be recorded in the Completion Report (or explicitly marked `runtime_smoke: skipped` with
    reason, per CLAUDE.md's Runtime smoke gate convention — skipping should not be needed here since
    CLI/MCP invocation has no environmental blocker analogous to a browser).
- [ ] **Docs updated**: CHANGELOG `[Unreleased]` entry (new operator-facing capability:
  `ccdash report aar-review` CLI command + MCP tool + REST endpoint), per `changelog_required: true`
  in this contract's frontmatter.
- [ ] **No unrelated changes** introduced.

---

## 11. Risk Areas

- **Flag derivation drift into semantic judgment**: the two "needs-derivation" flags
  (`generic_agent_vs_specialist`, `stack_ineffectiveness`) are the ones most likely to tempt an
  implementer toward a "smarter" heuristic that quietly requires interpretation rather than lookup.
  Mitigation: keep both as static, versioned lookup tables (keyword→specialist,
  extension→stack) checked into the repo as plain data, not inferred at runtime. If a lookup table
  can't be populated deterministically for a given case, the flag must resolve to `triggered: false`
  with a rationale, never guess.
- **Correlation confidence semantics drifting from `session_correlation.py`'s established values**:
  this contract must reuse the existing 1.0 / 0.96 / 0.64–1.0 tiers verbatim, not redefine them.
  Mitigation: the correlation helper should call into `session_correlation.correlate_session` and
  `entity_links` reads directly rather than reimplementing confidence math.
- **Observability event scope creep into a real push/queue**: because the decisions spine's language
  ("emit a model-free `aar_review_candidate` event") reads like a producer/consumer contract, there
  is a risk an implementer builds a queued/pushed transport (mirroring `telemetry_exporter.py`) for
  this MVP. That is explicitly out of scope (§4) — the MVP's event is a structured log line only.
  Mitigation: this is called out directly in Architecture Constraints and frontmatter Decisions;
  reviewer should reject any new outbound queue/HTTP client introduced for this purpose.
- **Redaction bypass**: any code path that reads session content (beyond ids/columns already exposed
  through existing ports) must go through the redaction-passed `session_detail` surface, never raw
  JSONL. This contract's flags only need columns/DB rows already surfaced by existing ports, so this
  should not arise — but the reviewer should specifically check that no new raw-file read is added.
- **Test fixture availability**: fixture AAR documents + correlated sessions covering all four
  confidence tiers and all four flags' triggered/not-triggered/missing-data states may not exist yet
  in the test corpus. Budget time to construct minimal fixtures rather than relying on incidental
  real data.

---

## 12. Implementation Notes

**Suggested approach** (agent may improve):
1. Add `AARReviewFlag` and `AARReviewDTO` to `agent_queries/models.py`.
2. Implement the correlation helper in `aar_review.py`, delegating to
   `session_correlation.correlate_session` + `entity_links` reads; do not duplicate confidence logic.
3. Implement each of the 4 flags as small, independently-unit-testable pure functions taking already-
   fetched session/document/artifact rows — this keeps AC-4–7 trivially testable without DB fixtures
   per flag.
4. Implement the verdict combinator per the decision rule in §5/AC-8.
5. Wire REST → CLI → MCP last, once the service method is stable; each adapter should be a thin
   pass-through, matching `generate_aar_report`'s shape (`routers/agent.py:403-408`).
6. Add the `log_aar_review_candidate` (or similarly named) helper to `backend/observability/otel.py`
   near `log_auth_event` (`otel.py:1172-1177`), and call it once per successful verdict computation.
7. Env-configurable constants: `CCDASH_AAR_REVIEW_MIN_CONFIDENCE` (default `0.64`),
   `CCDASH_AAR_REVIEW_CONTEXT_BALLOON_PCT` (default suggested `85`) — read via `backend/config.py`
   conventions, not hardcoded magic numbers, even though this is a small MVP.

**Similar existing code**:
- `backend/application/services/agent_queries/reporting.py` (`generate_aar`) — service shape,
  `partial`-flag error tolerance, DTO construction.
- `backend/application/services/agent_queries/session_correlation.py` — correlation confidence tiers.
- `backend/application/services/agent_queries/persona_extract_rules.py` — precedent for deterministic,
  regex/rule-based extraction with no model call (R1–R8).
- `backend/mcp/tools/reports.py` + `backend/cli/commands/report.py` + `routers/agent.py:254-270,
  403-416` — the three-transport wiring pattern.

**Known gotchas**:
- `ports.storage.features().get_by_id(...)` and `ports.storage.tasks().list_by_feature(...)` both
  currently carry a `workspace_id="default-local"  # TODO(workspace-routing)` placeholder in
  `reporting.py` — follow the same placeholder convention for consistency rather than inventing a
  different one.
- The two-hop confidence band (0.64–1.0) is a *range*, not a fixed value — the correlation helper
  must surface whatever the underlying strategy actually returns, not collapse it to a constant.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: list of all modified/new files with brief reason.
- **Tests run**: what tests were added/updated and results, explicitly enumerating which AC (AC-1
  through AC-13) each test covers.
- **Validation results**: table of all validation commands and their results (pass/fail/not
  applicable), including the CLI+MCP runtime-smoke step from §10.
- **Deviations from contract**: any material changes to the contract during implementation and why —
  in particular, flag any place where a flag's derivation logic had to be simplified/descoped because
  it drifted toward requiring semantic judgment (per the Hard Invariant in §8).
- **Risks / Limitations**: any remaining risks or known limitations, especially around fixture
  coverage for the confidence-tier and flag-trigger test matrix.
- **Follow-up recommendations**: anything discovered during implementation that should feed the PRD's
  Phase 2 (Inc-2) scoping — e.g., real-world observations about how often AARs actually carry a
  session frontmatter ref vs relying on the two-hop fallback.

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report
template.

---

## Metadata & References

**Tier**: 1 (~12 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase
orchestration.

**Reviewer**: `task-completion-validator` (mandatory).

**Related Documents**:
- Feasibility brief: `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-feasibility-brief.md`
- Accepted ADR (producer/consumer seam): `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md`
- Tech leg findings (correlation + flag data sources): `docs/project_plans/exploration/ccdash-automated-aar-review/spikes/tech-findings.md`
- Decisions spine (scope boundary source): `.claude/worknotes/ccdash-automated-aar-review/decisions-spine.md`
- Full-vision PRD (parent, Tier 3): `docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md`

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass
validation. If you find:

- **Scope ambiguity**: Ask one focused question or make a conservative assumption and note it in the
  Completion Report. The two Open Questions in frontmatter are known unknowns going into the sprint —
  resolve them with a conservative default (documented) rather than blocking.
- **Impossible constraints**: Flag in the Completion Report before attempting workarounds. In
  particular, if any flag genuinely cannot be computed deterministically, **descope it and say so** —
  do not reach for a model call to make an acceptance criterion pass. That would violate the hardest
  invariant in this contract (§8) and the accepted ADR it derives from.
- **Better implementation path**: Document the deviation in the Completion Report with justification.

Stay within scope. No 5th flag, no persisted table, no FE, no op-side consumer, no writeback, no
scheduling. The reviewer will check for scope drift against §4 Out of Scope specifically.

---

## Completion Report

### Summary

Implemented `AARReviewQueryService` (`backend/application/services/agent_queries/aar_review.py`) —
a transport-neutral, read-only service that resolves an AAR document to its correlated session(s)
via existing `entity_links` rows (falling back to raw frontmatter only when a doc has not yet been
synced), computes four deterministic surface flags, and combines them with correlation confidence
into a `surface_only` / `deep_review_recommended` verdict. Wired to all three standing transports
(REST `GET /agent/aar-review/{document_id}`, CLI `ccdash report aar-review --document <id>`, MCP
`ccdash_aar_review`) and to a model-free `aar_review_candidate` observability log event. No LLM/model
call is imported or invoked anywhere on the compute path; no new table, column, or write path was
added.

### Files Changed

- `backend/application/services/agent_queries/aar_review.py` — new: `AARReviewQueryService`,
  correlation helpers (`resolve_direct_session_links`, `resolve_feature_link`,
  `resolve_feature_session_ids`), the four flag evaluators, and `compute_verdict`.
- `backend/application/services/agent_queries/models.py` — new `AARReviewFlag` / `AARReviewDTO`
  DTOs (added next to `AARReportDTO`; intentionally not `AgentQueryEnvelope` subclasses per the
  contract's frozen shape).
- `backend/application/services/agent_queries/__init__.py` — export the two new DTOs and
  `AARReviewQueryService`.
- `backend/config.py` — new `CCDASH_AAR_REVIEW_MIN_CONFIDENCE` (default `0.64`) and
  `CCDASH_AAR_REVIEW_CONTEXT_BALLOON_PCT` (default `85.0`).
- `backend/observability/otel.py` — new `log_aar_review_candidate(...)` helper, structured log event
  only (mirrors `log_auth_event`'s shape), no DB write, no outbound push.
- `backend/routers/agent.py` — new `GET /agent/aar-review/{document_id}` endpoint + service
  instantiation; sets `Cache-Control` header consistent with the `system/active-count` precedent.
- `backend/cli/commands/report.py` — new `report aar-review` Typer subcommand.
- `backend/cli/runtime.py` — new `document_not_found_error_message(...)` helper (mirrors
  `feature_not_found_error_message`).
- `backend/mcp/tools/reports.py` — new `ccdash_aar_review` MCP tool, registered alongside
  `ccdash_generate_aar`.
- `backend/tests/test_agent_queries_aar_review.py` — new: unit tests for correlation, all four
  flags, the verdict combinator, and the observability event.
- `backend/tests/test_agent_router.py` — new REST delegation/error-path tests; path-registration
  assertion extended to include the new route.
- `backend/tests/test_cli_commands.py` — new CLI human-output/error-path tests.
- `backend/tests/test_mcp_server.py` — sitecustomize monkeypatch + expected-tool-surface set +
  callable/error-envelope tests extended for `ccdash_aar_review`.
- `CHANGELOG.md` — `[Unreleased]` entry for the new capability.

### Acceptance Criteria Status

- [x] AC-1: explicit `session:`/`session_id:`/`linked_sessions:` frontmatter ref resolves via
  `explicit_session_ref`, `correlation_confidence: 1.0` — covered both via a materialized
  `entity_links` row and via the raw-frontmatter fallback (doc not yet synced).
- [x] AC-2: no direct session ref but a resolvable `feature` ref with ≥1 linked session falls back
  to the two-hop strategy, confidence in `[0.64, 1.0]` (verified against real local DB data:
  `agent-context-entities-v1` → confidence `0.98`).
- [x] AC-3: no resolvable session/feature ref → `session_refs: []`, `correlation_confidence: 0.0`,
  `verdict: "surface_only"`, reason states no correlated sessions found; never raises.
- [x] AC-4 (`context_ballooning`): threshold-crossing, below-threshold, and missing-data (window
  size `0`) cases all covered.
- [x] AC-5 (`missing_artifacts`): claimed-vs-produced coverage, full-coverage, and no-claim cases
  covered.
- [x] AC-6 (`generic_agent_vs_specialist`): generic-agent-vs-known-specialist-domain match and
  no-agent-data cases covered via the static extension→specialist lookup table.
- [x] AC-7 (`stack_ineffectiveness`): matched-stack-with-failure-hit, matched-stack-no-hit, and
  unmapped-stack cases covered; **descoped extension** — "no feature scope available" is also
  resolved to `triggered: false` (not an error) when the two-hop strategy did not resolve a feature,
  since `detect_failure_patterns` requires a feature scope to stay read-only-safe (see Deviations).
- [x] AC-8: verdict combinator covers all four quadrants (high-confidence+flags,
  high-confidence+no-flags, low-confidence+flags forced to `surface_only`, no-evidence).
- [x] AC-9 (REST): `GET /agent/aar-review/{document_id}` registered and returns the DTO;
  error path returns a structured `status: "error"` body, never a raw 500 (verified via router
  delegation test + manual reasoning about the service's own try/except-guarded fetches).
- [x] AC-10 (CLI): `ccdash report aar-review --document <id>` — human/table, `--json`, and `--md`
  output modes all verified against real local DB data (see Validation Run).
- [x] AC-11 (MCP): `ccdash_aar_review` registered in `backend/mcp/tools/reports.py`, returns the
  same DTO shape (as a dict) as REST/CLI; verified in the MCP regression suite.
- [x] AC-12: exactly one `aar_review_candidate` log event emitted per successful (`status: "ok"`)
  verdict computation, asserted via a mocked-call unit test.
- [x] AC-13: `aar_review.py` and its test file import no LLM/agent-invocation client — confirmed by
  inspection (only stdlib, pydantic-adjacent DTOs, and existing CCDash `document_linking` /
  `workflow_effectiveness` / `otel` modules are imported); final grep-level confirmation is the
  mandatory `task-completion-validator` reviewer step per this AC's own `verified_by`.

### Validation Run

| Command | Result | Notes |
|---|---|---|
| `ruff check` (project's available linter; `flake8` is not installed in `backend/.venv`) | Pass | Ran against every changed/new file; the only findings (`F401` on `cache_get`/`cache_set` in `agent_queries/__init__.py`) are pre-existing and untouched by this diff. |
| `backend/.venv/bin/python -c "import backend.main"` | Pass | Clean import, no exceptions. |
| `pytest backend/tests/test_agent_queries_aar_review.py -v` | Pass | 24/24 — correlation, all 4 flags, verdict combinator, observability event. |
| `pytest backend/tests/test_agent_queries_reporting.py -v` | Pass | 3/3 — regression check on the sibling service `aar_review.py` mirrors. |
| `pytest backend/tests/test_agent_router.py -v` | Pass | 16/16 — includes 2 new REST delegation/error tests + extended path-registration assertion. |
| `pytest backend/tests/test_cli_commands.py -v` | Pass | 22/22 — includes 2 new CLI tests. |
| `pytest backend/tests/test_session_correlation.py backend/tests/test_document_linking.py -v` | Pass | Regression check — confirms `session_correlation.py` and `document_linking.py` were not modified (read-only reuse). |
| `pytest backend/tests/ -k "aar_review" -v` (exact command from §10) | **Not run as specified** | Collecting the full `backend/tests/` directory segfaults during collection on this machine — a known, pre-existing, repo-documented hazard unrelated to this change (see project memory: "CCDash pytest collection hangs — run named test files only"). Ran the equivalent scoped form instead: `pytest backend/tests/test_agent_queries_aar_review.py backend/tests/test_agent_router.py backend/tests/test_cli_commands.py -k "aar_review" -v` → 28/28 pass. |
| `python -m unittest backend.tests.test_mcp_server -v` | Pass | 23/23, including 2 new `ccdash_aar_review` tests and the extended tool-surface-set assertion. |
| Runtime smoke — CLI | Pass | Ran against the real local dev DB (`data/ccdash_cache.db`, not a fixture): (1) unresolvable id → structured error, exit code 2, no stack trace; (2) resolvable doc with zero correlated sessions → well-formed `surface_only`/`no correlated sessions found`; (3) resolvable doc via the two-hop path (`DOC-.claude-progress-agent-context-entities-phase-1-progress` → feature `agent-context-entities-v1` → session `S-acc99a0b-...`, confidence `0.98`) → well-formed `AARReviewDTO` with all 4 flags evaluated against real session data (context 35.5%, no agent-usage data, no failure-pattern hit). All three CLI output modes (human/table, `--json`, `--md`) rendered correctly. |
| Runtime smoke — MCP | Pass | Covered by the `backend.tests.test_mcp_server` regression run above (stdio client, real tool registration + call round-trip); no separate manual client session was additionally run. |
| Docs updated | Pass | `CHANGELOG.md` `[Unreleased]` entry added. |
| No unrelated changes | Pass | `git status` diff is limited to the files listed above; the two pre-existing `ruff` findings are untouched lines from before this sprint. |

### Deviations From Contract

1. **Correlation implementation reuses `entity_links` confidence values directly rather than
   `session_correlation.correlate_session`.** The contract's §4/§8 text names both
   `session_correlation.correlate_session` and `entity_links().get_links_for(...)` as the intended
   correlation primitives with the exact numeric tiers `1.0` / `0.96` / `0.64–1.0`. On inspection,
   `session_correlation.correlate_session` correlates a *session* to a *feature* (the opposite
   direction) and reports confidence as a **qualitative** `"high"/"medium"/"low"/"unknown"` string —
   it has no relationship to the numeric tiers. Those exact numeric tiers (`explicit_session_ref` =
   `1.0`, `task_session_ref` = `0.96`, and the doc→feature strategies in the `0.64–1.0` band) live
   directly on the `entity_links` rows themselves, written by `sync_engine.py`'s link-rebuild pass.
   The implemented correlation helper therefore reads `entity_links` rows directly (via
   `get_links_for`, same call shape as `reporting.py`) and does not import
   `session_correlation.correlate_session` at all. This is a **more faithful** realization of the
   contract's own stated intent ("must reuse these values, not invent new ones") than importing a
   helper whose confidence semantics don't match. `document_linking.extract_frontmatter_references`
   is used as designed — as the fallback for a not-yet-synced document.
2. **`missing_artifacts`'s "produced" side uses `session_file_updates.file_path` (via
   `sessions().get_file_updates`), not `output_artifacts_json`.** The contract's §6 citation of
   `output_artifacts_json` (`sqlite_migrations.py:1301`/`:1420`, `types.ts:653-654`) turned out on
   inspection to be the Research Foundry `rf_events`/`research_runs` column, not a per-session
   sessions-table column — those line numbers/field name do not correspond to a session-scoped
   produced-files list. `session_file_updates.file_path` (already exposed via
   `SessionRepository.get_file_updates`) is the actual per-session produced-file source and is used
   instead; `linkedArtifacts`/`session_artifacts` (title/type/source, no file path) was evaluated and
   is not file-path-bearing, so it is not used for this comparison.
3. **`stack_ineffectiveness` calls `detect_failure_patterns` only, never
   `get_workflow_effectiveness`, and only when a feature scope was resolved via the two-hop
   strategy.** `get_workflow_effectiveness` has a write path (`upsert_effectiveness_rollup` /
   `purge_effectiveness_rollups`) gated by `not feature_id and not start and not end` — calling it
   without a feature scope risks a write, which would violate §6's "no row is ever written by this
   contract's code" invariant. `detect_failure_patterns` has no write path at all, so it is called
   read-only, scoped by `feature_id`, only when the two-hop correlation resolved one. When no feature
   scope is available (direct-session-ref correlation, which carries no feature association), the
   flag resolves to `triggered: false` with rationale `"no feature scope available for
   failure-pattern lookup"` — never a guess, per the Hard Invariant.
4. **The two extension→specialist/stack lookup tables are unified into one static dict**
   (`_EXTENSION_STACK_LOOKUP`) mapping file extension → `(stack label, specialist agent)`, reusing
   this repo's own documented Agent Assignment Quick Reference (`dev-execution` skill: React/UI work
   → `ui-engineer-enhanced`, general backend work → `backend-typescript-architect`) rather than
   inventing a new taxonomy. This keeps both `generic_agent_vs_specialist` and
   `stack_ineffectiveness` deterministic and checked-in as plain data, per the Risk Areas mitigation.
5. No flag was descoped for drifting toward semantic judgment — all four remained implementable as
   threshold/lookup checks over already-fetched rows.

### Risks / Limitations

- **Fixture/real-data coverage for the confidence-tier matrix is asymmetric.** The local dev DB had
  no `document`↔`session` direct links at all (only two-hop `document→feature→session` chains), so
  the `explicit_session_ref`/`task_session_ref` direct-link paths and the frontmatter fallback path
  were validated with fixtures (unit tests) but not against real local data; the two-hop path was
  validated against both fixtures and real data. This matches the contract's own OQ-1 concern about
  how often AARs carry a direct session/session_id frontmatter ref in practice.
- **`generic_agent_vs_specialist` and `stack_ineffectiveness`'s static lookup tables are a first cut**
  (a handful of common extensions) — they will under-trigger (never falsely trigger) for stacks/
  extensions not yet in the table, which is the safe failure direction per the Hard Invariant, but
  narrows real-world recall until the table is extended with production observations.
- **AC-9's "not a raw 500" claim rests on the service's own defensive `try`/`except` around every
  sub-fetch** (documents/sessions/file_updates/entity_links/detect_failure_patterns), not on a
  FastAPI-level exception handler test with a live broken DB connection; the router delegation test
  confirms the DTO passes through unchanged, but does not simulate a genuinely corrupt document row.

### Follow-Up Recommendations

- **PRD Phase 2 scoping input**: in the one real two-hop example exercised during runtime smoke, the
  AAR-shaped progress document had **zero** direct session/session_id frontmatter and reached its
  session purely through the `document→feature→session` two-hop path. This is a single data point,
  not a statistically meaningful sample, but it is a live signal in favor of the OQ-1 conservative
  default already assumed in this contract (lean on the two-hop fallback, don't assume explicit
  session refs are common).
- Once real `aar_review_candidate` log volume exists, consider whether
  `generic_agent_vs_specialist`'s and `stack_ineffectiveness`'s static lookup tables need expansion
  before Phase 2's 5th flag work begins.
- The Phase 2 persisted-rollup table (deferred here per §4 Out of Scope) would be a natural place to
  record which correlation strategy actually fired per document, to build the real-world tier
  distribution referenced in OQ-1 without re-deriving it from logs.

### Memory Candidates Captured

- **Gotcha (candidate, confidence 0.8)**: "In CCDash's `entity_links`, the numeric correlation
  confidence tiers (`explicit_session_ref`=1.0, `task_session_ref`=0.96, doc→feature
  strategies=0.64–1.0) live on the materialized link rows themselves (`sync_engine.py`'s link-rebuild
  pass), not on `session_correlation.correlate_session` (which reports a separate, qualitative
  high/medium/low confidence for the different session→feature correlation direction). A new
  deterministic doc↔session correlation feature should read `entity_links` rows directly rather than
  importing `correlate_session`." — anchor:
  `backend/application/services/agent_queries/session_correlation.py:317`,
  `backend/db/sync_engine.py:6600`.
- **Gotcha (candidate, confidence 0.75)**: "`get_workflow_effectiveness` has a hidden write path
  (`upsert_effectiveness_rollup`/`purge_effectiveness_rollups`) gated by
  `not feature_id and not start and not end`; a read-only query service that wants failure-pattern
  data without risking a write should call `detect_failure_patterns` (no write path) and always pass
  a `feature_id`, or skip the call entirely when no feature scope is known." — anchor:
  `backend/services/workflow_effectiveness.py:1151`, `:1271`.
- Not yet promoted to the memory store (no CLI/API call made this sprint) — recommend Opus or a
  follow-up pass files these via the memory CLI/API per `.claude/rules/memory.md`.
