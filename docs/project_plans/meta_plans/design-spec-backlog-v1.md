---
schema_version: "1.0"
doc_type: meta-plan
title: "CCDash Design-Spec Backlog — Meta-Plan v1"
status: active
created: "2026-05-08"
updated: "2026-05-08"
owner: "@nick"
tags: [meta-plan, design-specs, backlog, planning, skillmeat, performance, ux]
waves:
  - id: 1
    title: "In-Flight Promotion"
    status: in-progress
    items:
      - title: "Promote remote-ccdash-streaming from spike to PRD"
        status: in-progress
        artifacts:
          spec: docs/project_plans/design-specs/remote-ccdash-streaming.md
  - id: 2
    title: "Quick UX Polish"
    status: planned
    items:
      - title: "Light-mode planning token ramp"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/planning-lightmode-tokens-v1.md
      - title: "Offline font bundling (remove CDN dependency)"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/bundled-fonts-offline-v1.md
  - id: 3
    title: "Deferred Performance Follow-ons"
    status: planned
    items:
      - title: "Transcript fetch-on-demand for large sessions"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/transcript-fetch-on-demand-v1.md
      - title: "Agent query cache LRU eviction policy"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/agent-query-cache-lru-v1.md
      - title: "Planning graph virtualization for large dependency trees"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/planning-graph-virtualization-v1.md
  - id: 4
    title: "Workflow & Infra Automation"
    status: planned
    items:
      - title: "Spike execution dispatch wiring"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/spike-execution-wiring-v1.md
      - title: "Planning primitives package extraction"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/planning-primitives-extraction-v1.md
  - id: 5
    title: "SkillMeat Intelligence Extensions"
    status: planned
    items:
      - title: "Collection rankings for non-deployed artifacts"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/skillmeat-collection-rankings-non-deployed.md
      - title: "Per-user usage rollups with local-mode privacy"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/skillmeat-per-user-rollup-local-mode.md
      - title: "Recommendation training signals from reviewer decisions"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/skillmeat-recommendation-training-signals.md
  - id: 6
    title: "Collaboration Infrastructure"
    status: planned
    items:
      - title: "Planning collaboration threads and discussion"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/planning-collab-threads-v1.md
---

# CCDash Design-Spec Backlog — Meta-Plan v1

This meta-plan captures all design-specs not yet promoted to PRDs or absorbed
by other features, organized into prioritized waves. It serves as a single
point of visibility for work that has been scoped and documented but not yet
scheduled for formal implementation planning. Wave ordering reflects a
combination of urgency, dependency depth, and cross-team readiness.

---

## Wave Rationale

- **Wave 1 — In-Flight Promotion**: Already in-progress spike work that needs
  formal PRD promotion before it can be scheduled for phased implementation.
- **Wave 2 — Quick UX Polish**: Low-complexity, high-polish wins that improve
  UX with minimal risk; these can be picked up opportunistically between larger
  feature tracks.
- **Wave 3 — Deferred Performance Follow-ons**: Deferred sub-features of
  shipped parent features; the underlying infra (sync engine, agent query
  cache, planning graph) already exists and only requires targeted extensions.
- **Wave 4 — Workflow & Infra Automation**: Developer workflow and tooling
  improvements that reduce friction in the inner loop but carry no user-facing
  urgency.
- **Wave 5 — SkillMeat Intelligence Extensions**: Depends on the artifact
  intelligence exchange maturing to a stable contract surface; best treated as
  future-wave material until rollup and ranking pipelines are proven in
  production.
- **Wave 6 — Collaboration Infrastructure**: Highest complexity wave; requires
  real-time infrastructure investment (presence, threading, conflict resolution)
  that is not yet justified by current usage patterns.

---

## Completed Specs

As of commit `febd9bc` (2026-05-08), the following design-specs were reconciled
during a backlog audit:

**Accepted** (5 specs — promoted to or fully absorbed by a shipped PRD):
- `cli-package-split-and-schemas`
- `cli-target-model-and-auth`
- `cli-versioned-api-surface`
- `ccdash-planning-control-plane-architecture`
- `container-project-onboarding-and-watchers-v1`

**Superseded** (3 specs — rendered obsolete by a different implementation path):
- `live-agent-sse-streaming-v1`
- `oq-frontmatter-writeback-v1`
- `spec-creation-workflow-v1`
