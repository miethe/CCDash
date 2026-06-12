---
schema_version: 2
doc_type: phase_plan
title: "CCDash Core Remediation v1 — Phases 1-3: Session Access (Transcript Service, REST v1, MCP/CLI)"
status: draft
created: 2026-06-10
updated: 2026-06-10
phase: 1
phase_title: "Transport-neutral transcript service + redaction; REST v1 detail+transcript; MCP/CLI session surfaces"
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
entry_criteria:
  - "Phase 0 green: get_by_id/get_many_by_ids enforce project_id (SQLite + Postgres); ADR-007 collision tests pass; get_session_family_v1 project-scoped (family anchor propagates project_id)."
  - "SessionTranscriptService.list_session_logs (backend/application/services/sessions.py) confirmed available and transport-neutral."
  - "Cross-project reads are zero-leak per Phase 0 collision fixture (hard gate; Phases 2/3 may not ship before this)."
exit_criteria:
  - "agent_queries/session_detail.py returns transcript + subagents + tokens + artifacts + links for ANY project_id via include-flags and cursor pagination; redaction unit-tested; no duplicate transcript reader introduced."
  - "GET /api/v1/sessions/{id}/detail?project_id=<id> returns full detail incl. transcript for a NON-active project; envelope pinned by contract test; redaction runs before serialization."
  - "MCP session_search/session_detail/session_transcript + repo-CLI session group return full detail for a non-active project; MCP/CLI/REST parity test green; MCP payload-size/chunk budget defined and documented; SKILL.md updated; runtime smoke recorded."
---

# Implementation Plan — Phases 1-3: Session Access

**Plan ID**: `IMPL-2026-06-10-CCDASH-CORE-REMEDIATION-P1-3`
**Date**: 2026-06-10
**Author**: implementation-planner (Opus-orchestrated)
**Related Documents**:
- **PRD**: `/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md`
- **Root plan**: `docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md`
- **Decisions block**: `.claude/worknotes/ccdash-core-remediation/decisions-block.md`
- **Diagnostic (evidence)**: `docs/project_plans/reports/investigations/ccdash-core-remediation-diagnostic-v1.md`
- **ADR-006** (DB-authoritative registry), **ADR-007** (DB write-failure surfacing): `docs/project_plans/adrs/`

**Complexity**: Large (top program deliverable; 3 of 13 phases)
**Total Estimated Effort**: ~13 pts (Phase 1 ~5, Phase 2 ~3, Phase 3 ~5)

## Executive Summary

These three phases deliver the program's top deliverable: any agent or external consumer can pull full session detail — transcript, subagents, workflow content, token telemetry, artifacts, links — for any project, over REST/MCP/CLI, with secret/PII redaction. Phase 1 builds the transport-neutral `session_detail` service by reusing the existing `SessionTranscriptService` (not a new retrieval engine) and adds a redaction layer. Phase 2 wires `/api/v1` detail + transcript endpoints with cross-project params and a pinned contract. Phase 3 exposes the same service through MCP tools and a repo-CLI session group, proves parity across all three transports, defines an MCP payload budget, and updates the MCP SKILL.md.

Architecture, conventions, and invariants are defined in root `CLAUDE.md` (transport-neutral agent-queries pattern, Router→Service→Repository, ADR-006/007, redaction local-trust model) and are referenced by path, not restated here.

## Implementation Strategy

### Architecture sequence (these phases)

1. **Service layer (Phase 1)** — `backend/application/services/agent_queries/session_detail.py` over `SessionTranscriptService`; redaction middleware; cursor pagination envelope `{items, cursor, limit, nextCursor}`.
2. **API layer (Phase 2)** — `/api/v1` handlers + response models + contracts package; cross-project `project_id` param.
3. **Agent transports (Phase 3)** — MCP tools + repo-CLI session group + standalone CLI rewire; parity test; payload budget; SKILL.md.

### Critical path

Phase 0 (prerequisite, external to this file) → **Phase 1 → Phase 2 → Phase 3**. Strictly sequential within this file: Phase 2 consumes the Phase 1 service contract; Phase 3 consumes both the service and the v1 envelope for parity.

