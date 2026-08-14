# Container Project Onboarding And Watcher Binding

Use this reference when an operator or agent needs to prepare a project for the containerized CCDash stack. Ground truth:

- `/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/design-specs/container-project-onboarding-and-watchers-v1.md`
- `/Users/miethe/dev/homelab/development/CCDash/docs/guides/containerized-deployment-quickstart.md`
- `/Users/miethe/dev/homelab/development/CCDash/deploy/runtime/README.md`
- `/Users/miethe/dev/homelab/development/CCDash/backend/scripts/container_project_onboarding.py`

## Core Boundary

Keep these concepts separate:

- Registry creation: host-side `projects.json` entry.
- Project selection: UI/API active project, standalone CLI `--project`, `CCDASH_PROJECT`, or target default project.
- Watcher binding: `worker-watch` process startup binding via `CCDASH_WORKER_WATCH_PROJECT_ID`.

In v1, `worker-watch` binds one project id for the life of that container. UI project switching and CLI target/project defaults do not rebind live ingest. The skill may prepare `projects.json` and env overlays, but it must not imply CCDash can remotely start, scale, or rebind watcher containers in the compose examples.

## Prepare `projects.json`

Use the helper for repeatable host-side setup:

```bash
python3 backend/scripts/container_project_onboarding.py \
  --projects-file projects.json \
  --project-id my-project \
  --name "My Project" \
  --root-container /workspace/my-project \
  --plan-docs docs/project_plans/ \
  --sessions-container /home/ccdash/.codex/sessions \
  --progress progress \
  --watcher-env deploy/runtime/watchers/my-project.env \
  --workspace-host-root /absolute/host/workspace \
  --workspace-container-root /workspace \
  --codex-home "$HOME/.codex" \
  --codex-container-home /home/ccdash/.codex
```

Helper behavior:

- Updates or inserts the project in `--projects-file` (`projects.json` by default).
- Defaults `--project-id` to a slug from `--name`.
- Requires `--name` and `--root-container`.
- Defaults `--plan-docs docs/project_plans/`, `--progress progress`, `--agent-platform "Claude Code"`, `--watcher-probe-port 9466`, and `--projects-file-for-env ../../projects.json`.
- Sets `activeProjectId` unless `--no-active` is passed.
- Writes `--watcher-env` when provided; otherwise prints the overlay to stdout.

Container path rules:

- `path` / `pathConfig.root` must be a container-visible project root.
- `planDocsPath` and `progressPath` are normally relative to the project root.
- `sessionsPath` must be container-visible and should be project-specific when possible.
- Broad `~/.codex/sessions` or `~/.claude/projects` roots can make startup sync expensive.

## Watcher Env Overlay

Generated overlays include the project binding, startup ownership, and optional mount variables:

```env
CCDASH_WORKER_PROJECT_ID=my-project
CCDASH_WORKER_WATCH_PROJECT_ID=my-project
CCDASH_WORKER_WATCH_PROBE_PORT=9466
CCDASH_WORKER_STARTUP_SYNC_ENABLED=false
CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED=true
CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED=true
CCDASH_INFERRED_STATUS_WRITEBACK_ENABLED=false
GIT_OPTIONAL_LOCKS=0
CCDASH_STARTUP_SYNC_LIGHT_MODE=true
CCDASH_PROJECTS_FILE=../../projects.json
CCDASH_WORKSPACE_HOST_ROOT=/absolute/host/workspace
CCDASH_WORKSPACE_CONTAINER_ROOT=/workspace
CCDASH_CLAUDE_HOME=~/.claude
CCDASH_CLAUDE_CONTAINER_HOME=/home/ccdash/.claude
CCDASH_CODEX_HOME=~/.codex
CCDASH_CODEX_CONTAINER_HOME=/home/ccdash/.codex
```

For multiple watchers, keep shared values in `deploy/runtime/.env` and pass one watcher-specific overlay after it so those values win:

```bash
docker compose \
  --env-file deploy/runtime/.env \
  --env-file deploy/runtime/watchers/my-project.env \
  -f deploy/runtime/compose.yaml \
  --profile enterprise --profile postgres --profile live-watch up --build
```

Do not use `docker compose --scale worker-watch=N` for v1. Each watcher needs a distinct project id and probe port, which requires distinct env or service configuration.

## Mounts

Required read-only ingest inputs:

| Input | Env |
| --- | --- |
| Project registry | `CCDASH_PROJECTS_FILE` |
| Workspace root | `CCDASH_WORKSPACE_HOST_ROOT`, `CCDASH_WORKSPACE_CONTAINER_ROOT` |
| Claude home | `CCDASH_CLAUDE_HOME`, `CCDASH_CLAUDE_CONTAINER_HOME` |
| Codex home | `CCDASH_CODEX_HOME`, `CCDASH_CODEX_CONTAINER_HOME` |

Use `CCDASH_EXTRA_MOUNT_1_HOST` / `CCDASH_EXTRA_MOUNT_1_CONTAINER` through slot 6 when a registry path lives outside the shared workspace or agent homes. If a registry path is an absolute host path, set the container target to the same absolute path so the path resolves unchanged inside the container.

## Validation

After health probes pass, verify project visibility before debugging ingestion logic:

```bash
curl -fsS http://localhost:8000/api/projects/active | python3 -m json.tool
curl -fsS 'http://localhost:8000/api/v1/features?view=cards&limit=5' | python3 -m json.tool
curl -fsS http://localhost:9466/detailz | python3 -m json.tool
```

If these show the wrong project or no data while probes are healthy, inspect `activeProjectId`, `CCDASH_WORKER_PROJECT_ID`, `CCDASH_WORKER_WATCH_PROJECT_ID`, and the container-resolvable paths in `projects.json`.

