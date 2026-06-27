---
schema_version: 2
doc_type: meta_plan
title: "Pre-Commitment Exploration Workflow (/plan:explore)"
description: "New planning capability for the upstream 'should we even build this?' phase — orchestrates SPIKEs, feasibility/value investigation, and proposed ADRs into a single verdict-terminating loop that gates Tier 1/2/3 commitment."
status: draft
scope: workflow
created: 2026-05-19
updated: 2026-05-19
owner: nick
feature_slug: plan-explore-pre-commitment-exploration
affects_skills:
  - planning
  - artifact-tracking
affects_commands:
  - /plan:explore
  - /plan:plan-feature
  - /plan:spike
  - /plan:design
  - /plan:architecture-scenario-explorer
new_artifacts_introduced:
  - exploration_charter (doc_type)
  - feasibility_brief (doc_type, or report subcategory)
  - recommendation_memo (verdict section)
outcome: "A pre-commitment exploration loop terminates in one of {go, no-go, conditional} with a citable verdict and a traceable artifact chain (charter → SPIKE(s) → feasibility brief → proposed ADR → verdict). The verdict feeds `/plan:plan-feature` tier classification or archives the idea with rationale."
related_documents:
  - .claude/skills/planning/SKILL.md
  - .claude/commands/plan/plan-feature.md
  - .claude/commands/plan/spike.md
  - .claude/commands/plan/design.md
  - docs/marketing/blogs/planning-workflow-blog-brief.md
plan_ref: null
---

# Pre-Commitment Exploration Workflow (`/plan:explore`)

## 1. Motivation

CCDash has a well-developed planning surface from PRD-onwards: `/plan:plan-feature` tier-classifies, `/plan:spike` runs charter-driven research, `/plan:design` shapes design_specs, `/plan:architecture-scenario-explorer` performs structured trade-off analysis. The skill, templates, and reviewer gates all exist.

What does **not** exist is an orchestrating loop for the phase *before* tier classification — the "should we even commit to building this?" phase. Today that phase is implicit and unstructured: a user has an idea, manually decides whether to invoke `/plan:spike`, may or may not produce an ADR, may or may not capture a feasibility verdict, and eventually drifts into `/plan:plan-feature` without a citable go/no-go decision.

This meta plan introduces a new `/plan:explore` command (and supporting templates/skill content) that bundles SPIKE(s) + feasibility/value synthesis + a proposed ADR into a single verdict-terminating loop. Its sole exit is one of three outcomes:

- **go** — promote to `/plan:plan-feature` (tier classification proceeds with citations)
- **no-go** — archive the idea with documented rationale
- **conditional** — defer pending a specific named precondition

The capability is greenfield: marketplace search across "spike", "feasibility", "adr", "exploration", "discovery", "go no-go", and "pre-commitment" returned **no bundled orchestrator artifact**. Individual legs exist (`spike-writer`, ADR generators, independent-research) but no shipped artifact composes them into a verdict loop.

## 2. Gap Analysis

### What CCDash already has

| Slice | Existing artifact | Notes |
|------|-------------------|------|
| Charter-driven SPIKE | `/plan:spike` + `spike-writer` agent | Parallel investigation threads; produces design/impl-plan/open-questions outputs |
| Trade-off analysis | `/plan:architecture-scenario-explorer` | Quality-attribute matrix (performance/scalability/dev/ops) |
| Design ideation | `/plan:design` + design_spec template (maturity: idea→shaping→ready→promoted) | Single-spec scoped |
| Deep thinking | `/plan:ultra_think` | Open-ended reasoning mode |
| Full planning | `/plan:plan-feature` | Tier-classifies; assumes commitment |
| ADR drafting | `create-adr` command (collection) | Standalone, no upstream investigation link |

### What is missing

