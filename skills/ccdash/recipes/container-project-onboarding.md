# Recipe: Container Project Onboarding

Use this when an operator or agent asks to prepare CCDash container project inputs, generate watcher env overlays, or diagnose an empty healthy-looking container deployment.

## Inputs To Confirm

- Stable project id, e.g. `my-project`.
- Container-visible project root, e.g. `/workspace/my-project`.
- Container-visible session JSONL root. Prefer a project-specific directory.
- Host workspace root and container mount root.
- Whether the watcher overlay should be written to `deploy/runtime/watchers/<project>.env` or printed to stdout.

## Steps

1. **Prepare the host-side registry and watcher overlay.**

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

   Add `--no-active` only when the project should not become `activeProjectId`.

2. **Check the generated binding values.**

   Confirm the overlay contains:

   ```env
   CCDASH_WORKER_PROJECT_ID=my-project
   CCDASH_WORKER_WATCH_PROJECT_ID=my-project
   CCDASH_WORKER_WATCH_PROBE_PORT=9466
   CCDASH_WORKER_STARTUP_SYNC_ENABLED=false
   CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED=true
   CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED=true
   ```

3. **Start or restart the compose stack with the overlay.**

   ```bash
   docker compose \
     --env-file deploy/runtime/.env \
     --env-file deploy/runtime/watchers/my-project.env \
     -f deploy/runtime/compose.yaml \
     --profile enterprise --profile postgres --profile live-watch up --build
   ```

   For a second live-ingest project, use a distinct watcher service or compose invocation with a different `CCDASH_WORKER_WATCH_PROJECT_ID` and `CCDASH_WORKER_WATCH_PROBE_PORT`.

4. **Validate runtime and project visibility.**

   ```bash
   curl -fsS http://localhost:8000/api/health/ready | python3 -m json.tool
   curl -fsS http://localhost:9465/readyz | python3 -m json.tool
   curl -fsS http://localhost:9466/readyz | python3 -m json.tool
   curl -fsS http://localhost:8000/api/projects/active | python3 -m json.tool
   curl -fsS 'http://localhost:8000/api/v1/features?view=cards&limit=5' | python3 -m json.tool
   curl -fsS http://localhost:9466/detailz | python3 -m json.tool
   ```

5. **If data is empty but probes are healthy, fix deployment inputs first.**

   Inspect:

   - `projects.json` `activeProjectId`
   - `CCDASH_WORKER_PROJECT_ID`
   - `CCDASH_WORKER_WATCH_PROJECT_ID`
   - whether every `path`, `sessionsPath`, `planDocsPath`, and `progressPath` resolves inside the container

## Do Not Infer

- Do not say UI project switching rebinds `worker-watch`.
- Do not say standalone CLI `--project` or `ccdash target add --project` creates server registry entries.
- Do not say the API, CLI, or skill can remotely start, scale, or rebind watcher containers in the compose examples.
- Do not use `docker compose --scale worker-watch=N` for multi-project live ingest in v1.

## Cross-Links

- Reference: `references/container-project-onboarding.md`
- Runtime troubleshooting: `recipes/unreachable-server.md`
- Quickstart: `/Users/miethe/dev/homelab/development/CCDash/docs/guides/containerized-deployment-quickstart.md`
