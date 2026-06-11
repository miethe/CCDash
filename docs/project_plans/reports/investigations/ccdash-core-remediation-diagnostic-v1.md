---
schema_version: 2
doc_type: report
report_category: investigation
title: "CCDash Core Remediation Diagnostic"
status: accepted
source: agent
created: 2026-06-10
updated: 2026-06-10
feature_slug: ccdash-core-remediation
related_documents:
  - docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
  - docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
raw_evidence:
  - .claude/worknotes/ccdash-core-remediation/evidence/diagnostic-roadmap-raw.json
  - .claude/worknotes/ccdash-core-remediation/evidence/verification-verdicts-raw.json
---

# CCDash Core Remediation Diagnostic

> Condensed from two multi-agent diagnostic workflows (7-leg subsystem audit + 9-verifier
> claim verification). **Full raw output** is preserved verbatim at the `raw_evidence` paths
> in frontmatter — consult those for complete evidence dumps. This report is the load-bearing
> summary the PRD and implementation plan are built on.

## Executive Summary

The diagnostics do not describe seven independent bugs; they describe **one architecture
optimized for a single active project** being asked to serve all projects, all agents, and
external consumers. Four root-cause themes recur:

1. **Active-project-centric scoping** leaks into every read and the steady-state sync path.
2. The **transport-neutral intelligence layer is only wired to REST/CLI-v1, not to MCP or the
   repo-local CLI** — so an agent cannot fetch a session transcript via MCP today.
3. **Detection by hardcoded enumeration** instead of derivation/normalization (pricing maps,
   model lists), with launcher/profile and reasoning-effort simply **absent from the logs**.
4. **Freshness work is feature-flagged off or run redundantly at startup** (incremental link
   rebuild defaults off → linked sessions lag; boot stacks redundant full syncs).

The leverage: the same active-only theme causes both cross-project staleness and link lag, and
the same transport-neutral gap blocks both the top deliverable (agent session access) and the
IntentTree API. Fixing scoping + MCP/CLI session parity unblocks the most operator pain per unit
effort, and it ships on SQLite without waiting on the already-complete Postgres path.

## Root-Cause Themes

| # | Theme | Spans | Core evidence |
|---|-------|-------|---------------|
| 1 | Active-project-centric scoping | sync-engine, file-watcher, rest-api, agent-queries | `backend/routers/api.py` `list_sessions` resolves one project via `resolve_project`, no cross-project param; `backend/adapters/jobs/runtime.py` `_run_all_projects_sync_job` runs only at startup, `allow_writeback=False` for non-active |
| 2 | Transport-neutral layer not wired to MCP/repo-CLI | mcp, cli, agent-queries | Rich detail exists at REST + `/api/v1` (`get_session_detail_v1`, drilldown, family, search) but `backend/mcp/tools/` registers only 7 analytics tools (no session tools); `backend/cli/commands/` has no session group |
| 3 | Detection by enumeration, profile/effort data-absent | parser, pricing, model-identity | `parser.py` `_estimate_cost` (≈998-1015) + `provider_pricing.py` `_ANTHROPIC_MODEL_ID_BY_LABEL` (28-40) list Opus/Sonnet/Haiku only; launcher/effort not present in JSONL at all |
| 4 | Freshness flagged-off / redundant at boot | sync-engine, runtime-jobs, links | `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` default False (`config.py:131`); startup stacks `startup_sync` + `all-projects-sync` (`runtime.py:221,284`); `uvicorn --reload` re-triggers |

## Verified Findings (9 verifiers)

### F1 — `/api/v1` session detail carries NO transcript — **PARTIAL/confirmed**
`get_session_detail_v1` returns `SessionIntelligenceDetailResponse` (`backend/models.py:961-969`):
summary + sentiment/churn/scope-drift facts only — **no transcript/tools/tokens/subagents**.
Transcript is served only by app routers `GET /{session_id}/logs` and `GET /{session_id}`
(`backend/routers/api.py:890-935`) via `SessionTranscriptService.list_session_logs`
(`backend/application/services/sessions.py:92`). **Correction:** that transcript reader IS
transport-neutral and already reused by `agent_queries/feature_forensics.py:163-173` (internally,
to derive rework signals — never returned). → **W1 is exposure/wiring + redaction, NOT a new
retrieval engine.** Mirror the `{items, cursor, limit, nextCursor}` pagination (`api.py:903-916`).

