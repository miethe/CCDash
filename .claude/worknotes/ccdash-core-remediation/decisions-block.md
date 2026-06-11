# Decisions Block — CCDash Core Remediation v1

> Opus-authored architectural scaffold (Tier 3). Expand into PRD + Implementation Plan via `implementation-planner`.
> Evidence: `docs/project_plans/reports/investigations/ccdash-core-remediation-diagnostic-v1.md` (two diagnostic workflows + 9 verified verdicts). **Do not restate the report — reference it.**

## Context (the delta only)

CCDash is a single-active-project-optimized app being asked to serve **all projects, all agents, and external consumers (IntentTree)**. The diagnostic produced four root-cause themes and 9 verified findings. This program restores the core workflows and adds the operator's top deliverable: **any agent can pull full detail (incl. transcript/subagent/workflow content) for any session in any project, via MCP/CLI/REST.**

### Locked operator decisions (gate scope — do not re-litigate)
1. **Egress**: local-trust, all surfaces (REST + MCP + repo-CLI), **with secret/PII redaction** on tool-call payloads.
2. **Detection**: ship **log-derivable now**; ica-delegate profile + Ultracode/effort are **data-absent in logs** → delivered only via a **launch-time capture** fast-follow (Phase 11).
3. **Postgres/containers**: **move now** → coalescing guard, PG parity, container smoke are P0-infra.
4. **Appetite**: **full roadmap, one orchestrated effort** (Phases 0–12).

### Corrected assumptions (from verification — bake into plan, do not re-discover)
- Token undercount (old W7) is **already fixed** (shipped 2026-03-09) → **excluded** from scope. Only residual: confirm no dashboard surfaces `analytics.py:553` per-lifecycle-event in+out sum as a workload total (tiny check folded into Phase 12).
- `/api/v1 get_session_detail_v1` returns **analytics facts only** (models.py:961) — **no transcript**. But `SessionTranscriptService.list_session_logs` (application/services/sessions.py:92) already exists, is transport-neutral, and is already reused by `feature_forensics.py`. → Phase 1 is **exposure/wiring + redaction**, NOT a new retrieval engine.
- `get_by_id`/`get_many_by_ids` are **project-unsafe** in BOTH sqlite (sessions.py:206/215) and postgres (postgres/sessions.py:142/148) despite composite PK (project_id,id). `get_session_family_v1` is **active-project-bound** (_client_v1_sessions.py:269). These are **prerequisites** that turn active the moment cross-project reads ship.
- Cross-project watchers **already register for all projects and survive active-switch** → Phase 8 is hardening (periodic reconcile + self-heal), not a rebuild. Moderated priority.
- Multiple Full Syncs: default-dev = single scan/project (active skipped by all-projects loop, runtime.py:811); pain = `uvicorn --reload` + always-on sweep. **Real** double-scan exists **only under JOB_QUEUE_BACKEND != memory** (postgres) — no coalescing. → Phase 7 coalescing is genuinely needed once Postgres is live.
- Fable: family derivation works; cost is **silently Sonnet-mispriced** (not $0). → Phase 6 reframed.

## Phase Boundaries