### Plan Generator Rules applied

- **R-P1** (scope-word AC expansion): Any AC using "all surfaces / any project / across" is expanded with explicit `target_surfaces` lists. Applied to the redaction-everywhere AC (Phase 1), the parity AC, and the SKILL.md/FE-touching ACs (Phase 3).
- **R-P4** (UI/agent-facing runtime smoke + MCP payload budget): Phase 3 carries a runtime-smoke task (MCP client + repo-CLI exercised against a realistic transcript via the dev server) AND a dedicated MCP payload-size/chunk-budget task. No Phase 3 `status: completed` on unit tests alone (CLAUDE.md runtime-smoke gate; PRD §6.2).

> R-P2 (auto FE-fallback AC) and R-P3 (integration_owner) are not triggered here: Phases 1-3 add no new optional backend FE field and no `*.tsx` files (FE fallbacks for new columns/unpriced state land in Phases 5/6). Phase 3 "FE-facing surface" = SKILL.md + agent-facing payloads, smoke-covered per R-P4.

### Column conventions

Per template Phase Breakdown header: `Estimate` = task size (story points); `Model` = executor (`sonnet`/`haiku`); `Effort` = reasoning budget (claude: `adaptive`|`extended`). Subagent + model routing taken from the decisions block §Agent Routing / §Model Routing (executors sonnet/adaptive; docs haiku/adaptive).

---

## Phase 1: Transport-neutral transcript service + redaction

**Estimate**: ~5 pts
**Dependencies**: Phase 0 complete (cross-project session correctness green)
**Primary Subagent**: python-backend-engineer
**Reviewer**: code-reviewer; task-completion-validator (gate)
**Resolves**: FR-3, FR-4; OQ-1 (redaction strategy)

### Overview

Build `backend/application/services/agent_queries/session_detail.py` as the single source of truth for session detail retrieval. It reuses `SessionTranscriptService.list_session_logs` (already used by `feature_forensics.py`) — **no new transcript reader** (decisions block: "exposure/wiring + redaction, NOT a new retrieval engine"). It assembles transcript + subagents + token telemetry + artifacts + links behind include-flags, returns cursor-paginated envelopes `{items, cursor, limit, nextCursor}`, and runs a composable redaction layer (OQ-1 resolution: **layered** — known secret patterns + tool-name-aware payload field redaction, env-configurable) on all payloads before they leave the service.

### Entry criteria

- Phase 0 cross-project repository correctness green (project_id enforced on ID-based reads; family anchor propagates project_id).
- `SessionTranscriptService.list_session_logs` confirmed transport-neutral and project-parameterizable.

### Exit criteria

- Service returns transcript + subagents + tokens + artifacts + links for any `project_id` (not just active) via include-flags + cursor pagination.
- Redaction unit-tested: known secret patterns scrubbed; tool-name-aware payload field redaction active; zero payload leaks in fixtures.
- No duplicate transcript-reading path introduced; `SessionTranscriptService` remains the sole reader.

