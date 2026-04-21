---
schema_version: 2
doc_type: design_spec
title: "SPIKE Execution Wiring v1"
status: draft
maturity: shaping
created: "2026-04-21"
updated: "2026-04-21"
feature_slug: "spike-execution-wiring"
prd_ref: "docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md"
plan_ref: "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
problem_statement: "The feature drawer surfaces SPIKE entries and execution affordances, but v2 defers actual dispatch wiring until the execution connector roadmap is settled."
open_questions:
  - "Which execution targets are valid for SPIKE dispatch in v1: local runtime, batch runner, or external connector?"
  - "What minimal confirmation and audit trail are required before dispatching a SPIKE action?"
  - "Should the wiring be feature-gated independently from the planning drawer UI?"
related_documents:
  - "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
  - "docs/project_plans/designs/ccdash-planning/README.md"
  - "docs/project_plans/designs/ccdash-planning/project/CLAUDE.md"
tags: [planning, execution, spikes, connectors]
---

# SPIKE Execution Wiring v1

The planning drawer can show SPIKE-specific execution controls now, but the
dispatch path itself remains a follow-on design. This spec keeps the UI and the
eventual wiring separate so the v2 reskin does not overcommit to a connector
shape that is still in flux.
