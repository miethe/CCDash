---
schema_version: 2
doc_type: design_spec
title: "Planning Primitives Extraction v1"
status: draft
maturity: shaping
created: "2026-04-21"
updated: "2026-04-21"
feature_slug: "planning-primitives-extraction"
prd_ref: "docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md"
plan_ref: "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
problem_statement: "The planning reskin introduces a richer primitive set that should eventually be extracted into a reusable package instead of staying embedded in the planning implementation."
open_questions:
  - "What primitive boundary is stable enough to extract without dragging in planning-specific layout code?"
  - "How should versioning work if downstream surfaces adopt the primitives incrementally?"
  - "Should the extraction preserve local styling hooks or normalize to a stricter shared API?"
related_documents:
  - "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
  - "docs/project_plans/designs/ccdash-planning/README.md"
  - "docs/project_plans/designs/ccdash-planning/project/CLAUDE.md"
tags: [planning, primitives, ui-components, extraction]
---

# Planning Primitives Extraction v1

This spec records the future extraction path for the planning primitive library.
For v2, the primitives can live close to the planning surfaces so the reskin can
land without a packaging detour, while this doc preserves the follow-on package
shape.
