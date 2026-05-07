---
schema_version: 2
doc_type: implementation_plan
title: "CCDash Claude Code Skill — Implementation Plan"
description: "Phased delivery of the ccdash Claude Code skill with a progressive-disclosure structure and an explicit update protocol for future CLI, MCP, and deployment-runbook growth."
status: draft
created: 2026-04-13
updated: 2026-05-06
feature_slug: ccdash-skill
priority: medium
risk_level: low
effort_estimate: "S (1-2 sessions)"
prd_ref: .claude/skill-specs/ccdash-skill/prd.md
plan_ref: null
related_documents:
  - docs/project_plans/ccdash-cli-mcp-enablement-plan.md
  - packages/ccdash_cli/README.md
  - docs/project_plans/design-specs/container-project-onboarding-and-watchers-v1.md
  - docs/guides/containerized-deployment-quickstart.md
  - deploy/runtime/README.md
---

# CCDash Claude Code Skill — Implementation Plan

## TL;DR

Build the `ccdash` skill as a thin natural-language router over the standalone `ccdash` CLI. Structure is progressive-disclosure: a short `SKILL.md` loads only the trigger + router rules; per-command reference files and per-intent recipes load on demand. Four delivery phases: MVP (install + status + doctor) → NL routing across full current CLI → recipes for multi-step forensics → MCP-aware integration once the enablement plan's MCP phase ships. An explicit update protocol makes new CLI subcommands additive (new reference file + one router row).

## Skill Directory Structure

Target location: the repo's `.claude/skills/ccdash/` for project-scoped iteration during development.

```text
ccdash/
  SKILL.md                      # Trigger description, routing table, when-not-to-use, pointers
  references/
    cli-overview.md             # Full command tree snapshot + global flags + target/auth resolution
    command-status.md           # status project — flags, examples, JSON shape notes
    command-feature.md          # feature list/show/sessions/documents
    command-session.md          # session list/show/search/drilldown/family
    command-workflow.md         # workflow failures
    command-report.md           # report aar / report feature — output=markdown guidance
    command-target.md           # target list/add/use/show/remove/login/logout/set-token/check
    command-doctor.md           # doctor — interpretation guide for connectivity/auth failures
    install-setup.md            # pipx install, from-repo fallback, verify steps
    output-modes.md             # human vs json vs markdown decision rules
    provenance.md               # IDs, timestamps, freshness fields to echo into agent context
    container-project-onboarding.md  # projects.json, watcher overlays, mount/path rules
  recipes/
    project-triage.md           # status project → risky feature → feature show → sessions
    feature-retrospective.md    # feature show → sessions → AAR report
    workflow-failure-rootcause.md  # workflow failures → pick workflow → session drilldown
    session-cluster-investigation.md  # session show → family → drilldown each sibling
    unreachable-server.md       # error → doctor → interpret → remediation branch
    target-onboarding.md        # fresh operator → install → target add → login → doctor
    container-project-onboarding.md  # host-side registry prep → watcher env overlay → validation
  scripts/
    preflight.sh                # optional: ccdash --version check + minimal doctor probe
    router-table.json           # machine-readable intent → command mapping (single source of truth for SKILL.md routing table)
  CHANGELOG.md                  # one-line-per-change log, updated whenever CLI surface changes
```

Design rules:

- `SKILL.md` stays focused on routing and guardrails; all depth is in `references/` and `recipes/`.
- `scripts/router-table.json` is the **single source of truth** for intent routing. `SKILL.md` renders a summary table from it by convention, but the skill loads `router-table.json` when disambiguation is needed.
- Reference files mirror CLI command groups 1:1. Adding a group = adding a file.
- Recipes capture *multi-step* flows; single-command invocations stay in reference files only.
- Deployment recipes may route to repo-shipped helper scripts and runbooks when no CLI/MCP command exists. They must state operational boundaries explicitly.

## Phased Delivery

### Phase 1 — MVP (Install + Status + Doctor)

**Goal**: Operator/agent can install the CLI and ask "how's my project?" with graceful failure handling.

Tasks:

