---
title: "Feature Contract: CCDash CLI Project Init (`ccdash project` command group)"
schema_version: 2
doc_type: feature_contract
status: draft
created: 2026-05-29
updated: 2026-05-29
feature_slug: "ccdash-cli-project-init"
category: "features"
estimated_points: 6
tier: 1
owner: null
priority: medium
risk_level: medium
changelog_required: true
related_documents:
  - "docs/project_plans/feature_contracts/enhancements/ccdash-skill-refresh-and-spec.md"
files_affected:
  - "packages/ccdash_cli/src/ccdash_cli/main.py"
  - "packages/ccdash_cli/src/ccdash_cli/commands/project.py"
  - "packages/ccdash_cli/tests/test_project_commands.py"
  - "packages/ccdash_cli/README.md"
  - "CLAUDE.md"
spike_ref: null
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
---

# Feature Contract: CCDash CLI Project Init (`ccdash project` command group)

## 1. Goal

Add a `ccdash project` Typer command group to the standalone CLI so an operator can register, list, and switch projects on a running CCDash instance without hand-editing `projects.json`.

---

## 2. User / Actor

- **Primary user**: Developer or operator onboarding a new repo to a local or remote CCDash instance from the terminal.
- **Secondary users**: CI/CD pipelines automating project registration during environment bootstrap.

---

## 3. Job To Be Done

When standing up CCDash for a new repository, the user wants to register the project against the active CCDash target from the CLI, so they can begin tracking sessions and artifacts without manually editing `projects.json` or running an internal onboarding script.

---

## 4. Scope

### In Scope

- New `project` Typer sub-app in `packages/ccdash_cli/src/ccdash_cli/commands/project.py`, registered in `main.py` alongside the existing `target` group.
- `ccdash project add` (alias `init`): register a new project on the resolved target via `POST /api/projects`. Required flags: `--name`, `--path` (server-side filesystem root). Optional flags: `--description`, `--repo-url`, `--active` (also call `POST /api/projects/active/{id}` after creation), `--target` (reuse global `--target` resolution from app state).
- `ccdash project list`: list all projects from the resolved target via `GET /api/projects`. Supports `--output` (table/json, matching existing CLI output modes).
- `ccdash project use <project_id>`: switch active project on the target via `POST /api/projects/active/{project_id}`.
- Idempotency for `add`: before posting, call `GET /api/projects` and check for an existing project with the same `path`. If found, print a warning and exit cleanly (no duplicate). `--force` flag skips the check and sends the request regardless (server will overwrite or error naturally).
- Error handling consistent with existing standalone CLI patterns (`target.py`, `client.py`): exit codes 1 (server/not-found), 2 (auth), 4 (unreachable), non-traceback stderr messages.
- Tests under `packages/ccdash_cli/tests/test_project_commands.py` covering add (success, idempotent/duplicate, error), list, and use.
- Docs: update standalone CLI `packages/ccdash_cli/README.md` with new command examples; add `ccdash project` to the command list in root `CLAUDE.md`.

### Out of Scope

- Filesystem scaffolding of `.claude/`, `docs/`, or any other directory structure inside the target project root.
- Project auto-discovery or filesystem scanning.
- Parity changes to the in-repo CLI (`backend/cli/`) — the in-repo CLI uses `ProjectManager` directly; note as a possible follow-up but do not implement here.
- Auth or target management changes — the existing `target` command group handles server targeting.
- Updates to the `ccdash` skill's `SPEC.md`/`SKILL.md` — that work is owned by the sibling contract `ccdash-skill-refresh-and-spec.md`; cross-reference only.

---

## 5. UX / Behavior Requirements

