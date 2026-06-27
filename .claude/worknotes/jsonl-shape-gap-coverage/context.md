---
schema_version: 2
doc_type: context
type: context
prd: "jsonl-shape-gap-coverage"
feature_slug: "jsonl-shape-gap-coverage"
status: active
created: 2026-05-19
updated: 2026-05-19
prd_ref: docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md
related_documents:
  - .claude/worknotes/jsonl-shape-audit/findings-2026-05-19.md
  - .claude/worknotes/jsonl-shape-gap-coverage/decisions-block.md
---

# JSONL Shape Gap Coverage - Development Context

**Status**: In-Progress (pre-execution — planning artifacts initialized)
**Created**: 2026-05-19
**Last Updated**: 2026-05-19

---

## Feature Goal

Close all 13 Claude Code JSONL shape gaps (unread top-level metadata fields, unhandled event types, and parsed-but-unrendered forensics) additively with zero breaking schema changes, surfacing attachment cards, permission-mode chips, turn-duration histogram, away-summary banner, and promptId/leafUuid forensics search across Session Inspector, CLI, MCP, and AAR pipelines.

---

## Source of Truth Links

- **PRD**: `docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md`
- **Implementation Plan**: `docs/project_plans/implementation_plans/enhancements/jsonl-shape-gap-coverage-v1.md`
- **Decisions Block**: `.claude/worknotes/jsonl-shape-gap-coverage/decisions-block.md`
- **Audit Findings**: `.claude/worknotes/jsonl-shape-audit/findings-2026-05-19.md`
- **Phase Progress**: `.claude/progress/jsonl-shape-gap-coverage/phase-[1-7]-progress.md`

---

## Key Decisions Made During Planning

### Phase Boundaries Rationale (§1)

- P1↔P2 boundary: Schema must be stable before event-type handlers persist into it. Both phases touch `parser.py` but P1 owns top-level field captures and P2 owns `type`-dispatched branches — file ownership is partitioned by code region, not by file.
- P2↔P3: API/agent_queries cannot expose what the parser does not yet capture. Sequential dependency.
- P3↔P4↔P5: Once contracts are stable, FE rendering (P4) and forensics CLI/MCP surfaces (P5) are file-disjoint and can run as parallel sprints. P4 touches `components/**`; P5 touches `packages/ccdash_cli/**` + `backend/mcp/**`.
- P6 always runs after all implementation phases: verifying the cross-owner contract is meaningless before it is wired end-to-end.
- P7 always last: docs reflect shipped behavior, not intent.

### Risk Hotspots — Severity Summary (§3)

| Risk | Severity | Key Mitigation Task |
|------|----------|---------------------|
| PostgreSQL migration parity drift | Medium | T1-003 + T1-005 (CI smoke both backends) |
| Attachment subtype coverage gaps | Medium | T2-001 `default` branch + `attachment:unknown` fallback fixture |
| Transcript render-cost regression | Medium | T4-010 perf guard + T6-003 large-transcript smoke |
| promptId indexing cost vs ROI | Low | T5-005 OQ-2 resolution (evaluate after CLI filters land) |
| FE resilience on pre-enrichment sessions | Low | T4-008 null-handling Vitest + T6-004 pre-enrichment smoke |

### OQ Leans (§7)

- **OQ-1**: Denormalized initially (P2 ships as system-log entries); promote to first-class artifact rows only if P5 forensics demand emerges. Plan does NOT add a new `attachments` table.
- **OQ-2**: Capture `promptId` in P1 unindexed; P5 (T5-005) adds index only if CLI/MCP forensics filters land. Evidence-driven.
- **OQ-3**: Both SQLite and PostgreSQL backends required. P1 exit gate runs both through CI (T1-005).
- **OQ-4**: Permission-mode transitions feed the existing per-turn timeline as inline chips. No separate "transitions" view.
- **OQ-5**: `attributionPlugin`/`attributionSkill` rollups live in `agent_queries/` (transport-neutral). P3 implements the query, P4 renders, P5 exposes via MCP filter.

---

## Open Questions

