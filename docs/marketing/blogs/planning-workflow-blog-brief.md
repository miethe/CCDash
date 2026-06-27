---
schema_version: 2
doc_type: content_brief
title: "The CCDash Planning Workflow — Tiers, SPIKEs, and the Missing Upstream Phase"
description: "Content brief for a long-form blog post and companion slide deck on the CCDash planning workflow, with the new pre-commitment exploration loop (/plan:explore) as the lead narrative beat."
status: draft
created: 2026-05-19
updated: 2026-05-19
owner: nick
audience:
  - developer-tools-curious engineers
  - engineering leaders evaluating agentic SDLC tooling
  - teams adopting Claude Code / SkillMeat-style artifact systems
formats:
  - long-form blog post (~2500 words)
  - companion slide deck (10–14 slides)
related_documents:
  - .claude/plans/plan-explore-pre-commitment-exploration-v1.md
  - .claude/skills/planning/SKILL.md
  - .claude/commands/plan/plan-feature.md
  - .claude/commands/plan/spike.md
status_notes: "Brief is the input to the eventual blog draft; actual prose lives in a sibling file once written."
---

# Content Brief: The CCDash Planning Workflow

## Working titles

- **"From 'Idea' to 'Done' Should Have More Than One Decision Point"** *(preferred for blog)*
- "Tiered Planning for AI-Agent SDLC: Why Most Workflows Skip the Hardest Step"
- "Make Your AI Agents Prove Their Ideas Before They Build Them"
- "The Verdict Step: Pre-Commitment Exploration in an Agentic Codebase"

## Core thesis

Most AI-agent coding workflows compress the SDLC into two steps: "idea" → "code". The middle — *exploration, feasibility, decision* — is collapsed into an invisible vibe-check that the model performs implicitly. CCDash's planning workflow makes that middle visible: a tier-classified planning surface (Tier 0 → 3) sitting downstream of an explicit pre-commitment exploration loop that terminates in a machine-readable verdict.

The result: ideas that should not become features get archived with a citable rationale; ideas that should become features arrive at the PRD stage with their feasibility, value, and architectural assumptions already documented and linked.

## Audience & motivation

- **Engineers** building with Claude Code, OpenAI agents, or similar tooling who feel the cost of "agent built the wrong thing fast."
- **Engineering leaders** evaluating agentic SDLC platforms who want to understand what governance looks like in practice.
- **Teams adopting SkillMeat-style artifact systems** who need a worked example of an end-to-end planning lifecycle.

What the reader gets:
- A mental model (Tier 0 → 3) they can apply tomorrow
- A concrete template (exploration charter + feasibility brief + verdict) they can copy
- A worked example showing the full chain from idea to verdict to (committed PRD or archive)

## Narrative arc

### Act 1 — The Missing Step (≈400 words)

Open with the failure mode: AI agents that produce a 1200-line implementation plan for an idea that should have been a no-go.

- The "shipped-fast, regretted-fast" trap of agentic SDLC tooling.
- Why "the LLM will figure it out" is not a substitute for an exploration phase.
- The cost of speculative work: not just tokens, but the cognitive load of unwinding decisions encoded in 50 files.

Hook: *"The most expensive feature is the one you built before deciding whether to build it."*

### Act 2 — The Tier Model (≈500 words)

Introduce the CCDash tier matrix as the first piece of legible structure:

| Tier | Size | Planning artifact | Execution |
|------|------|-------------------|-----------|
| 0 | 1–3 pts, 1 file | none | `/dev:quick-feature` |
| 1 | 3–8 pts | Feature Contract | one autonomous sprint |
| 2 | 8–13 pts | PRD + Implementation Plan | phase-by-phase |
| 3 | 13+ pts | SPIKE + PRD + Plan | phase-by-phase + extra reviewer gates |

Key points:
- Tier classification is a routing decision, not a planning decision.
- The artifact heavyweight scales with the risk and surface area, not the user's enthusiasm.
- Tier 0 doesn't generate a doc; it just runs. That is the right answer for most "add a button" requests.

Why this matters: most tooling defaults to PRD-first regardless of scope. CCDash's tier matrix admits that a 2-point change does not deserve a 1200-line plan.

### Act 3 — The Missing Upstream Slice (≈600 words)

Introduce the new `/plan:explore` capability. This is the lead.

The phase that *every* tier model still assumes is implicit: "should we even commit to this?" The user wants something; an LLM cheerfully helps them tier-classify it; nobody asked whether it should exist.

