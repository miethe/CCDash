---
title: "Local Streaming Worker (macOS launchd)"
description: "Run a persistent local CCDash worker that streams Mac session logs to the remote node Postgres"
category: guides
tags: [streaming, worker, launchd, macos, postgres, node, deployment]
updated: 2026-06-27
---

# Local Streaming Worker (macOS launchd)

This guide sets up a **persistent local worker** on your Mac that watches your
Claude Code session logs and streams them into the **remote node's shared
Postgres**. The node API/UI then read from that DB. The worker is managed as a
macOS LaunchAgent so it starts on login and restarts on crash.

> Artifacts live in `deploy/local-streaming/`. The management CLI is
> `deploy/local-streaming/ccdash-stream.sh`.

---

## Architecture — why local, not on the node

```
  ~/.claude/projects/<dir>/*.jsonl   (Mac filesystem, per-project leaf dirs)
            │  watched by
            ▼
  local worker-watch process  ──sync──▶  node Postgres  10.42.10.76:5440
  (this Mac, launchd-managed)                    │
                                                 ▼
                                  node API/UI (10.42.10.76:8090 / :3010)
```

The session JSONL logs only exist on **your Mac**. The node cannot see Mac
paths, so the sync must run **locally**. The worker connects out to the node's
Postgres and writes derived rows there; the node services read from the same DB.

This is the `worker-watch` runtime profile (`python -m backend.worker` with
`CCDASH_RUNTIME_PROFILE=worker-watch`), the same one the node runs in its
enterprise compose stack — here it runs locally instead.

---

## Prerequisites

1. **Backend venv.** From the repo root: `npm run setup` (creates
   `backend/.venv` and installs Python deps). The worker runs
   `backend/.venv/bin/python -m backend.worker`.
2. **Network reach to the node Postgres** at `10.42.10.76:5440` and the node
   API at `10.42.10.76:8090`.
3. **Schema parity.** The repo's `SCHEMA_VERSION`
   (`backend/db/postgres_migrations.py`, currently **35**) must match the node
   DB's `schema_version` (currently **35**). If your local repo is **ahead**,
   the worker will **auto-migrate the shared node DB on startup** — that is a
   real, shared-infra change. Keep the repo on the same revision as the node
   (`git pull`) before starting the worker unless you intend to migrate the
   node DB. If your local repo is **behind**, the worker still connects but
   won't downgrade; pull first.

---

## Install

```bash
# 1. First run seeds the env file and stops.
deploy/local-streaming/ccdash-stream.sh install

# 2. Fill in credentials.
$EDITOR ~/.ccdash/stream.env
#   - CCDASH_REPO          → your CCDash checkout path
#   - CCDASH_DATABASE_URL  → replace CHANGEME with the LAN dev password (ccdash)
#   - CCDASH_WORKER_PROJECT_ID stays ccp-2a984316f63a (the CCDash project)
#   - CCDASH_WORKER_WATCH_PROJECT_ID stays EMPTY (registry fan-out)

# 3. Re-run install to render + load both LaunchAgents.
deploy/local-streaming/ccdash-stream.sh install

# 4. Verify.
deploy/local-streaming/ccdash-stream.sh status
deploy/local-streaming/ccdash-stream.sh logs
```

The installer copies the wrappers to `~/.ccdash/bin/`, renders the plists into
`~/Library/LaunchAgents/`, and `launchctl bootstrap`s both agents. Secrets stay
in `~/.ccdash/stream.env` (mode 600) and never enter the plists.

### Env contract (the bits that matter)

| Var | Value | Why |
|-----|-------|-----|
| `CCDASH_RUNTIME_PROFILE` | `worker-watch` | filesystem watch + fan-out sync |
| `CCDASH_WORKER_PROJECT_ID` | `ccp-2a984316f63a` | **required non-empty**; worker binding |
| `CCDASH_WORKER_WATCH_PROJECT_ID` | *(empty)* | empty ⇒ watch **all** registered projects |
| `CCDASH_DB_BACKEND` | `postgres` | write to node Postgres |
| `CCDASH_DATABASE_URL` | node DSN | `…@10.42.10.76:5440/ccdash` |
| `CCDASH_WORKER_PROBE_PORT` | `9466` | avoid clashing with local dev (8000 / 9465) |

