---
schema_version: 2
doc_type: prd
title: "CCDash Claude Code Skill — PRD"
description: "Natural-language skill that routes agent intent to the standalone ccdash CLI for project, feature, session, and workflow intelligence."
status: draft
created: 2026-04-13
updated: 2026-04-13
feature_slug: ccdash-skill
priority: medium
risk_level: low
owner: nick
contributors: [nick]
related_documents:
  - docs/project_plans/ccdash-cli-mcp-enablement-plan.md
  - packages/ccdash_cli/README.md
  - docs/guides/standalone-cli-guide.md
prd_ref: null
plan_ref: .claude/skill-specs/ccdash-skill/implementation-plan.md
---

# CCDash Claude Code Skill — PRD

## TL;DR

A Claude Code skill named `ccdash` that lets any Claude Code session drive the standalone `ccdash` CLI from natural language. The skill routes operator/agent intent (project status, feature forensics, session search, workflow failures, AAR reports) to the correct `ccdash` subcommand with the right `--output` mode, surfaces provenance for chaining, and degrades gracefully through `ccdash doctor` when install/target/auth is misconfigured. Designed for progressive disclosure so future CLI and MCP surface growth is additive, not a rewrite.

## Problem

CCDash exposes rich project/session intelligence through a standalone CLI (`packages/ccdash_cli/`), but coding agents inside Claude Code cannot fluently access it:

- Agents don't know the CLI exists or when to invoke it.
- Subcommand surface (`status`, `feature`, `session`, `workflow`, `report`, `target`, `doctor`) is non-obvious from natural language.
- Output mode selection (`human` vs `json` vs `markdown`) is context-dependent and easy to get wrong.
- Target/auth setup (`target add`, `target login`, config precedence) is a silent failure mode.
- Multi-step forensic flows (triage → investigate → report) require orchestration the agent rarely performs unaided.

Without a skill, every session re-learns the CLI by reading `--help` — slow, lossy, and inconsistent.

## User Stories

### Agent (primary)

- As a coding agent, when the user asks "what's the state of this project", I invoke `ccdash status project --output json` and summarize the response with session/feature IDs intact so I can follow up.
- As a coding agent, when the user asks "why did FEAT-123 take so long", I run `ccdash feature show FEAT-123 --output json` then `ccdash feature sessions FEAT-123 --output json`, pick the costliest session, and run `ccdash session drilldown` for root cause.
- As a coding agent, when the user asks for a retrospective on a feature, I run `ccdash report aar --feature <id> --output markdown` and render the result verbatim.
- As a coding agent, when `ccdash` returns a connection error, I run `ccdash doctor` before surfacing the error to the user.

### Operator (secondary)

- As an operator new to the CCDash CLI, when I ask "set up ccdash against my staging server", the skill walks me through `pipx install ccdash-cli`, `ccdash target add`, `ccdash target login`, and `ccdash doctor`.
- As an operator, when I say "use the staging target for the next command", the skill adds `--target staging` or sets `CCDASH_TARGET` for the session.

### Maintainer (tertiary)

- As a maintainer shipping a new `ccdash` subcommand, I add one reference file under the skill directory and one router-table entry; `SKILL.md` does not need rewriting.

## Success Metrics

| Metric | Target |
|---|---|
| Intent → correct subcommand routing accuracy (human eval, 20 scenarios) | ≥ 90% |
| Skill triggers on in-scope natural-language requests (precision) | ≥ 95% (no false fires on unrelated coding tasks) |
| Time-to-first-useful-answer on cold-start operator (install → first `status project`) | ≤ 3 minutes guided |
| New CLI subcommand onboarding cost (maintainer) | 1 reference file + 1 router entry, no SKILL.md edit |
| Graceful degradation rate when server unreachable | 100% runs `doctor` before surfacing raw error |

## In Scope

Skill capabilities mapped to current CLI surface:

| Capability | CLI Command(s) | Primary Output Mode |
|---|---|---|
| Project status summary | `ccdash status project` | json (agent) / human (operator) |
| Workflow failure triage | `ccdash workflow failures` | json |
| Feature list / filter | `ccdash feature list` | json |
| Feature forensic detail | `ccdash feature show <id>` | json |
| Feature → sessions | `ccdash feature sessions <id>` | json |
| Feature → documents | `ccdash feature documents <id>` | json |
| Session list / filter | `ccdash session list` | json |
| Session detail | `ccdash session show <id>` | json |
| Session transcript search | `ccdash session search <query>` | json |
| Session drilldown (concern) | `ccdash session drilldown <id>` | json |
| Session family (root cluster) | `ccdash session family <id>` | json |
| Narrative feature report | `ccdash report feature <id>` | markdown |
| After-action report | `ccdash report aar --feature <id>` | markdown |
| Target management | `ccdash target list/add/use/show/remove/login/logout/set-token/check` | human |
| Connectivity diagnostics | `ccdash doctor` | human / json |

Cross-cutting capabilities:

- Install detection + guided `pipx install ccdash-cli` (from-repo fallback documented).
- Target/auth resolution awareness (env > config > implicit local).
- Multi-step recipes: project triage, feature retrospective, workflow failure root-cause, session cluster investigation.
- Provenance surfacing: always echo stable IDs (feature, session, document) and freshness timestamps into agent context.
- Graceful degradation via `ccdash doctor` on transport errors.

## Out of Scope

- Reimplementing CLI logic in the skill (skill always shells out).
- Modifying the CCDash backend, frontend, or CLI package itself.
- MCP tool invocation — deferred until the MCP surface in the enablement plan ships (Phase 4 of the parent plan). Skill will add an MCP-aware recipe layer at that point; not on day one.
- Authoring new CCDash reports, workflows, or analytics queries.
- Secret management beyond delegating to `ccdash target login` (keyring-backed).
- Any task unrelated to CCDash observability (e.g., writing React components, debugging unrelated services).

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CLI subcommands drift; skill issues stale flags | Med | Med | Reference files live alongside CLI; update protocol in implementation plan requires reference-file update on CLI change. Skill preambles run `ccdash --help` / `ccdash <cmd> --help` on uncertainty. |
| Skill over-triggers on generic "project status" asks unrelated to CCDash | Med | Low | Trigger description explicitly scopes to CCDash/agent-session analytics; "when NOT to use" block in SKILL.md. |
| Operator lacks install; skill fails silently | Low | Med | Preflight `ccdash --version`; if missing, run install recipe before any query. |
| Server unreachable → cryptic HTTP error leaks to user | Med | Low | All query failures route through `ccdash doctor` interpretation recipe. |
| Output mode confusion (json dumped to operator, markdown dumped to agent reasoning) | Med | Low | Router decides mode per intent; explicit rules in SKILL.md. |
| Multi-project ambiguity (which project/target is active) | Med | Med | Recipes always resolve `ccdash target show` + `ccdash status project` context first if project scope is unclear. |

## Open Questions

1. Should the skill cache `ccdash target show` output within a session to avoid repeated invocations? (Lean: no cache; cost is negligible and staleness risk is real.)
2. When MCP ships (enablement plan Phase 4), does the skill prefer MCP tools over CLI shelling for in-process Claude Code, or keep CLI as the single transport? (Defer to MCP phase; keep an ADR-style note in implementation plan.)
3. Should `report aar` / `report feature` outputs be saved to disk by default, or only on explicit request? (Default: stream to agent; save only if user asks.)
4. How should the skill handle project selection when multiple projects exist server-side? (Lean: surface list, ask once, then use `CCDASH_PROJECT` env for session.)

## Dependencies

- `ccdash-cli` installed globally (`pipx install ccdash-cli`) OR available via repo venv `packages/ccdash_cli`.
- A reachable CCDash server (`localhost:8000` default; remote targets supported).
- `~/.config/ccdash/config.toml` writable for `target add`.

## Acceptance Criteria

1. Skill triggers on explicit `/ccdash` invocation and on natural-language intents that map to CCDash capabilities listed in "In Scope."
2. Skill does not fire on unrelated coding tasks (verified against a negative-case eval set in implementation plan).
3. Every CLI capability in "In Scope" has a referenced recipe or router entry.
4. All agent-consumed commands default to `--output json`; all human-narrative commands default to `--output markdown`.
5. Install, target, and connectivity failure paths all route through `ccdash doctor` guidance.
6. Adding a new CLI subcommand requires only a new reference file + router entry (documented update protocol in the implementation plan).
7. SKILL.md stays under 150 lines; depth lives in `references/` and `recipes/`.
