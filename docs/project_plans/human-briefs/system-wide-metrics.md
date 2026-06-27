---
schema_name: ccdash_document
schema_version: 2
doc_type: human_brief
title: "System-Wide Metrics - Human Brief"
status: draft
category: human-briefs

feature_slug: system-wide-metrics
feature_family: observability
feature_version: v1

prd_ref: docs/project_plans/PRDs/features/system-wide-metrics-v1.md
plan_ref: docs/project_plans/implementation_plans/features/system-wide-metrics-v1.md
intent_ref: null
epic_ref: null

related_documents:
  - .claude/worknotes/system-wide-live-metrics-spike/spike.md
  - .claude/worknotes/system-wide-metrics/decisions-block.md
  - docs/project_plans/feature_contracts/features/live-agents-count-v1.md
  - docs/project_plans/feature_contracts/features/watcher-rebind-on-active-project-switch-v1.md

owner: nick
contributors: []

audience: [humans]

priority: medium
confidence: medium-high

created: 2026-05-20
updated: 2026-05-20
target_release: null

tags: [human-brief, observability, system-metrics, cross-project]
---

# System-Wide Metrics — Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-05-20

---

## 1. Context Pointers

- **PRD**: `docs/project_plans/PRDs/features/system-wide-metrics-v1.md` — requirements, functional spec, AC-1 through AC-6, §12 open questions, §13 estimation sanity check
- **Plan**: `docs/project_plans/implementation_plans/features/system-wide-metrics-v1.md` — phase task breakdown, batch definitions, model routing (created by implementation-planner after this brief)
- **Decisions Block**: `.claude/worknotes/system-wide-metrics/decisions-block.md` — Opus orchestration judgment: phase boundaries, risk hotspots, parallelism opportunities, model routing, OQ-EXP-1 through OQ-EXP-5
- **SPIKE**: `.claude/worknotes/system-wide-live-metrics-spike/spike.md` — primary research; OQ-3 runtime verification at §OQ-3 is the evidentiary backbone for the watcher-rebind HARD precondition
- **Tier 1 Precondition (soft)**: `docs/project_plans/feature_contracts/features/live-agents-count-v1.md` — provides `SessionsRepository.count_active()` and `idx_sessions_project_status_updated`
- **Tier 1 Precondition (HARD release gate)**: `docs/project_plans/feature_contracts/features/watcher-rebind-on-active-project-switch-v1.md` — without this, non-active project counts are arbitrarily stale

---

## 2. Estimation Sanity Check

_Migrated verbatim from PRD §13. This is the canonical location going forward._

**Bottom-up total**: 9.0 pts (PRD H1–H6 derivation) → locked at **10 pts** (Decisions Block adds 0.5 pt for R-P3 seam task in P4 not separately budgeted by the PRD, plus 0.5 pt OQ-5 Postgres staleness path buffer)

**Top-down anchor**: `ccdash-cli-mcp-enablement-v1` — transport wiring (REST + MCP + CLI) for existing backend intelligence services, no new DB schema, estimated ~8 pts. This feature adds a new service layer on top of equivalent transport scope plus a frontend surface.

**Reconciliation**: Bottom-up Σ of 9.0 pts is within ±15% of the spike's "8–10 pts" bracket and within ±12% of the anchor. The Decisions Block adds a clean 0.5–1 pt delta for the R-P3 FE/BE seam task and the OQ-5 buffer, arriving at 10 pts with a documented buffer absorption path.

### H1 — Noun counting

New domain nouns introduced: **2**
- `SystemActiveCountDTO` (aggregate response DTO)
- `ProjectActiveCountSummaryDTO` (per-project summary DTO)

Both are read-only DTOs — no new CRUD tables, no new write paths. H1 floor: ~0.5 pts for DTO authoring. Value of this feature is in service and transport wiring.

### H2 — Dual-implementation multiplier

**Not applied.** CCDash repositories use a single SQLite/Postgres path (not split local/enterprise implementations). The `count_active` repository method from the Tier 1 primitive is already authored.