1. **Triage gate** — no command answers "does this idea even warrant a SPIKE, or is it a Tier 1 contract straight away?" before charter creation.
2. **Multi-leg parallel investigation** — `/plan:spike` runs one charter at a time; the upstream phase often needs *parallel* legs (technical feasibility, user value, risk, comparable prior art) feeding a single verdict.
3. **Value/desirability axis** — every existing planning artifact is engineering-feasibility-shaped. Desirability ("should we want this?") research is absent from the planning loop.
4. **Verdict/recommendation memo** — no template produces a structured go/no-go memo with cost, value, confidence, deal-killers, and recommended next action as first-class fields. Closest analog is `roadmap-backcast`'s feasibility section in the SkillMeat collection.
5. **Bundled orchestration** — no command runs `triage → charter → SPIKE(s) → feasibility synth → proposed ADR → verdict` as one loop. Each step is manual today.
6. **Verdict-as-frontmatter** — design_spec `maturity` field tracks ideation progress, but there is no machine-readable `verdict: go | no-go | conditional` field that downstream tooling can gate on.

### What we will **not** rebuild

- ADR generation — reuse the existing `create-adr` command and MADR-compatible format. The marketplace has 8+ near-identical ADR generators; do not add to the sprawl.
- SPIKE execution — `/plan:spike` already covers this; `/plan:explore` calls into it for each investigation leg.
- Design_spec authoring — `/plan:design` already covers this; `/plan:explore` can produce a design_spec as a side-effect when the verdict is `conditional` (capturing the next-step shape).
- Trade-off analysis — `/plan:architecture-scenario-explorer` is the canonical surface; the synthesis phase may call into it.

## 3. Design

### 3.1 Command shape — `/plan:explore`

**Argument hint**: `[idea-description-or-file] [--timebox=N] [--legs=technical,value,risk,priorart] [--charter=path]`

**Output**: a Bundle of artifacts living under `docs/project_plans/exploration/[idea-slug]/`:

```
docs/project_plans/exploration/[idea-slug]/
├── [idea-slug]-charter.md             # exploration_charter
├── spikes/                             # SPIKE outputs (delegated to /plan:spike)
│   └── ...
├── [idea-slug]-feasibility-brief.md    # feasibility_brief with verdict
└── [idea-slug]-proposed-adr.md         # ADR, status: proposed (only if architectural)
```

### 3.2 Phase flow

```
Phase 0: Triage              (Opus, ~3K tokens)
  ↓
Phase 1: Charter             (delegated to charter-writer / spike-writer in scoping mode)
  ↓
Phase 2: Parallel legs       (delegated; 1–4 SPIKEs in parallel)
  ├── Technical feasibility   → spike-writer / research-technical-spike
  ├── Value / desirability    → ux-researcher / search-specialist
  ├── Risk / blast radius     → backend-architect / data-layer-expert
  └── Comparable prior art    → search-specialist / docs-seeker
  ↓
Phase 3: Synthesis           (delegated to documentation-writer / spike-writer)
  → feasibility_brief
  → proposed ADR (if a decision is forced)
  ↓
Phase 4: Verdict             (Opus + user sign-off)
  → go | no-go | conditional
  → handoff to /plan:plan-feature OR archive with rationale
```

**Token budget target**: ~30–60K tokens end-to-end for a typical exploration. Each parallel leg target ~10K tokens; synthesis ~5K; verdict ~3K.

### 3.3 New artifact contracts

#### 3.3.1 `exploration_charter`

Lightweight predecessor to the existing SPIKE charter. Defines the exploration's *boundary conditions* so it cannot drift.

