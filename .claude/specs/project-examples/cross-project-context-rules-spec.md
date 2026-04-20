# Cross-Project Context Rules Spec

Foundational operating procedures distilled for reuse across Claude-Code-driven projects. Drop these sections into a new project's root `CLAUDE.md` and adapt the project-specific bits (file paths, task ID prefixes, model versions). Skip anything tied to a single project's domain (architecture, GitHub clients, marketplace, memory systems, etc.).

**Source**: distilled from `skillmeat-spec.md` and applied to MeatyWiki on 2026-04-16.
**Scope**: agent operating procedures, delegation patterns, progress tracking, context discipline. NOT architecture, NOT domain models.

---

## What to Pull (foundational, reusable)

These sections belong in every project's root `CLAUDE.md`:

1. **Operating Procedures**
   - Prime Directives table (delegate everything, token efficient, rapid iteration, no over-architecture)
   - Opus Delegation Principle (orchestrate, don't implement; pattern; file-context rule)
   - Documentation Policy (allowed/prohibited; reference `.claude/specs/doc-policy-spec.md`)
   - Command-Skill Bindings table (commands don't auto-load skills — call `Skill()` first)

2. **Agent Delegation**
   - Model Selection table (Opus / Sonnet / Haiku — current versions per project)
   - Multi-Model Integration (codex, gemini-cli, bob-shell-delegate, nano-banana — opt-in supplements)
   - Disagreement protocol (tests decide, CI is the arbiter)
   - Background Execution rules (`run_in_background`, `TaskOutput`, verification on disk)
   - Context Budget Discipline (~52K baseline, ~25–30K per phase, no `TaskOutput` for file-writers)

3. **Orchestration & Progress Tracking**
   - File locations (one phase progress + one PRD context per scope)
   - CLI-First Updates with the four scripts: `update-status.py`, `update-batch.py`, `update-field.py`, `manage-plan-status.py`
   - When to use agents instead (file creation, narrative notes, blockers)
   - Workflow (read YAML → parallel `Task()` → CLI update → validate)
   - Token efficiency table (CLI vs agent for status updates)

4. **Progressive Disclosure Context** — loading ladder:
   1. Runtime truth (symbols, OpenAPI, generated graphs)
   2. Entry `CLAUDE.md`
   3. Nested `CLAUDE.md` for the package being touched
   4. Key-context playbooks (only when working in that domain)
   5. Authoritative spec/PRD/phase plan
   6. Historical plans/reports — for rationale only, verify behavior from runtime truth

---

## What to Skip (project-specific)

Do **not** copy from a source CLAUDE.md when porting to a new project:

- Architecture overview, package layout, data-flow principles
- Domain wrappers (e.g., `GitHubClient`, `EngineAdapter`)
- Editions / feature flags / tenancy model
- Manifest / lockfile / artifact-source formats
- Memory system specifics (project-specific schema, anchors, capture commands)
- Long agent rosters with project-specific permissioning
- Domain-specific routing tables, endpoint maps, component patterns
- `.claude/context/key-context/*` filenames — list only the ones the target project actually has
- CLI command tables for the source product

---

## Adaptation Checklist (when porting to a new project)

Before pasting these sections into a new project's `CLAUDE.md`:

- [ ] **Verify scripts exist**: confirm `.claude/skills/artifact-tracking/scripts/{update-status,update-batch,update-field,manage-plan-status}.py` are present. If not, install the `artifact-tracking` skill first or remove the CLI section.
- [ ] **Replace task-ID prefix examples**: e.g., `P3-07` → whatever the new project uses (`TASK-1.1`, `EP01-S03`, etc.).
- [ ] **Replace progress-file paths**: `.claude/progress/<actual-prd-name>/...`.
- [ ] **Replace plan path** in the `manage-plan-status.py` example with the project's actual implementation plan.
- [ ] **Update model versions** in the Model Selection table to match the project's current pinned models (Opus 4.7 / Sonnet 4.6 / Haiku 4.5 as of 2026-04).
- [ ] **List only existing key-context files** in the Progressive Disclosure ladder — `ls .claude/context/key-context/` and reference what's actually there.
- [ ] **Confirm referenced specs exist**: `.claude/specs/doc-policy-spec.md`, `.claude/specs/multi-model-usage-spec.md`. If absent, either install them or drop the reference.
- [ ] **Check skill availability**: `Skill("debug")`, `Skill("planning")`, `Skill("artifact-tracking")`, `Skill("dev-execution")` — only list commands whose required skills exist in the project.
- [ ] **Branch / commit conventions**: keep the source project's branch naming if it makes sense; otherwise replace with the new project's convention.

---

## Placement Within `CLAUDE.md`

Recommended ordering:

1. Repository Status (project-specific)
2. Standard Commands (project-specific)
3. What This Project Is (project-specific)
4. Authoritative Documents (project-specific)
5. V1 Scope Discipline / Deferred Items (project-specific)
6. Working in this Repository (code conventions, doc conventions, commits/branches — mostly project-specific)
7. **→ Operating Procedures (FROM THIS SPEC)**
8. **→ Agent Delegation (FROM THIS SPEC)**
9. **→ Orchestration & Progress Tracking (FROM THIS SPEC)**
10. **→ Progressive Disclosure Context (FROM THIS SPEC)**
11. `.claude/` Directory inventory (project-specific)
12. External Systems (project-specific)

Sections 7–10 form a self-contained operations block. Keeping them together makes it easy to refresh the block from this spec when conventions evolve.

---

## Why These Sections Are Foundational

| Section | Without it, what breaks |
|---------|-------------------------|
| Opus Delegation Principle | Opus burns tokens implementing instead of orchestrating |
| Command-Skill Bindings | `/dev:*` commands silently miss skill guidance — workflow drifts |
| Model Selection | Subagents default to Opus everywhere — cost explodes |
| CLI-First Updates | Each status flip pulls a 25KB markdown file into context |
| Background Execution rule (no `TaskOutput()` for file-writers) | Background-agent transcripts get re-pulled into Opus context, defeating the parallelism gain |
| Context Budget Discipline | Phases overflow context window mid-execution |
| Progressive Disclosure ladder | Agents read deep specs before runtime truth — and act on stale plans |

---

## Maintenance

When any of the underlying conventions change in a way that affects multiple projects (model rev, new artifact-tracking script, new escalation protocol):

1. Update this spec.
2. Open the projects that have already pulled these sections, find the corresponding block in their `CLAUDE.md`, and refresh.
3. Note the date of the refresh in this spec's frontmatter or in a brief changelog at the bottom.

---

## Changelog

- **2026-04-16** — Initial extraction from `skillmeat-spec.md`, applied to MeatyWiki `CLAUDE.md`.