### Task table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| T1-001 | Service scaffold + include-flag contract | Create `agent_queries/session_detail.py` exposing `get_session_detail(project_id, session_id, include={transcript,subagents,tokens,artifacts,links}, cursor, limit)`. Reuse `SessionTranscriptService.list_session_logs`; thread project_id end-to-end; reuse Phase 0 project-safe repo reads. No new reader. See AC R1.1. | AC R1.1 (below) | 2 pts | python-backend-engineer | sonnet | adaptive |
| T1-002 | Cursor pagination envelope | Return `{items, cursor, limit, nextCursor}` for transcript and any list-shaped include; opaque cursor encodes offset/position; `nextCursor: null` at end; default + max `limit` documented as service constants. | Envelope shape matches `{items,cursor,limit,nextCursor}`; round-trip cursor test returns next page with no gaps/dupes; over-max `limit` clamps and is logged; unit tests cover empty, single-page, multi-page. | 1 pt | python-backend-engineer | sonnet | adaptive |
| T1-003 | Layered redaction module | New redaction module (e.g. `agent_queries/redaction.py`): (1) known-secret pattern scan (API keys, bearer tokens, AWS/GCP creds, `.env`-style KEY=secret); (2) tool-name-aware payload field redaction (e.g. `Bash` command env, file-write secrets); env-configurable via `CCDASH_REDACTION_*`. Emits structured redaction-event log (redacted field count only, NEVER contents — PRD §6.2 Observability). | AC R1.2 (below) | 2 pts | python-backend-engineer | sonnet | adaptive |
| T1-004 | Wire redaction before egress + assemble bundle | Apply redaction to assembled transcript/subagent/tool-call payloads inside the service before return (the egress boundary for REST/MCP/CLI). Assemble subagents + tokens + artifacts + links via existing repositories. Add OTEL spans for `get_session_detail`. | Redaction runs on every include branch that can carry payload content; fixture asserting an embedded secret never appears in service output; OTEL span emitted per call; bundle assembles for a non-active project_id in a unit test. | 1 pt | python-backend-engineer | sonnet | adaptive |
| T1-005 | Redaction + non-active-project unit suite | Unit tests: redaction patterns (positive + negative), tool-name-aware field redaction, env-config toggle on/off, and a non-active-project assembly path returning full detail. Asserts no second transcript reader exists (grep/structural guard). | All listed unit cases pass; structural test confirms `SessionTranscriptService` is the only transcript reader (no duplicate). | 1 pt | python-backend-engineer | sonnet | adaptive |

**files_affected** (from decisions block; do NOT read):
- `backend/application/services/agent_queries/session_detail.py` (new)
- `backend/application/services/agent_queries/redaction.py` (new)
- `backend/application/services/sessions.py` (`SessionTranscriptService.list_session_logs:92` — reuse only)
- `backend/application/services/agent_queries/feature_forensics.py` (existing reuse reference)
- `backend/config.py` (`CCDASH_REDACTION_*` env knobs)
- `backend/db/repositories/sessions.py`, `backend/db/repositories/postgres/sessions.py` (Phase 0 project-safe reads — consumed, not edited here)
- `backend/tests/test_session_detail_service.py`, `backend/tests/test_redaction.py` (new)

### Structured Acceptance Criteria

#### AC R1.1: session_detail service returns full detail for any project
- target_surfaces:
    - backend/application/services/agent_queries/session_detail.py
    - backend/application/services/sessions.py
- propagation_contract: >
    `get_session_detail(project_id, session_id, include=..., cursor, limit)` threads project_id into
    every repository call and into `SessionTranscriptService.list_session_logs`; assembled fields
    (transcript, subagents, tokens, artifacts, links) are gated by the `include` flag set; no field
    is read from the active-project singleton.
- resilience: >
    A missing optional segment (e.g. no artifacts, no sidecar) returns an empty list/`null` for that
    include key, never an error; an unknown include flag is ignored with a warning, not a 500.
- visual_evidence_required: false
- verified_by:
    - T1-005
    - T3-008-smoke

#### AC R1.2: layered redaction scrubs secrets/PII across all egress payloads
- target_surfaces:
    - backend/application/services/agent_queries/redaction.py
    - backend/application/services/agent_queries/session_detail.py
- propagation_contract: >
    Redaction is applied inside `session_detail.py` before return, so all three transports
    (REST/MCP/CLI) inherit it without per-transport code. Strategy is layered (OQ-1): pattern scan +
    tool-name-aware field redaction; both layers configurable via `CCDASH_REDACTION_*`.
- resilience: >
    If redaction config is unset, secure defaults apply (patterns ON); if a tool name is unknown,
    generic pattern scan still runs (fail-closed, never fail-open). Redaction-event logs record
    redacted field COUNT only — never payload contents.
- visual_evidence_required: false
- verified_by:
    - T1-005

**Phase 1 Quality Gate:** task-completion-validator — confirm AC R1.1 + R1.2 met, redaction suite green, no duplicate transcript reader, OTEL spans present, existing suites unaffected.

