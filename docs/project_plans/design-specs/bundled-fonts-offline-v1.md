---
schema_version: 2
doc_type: design_spec
title: "Bundled Fonts Offline v1"
status: draft
maturity: shaping
created: "2026-04-21"
updated: "2026-04-21"
feature_slug: "bundled-fonts-offline"
prd_ref: "docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md"
plan_ref: "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
problem_statement: "The planning reskin uses Geist, JetBrains Mono, and Fraunces for visual fidelity, but the long-term offline posture needs a bundled-font path instead of CDN-only loading."
open_questions:
  - "Which font files and weights are mandatory for the planning surfaces to remain legible offline?"
  - "Should font assets be shipped through the frontend build, a static asset pipeline, or a shared cache layer?"
  - "What fallback behavior is acceptable when a font asset is missing or corrupt?"
related_documents:
  - "docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md"
  - "docs/project_plans/designs/ccdash-planning/README.md"
  - "docs/project_plans/designs/ccdash-planning/project/CLAUDE.md"
tags: [planning, fonts, offline, typography]
---

# Bundled Fonts Offline v1

This spec captures the deferred offline typography path for the planning bundle.
The v2 implementation can rely on hosted fonts during the rollout window, while
this spec holds the work needed for environments that require fully bundled font
assets.