### F2 — `get_by_id` is project-unsafe — **CONFIRMED**
`backend/db/repositories/sessions.py:206-213` `get_by_id` runs `SELECT * FROM sessions WHERE id = ?`
with no `project_id`, despite composite PK `(project_id, id)` (`sqlite_migrations.py:228`, v31).
Sibling `get_many_by_ids` (215-224) shares it. Postgres identical (`postgres/sessions.py:142-155`).
~11 callers pass no project_id (`api.py:899,930,1275,1377,1477`; `features.py:1772`;
`_client_v1_sessions.py:259`; etc.). Latent only because ids are effectively unique today; the
schema permits collisions. **Worst failure mode:** family resolution (F3). **Fix:** add `project_id`
param to all four methods (both backends) + NULL/'' tolerance mirroring `update_status`
(`sessions.py:192`); ADR-007 collision tests. **Prerequisite for any cross-project read.**

### F3 — `get_session_family_v1` is active-project-bound — **CONFIRMED**
`_client_v1_sessions.py:259` resolves anchor via unscoped `get_by_id`, but `:269` derives
`project_id` from `app_request.context.project` (active context, **not the anchor row**) and
passes it to `list_paginated` which applies `WHERE project_id = ?`. → a non-active-project session
returns **zero family members**. Adding a request param does not fix it. **Fix:** derive
`project_id` from `anchor.get('project_id')` (~1 line) after scoping `get_by_id`. **Also audit**
`session_intelligence_read_service.drilldown` — `get_session_drilldown_v1` is context-bound at this
layer; cross-project behavior **inconclusive** without inspecting that service.

### F4 — Novel-model pricing is silent Sonnet mis-pricing, not $0 — **PARTIAL/reframed**
Family derivation works generically (`model_identity.py:48-49` → `claude-fable-5` ⇒ family `Fable`).
But `_estimate_cost` (`parser.py:1009-1015`) initializes the fallback to `(3.0, 15.0)` = **Sonnet
rates**, so an unmatched model is **silently billed at Sonnet**, not zero. The data-driven
`pricing_catalog.py` returns **None** (no cost) via `missing_required_rates` (598-603). **Fix (3
edits):** (a) `_estimate_cost` must not Sonnet-default unknown → 0 + explicit `unpriced` flag or
consult catalog; (b) `pricing_catalog._pricing_family` (80-92) derive family generically / surface
explicit no-pricing; (c) add Fable to catalog/labels (`provider_pricing.py` is a scraper allowlist,
lower priority). Regression fixture: novel `claude-<family>` flagged unpriced, not Sonnet.

### F5 — Non-active watchers register AND survive active-switch — **CONFIRMED (good news)**
With `CCDASH_SYNC_ALL_PROJECTS=True` (default, `config.py:988`) the registry creates an independent
persistent `FileWatcher` per project (`file_watcher.py:377-419`), created once by the startup
`_run_all_projects_sync_job`. The active-switch rebind (`runtime.py:511-534`) only stops/restarts
the singleton + unregisters/registers old/new active ids — it **never touches other registry
entries**, so non-active watchers survive. **Residual risks:** single point of registration at boot
(no self-heal for a crashed watcher), `SYNC_ALL_PROJECTS=False` ⇒ never watched, dirs created
post-boot watched on stale/empty paths (`_resolve_watch_paths` drops non-existent paths at
registration), no periodic reconcile. → **W8 is hardening, MODERATED priority.**