### H3 — Algorithmic flag

No algorithmic surface. Fan-out aggregation is trivially parallel; staleness calculation is a timestamp comparison. **No flag triggered.**

### H4 — Bundle decomposition (≥3 capability areas)

| Capability area | Independent estimate | Notes |
|-----------------|---------------------|-------|
| `SystemMetricsQueryService` (fan-out + staleness + cache) | 2.5 pts | Core service; new `system_metrics.py`; cache fingerprint helper |
| REST endpoint + DTO models | 1.0 pt | Thin router adapter; Pydantic models; OpenAPI schema |
| MCP tool | 0.5 pt | Single tool registration; delegates to service |
| CLI command | 0.5 pt | `ccdash system active-count`; reuses existing Typer patterns |
| Frontend (chip + breakdown + polling + resilience) | 2.5 pts | New component; polling hook; expand interaction; 3 resilience states |
| Testing (unit + integration + smoke) | 1.5 pts | Multi-project fixture; transport parity test; performance test |
| Docs + CHANGELOG + CLAUDE.md update | 0.5 pt | H6 plumbing budget included here |
| **Σ** | **9.0 pts** | |

### H5 — Anchor reference

**Anchor:** `ccdash-cli-mcp-enablement-v1` — ~8 pts for transport wiring of existing intelligence services.
**Delta justification:** +1 pt for the new service (fan-out logic, staleness computation, cache fingerprint) and +0.5–1 pt for the frontend chip. Bottom-up Σ of 9 pts is within ±15% of the spike's "8–10 pts" bracket. No re-derivation needed.

### H6 — Hidden plumbing budget

Included in the Documentation row (0.5 pt): env var declarations in `config.py`, `CLAUDE.md` convention pointer, CHANGELOG entry, OpenAPI schema registration, `Cache-Control` header wiring.

### Sanity check summary

**Bottom-up total:** 9.0 pts
**Spike recommendation:** 8–10 pts
**Locked estimate:** **10 pts** (1 pt buffer = 0.5 pt for R-P3 seam task per Decisions Block §4 + 0.5 pt for OQ-5 Postgres staleness path uncertainty)

**If OQ-5 resolves cheaply** (extend `count_active` to return `max_updated_at`, single round-trip): P1 stays flat, budget rounds back to 9.5 pts — the buffer is absorbed. If OQ-5 costs more (separate cross-join or separate query per project on Postgres): buffer is consumed, stay at 10 pts. Do not add points without re-confirming with Opus.

---

## 3. Wave & Orchestration Notes

_Critical path narrative and parallelization notes. The plan owns the phase summary table and batch YAML._

### Phase strategy (5 phases)

| Phase | Name | Points | Parallelizable with |
|-------|------|--------|---------------------|
| P1 | Service primitive | 2.5 | — (serial gate; DTO shape must be frozen before P2/P3) |
| P2 | Transport wiring (REST + MCP + CLI) | 2.0 | P3 (disjoint file ownership) |
| P3 | Frontend home dashboard surface | 2.5 | P2 (disjoint file ownership) |
| P4 | Testing & performance validation | 1.5 | P4-BE and P4-FE can run in parallel |
| P5 | Runtime smoke + documentation | 1.0 | Docs can begin during P4 |

### Critical path

**P1 → P2 → P4 → P5** is the gating spine. P3 is parallel with P2 once P1 freezes the DTO shape. P5 smoke gate cannot close until P4 integration tests pass.

### P2/P3 parallelism opportunity

After P1 ships and the `SystemActiveCountDTO` shape is frozen:
- **P2 owner** (`python-backend-engineer`) takes `backend/routers/agent.py`, `backend/mcp/server.py`, `backend/cli/`.
- **P3 owner** (`ui-engineer-enhanced`) takes `components/Dashboard.tsx` and the new `components/SystemMetricsChip.tsx`, developing against a mocked REST response matching the frozen DTO.
- **Zero file overlap** — can be issued as a parallel batch. Integration happens in P4 via the R-P3 seam task (`test_dashboard_contract_parity`).