| Phase | Name | Scope | Exit gate |
|------|------|-------|-----------|
| 0 | Cross-project session correctness | project_id on get_by_id/get_many_by_ids (sqlite+pg) w/ NULL/'' tolerance; family anchor-derived project_id; drilldown audit/fix; thread ~11 call sites | ADR-007 collision tests green (colliding ids across 2 projects resolve correctly); existing suites pass |
| 1 | Transport-neutral transcript service + redaction | New `agent_queries/session_detail.py` reusing SessionTranscriptService; include-flags; pagination {items,cursor,limit,nextCursor}; redaction layer | Service returns transcript+subagents+tokens+artifacts+links for any project_id; redaction unit-tested; no transcript reader duplicated |
| 2 | /api/v1 detail + transcript endpoints | v1 handlers + response models (client_v1.py, _client_v1_sessions.py); contracts package; cross-project param | v1 returns full session detail incl. transcript for non-active project; contract test pins envelope |
| 3 | MCP session tools + repo-CLI session group | `mcp/tools/sessions.py` (search/detail/transcript); `cli/commands/session.py`; standalone CLI rewire; parity test; SKILL.md update; MCP size/chunk budget | MCP session_detail returns full detail for non-active project; MCP/CLI/REST parity test green; runtime smoke |
| 4 | Live link freshness | prove scoped link-rebuild fires on watcher path; flip CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED default True; family-scoped rebuild | New subagent jsonl → linked within one watcher cycle, no restart; no global fingerprint scan on hot path |
| 5 | Detection (log-derivable) | model bare-slug; workflow.json sidecar parser + runId/taskId join for [1m]; workflow+subagent linkage hardening; skill attribution; new columns (dual DDL + parity) + FE fallbacks | A 1M session shows 1M-context (via sidecar join); workflow groups root+subagents; subagent linkage survives null sidecar; columns parity-clean both backends |
| 6 | Pricing correctness | _estimate_cost no Sonnet-default for unknown; pricing_catalog generic family/explicit-unpriced; Fable in catalog; FE unpriced state | Novel claude-<family> id flagged unpriced (not Sonnet); regression fixture green |
| 7 | Sync coalescing + recent-first + startup hygiene | project_id-keyed coalescing guard at sync dispatch (in-proc + durable); recent-first parse + lazy backfill (flag); reload boot-cost reduction | No duplicate full-sync per project/trigger under postgres; recent sessions queryable in seconds; backfill count == baseline |
| 8 | Cross-project freshness hardening | periodic all-projects reconcile; watcher liveness self-heal; SYNC_ALL_PROJECTS=False + post-boot dirs; docs/plans parity | Plan added to non-active project appears within reconcile interval; crashed watcher self-heals; writeback stays off for non-active (tested) |
| 9 | Postgres parity + container/compose | validate all new columns on PG (dual DDL + COLUMN_PARITY_DRIFT_ALLOWLIST); **Bash-enabled PG seam review**; api+worker+postgres compose + e2e smoke; durable queue + coalescing; readyz | compose e2e smoke green; PG seam review (WITH Bash) signs off; parity tests green |
| 10 | External API (IntentTree) | /api/v1 as external contract; OpenAPI checked in; capability advertisement; CORS/bind/auth for LAN; example client | IntentTree can list/search/detail any project_id via documented schema; OpenAPI committed; contract test pins shape |
| 11 | Launch-time profile/effort capture (fast-follow) | wrapper/hook records launcher/profile (ica-delegate)/effort/model-variant sidecar; parser ingests → first-class fields; FE fallbacks | A session launched via ~/ica-claude.sh attributes profile=ica-delegate; Ultracode/effort tier populated; columns parity-clean |
| 12 | Docs finalization + CHANGELOG + karen | CHANGELOG [Unreleased]; feature-surface-architecture.md; CLAUDE.md conventions; observability freshness probes; analytics.py:553 check | karen end-of-feature pass; CHANGELOG present; runtime smoke for all UI phases |

## Agent Routing (primary / secondary per phase)

| Phase | Primary | Secondary / reviewer |
|------|---------|----------------------|
| 0 | data-layer-expert | senior-code-reviewer (WITH Bash for PG); task-completion-validator |
| 1 | backend-typescript-architect? **no** → python-backend-engineer | code-reviewer |
| 2 | python-backend-engineer | api-librarian (envelope/pagination); task-completion-validator |
| 3 | python-backend-engineer (MCP+CLI) | ai-artifacts-engineer (SKILL.md); task-completion-validator |
| 4 | data-layer-expert | ultrathink-debugger (causal-link proof); task-completion-validator |
| 5 | python-backend-engineer (parser) + ui-engineer-enhanced (FE) | data-layer-expert (columns); **integration_owner** required (FE+BE seam) |
| 6 | python-backend-engineer | ui-engineer-enhanced (FE unpriced state) |
| 7 | python-backend-engineer / backend-architect | ultrathink-debugger (concurrency) |
| 8 | python-backend-engineer | data-layer-expert |
| 9 | data-layer-expert + devops-architect | **senior-code-reviewer WITH Bash** (mandatory PG seam); karen |
| 10 | api-designer / python-backend-engineer | api-documenter (OpenAPI) |
| 11 | python-backend-engineer | data-layer-expert |
| 12 | documentation-writer + changelog-generator | karen (end-of-feature) |

Default executor model **sonnet**; docs **haiku**; Opus only for cross-phase decisions. PG seam review escalates to a Bash-enabled reviewer (per memory: edit-less reviewer missed 3 PG-only bugs).

## Risk Hotspots