### F6 — Token undercount is ALREADY FIXED — **REFUTED (as current state)**
Cache tokens ARE parsed (`parser.py:2791-2794, 3166-3171`), persisted as first-class columns
(`sqlite_migrations.py:169-183`: `model_io_tokens`, `cache_creation_input_tokens`,
`cache_read_input_tokens`, `cache_input_tokens`, `observed_tokens`, `tool_result_cache_*`), and
included in analytics (`analytics.py:216-244`: `observed_tokens = model_io_tokens + cache_input_tokens`,
`totalTokens = observedTokens`). The 376× undercount was the **2026-03-08** pre-remediation state;
PRD/plan `claude-code-session-usage-analytics-alignment-v1` shipped **completed 2026-03-09**. Only
residual: `analytics.py:553` sums in+out for a per-lifecycle-EVENT delta (not the workload total).
→ **EXCLUDED from scope**; tiny dashboard-usage check folded into Phase 12.

### F7 — Startup full-sync triggers — **PARTIAL**
Two boot triggers: active `startup_sync` (`runtime.py:221`) + all-projects sweep (`:284`, default-on).
The all-projects loop **explicitly skips the active id** (`:811-812`) → in default dev (SQLite,
`JOB_QUEUE_BACKEND=memory`) the active project is scanned **once**. Operator's "multiple Full Syncs"
= `uvicorn --reload` restarting boot + the always-on sweep. A **genuine active-project double-scan
exists ONLY when `JOB_QUEUE_BACKEND != memory`** (postgres/enterprise): a durable `sync` job
(`:206`) + the in-process `startup_sync` both run with **no coalescing** (`durable_queue.py:94-96`).
→ **W7 coalescing guard genuinely needed once Postgres is live.**

### F8 — Session JSONL signal ground-truth — **PARTIAL (inventory below)**
See the table in the next section. Key takeaways: model id is the **bare slug** (`claude-opus-4-8`,
never `[1m]`) in `message.model`; the `[1m]` 1M-context variant lives **only** in `workflows/*.json`
sidecars (`defaultModel` / `workflowProgress.N.model`); **ica-delegate profile/launcher and
reasoning-effort/Ultracode are ABSENT from all logs** (data-absence, not parser gap).

### F9 — ccdash skill vs MCP/CLI reality — **PARTIAL**
MCP registers exactly 7 tools, **zero session-specific** (no `backend/mcp/tools/sessions.py`).
Repo-local CLI has no session group. Standalone `ccdash_cli` `session show` hits `/api/v1/sessions/{id}`
which (per F1) lacks a transcript. **Correction:** `SKILL.md` does **not** over-promise — it fences
session drilldown/transcript to the standalone CLI (line 36) and tells agents not to route session
commands to MCP/repo-CLI (line 78). → No skill-doc contradiction; the gap is a **capability gap**:
no surface returns transcript content today.

## Ground-Truth: Session JSONL Signal Inventory

| Signal | Capturable from `.jsonl` message transcripts | Only in `workflows/*.json` sidecars | Absent entirely (cannot detect) |
|--------|----------------------------------------------|-------------------------------------|---------------------------------|
| Model id | ✅ `message.model` — **bare slug** (`claude-opus-4-8`/`4-7`/`sonnet`/`haiku`); never `[1m]` | `[1m]` 1M variant via `defaultModel` / `workflowProgress.N.model` | — |
| Tokens/usage | ✅ `message.usage.{input,output,cache_creation,cache_read}_input_tokens`, server_tool_use, service_tier, ephemeral split | aggregate `totalTokens`/`totalToolCalls`/`agentCount` | — |
| Subagent linkage | ✅ `agentId`, `attributionAgent`, `isSidechain`, `parentUuid`, `sessionKind='bg'` (note `parentToolUseID`/`taskSubagentType` often NULL) | — | — |
| Skill/command attribution | ✅ `attributionPlugin`, `attributionSkill` | — | — |
| Workflow linkage | ✅ `runId`, `taskId`, `pendingWorkflowCount` | `workflowName`, `phases`, `result.graph.waves` | — |
| Context | ✅ `cwd`, `gitBranch`, `entrypoint`, harness `version`, `userType`, `sessionKind` | — | — |
| **Launcher/profile (ica-delegate)** | — | — | ❌ no `provider`/`baseURL`/`apiKeySource`/`argv`/`env`/`ica-claude` anywhere |
| **Reasoning effort / Ultracode** | — | (workflow `effort` = task story-points, false friend) | ❌ only extended-thinking content block; no level/budget |

