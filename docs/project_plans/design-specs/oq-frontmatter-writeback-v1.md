---
schema_version: 2
doc_type: design_spec
title: "OQ Frontmatter Writeback v1"
status: draft
maturity: shaping
created: "2026-04-21"
updated: "2026-04-21"
feature_slug: "oq-frontmatter-writeback"
prd_ref: "docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md"
plan_ref: "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
problem_statement: "Planning v2 needs a durable path for answering open questions inline, but the underlying filesystem write-back workflow still needs explicit rules for conflict handling and persistence."
open_questions:
  - "Should answers write directly to source frontmatter, or go through a queue/sync layer first?"
  - "How do we preserve the raw OQ text and provenance when an answer is pending sync?"
  - "What is the expected conflict policy if the source file changes before writeback completes?"
related_documents:
  - "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
  - "docs/project_plans/designs/ccdash-planning/README.md"
  - "docs/project_plans/designs/ccdash-planning/project/CLAUDE.md"
tags: [planning, open-questions, filesystem, writeback]
---

# OQ Frontmatter Writeback v1

This spec covers the deferred mutation path for open questions. The inline editor
exists in the v2 drawer, but the filesystem write-through model still needs a
clear contract for sync, conflicts, and operator feedback before it becomes the
canonical storage path.
