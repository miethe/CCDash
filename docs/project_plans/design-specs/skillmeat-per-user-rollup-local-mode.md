---
schema_version: 2
doc_type: design_spec
title: "SkillMeat Per-User Rollup Local Mode"
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
  - artifact-usage
  - local-mode
  - privacy
problem_statement: "The SkillMeat artifact intelligence exchange needs per-user rollups, but local CCDash deployments may not have authenticated users and must not export stable personal identifiers by accident."
---

# SkillMeat Per-User Rollup Local Mode

## Context

DF-001 covers the local-mode identity gap for per-user artifact usage rollups. Hosted deployments can derive a user scope from auth or trusted telemetry attributes. Local deployments often only have project paths, hostnames, process context, or developer-provided labels, none of which should become exported personal identity by default.

## Shaping Direction

Local mode should treat `userScope` as optional and privacy-preserving. A project may export aggregate project and collection rollups without any user dimension until an explicit local identity policy is configured.

The likely V1 posture is:

1. Default local exports omit `userScope`.
2. Optional local pseudonyms are derived from a project-scoped salt, not host-global identifiers.
3. Pseudonyms rotate when the project binding or salt changes.
4. UI and API surfaces label pseudonymous rollups as local scopes, not real users.
5. SkillMeat must store local pseudonymous scopes separately from hosted principal scopes.

## Open Questions

1. Should pseudonymous local user scopes be opt-in per project, or enabled when artifact intelligence is enabled?
2. Where should the local salt live so exports remain stable enough for trend analysis without becoming globally linkable?
3. Should local mode support a user-provided display alias, or only opaque scope IDs?
4. How should mixed hosted/local history be merged or kept separate if a project later moves to hosted auth?

## Promotion Criteria

Promote this spec when the privacy policy for local pseudonyms is accepted and the SkillMeat storage contract distinguishes hosted principal scopes from CCDash-local pseudonymous scopes.
