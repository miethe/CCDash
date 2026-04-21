---
schema_version: 2
doc_type: design_spec
title: "Live Agent SSE Streaming v1"
status: draft
maturity: shaping
created: "2026-04-21"
updated: "2026-04-21"
feature_slug: "live-agent-sse-streaming"
prd_ref: "docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md"
plan_ref: "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
problem_statement: "The live agent roster in Planning v2 needs faster-than-polling updates for state, task context, and thinking activity, but the current planning surfaces still rely on request/response refresh cycles."
open_questions:
  - "Should the roster subscribe to one project-level SSE channel or one channel per feature/agent scope?"
  - "Which events are required for v1: roster membership, status transitions, thinking-count changes, and task handoffs?"
  - "How should reconnects and stale-stream fallback behave when the live transport drops?"
related_documents:
  - "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
  - "docs/project_plans/designs/ccdash-planning/README.md"
  - "docs/project_plans/designs/ccdash-planning/project/CLAUDE.md"
tags: [planning, live-updates, streaming, roster]
---

# Live Agent SSE Streaming v1

This spec captures the deferred live-update transport for the planning roster. The
v2 surface can ship with polling or coarse invalidation, but the long-term target
is a single shared SSE feed that keeps the roster and related planning indicators
fresh without repeated fetches.