---

## Phase 2: REST /api/v1 detail + transcript endpoints

**Estimate**: ~3 pts
**Dependencies**: Phase 1 complete (service contract stable)
**Primary Subagent**: python-backend-engineer
**Reviewer**: api-librarian (envelope/pagination); task-completion-validator (gate)
**Resolves**: FR-5

### Overview

Expose the Phase 1 service over `/api/v1`. Add v1 handlers + response models in `client_v1.py` / `_client_v1_sessions.py`, define the contract in the contracts package, and accept a cross-project `project_id` param so a non-active project's detail (incl. transcript) is retrievable. The current `get_session_detail_v1` returns analytics facts only (models.py:961, no transcript) and `get_session_family_v1` is active-project-bound (_client_v1_sessions.py:269) — this phase adds the transcript-bearing detail + transcript endpoints and threads cross-project params, building on the Phase 0 family fix.

> ⚠ **Shared `/api/v1` namespace — `remote-ccdash-streaming` (see plan §Contending / Unmerged Work).** The paused streaming branch already added a **write** route `POST /api/v1/ingest/sessions` plus the `_EXPECTED_API_VERSION` versioning convention on this same namespace. This phase owns **read** routes only. Reuse (do not fork) the existing version constant, and add only `sessions/{id}/detail` + `sessions/{id}/transcript` read handlers — do not restructure the v1 router in a way that would reject an additive ingest route on merge.

### Entry criteria

- Phase 1 service exit criteria met; envelope `{items, cursor, limit, nextCursor}` stable.
- Phase 0 family-scope fix in place (`get_session_family_v1` project-scoped).

### Exit criteria

- `GET /api/v1/sessions/{id}/detail?project_id=<id>` returns full detail incl. transcript for a non-active project.
- Response envelope matches contracts-package model; contract test pins shape.
- Redaction (Phase 1) runs before response serialization (inherited via service; asserted at the API layer).

### Task table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| T2-001 | v1 response models + contracts | Define `SessionDetailV1` / `SessionTranscriptPageV1` response models in the contracts package + `_client_v1_sessions.py`; mirror the service include-flags and `{items,cursor,limit,nextCursor}` envelope. | Models serialize the full bundle (transcript/subagents/tokens/artifacts/links); cursor fields present; models importable from `packages/ccdash_contracts`. | 1 pt | python-backend-engineer | sonnet | adaptive |
| T2-002 | Detail + transcript v1 handlers | Add `GET /api/v1/sessions/{id}/detail` and `GET /api/v1/sessions/{id}/transcript` handlers in `client_v1.py`; accept `project_id` query param (cross-project), `include` flags, `cursor`/`limit`; delegate to Phase 1 service. | AC R2.1 (below) | 1 pt | python-backend-engineer | sonnet | adaptive |
| T2-003 | Cross-project param + family-aware detail | Thread `project_id` through to the service and the Phase 0-scoped family lookup so detail for a non-active project resolves the correct family/anchor; reject missing/ambiguous project_id with 400 (not silent active-project fallback). | Non-active project_id resolves correct session + family; omitted project_id returns 400 with actionable message; no active-project fallback path remains. | 0.5 pts | python-backend-engineer | sonnet | adaptive |
| T2-004 | Contract test (envelope pin) + redaction-at-API assertion | Contract test pinning the v1 detail + transcript envelope shape; integration test that a known secret in fixture transcript is absent from the HTTP response body (redaction inherited from service). | AC R2.2 (below) | 0.5 pts | python-backend-engineer | sonnet | adaptive |

**files_affected** (from decisions block; do NOT read):
- `backend/routers/client_v1.py`
- `backend/routers/_client_v1_sessions.py` (`get_session_detail_v1`, `get_session_family_v1:269`)
- `backend/models.py` (`:961` analytics-only detail model — extended/superseded for transcript-bearing response)
- `packages/ccdash_contracts/` (new v1 detail/transcript response contracts)
- `backend/application/services/agent_queries/session_detail.py` (Phase 1 service — consumed)
- `backend/tests/test_client_v1_session_detail.py` (new)