```yaml
---
schema_version: 2
doc_type: exploration_charter
title: "[Idea name] — Exploration Charter"
status: draft | in-progress | concluded
created: YYYY-MM-DD
feature_slug: kebab-slug
timebox_days: 3                     # mandatory; hard cutoff
hypothesis: "We believe X is worth building because Y."
deal_killer: "If Z is true, abandon."  # mandatory single-line
investigation_legs:                  # 1–4 legs
  - id: tech
    question: "Is X technically feasible inside the existing layered architecture?"
    assigned_to: spike-writer
  - id: value
    question: "Do users currently work around the absence of X?"
    assigned_to: ux-researcher
verdict_criteria:                    # exit gates
  go:
    - "All legs report confidence >= 0.7"
    - "No deal-killer triggered"
  no_go:
    - "Deal-killer triggered"
    - "Technical leg reports infeasibility with confidence >= 0.8"
  conditional:
    - "Open question(s) remain that can be resolved by a specific subsequent investigation"
verdict: null                        # populated at conclusion
verdict_rationale: null              # populated at conclusion
output_artifacts: []                 # populated as legs land
---
```

#### 3.3.2 `feasibility_brief`

Reuses the existing `report` doc_type with `report_category: feasibility` rather than introducing a new doc_type. This keeps the report taxonomy coherent and avoids schema sprawl. Stored at `docs/project_plans/reports/feasibility/[idea-slug]-feasibility-brief.md`.

Required sections:

1. **Synopsis** — one-paragraph idea statement
2. **Investigation summary** — table of legs with confidence, findings link, and conclusion
3. **Cost estimate** — story-point rough order, anchored to a comparable past feature (H5 from `estimation-heuristics.md`)
4. **Value statement** — who benefits, evidence (logs, requests, complaints), and counterfactual ("what happens if we don't build this?")
5. **Risks & blast radius** — technical, operational, organizational
6. **Architectural implications** — links to proposed ADR if one was drafted
7. **Verdict** — `go | no-go | conditional` with rationale and recommended next action
8. **Citations** — back-links to SPIKE outputs, charter, and any web sources

Frontmatter must include:

```yaml
verdict: go | no-go | conditional
verdict_confidence: 0.0–1.0
exploration_charter_ref: path
proposed_adr_ref: path | null
recommended_next_action: "/plan:plan-feature --tier=2" | "archive" | "defer-until: [condition]"
```

#### 3.3.3 Proposed ADR

When the exploration surfaces a decision that should be captured *during* deliberation (per MADR 4.0 guidance — write ADRs as `proposed`, not after the fact), the synthesis phase drafts an ADR via the existing `create-adr` command with `status: proposed` and a reference back to the feasibility brief. The verdict phase may upgrade it to `accepted` (if go) or `rejected` (if no-go).

### 3.4 Skill placement decision

**Recommendation**: extend the existing `planning` skill with a new workflow rather than creating a sibling skill.

**Rationale**:
- The planning skill is already the named owner of tier classification, design_spec maturity, and the SPIKE workflow. Exploration is the upstream slice of the same lifecycle.
- A sibling skill would force loaders to disambiguate which planning skill applies — adds cognitive overhead.
- Adding a new "Workflow: Pre-Commitment Exploration" section (parallel to "Workflow 1: Create PRD" and "Workflow: Tier 1 Feature Contract") keeps the discovery → planning → execution lifecycle in one document.

**What this means concretely**:
- Add a new top-level workflow section to `.claude/skills/planning/SKILL.md`
- Add `templates/exploration-charter-template.md` and update `feasibility-brief` guidance (under the `report` template umbrella with category-specific notes)
- Update the Tier Matrix table to clarify that `/plan:explore` is the upstream gate for Tier 2/3, optional for Tier 1, and skipped for Tier 0
- Add a "Pre-Commitment Exploration" entry to the Lifecycle Guidance section

**Alternative considered**: a new `planning-exploration` skill. Rejected because the artifacts (PRD, design_spec, feasibility_brief, ADR) form a single connected graph; splitting the skill would force cross-skill linkage policy.

### 3.5 Integration with existing commands