`/plan:explore` makes the upstream phase explicit:

- **Exploration Charter** — defines hypothesis, deal-killer, timebox, and investigation legs in frontmatter.
- **Parallel legs** — technical feasibility, value/desirability, risk/blast radius, comparable prior art. Each leg is a SPIKE delegated to a specialist agent.
- **Feasibility Brief** — synthesizes legs into a structured document with a `verdict` frontmatter field.
- **Proposed ADR** — drafted *during* exploration (per MADR 4.0 guidance: ADRs as thinking tools, not commitment artifacts).
- **Verdict** — `go`, `no-go`, or `conditional`. No "needs more time" without a named precondition.

Show the actual phase diagram from the meta plan §3.2. Show the frontmatter snippet.

The forcing functions:
- Mandatory `timebox_days` field (no endless investigations)
- Mandatory `deal_killer` field (no scope creep into "maybe X")
- Mandatory `verdict` to set `status: concluded` (no exploration without a verdict)
- Mandatory citation chain back to SPIKE outputs (verdicts are auditable)

### Act 4 — Anti-Patterns This Prevents (≈300 words)

A table the reader can quote back:

| Anti-pattern | Why it happens | What `/plan:explore` does |
|--------------|----------------|---------------------------|
| Endless investigation | No timebox | `timebox_days` is mandatory frontmatter; default 3, hard max 7 |
| Premature PRD | Eager-to-please LLM | `/plan:plan-feature` Phase 0 checks for an exploration charter on speculative ideas |
| Exploration without verdict | Reports that end "needs further study" | `verdict` field is mandatory to conclude the exploration |
| Siloed investigation | One agent at a time | Phase 2 parallel legs are the default |
| ADR after commitment | Documenting sunk cost | Proposed ADRs are drafted during exploration; verdict upgrades to accepted/rejected |
| Verdict-as-vibes | Prose-only conclusions | `verdict` and `verdict_confidence` are structured frontmatter fields |

Each row is one diagram-able beat for the slide deck.

### Act 5 — Worked Example (≈500 words)

Show one real exploration end-to-end. The blog draft will use whichever real exploration ran first during dogfooding (see meta plan Phase 6). Candidates as of writing:

- (placeholder) a high-risk infrastructure change that produced a `no-go` with archive rationale
- (placeholder) a speculative UX feature that produced a `conditional` with a named precondition
- (placeholder) a clear `go` that flowed cleanly into a Tier 2 PRD

Walk through:
1. The charter (10 lines of YAML + 30 lines of body)
2. The three SPIKE outputs (linked, not quoted)
3. The feasibility brief (verdict, confidence, recommended next action)
4. The downstream artifact (the PRD that cites it, *or* the archive entry that prevents rediscovery)

The point: at no step is the user reading 1000 lines of generated content. The artifacts are short, linked, and machine-readable.

### Act 6 — Why This Matters for Agentic SDLC (≈300 words)

Close the loop:

- Verdicts are first-class data. Tooling can query "what did we decide about X?" instead of grepping commit messages.
- Exploration becomes a deliverable, not a vibe. You can point at it in retro.
- The agent's confidence is captured. When the agent was wrong, you can see *how* wrong with what confidence.
- Archived no-gos prevent re-exploration. The most valuable feature of a verdict system is preventing the same idea from cycling.
- The tier model + exploration loop is the seam that makes agentic SDLC governance plausible. Every other governance attempt boils down to "wait, slow down" — this one says "go fast, but produce the artifact that proves we should go this fast."

End with a forward-looking note: this is one piece of a broader pattern where AI-agent workflows produce *auditable* artifacts at every decision boundary. The exploration verdict is the first such boundary. There will be more.

## Diagrams to commission

Listed in narrative order. Each is one slide.

1. **Idea-to-code, with and without the exploration loop** — split-screen showing the implicit vs. explicit decision step.
2. **The tier matrix** — clean version of the table above with one example feature per tier.
3. **The exploration phase diagram** — Phase 0 → 4 from meta plan §3.2.
4. **The artifact chain** — charter → SPIKEs → feasibility brief → proposed ADR → verdict → downstream PRD.
5. **The frontmatter snippet** — exploration charter YAML with annotations pointing to each forcing function.
6. **The verdict gate** — three-arrow diagram showing go / no-go / conditional outcomes and their downstream targets.
7. **The anti-pattern table** — visual version of the table in §4.
8. **The worked example timeline** — 3-day timebox with leg activities and the verdict landing on day 3.
9. **Cost comparison** — speculative tokens-to-decision in a tier-only workflow vs. exploration-first workflow.