---

## Adding new projects

The worker only syncs projects that are **registered** in the node DB registry.
Registration enumerates `~/.claude/projects/<dir>` leaf dirs and POSTs each as
its own project (per-repo `sessionsPath`).

- **Automatic:** the `com.ccdash.register-projects` LaunchAgent runs at load and
  **every 6 hours** (`StartInterval=21600`) to pick up newly-used repos.
- **On demand:** `ccdash-stream.sh register`.

The curated filter (in `bin/ccdash-register.sh`):

```
--no-worktrees --min-sessions 5 \
--exclude=--claude-jobs --exclude=-private-tmp --exclude=intenttree-
```

- `--min-sessions 5` skips low-noise dirs; `--no-worktrees` skips worktree leaf
  dirs; the `--exclude` patterns drop known non-projects.
- The `--exclude=VALUE` form is **required** because the dir names start with
  `-`; `--exclude -claude-jobs` would be misparsed as a flag.
- To register something the filter excludes, edit the curated flags in
  `~/.ccdash/bin/ccdash-register.sh` (e.g. lower `--min-sessions`, or drop an
  `--exclude`), then run `ccdash-stream.sh register`.

Registration is **idempotent** — re-running never double-registers.

---

## Updating the worker

```bash
cd "$CCDASH_REPO"
git pull
# (re-check schema parity vs the node — see Prerequisites)
deploy/local-streaming/ccdash-stream.sh restart
```

If `git pull` advanced `SCHEMA_VERSION` past the node's, the **next worker start
will migrate the shared node DB**. Coordinate that intentionally.

---

## Known limitation — worktrees

Git worktrees are **not** folded into their parent project today. Each
registered project has a single `sessionsPath` and a flat layout, and
`--no-worktrees` skips worktree leaf dirs entirely. Folding worktree sessions
into the parent repo is **deferred to `remote-ccdash-streaming-v1` Phase 3/4**.
For now, worktree sessions are simply not streamed.

---

## Expected behaviors that look like errors but aren't

- **The node's OWN worker-watch may report `unhealthy` / log errors about these
  Mac paths.** If the node also runs a worker-watch container, it tries to stat
  `~/.claude/projects/...`-style paths that **don't exist on the node**. Those
  warnings are harmless — the Mac-local worker is the one actually syncing those
  projects. Do not chase them.
- **Worker-only enrichments degrade to zero/null** in surfaces that don't have a
  worker context — that is a contract state, not a bug.
- **Schema drift warning on start** is informational unless the worker actually
  ran a migration (see Updating).

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Worker won't start | `CCDASH_WORKER_PROJECT_ID` must be **non-empty** (required for worker-watch). Tail `~/.ccdash/logs/stream-worker.err.log`. |
| `venv python not found` | Run `npm run setup` in `$CCDASH_REPO`. |
| Nothing syncing for a repo | Is it **registered**? `ccdash-stream.sh register` then check `status` project count. Confirm its `sessionsPath` leaf dir exists under `~/.claude/projects`. |
| Can't reach node | `ccdash-stream.sh status` shows `health/ready: UNREACHABLE`. Verify `CCDASH_API` and that the node is up. |
| Unexpected node DB migration | Local repo `SCHEMA_VERSION` ran ahead of the node. Pin both to the same revision. |
| Port clash | Change `CCDASH_WORKER_PROBE_PORT` in `~/.ccdash/stream.env`, then `restart`. |

### Commands

```bash
ccdash-stream.sh status      # launchd state + node health/counts
ccdash-stream.sh logs        # tail -f the worker logs
ccdash-stream.sh restart     # after a git pull
ccdash-stream.sh register    # register new projects now
ccdash-stream.sh uninstall   # remove agents (keeps env + logs)
```
