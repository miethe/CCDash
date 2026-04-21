---
schema_version: 2
doc_type: design_spec
title: "Planning Collab Threads v1"
status: draft
maturity: shaping
created: "2026-04-21"
updated: "2026-04-21"
feature_slug: "planning-collab-threads"
prd_ref: "docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md"
plan_ref: "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
problem_statement: "Planning artifacts may eventually need comment threads and collaboration history, but v2 does not yet have a durable collaboration model across projects and tenants."
open_questions:
  - "Are threads anchored to artifacts, frontmatter fields, or both?"
  - "How should collaboration permissions interact with local-first project ownership and future tenancy?"
  - "What is the expected notification and reply model for threaded planning comments?"
related_documents:
  - "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
  - "docs/project_plans/designs/ccdash-planning/README.md"
  - "docs/project_plans/designs/ccdash-planning/project/CLAUDE.md"
tags: [planning, collaboration, threads, comments]
---

# Planning Collab Threads v1

This spec preserves the deferred collaboration surface for planning artifacts.
The v2 planning UI can stay focused on navigation and execution affordances while
this document captures the longer-term threading model.