## Companion slide deck — 12 slides

| # | Title | Beat |
|---|-------|------|
| 1 | "From 'Idea' to 'Done' Should Have More Than One Decision Point" | Title |
| 2 | The expensive feature is the one you built before deciding to build it | Problem statement |
| 3 | The CCDash tier matrix | Routing model |
| 4 | The phase your workflow probably skips | Pre-commitment slice |
| 5 | The exploration loop | Phase diagram |
| 6 | The exploration charter | Forcing functions in YAML |
| 7 | The feasibility brief | Synthesis + verdict |
| 8 | The verdict gate | Three outcomes |
| 9 | Anti-patterns this prevents | Table |
| 10 | A real exploration, 3 days end-to-end | Worked example |
| 11 | What it looks like downstream | PRD citing the brief, or archive preventing rediscovery |
| 12 | Why this matters for agentic SDLC | Close |

Optional 13–14: deep-dive slides on `/plan:explore` invocation and SkillMeat artifact composition.

## SEO / discoverability angles

Primary keywords:
- "AI agent feasibility study"
- "go/no-go for AI development"
- "Claude Code planning workflow"
- "AI SDLC governance"
- "SPIKE methodology agentic"
- "ADR as proposed during exploration"
- "tiered planning AI agents"

Secondary:
- "dual-track agile AI"
- "MADR template agent workflow"
- "feature contract vs PRD"

The post should rank for "AI agent feasibility" and "Claude Code planning" — both currently underserved by tutorial-shaped content. Prior art tends to be either consultancy whitepapers (too abstract) or single-feature how-tos (too narrow). A worked example + a citable mental model is the gap.

## Voice and constraints

- **First-person plural is fine** ("we built CCDash" / "we observed"); avoid royal we.
- **No marketing-speak.** This audience smells it. Write the way you'd write a postmortem.
- **Quote real artifacts.** YAML frontmatter is a feature, not a wall to hide behind. Use real frontmatter from the meta plan and templates.
- **Avoid emojis** in the prose; allowed in diagrams only if they aid scanning.
- **No "10x" / "game-changer" / "revolutionary"**. The pitch is "this is the obvious next step", not "we invented planning".
- **Quote one number.** Pick one measurable claim and stand behind it — e.g., "explorations conclude in under 60K tokens" or "the verdict-to-PRD chain is one click apart". Don't list five metrics.

## Open questions for the brief

- **OQ-B1** — Where does this get published? Personal blog, project README, dev.to, hashnode, the CCDash docs site? Likely the docs site has the canonical version with cross-posts elsewhere.
- **OQ-B2** — Is the slide deck for a specific venue (conference, internal talk, recorded explainer)? Length and depth depend.
- **OQ-B3** — Who is the named author? CCDash project voice or personal byline? This affects tone.
- **OQ-B4** — Should the worked example be anonymized, or is it OK to name the actual feature?
- **OQ-B5** — Is there an accompanying short-form (Twitter/X thread, LinkedIn carousel) version? If so, the diagrams above need to be exportable individually.

## Linked artifacts (for the writer)

When the blog draft is written, the writer should have these tabs open:

- `.claude/plans/plan-explore-pre-commitment-exploration-v1.md` — the meta plan; primary source of truth
- `.claude/skills/planning/SKILL.md` — tier matrix, lifecycle guidance, frontmatter rules
- `.claude/commands/plan/plan-feature.md` — current tier-classification flow
- `.claude/commands/plan/spike.md` — the leg-execution surface
- `.claude/skills/planning/references/estimation-heuristics.md` — for the cost-estimate beat
- Sample real PRDs from `docs/project_plans/PRDs/` — for the "downstream artifact" example
- Sample real implementation plans from `docs/project_plans/implementation_plans/` — to show the contrast in heaviness

## Next actions

1. Wait for at least one real `/plan:explore` run to land (meta plan Phase 6) before drafting the worked-example section.
2. Commission diagrams 1–4 first (the conceptual ones). Diagrams 5–9 can wait for the worked example.
3. Draft Acts 1–4 in parallel with the dogfooding; they don't depend on the worked example.
4. Resolve OQ-B1 through OQ-B5 before drafting Acts 5–6.
