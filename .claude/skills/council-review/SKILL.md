---
name: council-review
description: >
  Run an Agent Review Council over a product, workflow, codebase, architecture,
  prompt, agent package, or GTM artifact. Produces evidence-backed structured findings,
  scorecard, risks, decision record, and validation plan.
allowed-tools: Read, Grep, Glob, Bash
---

# Council Review Skill

Use this skill for full ARC runs that need coordinated evidence collection, independent reviewer passes, adjudication, and schema-valid outputs.

## Workflow

1. Confirm target, objective, council definition, constraints, and required outputs.
2. Read `references/run-workflow.md` for the end-to-end council procedure.
3. Read `references/output-contract.md` before creating or validating run artifacts.
4. Read `references/external-reviewers.md` only when the run includes Codex, GitHub, Copilot, LangGraph, or other non-Claude reviewers.
5. Write artifacts under `runs/<date>-<slug>/`.
6. Validate with `uv run arc validate runs/<date>-<slug>`.

## Ground Rules

- Findings without evidence are hypotheses.
- High-severity findings require strong evidence or explicit uncertainty.
- Run independent reviewer passes before synthesis.
- Preserve accepted, rejected, disputed, and watchlist findings.
- Do not create tickets or durable memory without approval.
- Keep final output concise, but preserve the structured artifacts.