- **OQ-1** (PRD): Should `attachment` events become first-class artifact rows (new table or new `event_kind`), or stay denormalized on session payload? **Lean**: denormalized initially (P2 ships as system-log entries); promote if forensics demand emerges in P5. The implementation plan does NOT add a new `attachments` table.
- **OQ-2** (PRD): Should `promptId` become a queryable index on `AgentSession.events` or just a passthrough field? **Lean**: capture in P1 unindexed on events; P5 adds index only if CLI/MCP forensics filters land. Plan explicitly flags index decision as a P5 task subject to evidence.
- **OQ-3** (PRD): Are PostgreSQL migrations required, or only SQLite? **Lean**: both backends required (CCDash dual-targets per CLAUDE.md). P1 exit gate runs both backends through CI.
- **OQ-4** (PRD): Should `permission-mode` transitions feed the existing per-turn timeline or a separate transition log? **Lean**: same per-turn timeline as chips inline with the turn they apply to; do NOT add a separate "transitions" view. Verify with ui-engineer-enhanced via `codebase-explorer` of existing timeline component.
- **OQ-5** (orchestration): Where do `attributionPlugin`/`attributionSkill` rollups live — agent_queries (multi-transport) or Session Inspector–only? **Lean**: agent_queries (per CCDash transport-neutral convention); P3 implements the query, P4 renders the rollup panel, P5 exposes via MCP filter `--attribution-plugin`/`--attribution-skill`. Confirm in plan.

---

## Reference Artifacts

Past PRDs cited as estimation anchors (decisions block §4):

- `docs/project_plans/PRDs/enhancements/claude-code-session-context-and-cost-observability-v1.md` — anchor for P1 (additive `AgentSession` fields + parser captures, ~2 pts) and P3 (agent_queries plumbing, ~1.5 pts).
- `docs/project_plans/PRDs/enhancements/claude-code-session-thread-scope-rollups-v1.md` — anchor for P3 (agent_queries plumbing, ~1.5 pts).
- `session-transcript-append-deltas-v1` — anchor for P2 (event-type expansion, ~3 pts for new event types + branch dispatch).
- `ccdash-planning-reskin-v2` — anchor for P4 per-component widgets (~0.5 pt each × 5 widgets).
- `ccdash-query-caching-and-cli-ergonomics-v1` — anchor for P5 CLI flag additions (~1 pt).

---

## Glossary

- **promptId**: Top-level field on JSONL entries identifying the logical prompt invocation. Captured on `AgentSession.prompt_id`; indexed for CLI forensics search (`ccdash session search --prompt-id`).
- **leafUuid**: UUID identifying the leaf node of the current session's conversation tree. Used for resume-hint row in Session Inspector and `ccdash session show --leaf-uuid` lookup.
- **attributionSkill**: Per-entry field recording which Claude Code skill was active when a tool call was made. Rolled into `skillsUsed` list on session assembly.
- **attributionPlugin**: Per-entry field recording which Claude Code plugin was active. Rolled into `pluginsUsed` list on session assembly.
- **attachment subtype**: The `subtype` field on `type: "attachment"` events. 14 known subtypes: `hook_success`, `file`, `nested_memory`, `edited_text_file`, `opened_file_in_ide`, `selected_lines_in_ide`, plus 8 others. 6 subtypes call `add_artifact()`; all produce a `"attachment:<subtype>"` system-log entry. Unknown subtypes stored as `"attachment:unknown"`.
- **system.subtype**: The `subtype` field on `type: "system"` entries. New values in scope: `turn_duration` (persist to `turnDurations[]`), `away_summary` (create artifact, truncate at 8 KB), `bridge_status` (system event log), `local_command` (system event log).
- **turn_duration**: A `system.subtype` event that captures per-turn elapsed time. Persisted to `AgentSession.turn_durations` (JSON). Rendered as a bar histogram in the session summary panel.
- **away_summary**: A `system.subtype` event containing a model-generated summary of work done during an away period. Rendered as a collapsible banner at the top of the transcript.
- **permission-mode**: A top-level event `type: "permission-mode"` recording a transition in the session's permission mode. Each transition has `{timestamp, mode}`. Rendered as inline chips in the transcript timeline.
- **ai-title**: Event `type: "ai-title"` containing the model-generated session title and `titleSource`. Sets `AgentSession.title` when `titleSource != "manual"`.
- **last-prompt**: Event `type: "last-prompt"` containing the last prompt text snippet (`lastPrompt`, first 200 chars) and the `leafUuid`. Used to populate the resume-hint row in Session Inspector.
- **bridgeSessionId**: Field on `type: "bridge-session"` events identifying the parent session being bridged. Captured on `AgentSession.bridge_session_id`.
- **sessionKind**: Top-level field on JSONL entries indicating session type (e.g., `"bg"` for background sessions). Drives the "BG" badge in session list cards and `PlanningAgentSessionBoard`.