### Structured Acceptance Criteria

#### AC R2.1: v1 detail+transcript endpoints serve any project incl. transcript
- target_surfaces:
    - backend/routers/client_v1.py
    - backend/routers/_client_v1_sessions.py
    - packages/ccdash_contracts
- propagation_contract: >
    Handlers read `project_id` from query param and pass it (with `include`, `cursor`, `limit`) to
    `session_detail.get_session_detail`; the response is the contracts-package model. Transcript page
    uses the same `{items,cursor,limit,nextCursor}` envelope as the service.
- resilience: >
    Unknown session_id → 404; missing project_id → 400 (never active-project fallback); empty optional
    segment → empty list/null in the typed response, not an error.
- visual_evidence_required: false
- verified_by:
    - T2-004
    - T3-007

#### AC R2.2: redaction runs before serialization and envelope is contract-pinned
- target_surfaces:
    - backend/routers/client_v1.py
    - packages/ccdash_contracts
- propagation_contract: >
    Redaction is inherited from the Phase 1 service (applied before return); the API layer adds no
    raw passthrough. A contract test pins the envelope so downstream consumers (Phase 3 parity,
    Phase 10 OpenAPI) have a stable shape.
- resilience: >
    If the service returns a redacted field-count >0, the response still serializes (redacted
    placeholders, not omitted keys); contract test tolerates redacted placeholder values.
- visual_evidence_required: false
- verified_by:
    - T2-004

**Phase 2 Quality Gate:** task-completion-validator (+ api-librarian envelope/pagination review) — confirm AC R2.1 + R2.2 met, contract test green, no active-project fallback remaining.

---

## Phase 3: MCP session tools + repo-CLI session group

**Estimate**: ~5 pts
**Dependencies**: Phase 1 + Phase 2 complete
**Primary Subagent**: python-backend-engineer (MCP + CLI)
**Reviewer**: ai-artifacts-engineer (SKILL.md); task-completion-validator (gate)
**Resolves**: FR-6, FR-7; OQ-2 (MCP chunk/envelope budget)

### Overview

Expose the Phase 1 service through the remaining two transports and prove parity. Add `backend/mcp/tools/sessions.py` (`session_search`, `session_detail`, `session_transcript`), a repo-CLI session group `backend/cli/commands/session.py`, rewire the standalone CLI to the new service, write a MCP/CLI/REST parity test, define a concrete MCP payload-size/chunk budget (OQ-2), and update the MCP SKILL.md. Per R-P4 + the CLAUDE.md runtime-smoke gate, Phase 3 carries an explicit runtime-smoke task (MCP client + repo-CLI exercised against a realistic transcript via the dev server) and a dedicated payload-budget task; Phase 3 cannot be `completed` on unit tests alone.

### Entry criteria

- Phase 1 service + Phase 2 v1 envelope stable (parity needs all three transports comparable).
- Dev server runnable for runtime smoke (`npm run dev` / `uvicorn backend.main:app`).

### Exit criteria

- MCP `session_detail` returns full detail (transcript + subagents + workflow) for a non-active project session.
- MCP/CLI/REST parity test green: same session via all three surfaces returns semantically equivalent content.
- MCP chunk/pagination budget defined + documented (concrete default + documented max bytes).
- Standalone CLI `ccdash session get` rewired to the new service; SKILL.md updated.
- Runtime smoke recorded (or explicit `runtime_smoke: skipped` + reason if dev server unavailable — CLAUDE.md gate).