**Implication:** model/token/subagent/workflow/skill detection is achievable from logs; 1M-context
needs a `runId`/`taskId` → `workflow.json` join (Phase 5); **ica-delegate profile + Ultracode/effort
require a new launch-time capture mechanism** (Phase 11) — they are not in any log.

## Corrected Claims & Scope Deltas

- **W1** scope-down on transcript engine (reuse `SessionTranscriptService`), scope-up on cross-project
  correctness (F2/F3 are prerequisites folded into Phase 0).
- **W7 token accounting → CLOSED** (shipped 2026-03-09); excluded.
- **W4 (freshness) → MODERATED** (watchers already survive switches; becomes reconcile + self-heal).
- **W5 startup → SPLIT**: real double-scan only under non-memory queue → coalescing guard (Phase 7);
  dev-reload amplification is QoL.
- **Detection → SPLIT**: log-derivable now (Phase 5); profile/effort deferred to launch-time capture
  (Phase 11) — data-absent.
- **NEW**: pricing-correctness workstream (Phase 6) — silent Sonnet mis-pricing.

## Recommended Workstream Order

1. **Phase 0** — cross-project session correctness (F2/F3) — prerequisite, de-risks all cross-project reads.
2. **Phases 1–3** — transcript service + redaction → `/api/v1` endpoints → MCP/CLI session tools (top deliverable).
3. **Phase 4** — live link freshness (incremental scoped rebuild).
4. **Phase 7** (coalescing) — needed once Postgres is live.
5. **Phases 5/6** — detection (log-derivable) + pricing correctness.
6. **Phase 8** — freshness hardening (moderated).
7. **Phase 9** — Postgres parity + container/compose (Bash-enabled PG seam review).
8. **Phase 10** — external API (IntentTree).
9. **Phase 11** — launch-time profile/effort capture (fast-follow).
10. **Phase 12** — docs + CHANGELOG + karen.

## Open Decisions & Operator Resolutions

| Decision | Resolution (locked) |
|----------|---------------------|
| Transcript egress / access model | **Local-trust, all surfaces (REST + MCP + repo-CLI), with secret/PII redaction** on tool-call payloads |
| Profile / effort detection (data-absent) | **Ship log-derivable now; launch-time capture as explicit fast-follow** (Phase 11) |
| Postgres / enterprise timeline | **Move to Postgres/containers now** → coalescing guard, PG parity, container smoke are P0-infra |
| Appetite | **Full roadmap, one orchestrated effort** (Phases 0–12) |

## Top Risks

1. **Shared-file collisions** — Phases 5/7/8 all edit `runtime.py`/`sync_engine.py`/`config.py`; single-thread those edits.
2. **Postgres column drift** — Phases 5/6/11 add columns; ship dual SQLite+PG DDL + `COLUMN_PARITY_DRIFT_ALLOWLIST` update in the same change; Phase 9 Bash-enabled PG seam review (memory note: edit-less reviewer missed 3 PG-only bugs).
3. **Cross-project read leakage** — Phase 0 is a hard prerequisite; tests assert `project_id` never returns another project's rows.
4. **Transcript egress secrets/PII** — redaction is a Phase 1 deliverable, not a courtesy.
5. **Incremental-link-rebuild perf regression** — prove scoped path before default-on; assert no global fingerprint scan on hot path.
6. **Recent-first backfill silently partial** — assert backfilled count == baseline full scan.
7. **Runtime smoke gate** — UI-touching phases (3/5/6/11) require live smoke; not `completed` on unit tests alone.
