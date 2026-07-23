---
type: request-log
doc_id: REQ-20260723-ccdash
title: proof-to-routing-loop — deferred (conditional verdict)
project_id: ccdash
item_count: 1
tags: [ai, docs]
items_index:
  - id: REQ-20260723-ccdash-01
    type: idea
    title: proof-to-routing-loop: defer-until shared task_class vocabulary negotiated with delegation-router
created_at: 2026-07-23T15:01:16.780Z
updated_at: 2026-07-23T15:01:16.780Z
archived: false
---

## REQ-20260723-ccdash-01 - proof-to-routing-loop: defer-until shared task_class vocabulary negotiated with delegation-router

**Type:** idea | **Domain:** api | **Priority:** medium | **Status:** backlog
**Subdomain:** routing-feedback
**Context:** Conditional verdict from /plan:explore (2026-07-23). Feasibility brief: docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-feasibility-brief.md (verdict: conditional, 0.75); charter + 3 spike findings alongside. Landed on main a3e4577. AOS backward-pass workstream #6.
**Tags:** ai, docs

#### Notes

**Note 1: General** (Created: 2026-07-23 15:01)

Defer-until precondition: negotiate the shared task_class vocabulary with the delegation-router owner (MeatySkills repo, branch ibm-main). task_class is a JOIN KEY against an externally-owned taxonomy; CCDash cannot pin its correct values from this repo. Until pinned, the router must NOT consume task_class as a real routing join key (silent non-join -> inert loop; coincidental overlap -> mis-routing).

**Note 2: General** (Created: 2026-07-23 15:01)

When precondition holds: /plan:plan-feature --tier=2 (est. 10-16 pts, anchored on aar_reviews). CCDash-side emission machinery (worker rollup + coarsened tuple + REST/MCP/CLI PULL surface + capabilities gate + default-off flag CCDASH_ROUTING_ROLLUP_ENABLED) is low-risk/additive and MAY be built speculatively in parallel. Corrected tuple: (skill_name-as-task_class x model) with an explicit _unclassified bucket; drop write-path-dead profile/effort_tier/model_variant; provider is derived-not-captured.

