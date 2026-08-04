---
schema_version: 2
doc_type: feature_contract
title: "Expose skill_name_source Provenance End-to-End"
description: "Surface the schema-v49 skill_name_source column through AgentSession, the API, types.ts, and a badge affordance so the FE can distinguish inherited vs observed skill attribution."
status: completed
tier: 1
estimated_points: 3
created: 2026-08-04
updated: 2026-08-04
feature_slug: expose-skill-name-source-provenance
category: enhancements
prd_ref: null
plan_ref: null
related_documents:
  - backend/parsers/skill_provenance.py
  - backend/parsers/effort_provenance.py
changelog_required: false
contributors: [claude]
commit_refs: ["ad7c70c"]
pr_refs: []
files_affected:
  - backend/models.py
  - backend/routers/api.py
  - types.ts
  - components/SessionInspector.tsx
---

```json autopilot-graph
{
  "tier": 1,
  "effort_points": 3,
  "wave_count": 1,
  "phase_count": 1,
  "file_count": 4,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/feature_contracts/enhancements/expose-skill-name-source-provenance.md",
  "execution_target": "execute-contract",
  "slug": "expose-skill-name-source-provenance",
  "category": "enhancements",
  "review_intensity": "standard",
  "files_affected": [
    "backend/models.py",
    "backend/routers/api.py",
    "types.ts",
    "components/SessionInspector.tsx"
  ],
  "escalation_recommendation": "If TranscriptView.tsx is later found to render a session-level skillName badge (it currently only renders per-message skill-mention tokens, a distinct feature), re-scope as a follow-on Tier 0 quick-feature rather than reopening this contract.",
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Expose skill_name_source end-to-end + badge affordance",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-1.1",
                "prompt": "Mode C: Autonomous Feature Sprint. Read backend/parsers/skill_provenance.py first to confirm the canonical vocabulary (tokens: `directly_detected`, `inherited_parent`; both live in SKILL_SOURCE_TRUST_ORDER / KNOWN_SKILL_SOURCES). Then: (1) In backend/models.py AgentSession class, add `skillNameSource: Optional[str] = None` immediately after the existing `skillName: Optional[str] = None` field (~line 275), with a short comment mirroring the effortTierSource comment block above it (mention schema v49, one-hop subagent skill inheritance, null == unknown/predates column, cite backend/parsers/skill_provenance.py for vocabulary). (2) In backend/routers/api.py, find BOTH AgentSession/serialization construction sites that currently set `effortTierSource=s.get(\"effort_tier_source\")` (around lines ~899 and ~1321 — these are exact precedent, same pattern). At each site, add a new line `skillNameSource=s.get(\"skill_name_source\"),` immediately after the existing `skillName=s.get(\"skill_name\")` line (or immediately adjacent to the effortTierSource line if skillName isn't set at that exact site — grep to confirm the exact local variable name used at each site, it may be `s.get(...)` on a dict or an ORM row attribute; match whatever pattern the surrounding lines use). Do not touch unrelated fields. (3) In types.ts, add `skillNameSource?: string | null;` to the AgentSession interface immediately after the `skillName?: string | null;` field (~line 581), with a comment block mirroring the effortTierSource comment above it: canonical vocabulary `directly_detected` (session's own transcript produced a skill detection) vs `inherited_parent` (copied one hop from parent's skillName because own value was null); null == unknown (row predates the column, or skillName itself is null); treat any unrecognised token as unknown, never hard-fail. (4) In components/SessionInspector.tsx at the skillName badge block (~line 5415-5422), when `session.skillNameSource === 'inherited_parent'` render the badge with an inherited visual affordance — prefix the label with '↳ ' and change the tooltip title to `Skill: ${session.skillName} (inherited from parent)`; otherwise (directly_detected, unrecognised token, or null/absent) render exactly the current badge unchanged — no prefix, current title `Skill: ${session.skillName}`. This must be a pure additive conditional; the `session.skillName ? (...) : null` outer guard stays exactly as-is so a missing/null skillName still renders nothing (resilience-by-default — never a crash or placeholder). Also grep components/SessionInspector/TranscriptView.tsx for any session-level `skillName` badge render (not the per-message skill-mention token matches at lines ~828-844, which are a different feature) — if none exists (expected, per current exploration), do not add one; note this in your completion summary. After edits: run `npx tsc --noEmit` scoped to touched files if feasible, and start the dev server (`npm run dev`) to browser-smoke a session with a skillName badge, confirming the plain-badge path renders unchanged. If no session with skillNameSource='inherited_parent' exists in local data, it is acceptable to verify by temporarily reading the DB (`sessions.skill_name_source`) for a real inherited row, or by trusting careful code review of the conditional plus the mock/unit coverage; state which verification method you used in your Completion Report. Do NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 3,
                "files_affected": [
                  "backend/models.py",
                  "backend/routers/api.py",
                  "types.ts",
                  "components/SessionInspector.tsx"
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

## Goal

Make the schema-v49 `sessions.skill_name_source` provenance column visible end-to-end (backend
model → API serialization → FE type → badge affordance) so the FE can visually distinguish a
one-hop-inherited skill attribution from a directly-observed one. The DB column and its writer
already ship; this contract closes the read-path gap only.

## User / Actor

An engineer or agent-ops reviewer inspecting a subagent session in SessionInspector, trying to
judge whether the displayed skill name reflects that subagent's own detected work or was merely
copied from its parent.

## Job To Be Done

When viewing a session's skillName badge, immediately tell whether the value is `directly_detected`
(trust it as this session's own signal) or `inherited_parent` (treat as a weaker, derived signal)
without needing to cross-reference the DB.

## Scope

**In scope:**
- `backend/models.py`: add `skillNameSource: Optional[str] = None` to `AgentSession`
- `backend/routers/api.py`: populate `skillNameSource` from `skill_name_source` at both existing
  `effortTierSource` serialization sites (~899, ~1321)
- `types.ts`: add `skillNameSource?: string | null;` to the `AgentSession` interface, documented
  with the canonical vocabulary
- `components/SessionInspector.tsx`: add an inherited-provenance visual affordance (↳ prefix +
  updated tooltip) to the existing session-level skillName badge (~line 5415), conditioned on
  `skillNameSource === 'inherited_parent'`

**Out of scope:**
- Any DB migration (column already shipped in schema v49)
- Any change to the parser/writer that populates `skill_name_source` (already correct)
- `components/SessionInspector/TranscriptView.tsx` — confirmed during exploration to have no
  session-level skillName badge (its `skillName` matches at ~828-844 are per-message skill-mention
  tokens, a distinct feature); no mirror change needed there unless a future audit finds otherwise
- Backfilling `skill_name_source` for pre-v49 rows (contract state: null == unknown, never guessed)
- MCP/CLI surfaces (this is a session-detail FE affordance only)

## UX / Behavior Requirements

- `skillNameSource === 'inherited_parent'` → badge shows `↳ <skillName>` (or equivalent visually
  distinct inherited styling) with tooltip `Skill: <skillName> (inherited from parent)`
- `skillNameSource === 'directly_detected'` → badge unchanged from current rendering
- `skillNameSource` null/absent/unrecognised token → badge unchanged from current rendering
  (treat unknown as "not inherited", never crash, never a placeholder)
- No skillName → no badge (existing behavior, unchanged)

## Data Requirements

- New optional field `skillNameSource` on `AgentSession` (backend Pydantic model, FE TS interface)
- Value sourced directly from `sessions.skill_name_source` (already exists both backends, written
  by parser); no new write path, no new migration

## API / Integration Requirements

- `AgentSession.skillNameSource` appears in both serialization sites already producing
  `effortTierSource` in `backend/routers/api.py`, using the exact same `s.get(...)` access pattern
  local to each site

## Architecture Constraints

- Mirror the effort-tier-source precedent shape-for-shape (comment style, null-means-unknown
  contract, FE fallback pattern) — this repo has two independent provenance columns
  (`effort_tier_source`, `skill_name_source`) that intentionally do not cross-import
- Canonical vocabulary lives solely in `backend/parsers/skill_provenance.py`; do not
  redefine/duplicate the token strings elsewhere — read them, don't hardcode a third spelling

## Acceptance Criteria

#### AC-1: Backend field added and populated
- target_surfaces:
    - backend/models.py
    - backend/routers/api.py
- propagation_contract: `sessions.skill_name_source` (DB) → `AgentSession.skillNameSource` (Pydantic) at both serialization sites
- resilience: absent/null DB value → `skillNameSource: None`, never an error
- visual_evidence_required: false
- verified_by: [TASK-1.1]

#### AC-2: FE type contract documented
- target_surfaces:
    - types.ts
- propagation_contract: `AgentSession.skillNameSource?: string | null` mirrors backend field name/nullability; comment documents `directly_detected` / `inherited_parent` vocabulary and null-is-unknown contract
- resilience: field absent from a payload → TS optional field, no runtime error
- visual_evidence_required: false
- verified_by: [TASK-1.1]

#### AC-3: Inherited-provenance badge affordance in SessionInspector
- target_surfaces:
    - components/SessionInspector.tsx
- propagation_contract: `session.skillNameSource === 'inherited_parent'` drives a visually distinct badge variant (↳ prefix + updated tooltip) on the existing skillName badge (~line 5415)
- resilience: any other value (`directly_detected`, null, absent, unrecognised token) renders the badge exactly as it does today; missing `skillName` still renders no badge at all
- visual_evidence_required: "browser smoke: session list showing at least one skillName badge, confirming the non-inherited path is visually unchanged; if a real inherited-parent row is available locally, confirm the ↳ affordance renders"
- verified_by: [TASK-1.1]

#### AC-4: No TranscriptView mirror needed (confirmed, not assumed)
- target_surfaces:
    - components/SessionInspector/TranscriptView.tsx
- propagation_contract: N/A — exploration confirmed no session-level skillName badge exists in this file
- resilience: N/A
- visual_evidence_required: false
- verified_by: [TASK-1.1]

## Risk Areas

- **Low risk, single-wave change.** The only real risk is drift between the two `api.py`
  serialization sites (one could be edited, the other missed) — TASK-1.1 explicitly calls out
  both line numbers as precedent-verified sites.
- Badge-styling regression risk is low; the conditional is purely additive and the outer
  `session.skillName ? (...) : null` guard is preserved untouched.

## Validation Requirements

- `npx tsc --noEmit` (or scoped equivalent) on touched TS/TSX files
- Browser smoke of SessionInspector session badge row (dev server), per Runtime smoke gate in
  root CLAUDE.md — required because this touches a `*.tsx` file and adds a new optional backend
  field (R-P2/R-P4 discipline)
- Confirm both `api.py` serialization sites were edited (grep for `skillNameSource=` should return
  2 hits)

## Completion Report Required

Yes — standard Tier 1 Completion Report per `.claude/skills/dev-execution/validation/completion-criteria.md`,
including which method was used to verify the inherited-badge path (real DB row vs. code review)
given inherited-provenance rows may be sparse in local dev data.