### HARD release gate on watcher-rebind Tier 1

The system-wide metrics feature is buildable, testable, and deployable independently. It must **not be released to users** until `watcher-rebind-on-active-project-switch-v1` also ships. The watcher-rebind contract is the mechanism that makes non-active project counts trustworthy. Until it lands, `is_stale` carries the full trust burden — and it is prominently surfaced by design. If the two features cannot ship together, ensure the per-project breakdown includes a persistent "inactive project data may be stale" banner and that `is_stale` tooltip displays `last_synced_at`. Do not suppress `is_stale` indicators as a cosmetic choice.

### Integration owner (R-P3)

The FE/BE seam between P2 (REST contract) and P3 (frontend consumer) must have a named integration owner. Per the Decisions Block, `python-backend-engineer` (the P2 contract author) owns the seam verification. The OpenAPI schema must be frozen at end of P2 and the P4 seam task (`test_dashboard_contract_parity`) must assert every field consumed by the frontend exists in the live REST response.

---

## 4. Open Questions Ledger

_Harvested from PRD §12 + Decisions Block §7. Update status column as resolved._

| ID | Source | Question | Status | Resolved By |
|----|--------|----------|--------|-------------|
| OQ-1 | PRD §12 | Should the service trigger a lazy per-project rescan (mtime-glob → parse-recent) for non-active projects during `get_system_active_count`? | Deferred | Scope risk in v1: rescan concurrency + stampede risk on home-dashboard load. `is_stale` flag is the mandatory mitigation. Lazy rescan deferred to follow-on spec. |
| OQ-2 | PRD §12 | Should `subagent` sessions be counted by default in the system-wide total? | Resolved: No | Mirrors `count_active(include_subagents=False)` default from live-count Tier 1. |
| OQ-3 | PRD §12 | Scale ceiling: when does the in-process fan-out need to be replaced? | Resolved: ~100 projects in-process; ~200 triggers background rollup | Deferred-items spec will document Option 2 (single-SQL `GROUP BY`) and Option 3 (background rollup) escape hatches with promotion thresholds. |
| OQ-4 | PRD §12 | Should `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS` default to 30 or to `CCDASH_QUERY_CACHE_TTL_SECONDS`? | Resolved: Separate default of 30s | General query cache defaults to 60s; 30s is more responsive for a live-count chip. Operator can align via env. |
| OQ-5 | PRD §12 | Postgres staleness computation: `max(sessions.updated_at)` — separate DB call or extended return from `count_active`? | Open — resolve at P1 | Preferred path: extend `count_active` to optionally return `max_updated_at` (single round-trip). If Postgres composite index doesn't cover this cleanly, escalate to Opus before P1 exits. |
| OQ-EXP-1 | Decisions Block §7 | Where exactly in `Dashboard.tsx` does the count chip live — top-right alongside project status, or a new row above the project switcher? | Open — resolve at P3 start | Deferred to `ui-engineer-enhanced` design judgment at implementation time. Examine current Dashboard layout first. |
| OQ-EXP-2 | Decisions Block §7 | New sub-component `components/SystemMetricsChip.tsx` or inline within `Dashboard.tsx`? | Recommended: new file | Follows existing CCDash component decomposition. Confirm against existing chip patterns before P3 starts. |
| OQ-EXP-3 | Decisions Block §7 | (Same as OQ-5) | Open — resolve at P1 | See OQ-5 above. |
| OQ-EXP-4 | Decisions Block §7 | Frontend cache layer — integrate with planning SWR+LRU cache, or implement own simpler polling? | Recommended: own simpler polling | Planning cache invalidation bus is overkill for a single-endpoint chip. Confirm by reading `services/planning.ts` at P3 start. |
| OQ-EXP-5 | Decisions Block §7 | `ccdash system active-count` CLI command — new `system` subcommand group (new file), or extend existing group? | Recommended: new group | Establishes the `ccdash system *` namespace for future system-wide commands. Verify at P2 start. |

