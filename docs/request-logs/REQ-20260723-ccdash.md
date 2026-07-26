---
type: request-log
doc_id: REQ-20260723-ccdash
title: "proof-to-routing-loop — T1 cleared, ready for planning"
project_id: ccdash
item_count: 1
tags: [ai, docs]
items_index:
  - id: REQ-20260723-ccdash-01
    type: idea
    title: "proof-to-routing-loop: shared task_class vocabulary pinned; proceed to planning"
created_at: 2026-07-23T15:01:16.780Z
updated_at: 2026-07-26T12:00:00-04:00
archived: false
---

## REQ-20260723-ccdash-01 - proof-to-routing-loop: shared task_class vocabulary pinned; proceed to planning

**Type:** idea | **Domain:** api | **Priority:** medium | **Status:** ready-for-planning
**Subdomain:** routing-feedback
**Context:** Conditional verdict from /plan:explore (2026-07-23). Feasibility brief: docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-feasibility-brief.md (verdict: conditional, 0.75); charter + 3 spike findings alongside. Landed on main a3e4577. AOS backward-pass workstream #6.
**Tags:** ai, docs

#### Notes

**Note 1: General** (Created: 2026-07-23 15:01)

Defer-until precondition: negotiate the shared task_class vocabulary with the delegation-router owner (MeatySkills repo, branch ibm-main). task_class is a JOIN KEY against an externally-owned taxonomy; CCDash cannot pin its correct values from this repo. Until pinned, the router must NOT consume task_class as a real routing join key (silent non-join -> inert loop; coincidental overlap -> mis-routing).

**Note 2: General** (Created: 2026-07-23 15:01)

When precondition holds: /plan:plan-feature --tier=2 (est. 10-16 pts, anchored on aar_reviews). CCDash-side emission machinery (worker rollup + coarsened tuple + REST/MCP/CLI PULL surface + capabilities gate + default-off flag CCDASH_ROUTING_ROLLUP_ENABLED) is low-risk/additive and MAY be built speculatively in parallel. Corrected tuple: (skill_name-as-task_class x model) with an explicit _unclassified bucket; drop write-path-dead profile/effort_tier/model_variant; provider is derived-not-captured.

**Note 3: T1 resolution** (Created: 2026-07-26)

Precondition cleared by the cross-project `aos.routing.feedback` v1.0.0 contract. Live evidence
confirmed the safe answer is **not** a direct join: 17 observed nonblank CCDash skill names and 12
router policy classes had zero exact overlaps. agentic_meta_dev owns the seam decision and exact
source mapping; MeatySkills `ibm-main` owns `aos.routing.task_class` v1.0.0 and the fail-closed
validator. CCDash must preserve `source_skill_name`, emit canonical `task_class` only through the
pinned mapping, and report `_unclassified` coverage. The router owns the bounded-adjustment
cap/floor, minimum-sample defense, human-override-wins, protected-class immunity, disable switch,
and RoutingRecord provenance.

Next action: `/plan:plan-feature --tier=2`. This request is ready for planning, not shipped:
CCDash has no routing-rollup surface and the router has no live empirical merge; consumption stays
disabled.
