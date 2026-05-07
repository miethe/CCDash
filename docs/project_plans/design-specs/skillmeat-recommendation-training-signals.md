---
schema_version: 2
doc_type: design_spec
title: "SkillMeat Recommendation Training Signals"
status: draft
maturity: shaping
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
  - recommendations
  - training-signals
  - review-outcomes
problem_statement: "CCDash can generate artifact recommendations, but SkillMeat cannot yet ingest reviewer decisions about those recommendations as privacy-safe training signals for future ranking and recommendation quality."
---

# SkillMeat Recommendation Training Signals

## Context

DF-002 covers recommendation review outcomes as future training signals. V1 recommendations are advisory and evidence-backed, but the exchange loop does not yet define how accepted, rejected, ignored, or modified recommendations should feed SkillMeat-side learning.

## Shaping Direction

Recommendation outcomes should be explicit review events, not inferred from later artifact changes. CCDash should only send minimal decision metadata needed to improve recommendation quality.

Candidate signal shape:

1. Recommendation identity, type, scope, confidence bucket, and evidence summary hash.
2. Reviewer action: accepted, rejected, dismissed, snoozed, modified, or superseded.
3. Optional reason code from a controlled vocabulary.
4. Time-to-decision and whether the recommendation was acted on manually.
5. No raw prompts, transcripts, local file paths, or reviewer free-text by default.

These signals should train ranking and recommendation calibration, not trigger automatic artifact mutations.

## Open Questions

1. Does SkillMeat need a new recommendation-outcome endpoint, or can this extend existing artifact outcome ingestion?
2. Which reason codes are stable enough for V1 without encouraging low-quality labeling?
3. Should ignored recommendations produce a signal, or only explicit reviewer actions?
4. How should CCDash handle local-only recommendations that are never exported?

## Promotion Criteria

Promote this spec when SkillMeat has an accepted write-back API shape for recommendation outcomes and CCDash has a privacy allowlist for exported review signal fields.