---

## 5. Deferred Items Rationale

_Populate as P5 spec stubs are authored. Plan owns the triage table. This section explains the orchestration-level "why" for each deferral._

- **Lazy on-demand per-project rescan (OQ-1)**: The risk of issuing N parallel filesystem rescans on every home-dashboard load (stampede on a cold cache) outweighs the accuracy benefit for v1. The `is_stale` flag gives users the transparency to know they're looking at potentially dated data. Promote when: the watcher-rebind Tier 1 ships and we have a bounded per-project rescan mechanism that can be safely composed into the fan-out without hitting the 200ms budget.

- **Background rollup table (spike Option 3)**: The in-process fan-out design scales to ~100 projects before wall-clock latency becomes a concern. The rollup table is an architectural investment that trades write complexity for near-instant reads. Promote when: project count exceeds ~100 or the p95 perf test consistently exceeds 150ms in CI.

- **Single-SQL `GROUP BY` escape hatch (spike Option 2)**: Simpler than the rollup table and covers the ~100–200 project range. Promote before the rollup table if project count growth is gradual.

- **Desktop widget API hardening**: The `GET /api/agent/system/active-count` endpoint is widget-friendly in v1 (small payload, `Cache-Control` header, freshness metadata). Widget-specific hardening (rate limiting, authentication, versioned contract stability SLA) deferred until a concrete widget integration is planned.

- **Multi-project file watcher (`CCDASH_WATCH_ALL_PROJECTS`)**: The `watchfiles.awatch` underlying `FileWatcher` already accepts multiple paths. Gated by the watcher-rebind Tier 1 as a prerequisite. The opt-in env flag is deferred until after watcher-rebind proves the rebind mechanism is stable.

---

## 6. Risk Narrative

_Orchestrator-facing risk rationale. The plan owns the per-phase mitigation table. This section explains why each risk is load-bearing at the orchestration level._

### Risk 1: Stale `sessions.status` produces wrong "live" counts (HIGH)

This is the central trust risk of the entire feature. The spike's OQ-3 runtime verification (2026-05-20) is not a theoretical concern — it is an empirical finding. At verification time, the CCDash project itself had a `status='active'` row with `updated_at` 57 days in the past. A separate verification project had one 93 days stale. These rows will be counted as "running" by a naive `WHERE status='active'` query.

The freshness clamp in `count_active` (the `updated_at >= now() - window_seconds` predicate from the live-count Tier 1) prevents these rows from inflating the count in practice. But the `is_stale` flag is still essential because it tells the user "this project's data was last refreshed N hours ago, and we cannot guarantee the count reflects current reality." Without `is_stale`, the dashboard would silently present outdated data as authoritative.

**Why this is an orchestration-level concern**: if `is_stale` is implemented incorrectly (e.g., always `false`, or missing from the DTO serialization chain), the feature ships a trust-destroying UX: a count that looks authoritative but is based on data up to 93 days stale. The `is_stale` field is a **mandatory contract field** — treat any AC that touches it as load-bearing.

### Risk 2: FE/BE seam gap between P2 REST contract and P3 frontend (MEDIUM)

CCDash's incident history (`ccdash-planning-reskin-v2-interaction-performance-addendum`) includes exactly this class of bug: a backend DTO field renamed or reshaped between phase completion and frontend integration, resulting in silent rendering breakage. The R-P3 rule in the plan generator mandates an `integration_owner` declaration and a seam task. This is not a formality — it is a direct response to a past incident.

**What to watch for**: any PR in P2 that renames `is_stale`, `per_project`, or `total` without a corresponding frontend update; any P3 component that accesses a field not present in the frozen OpenAPI schema from P2. The P4 seam task (`test_dashboard_contract_parity`) is the enforcement mechanism.

### Risk 3: Performance regression at scale (MEDIUM)

