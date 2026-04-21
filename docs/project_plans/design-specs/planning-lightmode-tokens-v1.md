---
schema_version: 2
doc_type: design_spec
title: "Planning Lightmode Tokens v1"
status: draft
maturity: shaping
created: "2026-04-21"
updated: "2026-04-21"
feature_slug: "planning-lightmode-tokens"
prd_ref: "docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md"
plan_ref: "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
problem_statement: "The current planning token system is optimized for the dark planning shell, but a separate light-mode token set still needs a dedicated design pass."
open_questions:
  - "Should light mode reuse the same semantic tokens with remapped ramps, or define a separate palette layer?"
  - "What contrast targets and component exceptions need special handling in light mode?"
  - "How should density, borders, and shadows differ between dark and light planning modes?"
related_documents:
  - "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
  - "docs/project_plans/designs/ccdash-planning/README.md"
  - "docs/project_plans/designs/ccdash-planning/project/CLAUDE.md"
tags: [planning, light-mode, tokens, accessibility]
---

# Planning Lightmode Tokens v1

This spec keeps the light-mode planning palette separate from the v2 dark-mode
reskin work. It preserves the unresolved token questions without blocking the
current design token rollout.
