# CCDash Integration — Agent Handover Context

**Purpose**: This directory contains the SkillMeat-side integration audit for the CCDash Agentic SDLC Intelligence Foundation V1.

## Files in This Packet

| File | Purpose | Audience |
|------|---------|----------|
| `integration-audit.md` | Complete 10-section audit answering all deliverables from the design spec | CCDash implementing agents |
| `example-payloads.json` | Sanitized example payloads for artifact, workflow, plan, context module, execution, and error responses | CCDash agents building DTOs and client code |
| `context.md` | This handover document | CCDash orchestrator |

## How CCDash Agents Should Use This

### Phase 1 (Integration Contract + Definition Cache)

1. Read `integration-audit.md` §1 (Integration Contract Summary) for auth, pagination, and error handling.
2. Read §2 (Canonical Contracts) for exact field inventories.
3. Read §3 (Project/Workspace Mapping) for the `external_definition_sources` config model.
4. Use `example-payloads.json` to build SkillMeat DTO normalization.

### Phase 2+ (Stack Extraction, Scoring, Recommendations)

1. Read §4 (Artifact Definition Guidance) for ID format, type priorities, and matching rules.
2. Read §5 (Workflow Definition Guidance) for SWDL parsing, stage-level artifacts, and plan consumption.
3. Read §6 (Context Module Guidance) for selector semantics and `ctx:name` resolution.
4. Read §7 (Deep-Link Contract) for UI linking patterns.

### Enhancement Planning

Read §8 (Enhancement Opportunities) for prioritized improvements that would improve CCDash fidelity.

## Answers to CCDash Open Questions

These map to the "Open Questions for the Next Implementation Round" in the CCDash PRD:

| # | Question | Answer |
|---|----------|--------|
| 1 | Canonical per-project mapping? | Store SkillMeat project filesystem path as integration setting. Use as `project_id` in API calls. See §3. |
| 2 | Auth model for local vs hosted? | Local: no auth needed (LocalAuthProvider). Hosted: Bearer JWT via Clerk. See §1. |
| 3 | Stable endpoints for V1? | Artifacts, workflows, context modules list+detail are stable. See §10. |
| 4 | Non-artifact stack elements (model, effort)? | Not SkillMeat artifacts. CCDash should represent these as CCDash-local stack components without SkillMeat resolution. |
| 5 | Base vs override workflows? | No inheritance. Project workflows are standalone. Recommend fetching both global + project-scoped and using project version as effective when names match. See §5. |
| 6 | Stable deep-link URLs? | `/artifacts/{type:name}` and `/workflows/{uuid}` are stable. Context modules have no dedicated page — link to project memory page. See §7. |
| 7 | Write effectiveness back to SkillMeat? | Not supported in V1. Enhancement opportunity in §8f (outcome metadata on executions). |

## Staleness Warning

This audit is a snapshot of SkillMeat as of 2026-03-08 on branch `feat/aaa-rbac-foundation`. The API is at version `0.1.0-alpha`. If SkillMeat reaches `1.0.0`, re-audit the breaking changes.