### Task table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| T3-001 | MCP session tools | Add `backend/mcp/tools/sessions.py` with `session_search`, `session_detail`, `session_transcript`; each accepts `project_id`; delegate to Phase 1 service; register with the FastMCP stdio server. | AC R3.1 (below) | 1.5 pts | python-backend-engineer | sonnet | adaptive |
| T3-002 | Repo-CLI session group | Add `backend/cli/commands/session.py` with `session search`/`session get`/`session transcript` (Typer); `--project`, `--json`/`--md`, `--cursor`/`--limit`; delegate to the same service. | Commands return full detail for a non-active project in JSON and markdown; `--project` required for cross-project; help text lists flags. | 1 pt | python-backend-engineer | sonnet | adaptive |
| T3-003 | Standalone CLI rewire | Rewire standalone CLI `ccdash session get` (over HTTP via `client_v1.py`) to the Phase 2 v1 detail/transcript endpoints; keep flag parity with repo-CLI (`--project`, `--json`, `--timeout`, `--no-cache`). | Standalone `ccdash session get <id> --project <slug>` returns transcript-bearing detail; existing CLI flags honored. | 0.5 pts | python-backend-engineer | sonnet | adaptive |
| T3-004 | MCP payload-size / chunk budget (OQ-2) | Define concrete MCP transcript chunk size + max envelope bytes (resolve OQ-2). Enforce via the service `limit` clamp + a documented per-call byte ceiling; oversize transcript paginates via `nextCursor` rather than truncating silently. Document the budget. | AC R3.2 (below) | 1 pt | python-backend-engineer | sonnet | adaptive |
| T3-005 | MCP/CLI/REST parity test | Parity test: query the same non-active-project session via MCP tool, repo-CLI, and REST v1; assert semantically equivalent content (same transcript items, subagents, token totals, redaction applied identically). | AC R3.3 (below) | 1 pt | python-backend-engineer | sonnet | adaptive |
| T3-006 | SKILL.md update | Update MCP SKILL.md (`ccdash` skill) with the new session tools (names, params, payload budget, project_id usage, redaction note). Bump SPEC/skills-index per docs convention. | SKILL.md documents `session_search`/`session_detail`/`session_transcript` with params + budget + redaction note; skills-index version bumped if applicable. | 0.5 pts | ai-artifacts-engineer | haiku | adaptive |
| T3-007 | MCP server regression test | Extend `backend/tests/test_mcp_server.py` to cover the new tools (registration, non-active project_id, redaction applied, cursor pagination). | New tools registered; non-active project_id returns full detail; redaction asserted; cursor round-trip passes; existing MCP regression cases unaffected. | 0.5 pts | python-backend-engineer | sonnet | adaptive |
| T3-008 | Runtime smoke (MCP + CLI) | Per R-P4 + CLAUDE.md gate: start dev server; exercise MCP `session_detail` via an MCP client and repo-CLI `session get` against a realistic (large) transcript for a non-active project; record no timeout + payload within budget. Record evidence or set `runtime_smoke: skipped` + reason in phase progress. | AC R3.4 (below) | 0.5 pts | python-backend-engineer | sonnet | adaptive |

**files_affected** (from decisions block; do NOT read):
- `backend/mcp/tools/sessions.py` (new)
- `backend/mcp/server.py` (tool registration)
- `backend/cli/commands/session.py` (new)
- `backend/cli/` (group wiring)
- `packages/ccdash_cli/` (standalone CLI rewire + tests)
- `backend/routers/client_v1.py` (consumed by standalone CLI)
- `.claude/skills/ccdash/SKILL.md` + `.claude/specs/skills-index.md` (docs)
- `backend/application/services/agent_queries/session_detail.py` (Phase 1 service — consumed)
- `backend/tests/test_mcp_server.py`, `backend/tests/test_session_parity.py` (new/extended)

### Structured Acceptance Criteria

#### AC R3.1: MCP session tools return full detail for any project
- target_surfaces:
    - backend/mcp/tools/sessions.py
    - backend/mcp/server.py
- propagation_contract: >
    Each MCP tool takes `project_id` and delegates to `session_detail.get_session_detail` (no
    active-project assumption); `session_transcript` exposes `cursor`/`limit`; tools are registered
    on the FastMCP stdio server.
- resilience: >
    Missing project_id → structured tool error (not active-project fallback); unknown session_id →
    structured not-found; empty optional segment → empty list in the tool result.
