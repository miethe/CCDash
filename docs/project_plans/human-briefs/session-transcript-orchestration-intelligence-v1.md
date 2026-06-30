---
schema_name: ccdash_document
schema_version: 2
doc_type: human_brief
doc_subtype: feature_brief
root_kind: project_plans
id: BRIEF-session-transcript-orchestration-intelligence-v1
title: "Session Transcript Orchestration Intelligence V1 - Human Brief"
status: draft
category: human-briefs
feature_slug: session-transcript-orchestration-intelligence-v1
feature_family: session-transcript-intelligence
feature_version: v1
prd_ref: docs/project_plans/PRDs/enhancements/session-transcript-orchestration-intelligence-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/session-transcript-orchestration-intelligence-v1.md
intent_ref: null
epic_ref: null
related_documents:
  - docs/project_plans/reports/plan-2-ccdash-observability-integration-analysis-2026-03-21.md
  - docs/project_plans/design-specs/session-transcript-orchestration-intelligence-v1.md
  - .claude/worknotes/session-transcript-orchestration-intelligence-v1/decisions-block.md
owner: platform-engineering
contributors:
  - codex
audience: [humans]
priority: high
confidence: 0.82
created: 2026-06-30
updated: 2026-06-30
target_release: null
tags:
  - human-brief
  - sessions
  - transcript
  - orchestration
---

# Session Transcript Orchestration Intelligence V1 - Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-06-30

## 1. Context Pointers

- **PRD**: `docs/project_plans/PRDs/enhancements/session-transcript-orchestration-intelligence-v1.md`
- **Plan**: `docs/project_plans/implementation_plans/enhancements/session-transcript-orchestration-intelligence-v1.md`
- **Design Spec**: `docs/project_plans/design-specs/session-transcript-orchestration-intelligence-v1.md`
- **Decisions Block**: `.claude/worknotes/session-transcript-orchestration-intelligence-v1/decisions-block.md`
- **Root Observability Context**: `docs/project_plans/reports/plan-2-ccdash-observability-integration-analysis-2026-03-21.md`
- **Related Completed Work**: `per-message-token-usage`, `planning-agent-session-board-v1`, `workflow-registry-and-correlation-v1`, `claude-code-session-usage-attribution-v2`

## 2. Estimation Sanity Check

**Bottom-up total**: 20 pts.
**Top-down anchor**: Planning Agent Session Board V1 is the closest UI/data-contract anchor; per-message-token-usage is the closest transcript-token anchor.
**Reconciliation**: This is larger than per-message-token-usage because it adds minimap, task/workflow registers, effort timeline, and plan metadata. It is smaller than Planning Agent Session Board because it reuses existing transcript/session surfaces and avoids launch orchestration.

H1-H6 heuristic application:

- **H1 (noun count)**: No new CRUD nouns in V1; a persisted marker table would change this.
- **H2 (dual implementation)**: Not applied because no new DB table is planned.
- **H3 (algorithmic service flag)**: Applies to title, effort, task, workflow, plan-link, and token-coverage resolvers.
- **H4 (bundle-vs-sum)**: Seven capability areas sum to 20 pts.
- **H5 (anchor)**: Planning Agent Session Board and per-message-token-usage justify the range.
- **H6 (plumbing)**: Included in P1/P5 for DTOs, flags, tests, docs, and changelog.
- **H7 (huge-file touch)**: `SessionInspector.tsx` and `TranscriptView.tsx` require scoped edits or extraction.

## 3. Wave and Orchestration Notes

**Critical path**: Fixture audit -> backend derived index -> minimap/register UI -> token rail -> validation.

**Parallel opportunities**:

- Title/header work can run parallel with minimap/register UI after the backend contract is stable.
- Task sidepane and workflow sidepane can split by component ownership.

**Merge order**:

1. Backend DTO/query contract and tests.
2. Session list/header fields.
3. Minimap and registers.
4. Token rail.
5. Docs, changelog, runtime smoke.

**Cross-feature coupling**:

- Per-message token usage supplies row-level source data.
- Usage attribution can improve agent/tool token detail but must not be required for the V1 rail.
- Workflow Registry remains the global workflow page; this feature adds transcript-local workflow context.

## 4. Open Questions Ledger

| ID | Source | Question | Status | Resolved By |
|----|--------|----------|--------|-------------|
| OQ-1 | PRD | What exact JSONL shape does Claude Code Agent Teams emit? | open | P0 fixture audit |
| OQ-2 | PRD | Should workflow output files be parsed during sync? | open | P0 workflow safety task |
| OQ-3 | Design Spec | What minimap density works for very long transcripts? | open | P3 runtime/perf pass |
| OQ-4 | Plan | Which plan/task links are high-confidence enough for primary display? | open | P1/P3 resolver tests |
| OQ-5 | PRD | Which stale path-style session links should be normalized? | open | P2 session link compatibility |

## 5. Deferred Items Rationale

- **Persisted marker table**: Deferred because V1 can derive markers and Agent Teams shape is not confirmed.
- **Full workflow output parsing**: Deferred until a safe metadata-only contract exists.
- **Cross-platform parity**: Deferred until Claude Code behavior is validated.

## 6. Risk Narrative

- **False precision in token UI**: Most important product risk. The implementation must label per-message versus attribution-event versus aggregate token data.
- **Huge transcript UI complexity**: Minimap, token rail, and grouped rows can break virtualization if implemented as layout side effects.
- **Over-correlated plan metadata**: Slug/task references need confidence labels and fallback behavior.
- **Agent Teams unknowns**: Present unknown team events as unclassified orchestration signals until fixtures prove structure.
- **Greenfield drift**: Existing route/API/transcript components already carry much of the needed structure; implementation should add a derived index and focused components rather than a parallel transcript reader.

## 7. What to Watch For

- Avoid hiding raw TaskCreate/TaskUpdate rows behind grouping with no expansion.
- Avoid making advanced effort look like a failure state.
- Avoid expanding `SessionInspector.tsx` further when extracting focused components would reduce risk.
- Confirm the live sample still reproduces `effortTier: null` before using it as a before/after proof point.

## 8. Expected Success Behaviors

- [ ] `/sessions` card for the live sample shows a useful `/plan:plan-feature ...` title with the raw id below.
- [ ] Header shows model plus `Ultracode -> High` or equivalent transition summary.
- [ ] Minimap jumps to effort changes, Workflow start/completion, task groups, and token hotspots.
- [ ] Task sidepane shows TaskCreate/TaskUpdate-derived state with transcript links.
- [ ] Workflow sidepane distinguishes dynamic workflow orchestration from normal subagent calls.
- [ ] Token rail shows row-level segments only where row-level token data exists.

## 9. Running Log

- [2026-06-30] Brief created with PRD, implementation plan, design spec, and decisions block.