- `ccdash project add --name "My Repo" --path /home/user/myrepo` prints the newly created project `id` on success and exits 0. Example output: `Project 'My Repo' registered (id: abc-123).`
- When `--active` is passed, the command additionally calls `POST /api/projects/active/{id}` and prints `Active project set to 'My Repo' (abc-123).`
- Re-running `add` with the same `--path` warns the user (`Warning: a project with path '/home/user/myrepo' already exists (id: abc-123). Use --force to re-register.`) and exits 0 (no-op, not an error).
- `--force` bypasses the idempotency check and always sends the `POST /api/projects` request; the server may return a conflict error — surface it verbatim to stderr.
- `ccdash project list` outputs a table (default) or JSON (`--output json`) of all projects on the resolved target. Table columns: `ID`, `Name`, `Path`, `Active` (marked with `*` for the currently active project). The active project is determined by comparing list items against `GET /api/projects/active`; if that request fails, the `Active` column is omitted with a note.
- `ccdash project use <project_id>` prints `Active project set to '<id>'.` on success and exits 0. On `WatcherRebindError`-flavored 4xx from the server (paths don't exist), surfaces the server's `detail` message to stderr and exits 1.
- All commands respect global `--target`, `CCDASH_TARGET`, and `active_target` resolution (the standard `resolve_target` + `build_client` path in `runtime/config.py` and `runtime/client.py`).
- When the target is unreachable, commands print a single-line error to stderr (`Error: cannot connect to '<url>'. Is the CCDash server running?`) and exit 4, without a Python traceback.
- Remote-target UX note: display a parenthetical reminder when `--path` contains a local-looking path against a non-localhost target (`Note: --path is interpreted on the server host, not the local machine.`).

---

## 6. Data Requirements

- **Payload-shape decision (resolved from architecture inspection)**: The server's `POST /api/projects` endpoint accepts a full `Project` Pydantic model in which `id: str` is required with no server-side default. The server does not generate IDs. The CLI must therefore build a minimal complete record client-side before posting:
  - `id`: generated via `str(uuid.uuid4())` on the CLI
  - `name`: from `--name` flag (required)
  - `path`: from `--path` flag (required; stored as-is, interpreted on server host)
  - `description`: from `--description` (optional, default `""`)
  - `repoUrl`: from `--repo-url` (optional, default `""`)
  - All remaining fields (`agentPlatforms`, `planDocsPath`, `sessionsPath`, `progressPath`, `pathConfig`, `testConfig`, `skillMeat`) must be sent with their model defaults so the server receives a valid `Project` object without validation errors.
- The simplest correct approach is to send the flat-field dict (`{"id": ..., "name": ..., "path": ..., ...}`) without constructing the nested `pathConfig` object. The `_migrate_legacy_path_config` validator on the server auto-constructs `pathConfig` from flat fields at parse time, so CLI-created records will be structurally identical to script-created ones after server-side migration.
- **Entities affected**: `projects.json` on the server host (written by `ProjectManager`); no client-side state changes beyond stdout/stderr.
- **State changes**: `active_project` field in `projects.json` is updated when `--active` is passed or `project use` is invoked.
- **Storage implications**: None on the CLI side. The server persists the record; no migration is needed.

---

## 7. API / Integration Requirements

**Endpoints used (all existing, no new server endpoints):**

- `GET /api/projects` — list all projects; used for idempotency check in `add` and for `list` display.
- `POST /api/projects` — create a project; request body is the full `Project` JSON object (flat-field form accepted; server migrates to nested form).
- `POST /api/projects/active/{project_id}` — set active project; used by `--active` flag in `add` and by `project use`.
- `GET /api/projects/active` — get active project; used by `list` to mark the active row. Returns 404 when no active project is set — treat as `active_id = None`, not an error.

**HTTP client integration:**

- Use existing `CCDashClient.get()` and `CCDashClient.post()` from `runtime/client.py`. The client handles auth headers, retries, and error-to-exception mapping.
- The `post()` method accepts `json_body: dict[str, Any]`; pass the constructed project dict directly.
- Map `CCDashClientError` subclasses to the established exit-code contract: `AuthenticationError` → exit 2, `ConnectionError` → exit 4, `ServerError` / `NotFoundError` → exit 1.

**Internal service dependencies:**

- `runtime/config.py:resolve_target` — target resolution (no changes).
- `runtime/client.py:build_client` — client construction (no changes).
- `runtime/state.py` — global `TARGET_FLAG` and `OUTPUT_MODE` state (no changes).

---

## 8. Architecture Constraints

**Must follow existing patterns in:**

- `packages/ccdash_cli/src/ccdash_cli/commands/target.py` — command-group structure, error surfacing pattern (`typer.echo(..., err=True)` + `raise typer.Exit(code=N)`), `resolve_target` + `build_client` usage inside command bodies.
- `packages/ccdash_cli/src/ccdash_cli/main.py` — `app.add_typer(project_app, name="project")` registration; global callback option wiring.
- `packages/ccdash_cli/src/ccdash_cli/runtime/client.py` — use `CCDashClient.get()` / `.post()` only; do not introduce raw `httpx` calls in command modules.
- `packages/ccdash_cli/src/ccdash_cli/formatters.py` — use `OutputMode` and existing formatters for table/json output in `list`.

**Must not change** (protected areas):

- `backend/routers/projects.py` — no server changes; this contract is client-only.
- `packages/ccdash_cli/src/ccdash_cli/runtime/config.py` — no changes to `ConfigStore` or `resolve_target`.
- `packages/ccdash_cli/src/ccdash_cli/runtime/client.py` — no changes to the client class or exception hierarchy.
- `projects.json` schema — do not introduce new fields; use only the existing `Project` model fields.

**New dependencies:**

- Allowed? **No** — the `uuid` module is part of the Python standard library and requires no new package dependency. No third-party additions are needed.

---

## 9. Acceptance Criteria

- [ ] `ccdash project add --name "X" --path /some/path` registers a project on the resolved target and prints the new project id to stdout; exit 0.
- [ ] The registered project appears in `ccdash project list` immediately after a successful `add`.
- [ ] Re-running `add` with the same `--path` (without `--force`) prints a warning referencing the existing project id and exits 0 without creating a duplicate.
- [ ] `ccdash project add --name "X" --path /some/path --force` bypasses the idempotency check and always attempts the `POST`; server errors are surfaced to stderr.
- [ ] `ccdash project add ... --active` calls `POST /api/projects/active/{id}` after creation and confirms the active switch in stdout; `ccdash project list` shows that project marked as active.
- [ ] `ccdash project list` outputs a table with at least `ID`, `Name`, `Path` columns; the active project row is distinguished (e.g., `*` marker). `--output json` emits a JSON array.
- [ ] `ccdash project use <id>` switches the active project on the server; subsequent `ccdash project list` reflects the change.
- [ ] `ccdash project use <nonexistent-id>` prints a clear error to stderr and exits 1 (not a traceback).
- [ ] All commands respect `--target` / `CCDASH_TARGET` / `active_target` resolution; `--target local` is accepted and routes to `http://localhost:8000`.
- [ ] When the CCDash server is unreachable, all `project` commands print a single-line error to stderr (no Python traceback) and exit 4.
- [ ] When the server returns HTTP 401, commands exit 2 with an authentication error message and a login hint.
- [ ] `ccdash --help` shows `project` in the top-level command list; `ccdash project --help` shows `add`, `list`, `use`.
- [ ] Tests in `packages/ccdash_cli/tests/test_project_commands.py` cover: `add` success, `add` idempotent no-op, `add --force`, `add --active`, `list` (table and JSON), `use` success, `use` not-found, and unreachable-target error path.
- [ ] **Resilience (R-P2):** If `GET /api/projects/active` returns a non-2xx response during `list`, the `Active` column is omitted and a parenthetical note `(active project unavailable)` is shown; the rest of the list renders normally.
- [ ] Standalone CLI `packages/ccdash_cli/README.md` updated with `project` command examples; root `CLAUDE.md` command table updated.

---

## 10. Validation Requirements

- [ ] **Lint** passes (`ruff check packages/ccdash_cli/` or equivalent configured linter for the package).
- [ ] **Type check** passes (`mypy packages/ccdash_cli/src/` or `pyright`; match existing CI config for this package).
- [ ] **Tests** added under `packages/ccdash_cli/tests/test_project_commands.py`; all new tests pass.
- [ ] **Existing test suite** passes (`python -m pytest packages/ccdash_cli/tests/ -v`); no regressions.
- [ ] **Build/install** passes (`pip install -e packages/ccdash_cli[dev]` succeeds in a clean venv).
- [ ] **Manual smoke**: executor runs `ccdash target check local`, then `ccdash project add --name "Smoke" --path /tmp/smoke`, `ccdash project list`, and `ccdash project use <id>` against a local server and records results in the Completion Report.
- [ ] **Docs updated**: `packages/ccdash_cli/README.md` and root `CLAUDE.md` reflect new commands.
- [ ] **No unrelated changes** introduced (no changes to server code, `runtime/config.py`, or `runtime/client.py`).

---

## 11. Risk Areas

- **Server payload shape / `id` ownership**: The `Project` model requires `id: str` with no server-side default. The CLI must generate the UUID. If the contract drifts (e.g., the server starts generating IDs in a future version), client-generated IDs will conflict. Mitigation: document the generation rule in code comments; add an integration test that posts and reads back.
- **Idempotency detection key**: Duplicate detection is keyed on `path`. If two projects share a path (unusual but legal), the check will warn on the second even if `name` differs. Mitigation: warn message displays the conflicting project's id and name so the operator can decide to `--force`.
- **Remote-target path semantics**: `--path` is stored and resolved on the server host. An operator running the CLI against a remote server who passes a local path will register a non-functional project. Mitigation: print the parenthetical reminder (§5) when the resolved target is non-localhost; document in README.
- **`pathConfig` field defaults**: The `Project` model's `_migrate_legacy_path_config` validator auto-constructs `pathConfig` from flat fields at parse time. Sending only flat fields is the safe approach; do not mix flat and nested. Confirm this in tests.
- **`POST /api/projects/active/{id}` watcher rebind error**: The server may return 4xx if the new project's paths don't exist on disk. `project use` must surface the `detail` message verbatim rather than swallowing it as a generic server error.

---

## 12. Implementation Notes

**Suggested approach** (agent may improve):

1. Create `packages/ccdash_cli/src/ccdash_cli/commands/project.py` with `project_app = typer.Typer(help="Manage CCDash projects.")` and the three command functions (`add`/`list`/`use`). Follow `commands/target.py` as the structural template.
2. Wire into `main.py`: `from ccdash_cli.commands.project import project_app` and `app.add_typer(project_app, name="project")`.
3. In `add`: call `resolve_target` + `build_client`, do the idempotency `GET`, build the project dict (uuid + flags + flat-field defaults), `POST /api/projects`, optionally `POST /api/projects/active/{id}`.
4. In `list`: fetch `GET /api/projects`, attempt `GET /api/projects/active` (catch all `CCDashClientError` and set `active_id = None`; also catch 404 explicitly as a clean no-active-project state), render table or JSON via existing formatters.
5. In `use`: `POST /api/projects/active/{project_id}`; map errors per exit-code contract.
6. Tests: use `typer.testing.CliRunner` and `unittest.mock.patch` on `build_client` (pattern established in `test_commands.py`).

**Similar existing code:**

- `packages/ccdash_cli/src/ccdash_cli/commands/target.py` — full command-group pattern to follow.
- `packages/ccdash_cli/tests/test_commands.py` — existing CliRunner + mock-client test patterns.
- `backend/scripts/container_project_onboarding.py` — reference for which `Project` fields to populate and their expected defaults (match field values so CLI-registered projects are indistinguishable from script-registered ones).

**Known gotchas:**

- The `CCDashClient.post()` method hits paths without the `/api/v1/` prefix (it uses `/api/projects` directly, consistent with how the server's router is mounted at `/api/projects`). Verify against `target_check` usage to confirm the correct base path.
- Sending the flat-field dict (not nested `pathConfig`) triggers the `_migrate_legacy_path_config` validator server-side, which is the intended behavior. Do not construct the nested `pathConfig` manually.
- The `GET /api/projects/active` endpoint returns 404 when no active project is set. Treat 404 as `active_id = None` in `list`, not as an error.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified/new files with brief reason.
- **Tests run**: What tests were added/updated and pass/fail results (`pytest packages/ccdash_cli/tests/ -v`).
- **Smoke test results**: Output of `ccdash target check local`, `ccdash project add ...`, `ccdash project list`, and `ccdash project use <id>` against a local server (or explicit `runtime_smoke: skipped` with reason if server is unavailable).
- **Validation results**: Table of all validation commands and their results (lint, typecheck, pytest, build install).
- **Deviations from contract**: Any material changes to this contract during implementation and justification.
- **Risks / Limitations**: Any remaining risks or known limitations after implementation.
- **Follow-up recommendations**: Suggested next steps (e.g., in-repo CLI parity, `ccdash project remove`, skill SPEC update coordination with `ccdash-skill-refresh-and-spec`).

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (3–8 points) — estimated 6 points

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase orchestration

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents:**

- `docs/project_plans/feature_contracts/enhancements/ccdash-skill-refresh-and-spec.md` — sibling contract; owns SKILL.md/SPEC.md updates for the `ccdash` skill (cross-reference, do not duplicate)
- `backend/routers/projects.py` — server endpoint contracts (read-only reference)
- `backend/models.py` (class `Project`, line 1652) — full `Project` model field list and defaults
- `packages/ccdash_cli/src/ccdash_cli/commands/target.py` — command-group structural template
- `packages/ccdash_cli/src/ccdash_cli/runtime/client.py` — HTTP client and exit-code contract
- `packages/ccdash_cli/src/ccdash_cli/runtime/config.py` — target resolution chain

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass validation. If you find:

- **Scope ambiguity**: Ask one focused question or make a conservative assumption and note it in the Completion Report.
- **Impossible constraints**: Flag in the Completion Report before attempting workarounds.
- **Better implementation path**: Document the deviation in the Completion Report with justification.

Stay within scope. Avoid changes to server code, runtime infrastructure, or the `ccdash` skill documentation (that work belongs to the sibling contract). The reviewer will check for scope drift.
