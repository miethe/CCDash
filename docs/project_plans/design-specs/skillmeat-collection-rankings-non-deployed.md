---
schema_version: 2
doc_type: design_spec
title: "SkillMeat Collection Rankings for Non-Deployed Artifacts"
status: draft
maturity: idea
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
prd_ref: docs/project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
plan_ref: docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md
created: 2026-05-07
updated: 2026-05-07
category: integrations
tags:
  - design-spec
  - integrations
  - skillmeat
  - collection-rankings
  - non-deployed-artifacts
  - artifact-discovery
problem_statement: "Collection owners may want rankings for artifacts that belong to a SkillMeat collection but are not deployed in the current CCDash project, yet the V1 ranking semantics are defined around observed project usage and deployed snapshot membership."
---

# SkillMeat Collection Rankings for Non-Deployed Artifacts

## Context

DF-003 covers collection-level ranking semantics for artifacts that are available in a collection but not deployed in a CCDash project snapshot. These artifacts cannot be ranked from local observed usage in the same way as loaded or deployed artifacts.

## Idea

Non-deployed collection rankings should be treated as discovery guidance, not project usage rankings. They may help catalog owners and workflow authors answer: "What high-performing collection artifacts are missing from this project?"

Possible direction:

1. Keep project rankings limited to deployed, observed-only, stale, and unresolved artifacts.
2. Add a separate collection discovery view for non-deployed artifacts.
3. Rank non-deployed artifacts using SkillMeat-side collection metrics, compatibility metadata, recency, and adoption signals.
4. Clearly label recommendations as candidates to evaluate, not proven project improvements.
5. Require a scope decision before mixing non-deployed artifacts into CCDash project recommendation feeds.

## Open Questions

1. Should non-deployed artifacts appear in CCDash at all, or only in SkillMeat collection/catalog surfaces?
2. What minimum compatibility metadata is required before recommending a non-deployed artifact for a project?
3. Should collection-level rankings be filtered by deployment profile, workflow type, or artifact family?
4. How should cold-start projects distinguish "unused because unavailable" from "unused despite being deployed"?

## Promotion Criteria

Promote this idea when an ADR defines whether non-deployed collection artifacts are part of CCDash project intelligence, SkillMeat catalog intelligence, or a separate discovery workflow.
