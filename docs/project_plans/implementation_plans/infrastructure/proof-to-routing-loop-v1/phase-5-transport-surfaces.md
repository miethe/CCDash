---
title: 'Phase 5: Transport Surfaces'
schema_version: 2
doc_type: phase_plan
status: draft
created: '2026-07-29'
updated: '2026-07-31'
feature_slug: proof-to-routing-loop
feature_version: v1
phase: 5
phase_title: Transport Surfaces
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
entry_criteria:
- "Phase 3 complete \u2014 RoutingRollupQueryService exists"
exit_criteria:
- DTO contract-lock test + disabled-state test green across REST/MCP/CLI
related_documents:
- docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
- docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
- docs/guides/aar-review-loop.md
- docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
- .claude/worknotes/proof-to-routing-loop/decisions-block.md
spike_ref: null
adr_refs: []
charter_ref: docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-charter.md
changelog_ref: null
test_plan_ref: null
integration_owner: null
ui_touched: false
target_surfaces: []
seam_tasks: null
owner: null
contributors: []
priority: medium
risk_level: medium
category: product-planning
tags:
- phase-plan
- implementation
- infrastructure
- routing-feedback
- transport
milestone: null
commit_refs:
- 5725b75
- e63f3c0
- c995b3f
- ca79e34
- a81ace6
pr_refs: []
files_affected:
- backend/routers/_client_v1_routing_rollup.py
- backend/routers/client_v1.py
- backend/mcp/tools/routing.py
- backend/mcp/tools/__init__.py
- backend/cli/commands/routing.py
- backend/cli/main.py
- backend/tests/test_routing_rollup_transports.py
- backend/tests/test_client_v1_routing_rollup.py
---

# Phase 5: Transport Surfaces

**Parent Plan**: [Proof → Routing Feedback Loop — CCDash Producer Surface (BP-6)](../proof-to-routing-loop-v1.md)
**Duration**: ~1–2 days
**Effort**: 3 story points
**Dependencies**: Phase 3 complete (`RoutingRollupQueryService` exists)
**Team Members**: python-backend-engineer (sonnet)

---

## Phase Overview