| Existing command | Change |
|------------------|--------|
| `/plan:plan-feature` | Add a Phase 0 check: if `feature_slug` matches an exploration_charter with `verdict: go`, auto-import the feasibility brief reference into the new PRD's `related_documents`. If no such charter exists and the request appears speculative, suggest `/plan:explore` first. |
| `/plan:spike` | Add an opt-in flag `--leg-of=[exploration-charter-path]` so `/plan:explore` can call into it for each leg with shared context. Today's invocation continues to work standalone. |
| `/plan:design` | When run on an idea that has no exploration charter, prompt "should this be an exploration first?" — non-blocking suggestion. |
| `/plan:architecture-scenario-explorer` | No change; `/plan:explore` synthesis phase may call into it. |
| `/dev:*` | No change. Exploration terminates upstream of execution. |

### 3.6 Anti-pattern guards (encoded in the command)

Each guard is enforced by a check in the command body or in the charter frontmatter validator:

| Anti-pattern | Guard |
|--------------|-------|
| Endless investigation | `timebox_days` in charter frontmatter is mandatory; default 3, hard max 7. Phase 2 must produce *something* at cutoff (partial findings + pivot is acceptable; silence is not). |
| Premature PRD | `/plan:plan-feature` Phase 0 check (see above) surfaces the missing charter for speculative ideas. |
| Exploration without verdict | `verdict` frontmatter field is mandatory in the feasibility brief; status `concluded` cannot be set without it. |
| Siloed investigation | Phase 2 legs are spawned in parallel by default. Sequential is opt-in via `--sequential` flag. |
| ADR after commitment | ADRs drafted during exploration carry `status: proposed`. Acceptance happens in the verdict phase, not implementation. |
| Missing deal-killer | `deal_killer` field in charter frontmatter is mandatory. Validator refuses to scaffold a charter without one. |
| Verdict-as-prose | `verdict` and `verdict_confidence` are structured frontmatter fields, not body sections. Tooling can read them. |

## 4. Borrowed Patterns

From SkillMeat collection research (`independent-research`, `roadmap-backcast`, `spike-writer`, `architecture-scenario-explorer`):

- **Charter-driven research** (from `spike-writer`) — every leg gets a question, an assigned agent, and an expected output location. Already canonical in CCDash via `/plan:spike`.
- **Parallel-fanout verification** (from `independent-research`) — spawn multiple WebSearch / research subagents *before* deciding. Encoded in Phase 2.
- **Quality-attribute trade-off matrix** (from `architecture-scenario-explorer`) — performance/scalability/dev/ops categorization as a structured artifact. Used in the synthesis phase when the exploration is architectural.
- **Backcast + feasibility check** (from `roadmap-backcast`) — combines target-outcome framing with risk/buffer analysis. Used in the value-leg template.

From web research (Cagan/Patton dual-track, MADR 4.0, SAFe SPIKE, BreezeDocs go/no-go, Stripe RFC pattern):

- **Hypothesis-first** — charter records the explicit hypothesis before exploration starts.
- **Time-boxed sprints** — mandatory `timebox_days` field.
- **ADRs as thinking tools** — drafted during exploration with `status: proposed`, not after the fact.
- **Three-verdict gate** — `go | no-go | conditional`. No "needs more time" without a named precondition.
- **Stakeholder sign-off** — verdict requires user confirmation in Phase 4; agent recommendation is not the verdict.

## 5. Implementation Plan

Phased rollout, each phase a small standalone change.

### Phase 1 — Templates & Schema (1 pt)

- Add `templates/exploration-charter-template.md` under `.claude/skills/planning/templates/`
- Add `templates/feasibility-brief-template.md` (or extend report template guidance with feasibility section)
- Update `.claude/specs/artifact-structures/` with `exploration_charter` schema and feasibility_brief frontmatter additions

**Deliverable**: templates exist; no command yet.

### Phase 2 — Skill Workflow (2 pts)

- Add "Workflow: Pre-Commitment Exploration" section to `.claude/skills/planning/SKILL.md`
- Update Tier Matrix and Lifecycle Guidance sections
- Add `references/exploration-legs-catalog.md` describing the canonical leg types (technical, value, risk, prior-art) with agent assignments

**Deliverable**: skill knows the workflow; can be invoked manually.