| ID | Task | Acceptance |
|---|---|---|
| P1-01 | Author `SKILL.md` with trigger description, when-not-to-use, pointer to `references/` and `recipes/` | Focused on routing and guardrails; passes `skill-creator` validation |
| P1-02 | Author `references/cli-overview.md` (command tree + global flags + target/auth resolution) | Matches `ccdash --help` output as of 2026-04-13; links to upstream README |
| P1-03 | Author `references/install-setup.md` | Covers pipx, pip, repo-local install; includes `ccdash --version` / `target show` / `doctor` verification steps |
| P1-04 | Author `references/command-status.md` and `references/command-doctor.md` | Each includes flag table, example human + json output, and JSON field glossary |
| P1-05 | Author `references/output-modes.md` + `references/provenance.md` | Decision rules + ID/timestamp field list |
| P1-06 | Author `recipes/unreachable-server.md` and `recipes/target-onboarding.md` | Deterministic step lists with explicit `ccdash` invocations |
| P1-07 | Seed `scripts/router-table.json` with MVP intents (project status, doctor, target management, install) | Valid JSON; referenced from SKILL.md |
| P1-08 | Seed `CHANGELOG.md` with the initial skill version row | Dated entry referencing the PRD |

Exit criteria:

- Fresh Claude Code session invoked with `/ccdash` responds with routing guidance and can walk an operator from zero-install to first `status project`.
- Server-down scenario routes through `doctor` interpretation, not raw HTTP error.

### Phase 2 — Full Current CLI Coverage (NL Routing)

**Goal**: Every subcommand of the current CLI is routable from natural language.

Tasks:

| ID | Task | Acceptance |
|---|---|---|
| P2-01 | Author `references/command-feature.md` | Covers list/show/sessions/documents with JSON field glossary |
| P2-02 | Author `references/command-session.md` | Covers list/show/search/drilldown/family |
| P2-03 | Author `references/command-workflow.md` | Covers failures subcommand |
| P2-04 | Author `references/command-report.md` | Includes aar + feature; documents `--output markdown` default |
| P2-05 | Author `references/command-target.md` | Full target subcommand surface, keyring-backed auth notes |
| P2-06 | Extend `scripts/router-table.json` with feature/session/workflow/report/target intents | Router table entries include: intent pattern, command, default output mode, provenance fields to echo |
| P2-07 | Add 20-scenario eval fixture to `references/eval-scenarios.md` (10 positive, 10 negative) | Used for manual routing accuracy check per PRD success metrics |

Exit criteria:

- All in-scope CLI capabilities in the PRD map to a router entry + reference file.
- Manual eval pass hits ≥90% routing accuracy and ≥95% precision (no false fires).

### Phase 3 — Forensic Recipes (Multi-Step Flows)

**Goal**: Skill drives multi-step investigations instead of single commands.

Tasks:

| ID | Task | Acceptance |
|---|---|---|
| P3-01 | Author `recipes/project-triage.md` | Ordered steps with branching on "healthy" vs "risky" project states |
| P3-02 | Author `recipes/feature-retrospective.md` | Ends with `report aar` rendered to user |
| P3-03 | Author `recipes/workflow-failure-rootcause.md` | Uses `session drilldown` with concern arg |
| P3-04 | Author `recipes/session-cluster-investigation.md` | Uses `session family` to bound scope |
| P3-05 | Cross-link recipes from command reference files | Each reference file points to recipes that use it |

Exit criteria:

- Each recipe runnable end-to-end against a live CCDash instance on the dev machine.
- Recipes echo provenance IDs (feature, session, document) at each step so chaining works.

### Phase 4 — MCP-Aware Integration (Deferred Until MCP Ships)

**Goal**: When the parent enablement plan lands its MCP server (phase 4 in that plan), the skill prefers MCP tool calls over CLI shelling where it wins.

Tasks (placeholder — do not execute until MCP surface exists):

| ID | Task | Acceptance |
|---|---|---|
| P4-01 | Add `references/mcp-tools.md` mirroring MCP tool surface | Tool names + arg shapes documented |
| P4-02 | Add MCP-vs-CLI selection rule to `SKILL.md` routing | In-process MCP preferred for structured queries; CLI preferred for ops (target mgmt, install) |
| P4-03 | Extend `scripts/router-table.json` with `transport: cli|mcp` column | Backward compatible |
| P4-04 | Add `recipes/mcp-assisted-*.md` variants where meaningfully different | Only where MCP reduces round-trips |