This phase clones the shipped Automated AAR Review Loop's three-transport pattern (REST + MCP + CLI)
for the routing-feedback rollup. No new derivation logic is written here — every task is a
mechanical, read-only clone of an already-shipped surface, wiring the same `RoutingRollupResponseDTO`
(frozen by Phase 3's `backend/application/services/agent_queries/models.py`) through the same three
door frames CCDash already uses for `aar_reviews`. Phase 5 has **no frontend surface** — no `.tsx`
files anywhere in `files_affected`, so `ui_touched: false` and no runtime-smoke task applies (R-P4 is
not triggered).

**Wave placement**: this phase runs in the **same wave as Phase 4** (parallel, disjoint files). Phase
5 touches `backend/routers/*`, `backend/mcp/*`, and `backend/cli/*`; Phase 4 touches
`backend/adapters/jobs/*` and `backend/runtime/container.py`. Both depend only on Phase 3 freezing the
`routing_rollup` table shape and the `RoutingRollupQueryService` read contract — once that contract is
frozen, Phase 4 (writer) and Phase 5 (reader) can proceed concurrently with zero file-ownership
conflict. `integration_owner`/`seam_tasks` are `null` for this phase — Phase 6 owns the cross-phase
seam verification (no-LLM guard, mapping-digest parity, disabled-state parity across all three
transports).

**Decision gate — D9 (resolved 2026-07-31, attempted)**: the parent plan's frontmatter carries
`decision_gates: [{gate: "D9 — socialize D5 metric-payload shape with router owner before Phase 5
(Transport Surfaces) ships", status: attempted}]`. D9 is a **schedule risk gate, not a blocking
dependency** — Phase 5 may proceed on its Phase-3-frozen DTO contract regardless of D9's resolution
state, but this phase's completion note (see **Notes → Learnings** below) MUST document the
socialization attempt to the router owner (MeatySkills/`ibm-main`) — even if informal (a Slack
message, a cross-repo issue, or an email thread
is sufficient evidence) — before this phase is marked `completed`. A pending-but-attempted
socialization is an acceptable completion state; a *never-attempted* socialization is not.

### Goals

- Expose the Phase-3-computed `routing_rollup` rollup read-only through REST, MCP, and CLI — the same
  three doors CCDash already opened for `aar_reviews`.
- Guarantee zero live aggregation on any of the three request paths (all three read the same persisted
  rows via `RoutingRollupQueryService`).
- Lock all three transports to the exact same `RoutingRollupResponseDTO` shape so no transport drifts
  into its own reshaped payload.
- Prove the default-off disabled envelope (`CCDASH_ROUTING_FEEDBACK_ENABLED=false`) is byte-identical
  across all three transports (AC-4, partial — finalized in Phase 6).

### Architecture Focus

This phase implements the **Transport/API layer** following CCDash's Router → Service → Repository
pattern — routers call the Phase 3 service directly, never raw SQL:
- **Layer**: API (REST router, MCP tool, CLI command) — no Service or Repository changes; Phase 3 and
  Phase 4 already own those layers.
- **Patterns**: transport-neutral agent-query surface (per root `CLAUDE.md` — "Add new cross-domain
  intelligence reads in `backend/application/services/agent_queries/` first, then wire them into
  `backend/routers/agent.py` [or `client_v1.py`], `backend/cli/`, and `backend/mcp/` as needed").
- **Standards**: the shipped `aar_reviews` three-transport trio is the literal clone anchor for every
  task in this phase — see the parent plan's "Clone Anchor Reference Map" for the full file-to-file
  mapping.

---

## Task Breakdown

### Epic: Read-Only Transport Trio (REST / MCP / CLI)

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|---------------------|-------|--------|--------------|
| T5-001 | REST endpoint | New `backend/routers/_client_v1_routing_rollup.py` mirroring `_client_v1_aar_review.py`'s exact module shape (a `get_routing_rollup_v1(project_id, request_context, core_ports, bypass_cache)` function). Wire `GET /api/v1/routing/rollup` into `backend/routers/client_v1.py` (import + route decorator, same pattern as the existing aar-review route). Read-only — serves Phase 2/4's persisted `routing_rollup` rows, zero live aggregation on the request path. | Route returns the full envelope when enabled; `project_id` required per existing v1 convention | 1 pt | python-backend-engineer | sonnet | adaptive | Phase 3 complete |
| T5-002 | MCP tool | New `backend/mcp/tools/routing.py` with `register_routing_tools(mcp)` exposing `ccdash_routing_rollup`, mirroring `reports.py`'s `ccdash_aar_review` tool shape exactly (same context/ports invocation pattern). Wire `register_routing_tools` into `backend/mcp/tools/__init__.py::register_tools` alongside the existing `register_report_tools` call. | Tool discoverable via the MCP server; same auth/context plumbing as `ccdash_aar_review` | 0.75 pts | python-backend-engineer | sonnet | adaptive | T5-001 |
| T5-003 | CLI command | New `backend/cli/commands/routing.py` with `routing_app = typer.Typer(...)` and `@routing_app.command("rollup")`, mirroring `report_app.command("aar-review")`'s shape. Register `app.add_typer(routing_app, name="routing", help="Routing feedback commands.")` in `backend/cli/main.py` alongside the existing `report_app` registration. Result: `ccdash routing rollup`. | `ccdash routing rollup --help` works; output matches the REST/MCP envelope shape | 0.75 pts | python-backend-engineer | sonnet | adaptive | T5-002 |
| T5-004 | Shared DTO + disabled-envelope test | Confirm all three transports serialize the SAME `RoutingRollupResponseDTO` (from Phase 3's `models.py`) with no per-transport reshaping. New `backend/tests/test_routing_rollup_transports.py`: assert REST/MCP/CLI return byte-identical disabled envelopes when `CCDASH_ROUTING_FEEDBACK_ENABLED=false` (`enabled: false`, empty `keys[]`, zero counts, REST returns HTTP 200 not 404 — AC-4). | All three transports produce identical JSON for the disabled case | 0.5 pts | python-backend-engineer | sonnet | adaptive | T5-003 |
| **Total** | — | — | — | **3 pts** | — | — | — | — |

**Model Selection Guidance**: All four tasks are Claude-only (no external model, no UI surface). Refer
to `.claude/config/multi-model.toml` for valid `Model`/`Effort` values.

**Effort Policy**: `adaptive` is correct for all four tasks — this is mechanical cloning of an
already-shipped 3-transport pattern with a bounded, well-understood contract (Phase 3's DTO). No task
in this phase warrants `extended`.

---

## Detailed Task Specifications

### Task T5-001: REST endpoint

**Estimate**: 1 point
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: Phase 3 complete (`RoutingRollupQueryService` exists)
**started**: 2026-07-31
**completed**: 2026-07-31
**verified_by**: [T5-004, T6-006]
**evidence**: ["commit:5725b75"]

**Description**:
Create `backend/routers/_client_v1_routing_rollup.py`, a byte-for-byte structural clone of
`backend/routers/_client_v1_aar_review.py`. The module exposes a single public handler,
`get_routing_rollup_v1(project_id, request_context, core_ports, bypass_cache) ->
ClientV1Envelope[RoutingRollupResponseDTO]`, which delegates entirely to Phase 3's
`RoutingRollupQueryService` — this module performs **zero** derivation of its own, mirroring the
`_client_v1_aar_review.py` module docstring's own claim ("performs zero derivation of its own"). Wire
the handler onto `client_v1_router` in `backend/routers/client_v1.py` as `GET /api/v1/routing/rollup`,
following the exact `project_aar_review` route pattern (~line 203–218: `Query(default=None, ...)` for
`project_id` and `bypass_cache`, `Depends(get_request_context)`, `Depends(get_core_ports)`).

**Acceptance Criteria**:
- [x] `backend/routers/_client_v1_routing_rollup.py` exists with a `get_routing_rollup_v1(project_id, request_context, core_ports, *, bypass_cache=False)` function returning `ClientV1Envelope[RoutingRollupResponseDTO]`
- [x] `GET /api/v1/routing/rollup` is registered on `client_v1_router` in `backend/routers/client_v1.py`, mirroring the `project_aar_review` route's decorator/param shape exactly
- [x] `project_id` is handled per the existing v1 convention: optional query param, falling back to context-resolved project scope (via `resolve_project_scope`) when omitted
- [x] Route returns the full envelope (real rollup data) when `CCDASH_ROUTING_FEEDBACK_ENABLED=true` and persisted rows exist — verified via manual pytest-harness round trip (seeded rows → correct `mapped_count`/`unclassified_count`/`distinct_unmapped_skill_names`/`keys[]`)
- [x] Zero live aggregation on the request path — the handler only deserializes/relays rows already computed by Phase 4's worker sweep via Phase 3's query service; no ad-hoc SQL or in-request GROUP BY
- [x] The capability string `"routing:feedback"` is present in `_V1_CAPABILITIES` (`backend/routers/client_v1.py` ~line 147–155) — Phase 1 already added it; this task does **not** re-add or duplicate the entry (verified, not touched)

**Implementation Notes**:
- **ICA-offload eligible** (`claude-sonnet-5[1m]`) — this is a mechanical clone of an already-shipped 3-transport pattern; fall back to the primary sonnet if ICA is unavailable. Phase 6 gates must re-run regardless of which execution provider produced the code.
- Clone `_client_v1_aar_review.py`'s exact structure: (1) a private cache-param extractor function (mirrors `_aar_review_list_params`), (2) a `@memoized_query("routing_rollup", param_extractor=...)`-decorated private fetch coroutine (mirrors `_fetch_aar_review_list`) that calls into Phase 3's `RoutingRollupQueryService`, and (3) the thin public handler `get_routing_rollup_v1` that wraps the fetch result in `ClientV1Envelope(data=result, meta=build_client_v1_meta(instance_id=_get_instance_id()))`.
- Cache freshness follows the same discipline as `aar_reviews`: `memoized_query`'s data-version fingerprint does not track the new `routing_rollup` table, so Phase 4's sweep job is responsible for calling `aclear_project_cache` on write (already scoped to Phase 4 — T5-001 only needs to consume the same `memoized_query` decorator, not implement invalidation itself).
- Resilience pattern: on a repository read failure, degrade to an empty/disabled-shaped `RoutingRollupResponseDTO`, never an HTTP error — mirrors `_fetch_aar_review_list`'s `try/except` → normalized-empty-payload behavior.
- Import `RequestContext` from `backend.application.context`, `CorePorts` from `backend.application.ports`, `resolve_project_scope` from `backend.application.services.agent_queries._filters` — identical import paths to `_client_v1_aar_review.py`.
- In `client_v1.py`: add `from backend.routers._client_v1_routing_rollup import get_routing_rollup_v1` alongside the existing `from backend.routers._client_v1_aar_review import get_aar_review_v1` (~line 59), and add the route function alongside `project_aar_review` (~line 203–218), following the same `Query`/`Depends` parameter shape.

**Files Involved**:
- `backend/routers/_client_v1_routing_rollup.py` - new module; clone of `_client_v1_aar_review.py`
- `backend/routers/client_v1.py` - add import (~line 59 pattern) + `GET /api/v1/routing/rollup` route decorator (~line 203–218 pattern)

---

### Task T5-002: MCP tool

**Estimate**: 0.75 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T5-001
**started**: 2026-07-31
**completed**: 2026-07-31
**verified_by**: [T5-004, T6-006]
**evidence**: ["commit:e63f3c0"]

**Description**:
Create `backend/mcp/tools/routing.py` with a `register_routing_tools(mcp)` function that registers a
single `@mcp.tool(name="ccdash_routing_rollup")` async tool, mirroring `backend/mcp/tools/reports.py`'s
`ccdash_aar_review` tool exactly: a module-level service singleton, an inline `_query(context, ports)`
closure delegating to Phase 3's `RoutingRollupQueryService`, `execute_query(...)` from
`backend.mcp.bootstrap`, and `build_envelope(result)` from `backend.mcp.tools` for response shaping.
Wire `register_routing_tools` into `backend/mcp/tools/__init__.py::register_tools` alongside the
existing `register_report_tools(mcp)` call.

**Acceptance Criteria**:
- [x] `backend/mcp/tools/routing.py` defines `register_routing_tools(mcp) -> None` and, inside it, `@mcp.tool(name="ccdash_routing_rollup")` decorating an async tool function
- [x] The tool's invocation pattern mirrors `ccdash_aar_review` exactly: an inline `async def _query(context, ports)` closure calling into the read path, wrapped by `execute_query(_query, tool_name="ccdash_routing_rollup", project_id=project_id)`, with `build_envelope(result)` as the return value — see Findings below re: the closure calls `_fetch_routing_rollup`, not `RoutingRollupQueryService`, mirroring T5-001's identical divergence
- [x] `register_routing_tools(mcp)` is called from `backend/mcp/tools/__init__.py::register_tools`, added alongside the existing `register_report_tools(mcp)` call
- [x] Tool is discoverable via the MCP server (`backend/tests/test_mcp_server.py::test_list_tools_exposes_expected_mcp_surface` updated to include `ccdash_routing_rollup` in the expected set; verified green — no live-stdio call test added here, that is T5-004's dedicated cross-transport file)
- [x] Same auth/context plumbing as `ccdash_aar_review` — no bespoke auth path, no direct DB access bypassing `execute_query`'s context/ports injection

**Implementation Notes**:
- **ICA-offload eligible** (`claude-sonnet-5[1m]`) — mechanical clone; fall back to primary sonnet if ICA is unavailable. Phase 6 gates must re-run regardless of execution provider.
- Module-level singleton pattern: `_routing_rollup_service = RoutingRollupQueryService()` (mirrors `_aar_review_service = AARReviewQueryService()` in `reports.py` line 10). Import `RoutingRollupQueryService` from wherever Phase 3 exports it (check `backend/application/services/agent_queries/__init__.py` for the export list — `AARReviewQueryService` is exported there; add the routing analog the same way if Phase 3 has not already done so).
- Tool signature should accept the same optional `project_id: str | None = None` parameter `ccdash_aar_review` accepts, plus whatever key parameters Phase 3's service requires (confirm against the frozen `RoutingRollupQueryService` signature — do not invent parameters not backed by the service).
- `build_envelope(result)` (from `backend/mcp/tools/__init__.py`) calls `result.model_dump(mode="json")` and separates `META_FIELDS` (`status`, `generated_at`, `data_freshness`, `source_refs`) from `data`. If `RoutingRollupResponseDTO` does not define one or more of these meta fields, `build_envelope` degrades gracefully (the field is simply omitted/`None` in `meta`) — this is not a blocking issue, but note it as a Findings-worthy observation if it surfaces, rather than adding bespoke fields to the DTO from this task.
- Wire-in location: add `from backend.mcp.tools.routing import register_routing_tools` to the local-import block inside `register_tools` (~line 53–61) and `register_routing_tools(mcp)` to the call sequence (~line 63–71), directly after `register_report_tools(mcp)`.

**Files Involved**:
- `backend/mcp/tools/routing.py` - new module; clone of `reports.py`'s `ccdash_aar_review` tool
- `backend/mcp/tools/__init__.py` - add import + `register_routing_tools(mcp)` call inside `register_tools`

---

### Task T5-003: CLI command

**Estimate**: 0.75 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T5-002
**started**: 2026-07-31
**completed**: 2026-07-31
**verified_by**: [T5-004, T6-006]
**evidence**: ["commit:c995b3f"]

**Description**:
Create `backend/cli/commands/routing.py` with `routing_app = typer.Typer(help="Routing feedback
commands.")` and a `@routing_app.command("rollup")` function, mirroring
`backend/cli/commands/report.py`'s `report_app.command("aar-review")` shape exactly: a service
singleton, an inline `_query()` → `runtime.execute_query(_invoke)` async pattern, error handling on
`result.status == "error"`, `resolve_output_mode` for `--output`/`--json`/`--md` flags, and
`get_formatter(mode).render(result, title=...)` for final output. Register
`app.add_typer(routing_app, name="routing", help="Routing feedback commands.")` in
`backend/cli/main.py` alongside the existing `report_app` registration. Result: `ccdash routing
rollup`.

**Acceptance Criteria**:
- [x] `backend/cli/commands/routing.py` defines `routing_app = typer.Typer(help="Routing feedback commands.")` and a `@routing_app.command("rollup")`-decorated function
- [x] The command function mirrors `aar_review`'s shape as closely as the DTO contract allows: `runtime.execute_query(_invoke)` closure calling the shared `_fetch_routing_rollup` fetch coroutine, `resolve_output_mode(output=output, json_output=json_output, markdown_output=markdown_output, default=runtime.OUTPUT_MODE)`, and `typer.echo(get_formatter(mode).render(result, title=...))` — see Findings below re: no literal `result.status == "error"` branch (the DTO has no `status` field to branch on)
- [x] `app.add_typer(routing_app, name="routing", help="Routing feedback commands.")` is registered in `backend/cli/main.py`, alongside `app.add_typer(report_app, name="report", ...)`
- [x] `ccdash routing rollup --help` runs without error and shows the auto-generated Typer help text (verified via both `backend/.venv/bin/ccdash routing rollup --help` and `python -m backend.cli routing rollup --help`)
- [x] `ccdash routing rollup` output matches the REST/MCP envelope shape (same `RoutingRollupResponseDTO` field set, rendered through the existing formatter registry — no bespoke CLI-only field renaming) — guaranteed by construction since all three transports call the identical `_fetch_routing_rollup` coroutine
- [x] Command supports the standard `--output`/`--json`/`--md` flags per existing CLI convention

**Implementation Notes**:
- **ICA-offload eligible** (`claude-sonnet-5[1m]`) — mechanical clone; fall back to primary sonnet if ICA is unavailable. Phase 6 gates must re-run regardless of execution provider.
- Module-level singleton: `_routing_rollup_service = RoutingRollupQueryService()` (mirrors `_aar_review_service = AARReviewQueryService()` in `report.py` line 13).
- Unlike `aar-review` (which requires a `--document`/`-d` option), the `rollup` command likely takes **no required option** beyond the global `--project` override already threaded through `runtime.execute_query`/`runtime.PROJECT_OVERRIDE` — confirm the exact parameter surface against Phase 3's frozen `RoutingRollupQueryService` signature before adding any command-specific flags; do not invent a required flag not backed by the service.
- Wire-in location: add `from backend.cli.commands.routing import routing_app` to the import block in `backend/cli/main.py` (~line 11, alongside `from backend.cli.commands.report import report_app`), and `app.add_typer(routing_app, name="routing", help="Routing feedback commands.")` to the registration block (~line 71, directly after the `report_app` line).
- Both the repo-local venv CLI (`backend/.venv/bin/ccdash routing rollup`) and `python -m backend.cli routing rollup` must work — this task does not touch the standalone `ccdash-cli` (pipx) package, which is HTTP-only and out of scope here.

**Files Involved**:
- `backend/cli/commands/routing.py` - new module; clone of `report.py`'s `aar_review` command
- `backend/cli/main.py` - add import + `app.add_typer(routing_app, ...)` registration

---

### Task T5-004: Shared DTO + disabled-envelope test

**Estimate**: 0.5 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T5-003
**started**: 2026-07-31
**completed**: 2026-07-31
**verified_by**: [T6-006]
**evidence**: ["commit:ca79e34"]

**Description**:
Confirm all three transports built in T5-001–T5-003 serialize the exact same
`RoutingRollupResponseDTO` (from Phase 3's `backend/application/services/agent_queries/models.py`)
with zero per-transport reshaping — no transport defines a subset, a renamed field, or a bespoke
wrapper around the DTO. Author `backend/tests/test_routing_rollup_transports.py`, asserting that
REST, MCP, and CLI return byte-identical disabled envelopes when
`CCDASH_ROUTING_FEEDBACK_ENABLED=false`: `enabled: false`, an empty `keys[]` list, zero counts across
all count fields, and — critically for REST — an HTTP 200 response (not a 404), per AC-4. This task is
this phase's primary contribution to AC-4 (finalized in Phase 6).

**Acceptance Criteria**:
- [x] All three transport modules (`_client_v1_routing_rollup.py`, `mcp/tools/routing.py`, `cli/commands/routing.py`) construct/return the same `RoutingRollupResponseDTO` type with no per-transport field renaming, subsetting, or bespoke wrapper types — confirmed by inspection (all three call the shared `_fetch_routing_rollup` coroutine) and by the test's cross-transport byte-identical assertion below
- [x] `backend/tests/test_routing_rollup_transports.py` exists and, with `CCDASH_ROUTING_FEEDBACK_ENABLED` set to `false`, asserts: `enabled: false`, `keys == []`, all numeric count fields `== 0`, identically across REST/MCP/CLI
- [x] REST's disabled-state response is HTTP 200, not 404 (AC-4 requirement — a disabled feature is a normal contract state, not a missing-route error)
- [x] The three transport assertions live in one file so future drift across any transport is caught at test-collection time
- [x] Test passes under `backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_transports.py -v` (4/4 green)

**Implementation Notes**:
- This task is primarily a verification/consistency gate, not new production code — if T5-001/T5-002/T5-003 faithfully cloned the AAR-review pattern, this test should pass with zero changes required to those three modules. Any required change surfaced here is itself a signal that a prior task under-cloned the pattern.
- Cite Phase 3's disabled-envelope construction (its `CCDASH_ROUTING_FEEDBACK_ENABLED=false` branch, per the parent plan's OQ-3/OQ-4 resolution notes) rather than re-deriving the field defaults in this test — the shape is Phase 3's contract, this task only proves transport parity against it.
- For the REST leg: use FastAPI's `TestClient` against `client_v1_router` (check existing REST test patterns under `backend/tests/test_client_v1_*.py` for the established fixture/harness before inventing a new one).
- For the MCP leg: invoke `register_routing_tools`'s tool function directly, or follow the existing `backend/tests/test_mcp_server.py` pattern — do not spin up a live stdio MCP transport for a unit-level parity check.
- For the CLI leg: use `typer.testing.CliRunner` against `routing_app` (check `backend/tests/test_cli_*.py` for the established CLI test harness first).
- Env var toggling (`CCDASH_ROUTING_FEEDBACK_ENABLED=false`) should use `monkeypatch.setenv` (or the repo's existing config-reload test fixture, if one exists for `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED`-style flags) — confirm `backend/config.py` reads the flag fresh per-request rather than caching it at import time before relying on `monkeypatch.setenv` alone.

**Files Involved**:
- `backend/tests/test_routing_rollup_transports.py` - new test file
- `backend/routers/_client_v1_routing_rollup.py` - read-only reference (assert-against, not modified)
- `backend/mcp/tools/routing.py` - read-only reference (assert-against, not modified)
- `backend/cli/commands/routing.py` - read-only reference (assert-against, not modified)

---

## Quality Gates

This phase is complete when:

- [x] **Functional**: `GET /api/v1/routing/rollup` returns the live rollup when `CCDASH_ROUTING_FEEDBACK_ENABLED=true` and persisted rows exist — verified by the committed `backend/tests/test_client_v1_routing_rollup.py::TestClientV1RoutingRollupEnabledSeeded` (enabled-empty and enabled-seeded, replacing T5-001's previously-uncommitted manual round trip). `ccdash_routing_rollup` (MCP) and `ccdash routing rollup` (CLI) are **not independently automated-tested at the enabled-seeded state** — flagging as a residual gap, not a blocker: both call the identical `_fetch_routing_rollup` coroutine REST's now-tested path exercises (T5-002/T5-003 Findings — no per-transport reshaping exists), and both were manually verified during T5-002/T5-003 (uncommitted). A follow-up could extend the enabled-seeded coverage to MCP/CLI directly; not required to close this review's fix #2, which scoped to `_client_v1_routing_rollup.py`'s reassembly functions specifically.
- [x] **Testing**: `backend/tests/test_routing_rollup_transports.py` passes (disabled-envelope parity, AC-4 partial); `backend/tests/test_client_v1_routing_rollup.py` passes (21/21 — enabled-path `_build_response_from_rows`/`_row_to_key_dto` unit coverage + enabled-seeded REST round trip), closing the review gap that flagged zero automated coverage for the enabled/seeded reassembly path.
- [x] **Performance**: N/A — read-only relay of already-computed rows; no aggregation on the request path to benchmark.
- [x] **Security**: N/A beyond existing `require_v1_auth` gating already applied to `client_v1_router` — no new auth surface introduced.
- [x] **Documentation**: N/A for this phase — consumer-contract doc and operator guide are Phase 6 deliverables (DOC-006, guide task).
- [x] **Code Quality**: `python -m py_compile` clean across all 7 `files_affected`; full pytest collection (42/42 across `test_routing_rollup_transports.py` + `test_client_v1_routing_rollup.py` + `test_routing_rollup_repo.py`) imports every touched module with zero errors; new modules follow the exact import/structure conventions of their clone anchors (per this phase's own Findings). No `ruff`/`mypy` binary is installed in `backend/.venv` to run a static linter/type-checker directly — clean compilation + clean test collection is the available substitute evidence in this environment.
- [x] **Architecture**: Router → Repository pattern honored (the phase's own Findings document the necessary, deliberate divergence from a literal "delegates to `RoutingRollupQueryService`" reading — that service has no read-back method; all three transports instead share one fetch coroutine, `_fetch_routing_rollup`, which reads `Sqlite/PostgresRoutingRollupRepository.get_by_project` directly). Verified: zero raw SQL/`GROUP BY` in any of the three transport modules (`grep` confirms the only `GROUP BY` string in `_client_v1_routing_rollup.py` is a negative claim in its own docstring); the `"routing:feedback"` capability string appears exactly once in `client_v1.py` (not duplicated).
- [x] **Seam verification**: N/A — `integration_owner`/`seam_tasks` are `null` for this phase; Phase 6 owns cross-phase seam verification (no-LLM guard, mapping-digest parity, disabled-state parity).
- [x] **Runtime smoke**: N/A — `ui_touched: false`, no `.tsx` files in `files_affected` (R-P4 not triggered).
- [x] **D9 decision gate**: the socialization attempt of the D5 metric-payload shape to the router owner (MeatySkills/`ibm-main`) is documented in this phase's completion note (**Notes → Learnings**) — a real, informal, cross-repo GitHub issue (<https://github.com/miethe/MeatySkills/issues/1>, opened 2026-07-31), response pending. Pending-but-attempted is the acceptable completion state this gate requires.

---

## Integration Points

### External Systems

- **MeatySkills / `ibm-main` delegation router**: the eventual PULL consumer of `GET
  /api/v1/routing/rollup` (and the MCP/CLI equivalents). This phase does not integrate with the
  router directly — no router-side code is touched from this repository (D1, D8) — but the D9
  decision gate requires documenting an attempt to socialize the D5 metric-payload shape with the
  router owner before this phase is marked complete.

### Internal Systems

- **Phase 3 (`RoutingRollupQueryService`)**: the sole data source for all three transports in this
  phase. Phase 5 tasks must treat Phase 3's service signature and `RoutingRollupResponseDTO` shape as
  frozen inputs — do not add fields, rename fields, or bypass the service with direct repository
  access from any transport module.
- **Phase 4 (`RoutingRollupSweepJob` / worker)**: the writer whose persisted `routing_rollup` rows this
  phase's REST/MCP/CLI surfaces read. Phase 5 does not depend on Phase 4's completion to build (both
  depend only on Phase 3), but end-to-end manual verification (real data flowing through all three
  doors) requires Phase 4's sweep job to have run at least once.
- **Phase 1 (`_V1_CAPABILITIES` / `"routing:feedback"`)**: the capability string this phase's REST
  route advertises was already added in Phase 1 — T5-001 verifies presence, does not duplicate it.

---

## Key Files Modified

| File Path | Lines | Purpose | Subagent |
|-----------|-------|---------|----------|
| `backend/routers/_client_v1_routing_rollup.py` | new file | REST handler clone of `_client_v1_aar_review.py` | python-backend-engineer |
| `backend/routers/client_v1.py` | ~59, ~203–218 | import + `GET /api/v1/routing/rollup` route decorator | python-backend-engineer |
| `backend/mcp/tools/routing.py` | new file | MCP tool clone of `reports.py`'s `ccdash_aar_review` | python-backend-engineer |
| `backend/mcp/tools/__init__.py` | ~53–61, ~63–71 | import + `register_routing_tools(mcp)` call | python-backend-engineer |
| `backend/cli/commands/routing.py` | new file | CLI command clone of `report.py`'s `aar_review` | python-backend-engineer |
| `backend/cli/main.py` | ~11, ~71 | import + `app.add_typer(routing_app, ...)` registration | python-backend-engineer |
| `backend/tests/test_routing_rollup_transports.py` | new file | REST/MCP/CLI disabled-envelope parity test | python-backend-engineer |
| `backend/tests/test_client_v1_routing_rollup.py` | new file | Enabled+seeded-rows reassembly test (`_build_response_from_rows`/`_row_to_key_dto` unit coverage + enabled-seeded REST round trip) — review fix, commit `a81ace6` | python-backend-engineer |

---

## Testing Strategy

### Unit Tests

- Transport-level construction tests: each of the three modules returns/serializes the same
  `RoutingRollupResponseDTO` type with no reshaping.

### Integration Tests

- REST: `TestClient` request against `GET /api/v1/routing/rollup` (enabled + disabled states).
- MCP: direct tool-function invocation (or `test_mcp_server.py`-style tool-listing check) for
  `ccdash_routing_rollup`.
- CLI: `typer.testing.CliRunner` invocation of `ccdash routing rollup` (enabled + disabled states,
  plus `--help`).
- Cross-transport parity: `backend/tests/test_routing_rollup_transports.py` asserts byte-identical
  disabled envelopes across all three (T5-004; AC-4 partial).

### E2E Tests (if applicable)

- N/A — no frontend surface in this feature; no user journey to cover.

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| A transport reshapes `RoutingRollupResponseDTO` into its own subset/renamed fields, silently drifting from the other two | Medium | T5-004's shared-DTO assertion + cross-transport parity test catches this at test-collection time, not in production |
| `"routing:feedback"` capability string is accidentally duplicated in `_V1_CAPABILITIES` (Phase 1 already added it) | Low | T5-001's acceptance criteria explicitly calls out "verify presence, do not re-add"; code review checks for a single entry |
| CLI/MCP command invents a required parameter not backed by Phase 3's service signature | Low | Implementation Notes on T5-002/T5-003 explicitly instruct confirming the frozen service signature before adding flags/parameters |
| D9 socialization is skipped entirely, risking an unconsumable rollup shape discovered only after ship | Medium | D9 decision-gate Quality Gate item requires documenting the socialization attempt in this phase's completion note before `status: completed` |

---

## Success Metrics

- **Disabled-state consistency**: 100% — REST/MCP/CLI return byte-identical disabled envelopes (T5-004; contributes to the parent plan's frontmatter `success_metrics`)
- **Coverage visibility**: every enabled-state response reports the same coverage fields (mapped/unclassified counts) regardless of transport
- **Zero live aggregation**: 100% of the three transport request paths delegate to Phase 3's persisted-row query service with no in-request SQL aggregation

---

## Notes

### Implementation Approach

T5-001, T5-002, and T5-003 are marked **ICA-offload eligible (`claude-sonnet-5[1m]`)** — each is a
mechanical clone of an already-shipped 3-transport pattern (REST/MCP/CLI for `aar_reviews`), making
them well-suited to offload. Fall back to the primary sonnet subagent if ICA is unavailable for any
task. Regardless of which execution provider (ICA offload vs. primary sonnet) produces the code,
**Phase 6's guard/parity/determinism/disabled-state test battery must re-run in full** — execution
provider is not a substitute for the gate.

### Gotchas

- **Do not re-add the capability string**: `"routing:feedback"` is already present in
  `_V1_CAPABILITIES` from Phase 1 — T5-001 only verifies it, never duplicates the list entry.
- **Do not invent parameters**: neither the MCP tool nor the CLI command should add a required
  parameter/flag beyond what Phase 3's `RoutingRollupQueryService` signature actually supports — check
  the frozen signature first.
- **DTO is the single source of truth**: `RoutingRollupResponseDTO` (Phase 3's `models.py`) is the only
  shape any transport may return — no transport-specific wrapper types, no field renaming.
- **`build_envelope`'s META_FIELDS assumption**: the MCP `build_envelope` helper expects `status`,
  `generated_at`, `data_freshness`, `source_refs` on the result object; if `RoutingRollupResponseDTO`
  lacks one or more of these, the meta block degrades gracefully (field omitted/`None`) rather than
  erroring — note as a Finding if observed, do not patch the DTO from this phase.

### Learnings

**D9 socialization attempt (recorded 2026-07-31)**: D9 is a schedule-risk gate, not a blocking
dependency (per the decisions block's own D9 rationale) — this phase's completion does not wait on
a router-owner response. An informal, real, cross-repo attempt was made before this phase was
marked `completed`:

- **Channel**: GitHub issue (cross-repo, informal — the evidence tier this phase's own header note
  names as sufficient: "a Slack message, a cross-repo issue, or an email thread").
- **Target repo**: `github.com/miethe/MeatySkills` (hosts the `delegation-router` skill and the
  `aos.routing.feedback` v1.0.0 contract that the router consumes, branch `ibm-main`).
- **URL**: <https://github.com/miethe/MeatySkills/issues/1>
- **Date**: 2026-07-31
- **Content**: The full D5 metric-payload shape (`model`/`provider`/`sample_count`/`success_rate`/
  `cost_index`/`regression_rate`/`confidence`/`eligible_for_adjustment`/`window_start`/`window_end`/
  `freshness_ts`, verbatim from `RoutingRollupKeyDTO`) plus three concrete questions ahead of DI-1's
  router-side merge-math work: whether `success_rate`/`regression_rate` always being `None` in v1
  blocks the router's bounded-adjustment-cap/effective-score-floor guardrails or degrades gracefully;
  whether `cost_index` needs router-side normalization; and whether `eligible_for_adjustment` is
  sufficient as the min-sample-gate signal versus the router using raw `sample_count` + its own
  threshold.
- **Response**: pending as of this phase's completion — no reply received yet. This is the recorded
  attempt, not a resolution; a pending-but-attempted socialization is the acceptable completion
  state this phase's Quality Gates require.
- Full record (including the risk-hotspot cross-reference) also lives in
  `.claude/worknotes/proof-to-routing-loop/decisions-block.md` § "D9 Socialization Attempt" and the
  D9 row of that file's decisions table (`status: attempted (informal)`).

### Findings Captured This Phase

*If any discoveries, plan/reality mismatches, bugs, or schema gaps were found during this phase,
append them here AND to the plan's findings doc (`findings_doc_ref`). Create the findings doc lazily
on first finding — do not pre-create.*

- [x] **T5-001 finding**: the task description's claim that the REST handler "delegates entirely to
  Phase 3's `RoutingRollupQueryService`" is imprecise, and the *actual* clone anchor
  (`_client_v1_aar_review.py`) does not do this either — it reads
  `Sqlite/PostgresAarReviewsRepository` directly and deserialises rows itself
  (`_row_to_aar_review_dto`), never calling into `AARReviewQueryService`. `_client_v1_routing_rollup.py`
  faithfully mirrors that *actual* pattern: it reads `Sqlite/PostgresRoutingRollupRepository.
  get_by_project` directly and deserialises each row into `RoutingRollupKeyDTO` itself
  (`_row_to_key_dto`). This is a deliberate, necessary divergence from a byte-literal reading of the
  task description, not from the clone anchor's real behavior — `RoutingRollupQueryService` has no
  "read the persisted table back" method (only the live-aggregation pipeline used by Phase 4's
  worker), and the files_affected list for this task does not include `routing_rollup.py`, so adding
  one was out of scope here.
- [x] **T5-001 finding**: the three FR-7 coverage counters (`mapped_count`/`unclassified_count`/
  `distinct_unmapped_skill_names`) are NOT persisted per-row in `routing_rollup` (they are
  response-level totals, summed across the whole project) — see `routing_rollup.py`'s DDL /
  `ROUTING_ROLLUP_COLUMNS`. `_client_v1_routing_rollup.py::_build_response_from_rows` therefore
  re-sums each already-fetched row's `task_class`/`sample_count` in-memory to reproduce these three
  counters, mirroring `RoutingRollupQueryService.compute_coverage_counters`'s exact policy but over
  persisted rows rather than a live aggregate. This is response reassembly, not new SQL aggregation
  (no `GROUP BY` added against `sessions`) — flagging for T5-002/T5-003 so the MCP/CLI transports
  replicate the identical summation, and for T5-004 to assert the three counters, not just `keys[]`.
- [x] **Environment gotcha for T5-002/T5-003/T5-004**: this repo's root `.env` pins
  `CCDASH_DB_BACKEND=postgres` / `CCDASH_DATABASE_URL` at the node (`backend/env_bootstrap.py`
  auto-loads it, `override=False`, **only when `pytest` is not already in `sys.modules`**). A
  throwaway verification script run as `python script.py` (not via `pytest`) will import
  `backend.config` before any test-local `patch.dict(os.environ, ...)` takes effect, silently
  connecting to the real remote Postgres node instead of an isolated SQLite temp file — the app
  still returns plausible-looking 200s (a nonexistent test project id legitimately has zero rows on
  the real DB too), which can mask the misrouting. Always verify new transport code via
  `backend/.venv/bin/python -m pytest <file_or_module>`, never a bare `python <script>.py`, and
  prefer the `test_client_v1_aar_review.py`-style class-based `TestCase` harness (imports at file
  top are safe under pytest specifically because `dotenv_autoload_enabled()` short-circuits on
  `"pytest" in sys.modules`).
- [x] **T5-002 finding**: same divergence as T5-001's first finding, one layer up — `RoutingRollupQueryService`
  has no "read the persisted table back" method, so the MCP tool's inline `_query(context, ports)` closure
  cannot literally "delegate to Phase 3's `RoutingRollupQueryService`" as the task description's prose states.
  `backend/mcp/tools/routing.py::ccdash_routing_rollup` instead imports and calls
  `backend.routers._client_v1_routing_rollup._fetch_routing_rollup` directly — the same coroutine T5-001's REST
  handler calls — rather than re-implementing the `Sqlite/PostgresRoutingRollupRepository.get_by_project` read
  + in-memory FR-7 counter reassembly a second time. This is a deliberate DRY choice: sharing one fetch
  implementation across REST and MCP is what *guarantees* T5-004's byte-identical-disabled-envelope assertion
  holds by construction, rather than by two independently-written implementations happening to agree. No
  other MCP tool module in this repo currently imports a router-private (`_client_v1_*`) helper — flagging as
  a precedent-setting pattern for Phase 6 review, not a defect.
- [x] **T5-003 finding**: same `RoutingRollupQueryService` "no read-back method" divergence as T5-001/T5-002,
  one layer up again — `backend/cli/commands/routing.py`'s `rollup` command's `_invoke(context, ports)` closure
  calls `backend.routers._client_v1_routing_rollup._fetch_routing_rollup` directly (the identical coroutine the
  REST handler and the MCP tool both call), rather than re-implementing the repository read + FR-7 counter
  reassembly a third time. All three transports now share one fetch implementation, which is what makes T5-004's
  byte-identical-disabled-envelope assertion hold by construction.
- [x] **T5-003 finding — cannot literally branch on `result.status == "error"`**: the AC/implementation-notes
  prose for this task (mirroring `aar_review`) calls for `result.status == "error"` handling with a
  `typer.Exit(code=2)` path. `RoutingRollupResponseDTO` (Phase 3's frozen `models.py` contract) defines no
  `status` field at all — unlike `AARReviewDTO`/`WorkflowDiagnosticsResult`, which do. Attempting
  `result.status` on this DTO raises `AttributeError` (plain `pydantic.BaseModel`, no `extra="allow"`), so a
  literal clone of `aar_review`'s error branch is not just unneeded here, it would crash on every invocation.
  This is a natural consequence of the same drift already flagged as a Finding in T5-002 (`build_envelope`
  status drift) — `_fetch_routing_rollup` never raises a transport-level error state by design (D6/FR-10
  resilience-by-default: disabled/no-project/read-failure all degrade to a normalized empty/disabled payload,
  never an error), so there is no error branch for this command to take. The `rollup` command therefore always
  renders the returned envelope, following the same no-error-branch shape as the REST handler
  (`get_routing_rollup_v1`) and the MCP tool (`ccdash_routing_rollup`), neither of which has an error branch
  either. Not touched: `RoutingRollupResponseDTO` is Phase 3's frozen contract and is not in this task's
  `files_affected`.
- [x] **T5-003 finding — no command-specific `--project` flag added**: per the task's own Implementation Notes
  ("confirm the exact parameter surface... before adding any command-specific flags"), the `rollup` command
  takes no `--project` option of its own. The global `--project` override (`backend/cli/main.py`'s
  `app.callback`) already threads through `runtime.execute_query`'s header-based project resolution
  (`x-ccdash-project-id`) exactly the way `workflow failures` (also no per-command project flag) relies on it —
  confirmed via manual invocation and the added `test_routing_rollup_renders_disabled_envelope` test.
- [x] **T5-002 finding — `build_envelope` status drift**: `backend/mcp/tools/__init__.py::build_envelope` returns
  `payload.get("status", "error")` as the envelope's top-level `status`. `AARReviewDTO` (used by
  `ccdash_aar_review`) defines `status: Literal["ok", "error"] = "ok"`, so that tool's envelope correctly
  reports `"ok"` on success. `RoutingRollupResponseDTO` (Phase 3's `models.py`) defines no `status` field at
  all, so `ccdash_routing_rollup`'s envelope reports `status: "error"` on *every* call, including a healthy
  disabled-by-default response with `enabled: false` and no read failure whatsoever — confirmed via a
  throwaway pytest sanity check against the registered tool function (not committed). This is a real
  transport-level drift from the `ccdash_aar_review` precedent, not touched from this task per the phase's own
  guidance ("note as a Finding if observed, do not patch the DTO from this phase") — `RoutingRollupResponseDTO`
  is Phase 3's frozen contract and is not in T5-002's `files_affected`. T5-004's disabled-envelope test and
  Phase 6's parity gates should assert on `data.enabled`/`data.keys`/the count fields, not on this tool's
  top-level `status` string, until a follow-up task (Phase 6 or later) either adds a `status` field to
  `RoutingRollupResponseDTO` or teaches `build_envelope` a per-DTO default.
- [x] **T5-004 finding — "byte-identical" is a DTO-level claim, not a raw-JSON-string claim**: the
  three transports intentionally wrap the shared DTO in different outer envelopes by design (REST:
  `{status, data, meta}` via `ClientV1Envelope`; MCP: `{status, data, meta}` via `build_envelope`,
  which moves `generated_at` out of `data` into `meta` per its `META_FIELDS` set (already flagged in
  T5-002's finding); CLI `--json`: the flat DTO, no wrapper). A literal full-response JSON-string diff
  across all three would therefore fail on structural grounds that have nothing to do with the DTO
  contract. `test_routing_rollup_transports.py` normalizes each transport back down to the DTO level
  (re-merging MCP's `meta.generated_at` into its `data` dict) before comparing — this is what makes
  the byte-identical assertion meaningful rather than vacuously true or spuriously false. The test
  deliberately does not assert on MCP's top-level envelope `status` field, per T5-002's finding that
  it always resolves to `"error"` for this DTO regardless of actual health.
- [x] **T5-004 finding — event-loop isolation is required to exercise all three transports for real
  in one process**: `aiosqlite.Connection` is bound to the event loop that created it, and
  `backend.db.connection.get_connection()` is a process-wide singleton shared by all three
  bootstraps (FastAPI lifespan, `backend.mcp.bootstrap.bootstrap_mcp`, `backend.cli.runtime
  .bootstrap_cli`). Running REST (via `TestClient` as a context manager), then MCP (via a single
  `asyncio.run()` that also calls `shutdown_mcp()` before returning), then CLI (via `CliRunner`,
  whose underlying `execute_query` already tears down its own container in a `finally`) **strictly
  in sequence, each fully entering and exiting before the next begins**, was sufficient to avoid any
  cross-loop reuse — no manual singleton surgery was needed beyond letting each transport's own
  existing teardown path run to completion. This is why the test does not use a single shared
  `setUpClass` fixture the way `test_client_v1_aar_review.py` does; each test method calls all three
  transports fresh via `setUp`/`tearDown`-scoped temp DB files instead.
- [x] **T5-004 finding — the disabled short-circuit never needs a resolvable project**: `_fetch_
  routing_rollup`'s `if not enabled: return _disabled_envelope()` check runs before any call to
  `resolve_project_scope`, so the test needed no seeded `projects` row and no stub
  `WorkspaceRegistry` at all — only an `AuthContext` override for the REST leg (to avoid a 401) and
  a migrated-but-empty SQLite file for all three (MCP/CLI's `build_request_context` still calls
  `resolve_scope`, which returns `(None, None)` cleanly when no project is registered, per
  `ProjectManagerWorkspaceRegistry.resolve_scope`).

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-29

[Return to Parent Plan](../proof-to-routing-loop-v1.md)
