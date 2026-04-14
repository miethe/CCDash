---
title: "Bob Shell Delegation Skill - Technical Specification"
type: "specification"
status: "draft"
created: "2026-04-11"
updated: "2026-04-11"
version: "1.0"
authors: ["Codex"]
tags: ["skill", "bob", "shell", "delegation", "agent", "cli"]
---

# Bob Shell Delegation Skill - Technical Specification

## Executive Summary

This document specifies a new Codex skill for delegating selected work to IBM Bob through Bob Shell from the command line.

The intent is not "use Bob for everything." The skill should help Codex decide when Bob is a good teammate, prepare a high-quality bounded prompt, run Bob through its shell interface, and integrate the result back into the main workflow.

The design must incorporate two inputs:

1. Official Bob Shell documentation, especially its positioning around interactive vs non-interactive use, specialized modes, automation support, MCP support, custom modes, slash commands, and sandboxing.
2. Our direct experience reviewing Bob's Phase 1 implementation on `ccdash-cli-mcp-enablement`, where Bob showed strong throughput and packaging ability but missed the real integration boundary and created tests around invented interfaces.

That second input is important. The skill should encode not only how to invoke Bob, but how to use Bob well.

## Problem Statement

We now have access to Bob as an additional agentic teammate with a favorable cost profile. That makes Bob valuable, but only if Codex can use Bob deliberately.

Right now there is no shared skill that tells Codex:

- when Bob is a good fit,
- when Bob is a poor fit,
- how to invoke Bob safely from the shell,
- how to structure prompts so Bob succeeds on bounded work,
- how to validate Bob outputs before trusting them,
- how to recover cleanly when Bob is unavailable locally.

Without that guidance, Bob is likely to be overused on the wrong problems or underconstrained on tasks where interface discipline matters.

## Goals

- Create a reusable skill that lets Codex use Bob via CLI for appropriate subtasks.
- Encode a clear Bob selection policy based on our observed strengths and weaknesses.
- Prefer bounded delegation patterns over open-ended "implement the whole feature" requests.
- Support both exploratory interactive use and automation-oriented non-interactive use where appropriate.
- Make the skill resilient when Bob Shell is not installed locally.
- Keep the resulting skill lean, practical, and focused on execution quality.

## Non-Goals

- Recreate Bob Shell documentation inside the skill.
- Treat Bob as a default replacement for Codex or existing normal agents.
- Build a full Bob integration platform or daemon in this first pass.
- Promise support for Bob features that cannot be validated from docs or local environment.

## Source Inputs

### Official Bob Shell docs

Primary source:

- [Bob Shell docs](https://bob.ibm.com/docs/shell)

Key points visible in the docs:

- Bob Shell supports both interactive sessions and non-interactive sessions for automation.
- Bob Shell offers specialized modes including code, ask, plan, and advanced.
- Bob Shell exposes shell-oriented tools, process execution, and MCP integration.
- Bob Shell supports custom modes and slash commands.
- Bob Shell documents sandboxing and trusted-folder concepts for safer operation.

The skill implementation should treat the docs as the authoritative source for CLI behavior and invocation patterns. During actual implementation, Skill_Seekers should load the official docs pages needed for:

- install/setup,
- interactive session startup,
- non-interactive session startup,
- usage examples,
- custom modes,
- slash commands,
- sandboxing/security.

### Local environment reality

At spec time, `bob` is not installed in the current workspace environment:

```bash
which bob
# bob not found
```

That means the skill must include environment detection and graceful fallback behavior instead of assuming Bob Shell is available.

### Observed Bob strengths from this project

Based on the Phase 1 review, Bob appears strong at:

- rapidly generating a large volume of code and docs,
- packaging work into coherent deliverables,
- scaffolding DTOs, tests, and README-heavy outputs,
- executing bounded tasks with clear local expectations,
- producing candidate implementations quickly enough to make cheap parallel exploration worthwhile.

### Observed Bob weaknesses from this project

Based on the same review, Bob appears weak or unreliable at:

- respecting existing repository and port contracts unless explicitly forced,
- distinguishing mocked test seams from real runtime seams,
- building new cross-layer integrations without contract verification,
- recognizing when a passing test suite is validating the wrong abstraction,
- making autonomous architecture decisions in critical-path backend code.

This should directly shape the skill's usage policy.

## Proposed Skill

### Proposed name

`bob-shell-delegate`

Rationale:

- short and triggerable,
- action-oriented,
- clearly distinguishes "delegate to Bob through shell" from Bob IDE or broader Bob platform topics.

### Proposed purpose

Provide a disciplined workflow for invoking IBM Bob through Bob Shell for bounded subtasks, using official Bob docs as the source of truth for CLI usage and enforcing task-selection guardrails based on our direct experience with Bob.

### Triggering intent

The skill should trigger when the user wants to:

- use Bob or IBM Bob from Codex,
- delegate a task to Bob through CLI,
- compare Codex work with Bob work,
- run a bounded experiment with Bob,
- draft or scaffold work cheaply with Bob,
- use Bob for documentation or boilerplate generation,
- use Bob for a sidecar subtask while Codex handles integration.

The skill description should also say when not to use it:

- do not use as the default path for architecture-heavy or integration-critical work,
- do not use for cross-layer backend changes unless the prompt explicitly requires contract verification against real interfaces.

## Skill Philosophy

The skill should frame Bob as a fast secondary engineer, not an autonomous senior engineer.

Operational posture:

- Use Bob for speed where correctness can be cheaply verified.
- Constrain Bob tightly when the task touches integration seams.
- Never trust mocked success if the task is really about real adapters or contracts.
- Treat Bob output as candidate work until validated.

This skill should bias toward "parallel sidecar teammate" more than "owner of the critical path."

## Recommended Bob Use Cases

The skill should explicitly recommend Bob for:

- drafting documentation,
- generating boilerplate,
- writing candidate DTOs or serializers,
- creating first-pass tests after the real contract is already known,
- drafting migration notes, reports, and summaries,
- exploring multiple wording or implementation variants,
- bounded refactors in isolated files,
- non-critical research or inventory tasks where Codex will validate results.

## Discouraged Bob Use Cases

The skill should explicitly discourage Bob for:

- defining new storage or repository boundaries,
- integration-heavy backend work across ports, repositories, routers, and services,
- "build Phase X end-to-end" tasks without strict scope,
- changes where passing tests can be achieved with mocks that bypass the real seam,
- high-trust tasks that require deep conformity with existing architecture.

If Codex still delegates one of these tasks to Bob, the skill should require a stronger prompt template with interface-verification steps.

## Required Skill Behavior

### 1. Detect Bob availability first

Before trying to use Bob, the skill should:

- check whether `bob` is installed,
- capture `bob --help` or equivalent only when available,
- stop early with a concise explanation if Bob is unavailable,
- point the caller to the official Bob Shell install docs rather than guessing installation steps.

### 2. Select delegation mode

The skill should help Codex choose between:

- interactive Bob session for exploratory work,
- non-interactive Bob execution for bounded scripted work.

Default guidance:

- use non-interactive invocation for deterministic, bounded, prompt-in/prompt-out tasks,
- use interactive only when the task benefits from conversation or iterative probing.

### 3. Structure the Bob prompt

The skill should provide prompt templates that include:

- the exact task,
- explicit scope boundaries,
- files or directories Bob is allowed to inspect or edit,
- validation requirements,
- contract-verification requirements when applicable,
- clear output expectations,
- "do not invent new interfaces" guidance when touching existing systems.

### 4. Capture Bob-specific guardrails

For integration-sensitive work, the prompt template should require Bob to:

- verify every called method against concrete implementations,
- avoid inventing repo or port helpers unless explicitly asked,
- call out contract mismatches before coding,
- prefer real integration validation over mock-only success,
- summarize assumptions separately from verified facts.

### 5. Review Bob output

The skill should instruct Codex to review Bob output for:

- contract drift,
- invented abstractions,
- mock-heavy tests that bypass real seams,
- overclaiming around test completeness,
- mismatch between generated code and repo conventions.

### 6. Integrate or reject cleanly

The skill should include a final decision step:

- accept Bob output,
- partially salvage it,
- reject and restart locally.

It should normalize rejection as a valid outcome instead of assuming Bob output must be integrated.

## Proposed Skill Workflow

The eventual skill should implement this workflow:

1. Confirm the task is appropriate for Bob.
2. Load the official Bob docs references needed for the selected CLI path.
3. Detect local Bob availability.
4. Choose interactive or non-interactive execution mode.
5. Build a bounded Bob prompt using the skill template.
6. Invoke Bob.
7. Capture output, artifacts, or diffs.
8. Validate the result against real contracts and repo expectations.
9. Integrate, revise, or discard the result.

## Proposed Skill Contents

### `SKILL.md`

Should contain:

- the Bob selection policy,
- the main workflow,
- the prompt templates,
- the validation checklist,
- explicit anti-patterns learned from the CCDash review,
- references to the Bob docs files in `references/`.

### `references/`

Recommended files:

- `references/bob-shell-overview.md`
- `references/bob-shell-invocation.md`
- `references/bob-shell-safety.md`
- `references/bob-selection-guidance.md`

Content guidance:

- `bob-shell-overview.md`: short summary of Bob Shell capabilities and when to use interactive vs non-interactive sessions.
- `bob-shell-invocation.md`: distilled command usage based on the official docs and any validated local help output.
- `bob-shell-safety.md`: sandboxing, trusted-folder, and approval expectations from the docs.
- `bob-selection-guidance.md`: our perspective on Bob's strengths, weaknesses, and recommended use cases.

### `scripts/`

Recommended only if implementation benefits from deterministic wrapping.

Possible scripts:

- `scripts/check_bob.sh`
- `scripts/run_bob_task.sh`

These should only be added if the CLI syntax can be validated from the official docs and local help output. Do not invent wrapper behavior first and hope the CLI supports it later.

## Prompt Design Requirements

The skill should include at least three prompt patterns.

### Prompt pattern 1: bounded drafting

Use for docs, summaries, boilerplate, or isolated file work.

Required characteristics:

- narrow scope,
- named files,
- explicit output format,
- no autonomy beyond the stated task.

### Prompt pattern 2: constrained implementation

Use for limited code generation where a real contract already exists.

Required characteristics:

- cite the exact interfaces to respect,
- require verification against concrete implementations,
- require Bob to stop and report mismatches before coding,
- require tests that exercise the real seam when feasible.

### Prompt pattern 3: exploratory sidecar

Use for low-risk exploration while Codex owns integration.

Required characteristics:

- ask for options, not final authority,
- gather alternatives or candidate drafts,
- avoid handing Bob the critical integration path.

## Validation Requirements For The Future Skill

The eventual skill should be considered complete only if it can handle these scenarios:

1. Bob not installed locally.
2. User asks to use Bob for documentation drafting.
3. User asks to use Bob for a bounded code task with real interface constraints.
4. User asks to use Bob for an inappropriate architecture-heavy task and the skill pushes back.
5. User asks for a cheap parallel candidate implementation and the skill structures it safely.

## Acceptance Criteria

- The skill uses the official Bob Shell docs as its primary reference source.
- The skill does not assume Bob is installed.
- The skill encodes a clear decision policy for when Bob is appropriate.
- The skill includes explicit guardrails derived from the CCDash Phase 1 review.
- The skill helps Codex structure Bob prompts instead of merely explaining Bob.
- The skill includes a validation checklist for reviewing Bob's outputs.
- The skill stays concise and does not duplicate the full Bob docs.

## Implementation Guidance For Skill_Seekers

Assumption: "Skill_Seekers" is the implementation workflow or agent group that will build the skill from this spec.

Recommended implementation sequence:

1. Read the official Bob Shell docs pages relevant to invocation, modes, slash commands, and sandboxing.
2. Validate the real local Bob CLI surface if `bob` is installed in the target environment.
3. Create the skill scaffold with `skill-creator` conventions.
4. Write `references/` first, keeping `SKILL.md` lean.
5. Encode the Bob selection policy from this spec directly into the skill description and body.
6. Add wrappers only after the CLI syntax is validated.
7. Forward-test the skill with realistic bounded delegation prompts.

## Recommended Forward-Tests

After the skill is built, test it with prompts like:

- "Use Bob to draft a migration report for these changed files."
- "Use Bob to propose DTOs for this existing API contract without changing repository interfaces."
- "Use Bob to generate a README for this CLI tool."
- "Use Bob to explore three implementation options for this isolated formatter."
- "Use Bob for this end-to-end backend phase."

The last case should be treated as a policy test. The skill should narrow the task, push back, or refuse to delegate it as-is.

## Risks

- Overfitting the skill to one negative experience with Bob.
- Encoding invented Bob CLI usage if the docs are not consulted precisely enough.
- Letting wrapper scripts obscure what Bob is actually doing.
- Creating a skill that is too verbose and not action-oriented.

## Mitigations

- Use the official Bob docs as the primary source of truth.
- Keep Bob policy guidance focused on observed patterns, not broad accusations.
- Favor prompt templates and validation checklists over large narrative sections.
- Forward-test the skill on both good-fit and bad-fit tasks.

## Recommendation

Build this skill, but build it as a constrained delegation skill, not a generic "Bob integration" skill.

That is the main lesson from the CCDash review: Bob is worth using, but only when the task selection and prompt structure force the right level of discipline.