Exit criteria:

- Skill works in environments with and without MCP available (feature-detected).
- Recipes remain CLI-backed by default; MCP is an optimization, not a dependency.

### Phase 5 — Container Project Onboarding And Watcher Binding

**Goal**: Agents can prepare deployment inputs for container projects and live watchers without implying CCDash can remotely orchestrate watcher containers.

Tasks:

| ID | Task | Acceptance |
|---|---|---|
| P5-01 | Add `references/container-project-onboarding.md` | Covers `projects.json`, container-visible paths, watcher env keys, mount variables, and validation probes |
| P5-02 | Add `recipes/container-project-onboarding.md` | Deterministic flow using `backend/scripts/container_project_onboarding.py`, watcher env overlays, and compose validation |
| P5-03 | Extend `SKILL.md` trigger/routing/do-not-say guidance | Explicitly separates registry creation, project selection, and watcher binding |
| P5-04 | Extend `scripts/router-table.json` with container onboarding intent | Routes project onboarding / watcher env / healthy-empty-stack requests to the new recipe |

Exit criteria:

- Skill points agents to host-side `projects.json` preparation before watcher startup.
- Skill states `worker-watch` is one project per process in v1 and binds at startup through `CCDASH_WORKER_WATCH_PROJECT_ID`.
- Skill does not imply UI project switching, CLI `--project`, or target defaults can rebind running watcher containers.

## Update Protocol — How to Extend the Skill

Pointer for future agents editing this skill. **When a new `ccdash` subcommand ships:**

1. Run `ccdash <new-command> --help` and capture flag table + example outputs.
2. **If the new command belongs to an existing group** (e.g., new `feature subcommand`): append a section to the existing `references/command-<group>.md`. Do not create a new file.
3. **If the new command is a new top-level group**: create `references/command-<group>.md` following the existing template (overview, flag table, JSON example, cross-links to recipes).
4. Add one row to `scripts/router-table.json` per intent the new command serves. Fields: `intent_pattern`, `command`, `default_output`, `provenance_fields`, `transport` (default `cli`).
5. If the new command enables a new multi-step flow worth naming, add a new `recipes/<flow>.md`. If it only augments an existing flow, update that recipe in place.
6. Append a dated one-liner to `CHANGELOG.md`.
7. **Do not edit `SKILL.md` unless trigger scope or when-not-to-use guidance changes.** The routing summary in SKILL.md should be regenerable from `router-table.json`.

**When a deployment helper or runtime runbook changes:**

1. Update the owning reference file under `references/`.
2. If the flow spans registry files, env overlays, compose commands, and probes, update or add a recipe under `recipes/`.
3. Add or update a router-table row only when agents need to recognize a new natural-language intent.
4. Preserve operational boundaries. A helper that writes deployment inputs is not a remote orchestration surface.

**When a CLI subcommand is removed or renamed:**

- Mark the router-table entry with `deprecated: true` and a `replacement:` pointer for one release cycle.
- Update the reference file with a deprecation callout at the top.
- Log in `CHANGELOG.md`.

**When output shape changes:**

- Update JSON field glossary in the owning reference file.
- Re-run the Phase 2 eval-scenarios fixture.

## Risks & Mitigations (Implementation-Specific)

| Risk | Mitigation |
|---|---|
| `SKILL.md` bloats as CLI grows | Update protocol forbids SKILL.md edits for routine command additions and keeps detail in references/recipes. |
| Router table drifts from reference files | Add a lightweight check in `scripts/preflight.sh` or a separate lint script that diffs router-table command names against reference-file filenames. |
| Agent ignores recipes and single-shots commands | Recipes are referenced from router-table entries under `recipe:` so router steers toward them for known multi-step intents. |
| Install-from-repo path rots as packages move | `install-setup.md` pins the canonical path (`packages/ccdash_cli/`, `packages/ccdash_contracts/`) and references the upstream CLI README as ground truth. |

## Dependencies

- `skill-creator` skill to scaffold and validate the skill layout.
- A working `ccdash` install for phase-gate verification.
- Completion of the PRD (`.claude/skill-specs/ccdash-skill/prd.md`).