The in-process fan-out across 36 projects at ~5–10ms each gives ~50–100ms wall clock with the bounded semaphore. This is comfortably under the 200ms p95 target. The risk is not current; it is latent. As project count grows, every 10 additional projects adds ~10ms. The performance test in P4 must establish a regression baseline so future project-list growth triggers a visible test failure rather than a silent SLA violation.

The Decisions Block's OQ-5 resolution has a secondary performance implication: if the Postgres staleness path collapses to a single `GROUP BY` query (spike Option 2), P1 grows by ~1 pt but P4's concurrency edge-case testing shrinks. This is a net-neutral or slightly positive trade at the feature level — worth making if the single-SQL path is cleaner.

### Risk 4: Postgres staleness query path divergence (LOW)

The `max(sessions.updated_at)` per-project query may not use the composite index `idx_sessions_project_status_updated` on Postgres the same way it does on SQLite. This is low severity because: (a) the query is cheap even without the index for 36 projects, (b) the staleness computation is only one query per project, (c) the OQ-5 preferred resolution (extend `count_active` to return `max_updated_at` in one pass) collapses the query count. If P1 implementation reveals unexpected Postgres behavior, escalate to Opus for re-routing before exiting P1. Do not silently accept a 2x latency increase.

### Risk 5: Frontend polling stampede (LOW)

Multiple open tabs, or a polling interval that doesn't respect the server-side cache TTL, could cause redundant fan-out. The `@memoized_query` cache with TTL=30s and the `Cache-Control: max-age=30` response header provide two layers of dedup. The "pause polling on hidden tab" requirement (FR-12) is the third layer. This risk is low but must be verified during the P5 smoke test: open two tabs on the home dashboard and confirm the backend logs show only one fan-out per 30s window.

---

## 7. What to Watch For

_Populate before phase start. Gotchas and trap-doors for real-time review during execution._

_None identified yet. Populate before P1 begins._

---

## 8. Expected Success Behaviors

_Observable, human-verifiable post-ship outcomes extracted from AC-1 through AC-6. These are the behaviors to confirm during P5 smoke testing and after release._

- [ ] Opening the home dashboard renders a "Live now" chip showing a numeric count of total agent sessions running across all projects; the chip is present on every dashboard load (AC-5, AC-6).
- [ ] Expanding the count chip reveals a per-project breakdown table: project name, count, and a visual warning indicator for any project whose data is older than 1 hour (AC-2, AC-5).
- [ ] At least one project in the breakdown shows a stale indicator with a tooltip displaying `last_synced_at` — confirming the staleness signal propagates end-to-end from service to UI (AC-2, AC-6).
- [ ] Running `ccdash system active-count --json` in a terminal returns a JSON payload whose `total` field matches the number shown in the dashboard chip (AC-1: CLI/REST parity).
- [ ] The MCP tool `ccdash_system_active_count` returns an identical aggregate to the REST response for the same DB state (AC-1: MCP/REST parity).
- [ ] If the backend dev server is restarted while the dashboard is open, the chip recovers within the next polling cycle (30s) and renders the last known value with a "data may be outdated" indicator until the fetch succeeds (AC-5 resilience).
- [ ] With the backend running and two dashboard tabs open, backend DEBUG logs show at most one fan-out per 30s window — not one per tab (Risk 5 / FR-6 cache validation).
- [ ] Navigating away from the dashboard tab pauses polling; returning to the tab resumes it within 30s (FR-12 visibility-state polling).
- [ ] A project with no sessions in the last hour shows `is_stale: true` in the breakdown, not a count of zero presented as fresh (AC-2 staleness accuracy).
- [ ] The performance integration test asserts p95 < 200ms for uncached aggregation across the 36-project fixture and p95 < 20ms for cached repeat calls (AC-4).

---

## 9. Running Log

_Append-only during execution. Agents may append here only if explicitly instructed in a task prompt._

- 2026-05-20 Brief created from PRD §13 (H1–H6), Decisions Block (§1–§7), and spike (OQ-3 runtime verification).