### Phase 3 — Command (2 pts)

- Add `.claude/commands/plan/explore.md` following the pattern of `/plan:spike` and `/plan:plan-feature`
- Add `--leg-of` flag handling to `/plan:spike` for sub-invocation
- Add Phase 0 charter-check to `/plan:plan-feature`

**Deliverable**: `/plan:explore` works end-to-end on a small test idea.

### Phase 4 — CLI / Tooling Glue (1 pt)

- Add `manage-exploration-status.py` script (mirrors `manage-plan-status.py`) to advance `status: draft → in-progress → concluded` and set `verdict`
- Add validator that refuses to set `status: concluded` without a populated `verdict`

**Deliverable**: scriptable status transitions; verdict invariant enforced.

### Phase 5 — Marketing / Communication (2 pts)

- Author `docs/marketing/blogs/planning-workflow-blog-brief.md` (see §7)
- Capture a real exploration as a worked example for the blog post

**Deliverable**: blog post / slide deck draft ready for polish.

### Phase 6 — Dogfooding & Retro (1 pt)

- Run `/plan:explore` on the next 2 speculative ideas before committing them to `/plan:plan-feature`
- Capture friction in a post-mortem report under `docs/project_plans/reports/post-mortems/`
- Adjust templates / command based on actual usage

**Deliverable**: validated workflow; documented adjustments.

**Total estimate**: ~9 points. This is itself a Tier 2 effort, but the artifact is a meta plan, not a PRD — execution is incremental and reversible per phase.

## 6. Open Questions

- **OQ-1** — Should `feasibility_brief` be a distinct `doc_type`, or a `report` with `report_category: feasibility`? *Tentative: reuse `report` to avoid schema sprawl.*
- **OQ-2** — When the verdict is `conditional`, what is the canonical artifact for the precondition? A new exploration charter? A SPIKE charter? A backlog item? *Tentative: explicit `recommended_next_action` field naming the next command (`/plan:explore` / `/plan:spike` / archive).*
- **OQ-3** — Should `/plan:explore` be a hard prerequisite for Tier 3, or a strong suggestion? Tier 3 already routes through SPIKE-first. *Tentative: strong suggestion for Tier 3; required only when `risk_level: high` or the idea has no comparable past feature anchor.*
- **OQ-4** — Where do verdicts get tracked across the project? Is there a `docs/project_plans/exploration/INDEX.md` or do we rely on grep against frontmatter? *Tentative: rely on `plan-status-report.py` to surface explorations alongside PRDs/plans.*
- **OQ-5** — Should the verdict require human sign-off or can Opus close it on its own when confidence is high? *Tentative: human sign-off required for `go` and `no-go`; `conditional` may auto-close if the precondition is concrete and time-bound.*
- **OQ-6** — How do we surface "ideas in exploration" so they don't get rediscovered? Likely a tracker entry plus an entry in `meatycapture` request-logs. *Tentative: `/plan:explore` creates a `meatycapture` entry automatically with type=exploration.*

## 7. Marketing / Communication Deliverable

The user requested a blog post / slide deck draft documenting the full CCDash planning workflow with this new exploration phase as the lead narrative beat.

**Location**: `docs/marketing/blogs/planning-workflow-blog-brief.md`

**Audience**: developer-tools-curious engineers and engineering leaders evaluating agentic SDLC tooling.

**Narrative arc**:

1. **The problem** — most AI agent workflows skip from "idea" to "code" with no exploration or verdict step. Speculative ideas burn budget; abandoned features leave no trail.
2. **The tier model** — Tier 0 → 3 with effort-appropriate artifacts (none → contract → PRD+plan → SPIKE+PRD+plan). Show the actual table.
3. **The missing upstream slice** — pre-commitment exploration as a first-class loop. SPIKE(s) + feasibility brief + proposed ADR + verdict.
4. **Anti-patterns this prevents** — endless investigation, premature PRD, ADR-after-the-fact, verdict-as-vibes.
5. **Worked example** — a real CCDash exploration that ran in 3 days and produced a verdict (go to Tier 2, no-go with archive, or conditional with named precondition).
6. **Why this matters for agentic SDLC** — verdicts are machine-readable, artifacts are linked, exploration is auditable. The exploration phase becomes a *deliverable*, not a vibe.