- visual_evidence_required: false
- verified_by:
    - T3-007
    - T3-008

#### AC R3.2: MCP payload-size / chunk budget enforced and documented (OQ-2)
- target_surfaces:
    - backend/mcp/tools/sessions.py
    - backend/application/services/agent_queries/session_detail.py
    - .claude/skills/ccdash/SKILL.md
- propagation_contract: >
    A concrete chunk size + max envelope byte ceiling is chosen (OQ-2) and enforced via the service
    `limit` clamp plus a per-call byte guard; oversize transcripts paginate via `nextCursor`.
- resilience: >
    Oversize content paginates rather than truncating silently; over-budget single records are
    flagged in the response metadata (e.g. `truncated: true` with a reason) — never silently dropped.
    Budget value documented in SKILL.md.
- visual_evidence_required: false
- verified_by:
    - T3-007
    - T3-008

#### AC R3.3: MCP/CLI/REST parity for non-active-project session
- target_surfaces:
    - backend/mcp/tools/sessions.py
    - backend/cli/commands/session.py
    - backend/routers/client_v1.py
- propagation_contract: >
    All three transports delegate to the single Phase 1 service; parity test queries one non-active
    session via each and asserts semantically equivalent transcript items, subagent list, token
    totals, and identical redaction outcome.
- resilience: >
    Transport-specific envelope wrappers (MCP tool result vs HTTP JSON vs CLI JSON) may differ in
    shape but MUST carry equivalent content; the parity test normalizes wrappers before comparison.
- visual_evidence_required: false
- verified_by:
    - T3-005

#### AC R3.4: runtime smoke — agent-facing surfaces serve realistic transcript without timeout
- target_surfaces:
    - backend/mcp/tools/sessions.py
    - backend/cli/commands/session.py
- propagation_contract: >
    With the dev server up, an MCP client calls `session_detail` and the repo-CLI calls `session get`
    against a realistic (large) non-active-project transcript; both return within client timeout and
    within the Phase 3 payload budget.
- resilience: >
    If the dev server cannot be started, the phase records `runtime_smoke: skipped` with an explicit
    reason (CLAUDE.md gate); a clean unit-test pass is NOT a substitute and does not satisfy this AC.
- visual_evidence_required: >
    Capture MCP tool-call result + CLI output for the realistic transcript (terminal transcript or
    screenshot); attach to phase progress notes.
- verified_by:
    - T3-008

**Phase 3 Quality Gate:** task-completion-validator (+ ai-artifacts-engineer SKILL.md review) — confirm AC R3.1–R3.4 met, parity + MCP regression tests green, payload budget documented, SKILL.md updated, and **runtime smoke recorded** (or `runtime_smoke: skipped` + reason). Per CLAUDE.md, Phase 3 may not be marked `completed` on a unit-test pass alone.

---

## Cross-phase notes

### Sequencing & file ownership

These three phases are strictly sequential (1 → 2 → 3) and do not collide with the program's shared-file hotspots (`runtime.py`, `sync_engine.py`, `config.py` — owned by Phases 5/7/8; this file only adds redaction env knobs to `config.py` in T1-003, single-threaded within Phase 1). Phase 0 is a hard upstream prerequisite (cross-project zero-leak); per the decisions block, Phases 2 and 3 must not ship before Phase 0 is green.

### Deferred items

None. OQ-1 (redaction strategy) resolved in Phase 1 (layered). OQ-2 (MCP payload budget) resolved in Phase 3 (T3-004). No deferred design-spec authoring tasks originate in this file.

### Reliability invariants (PRD §6.2 / ADR-007)

This file adds no new DB write paths (read/exposure only). If a write path is introduced during execution (unexpected), it must use `repositories/base.py:retry_on_locked` and ship a direct-count assertion test (ADR-007), and any independent SQLite connection must issue `PRAGMA busy_timeout = 30000` (CLAUDE.md).

### Progress tracking

`.claude/progress/ccdash-core-remediation/phase-1-progress.md`, `phase-2-progress.md`, `phase-3-progress.md` (one per phase).