| Risk | Severity | Mitigation |
|------|----------|------------|
| Shared-file collisions: Phases 5/7/8 all edit runtime.py, sync_engine.py, config.py | high | **Single-thread** sync/runtime edits; explicit file-ownership per phase; no parallel agents on these files |
| Postgres column drift (Phases 5/6/11 add columns) | high | Dual SQLite+PG DDL + COLUMN_PARITY_DRIFT_ALLOWLIST update **in the same change**; Phase 9 Bash-enabled PG seam review |
| Cross-project read leaks wrong project's rows | high | Phase 0 is a hard prerequisite; tests assert project_id never returns another project's rows; do not ship Phase 2/3 before Phase 0 green |
| Transcript egress leaks secrets/PII | high | Redaction layer is a Phase 1 deliverable, not a courtesy; redaction unit tests; local-trust documented |
| Flipping incremental-link-rebuild regresses perf (global fingerprint scan) | med | Phase 4 proves scoped path BEFORE default-on; assert no global scan on hot path |
| Recent-first backfill silently partial | med | Backfill count == baseline full-scan assertion; log dropped/deferred counts (no silent caps) |
| Runtime smoke gate (CLAUDE.md) for UI phases (3,5,6,11) | med | Dev server up; browser smoke per target_surfaces; no phase `completed` on unit tests alone |
| MCP transcript payload size | med | Defined chunk/pagination budget + documented max (Phase 3) |

## Estimation Anchors (bottom-up, H1–H6)

- Phase 0: ~3 pts (mechanical param-threading + tests; 2 backends ×H2).
- Phases 1–3 (top deliverable): ~13 pts (new service + redaction + v1 endpoints + MCP/CLI + parity; H3 algorithmic-ish redaction; H4 bundle of 3 surfaces).
- Phase 4: ~3 pts. Phase 5: ~8 pts (new sidecar parser + join + columns + FE; H1 columns, H3 join). Phase 6: ~3 pts.
- Phase 7: ~5 pts (concurrency guard, H3). Phase 8: ~5 pts. Phase 9: ~8 pts (container + PG seam, H2). Phase 10: ~5 pts. Phase 11: ~8 pts (new capture mechanism). Phase 12: ~3 pts.
- **Total ~67 pts** → unambiguously Tier 3. No single comparable anchor exists (H5 unknown) → diagnostic served as the SPIKE. Add ~18% hidden plumbing (DTOs/DI/OpenAPI/migrations/CHANGELOG, H6).

## Dependency Map / Critical Path

```
0 ─▶ 1 ─▶ 2 ─▶ 3 ─▶ 11
          └──▶ 10
4 (independent, P0)
5 ─▶ 9 ;  6 ─▶ 9 ;  7 ─▶ 9
8 (independent hardening)
{4,5,9,10,11} ─▶ 12 (+ karen)
```

**Critical path**: 0 → 1 → 2 → 3 (top deliverable). Parallelizable after 0: {1-chain} ∥ {4} ∥ {5,6} ∥ {7}. Phase 9 is the PG/enterprise convergence gate for column-adding phases. Phase 12 + karen close.

**Wave plan (for orchestrated execution)**:
- Wave 1: Phase 0 (blocking).
- Wave 2: Phase 1 ∥ Phase 4 ∥ Phase 6 ∥ Phase 7 (independent of the 1-chain tail; 5/7/8 sync-file edits single-threaded among themselves).
- Wave 3: Phase 2 ∥ Phase 5 ∥ Phase 8.
- Wave 4: Phase 3 ∥ Phase 9 ∥ Phase 10.
- Wave 5: Phase 11.
- Wave 6: Phase 12 + karen.

## Model Routing per phase
All executors **sonnet/adaptive** unless noted. Docs **haiku/adaptive**. PG seam review + karen as gates (no model override needed — agent definitions carry it). No external-model tasks in this program except optional Codex debug-escalation if Phase 4 causal-link or Phase 7 concurrency stalls >2 cycles.

## Open Questions for implementation-planner (OQ-*)
- **OQ-1**: Redaction strategy — pattern-based secret scan vs allowlist field redaction vs both? (Phase 1) Recommend layered: known secret patterns + tool-name-aware payload field redaction; configurable via env.
- **OQ-2**: MCP transcript chunk size / max envelope bytes — pick a concrete default (Phase 3).
- **OQ-3**: Recent-first window definition — N most-recent sessions vs last-K-days vs mtime budget? (Phase 7).
- **OQ-4**: Periodic reconcile cadence + whether registry-change-event-driven is feasible now (Phase 8).
- **OQ-5**: Launch-time capture transport — wrapper script around `~/ica-claude.sh` / Claude Code SessionStart hook / sidecar file convention? (Phase 11).
- **OQ-6**: Auth model for cross-host LAN /api/v1 — bearer token vs none-on-LAN under local-trust? (Phase 10).

## Plan Skeleton Pointer
- Template: `.claude/skills/planning/templates/implementation-plan-template.md`
- PRD output: `docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md`
- Plan output: `docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md` (will exceed 800 lines → split into phase files `ccdash-core-remediation-v1/phase-N-*.md`)
- Progress: `.claude/progress/ccdash-core-remediation/phase-N-progress.md`
- changelog_required: true