**Slide deck variant** — same arc, 10–14 slides, one diagram per slide:

- Slide 1: title
- Slide 2: the problem (one-pager from §1 of this doc)
- Slide 3–4: the tier model (visual table; one example feature per tier)
- Slide 5–7: the exploration loop (phase diagram, artifact chain, frontmatter snippet)
- Slide 8: anti-patterns table
- Slide 9–11: worked example (charter, feasibility brief, verdict)
- Slide 12: tooling integration (`/plan:explore` invocation; how it links to `/plan:plan-feature`)
- Slide 13: results / outcomes
- Slide 14: open questions and what's next

A content brief lives at the path above (created in Phase 5) with the outline expanded, a list of diagrams to commission, and links to candidate worked-example explorations.

## 8. Risks

- **Risk: command sprawl** — `/plan:explore` becomes the eighth command in `/plan:*`. Mitigation: extending the existing planning skill (not creating a new one) keeps the conceptual surface flat.
- **Risk: charter becomes ceremony** — the timebox + deal-killer fields are intended as forcing functions, not paperwork. Mitigation: keep the charter under 60 lines; templates ship with sensible defaults; `/plan:explore` can scaffold most fields from the idea description.
- **Risk: verdict gating slows simple ideas** — for Tier 0/1 cases, exploration is overkill. Mitigation: `/plan:plan-feature` should *suggest* `/plan:explore` only for genuinely speculative cases (no comparable past feature, no clear deal-killer obvious from the request, high risk_level).
- **Risk: ADR-as-proposed clutters the ADR space** — drafting ADRs that get rejected at the verdict phase produces noise. Mitigation: only draft a proposed ADR when the synthesis phase identifies an architectural decision that *will* exist regardless of verdict direction (only the choice changes). Otherwise the feasibility brief captures the reasoning without ADR commitment.
- **Risk: duplication with `/plan:spike` and `/plan:design`** — exploration is one level up but could feel redundant. Mitigation: the relationship is composition, not replacement. `/plan:explore` calls `/plan:spike` for each leg; `/plan:design` is the surface for the *output* of a `conditional` verdict.

## 9. Success Criteria

- Three real explorations conclude with verdicts of distinct types (one `go`, one `no-go`, one `conditional`).
- At least one `go` verdict flows cleanly into `/plan:plan-feature` and references the feasibility brief in the resulting PRD's `related_documents`.
- At least one `no-go` verdict produces an archived charter that is later cited when a similar idea resurfaces (no re-exploration of settled ground).
- The blog post / slide deck draft is published or queued for review with a worked example.
- No new schema field is added to `prd` or `implementation_plan` frontmatter (exploration is upstream-only).
- Token budget for a typical exploration stays under 60K end-to-end.

## 10. Cross-References

- `.claude/skills/planning/SKILL.md` — primary integration point
- `.claude/skills/planning/templates/feature-contract-template.md` — parallel structure reference
- `.claude/commands/plan/spike.md` — leg-execution surface
- `.claude/commands/plan/plan-feature.md` — downstream consumer of `go` verdicts
- `.claude/specs/artifact-structures/human-brief-spec.md` — parallel structure for new artifact spec
- `docs/marketing/blogs/planning-workflow-blog-brief.md` — companion content brief
- Web sources: MADR 4.0 (2024), Cagan dual-track agile, SAFe SPIKEs, BreezeDocs go/no-go template, Pragmatic Engineer RFC patterns
- SkillMeat collection precedents: `spike-writer`, `independent-research`, `roadmap-backcast`, `architecture-scenario-explorer`, `create-adr`
