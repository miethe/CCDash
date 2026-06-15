---
title: Offline CLI Guide
description: Use the repo-local CCDash CLI to read session data directly from source without a running server or worker
audience: developers, operators
tags: [cli, offline, sessions, sync]
created: 2026-06-15
updated: 2026-06-15
category: How-To
status: stable
related: ["cli-user-guide.md", "cli-timeout-debugging.md", "query-cache-tuning-guide.md"]
---

## What is offline mode?

Offline mode lets the **repo-local CLI** (`backend/.venv/bin/ccdash` / `python -m backend.cli`)
parse session JSONL files directly from disk — no running CCDash server, no worker, no network
connection required.

**When to use it:**

- Fresh checkout of a project with existing JSONL logs and no worker running yet
- Laptop / air-gapped environment where the backend is not started
- Quick session lookup without waiting for a full `npm run dev` startup
- CI or scripted audit pipelines that only need read access

> **Not the standalone CLI.** The standalone `ccdash-cli` package (installed via
> `pipx install ccdash-cli`) is HTTP-only and requires a live server.  Offline mode is
> exclusively a feature of the repo-local CLI in `backend/`.

---

## Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--offline` | off | Enable offline mode (or set `CCDASH_OFFLINE=1`) |
| `--ephemeral` | off | Use a throwaway temp-file DB; discarded on exit |
| `--refresh` | off | Force a full re-parse of all session files, ignoring the incremental cache |
| `--config <path>` | see below | Override the offline project registry path |

All flags are global options placed before the sub-command:

```bash
backend/.venv/bin/ccdash --offline [--ephemeral] [--refresh] [--config <path>] <command>
```

---

## The offline project registry

Offline mode needs to know where your project's session files live.  It reads a
`projects.json` file (the same export shape used by the DB-authoritative project registry)
to locate the filesystem paths.

### Resolution precedence

1. `--config <path>` (explicit override)
2. `CCDASH_PROJECTS_FILE` environment variable
3. `~/.ccdash/projects.json`
4. `./projects.json` (current working directory)

If none of these exist the CLI exits with a clear message asking you to export a registry.

### Obtaining a registry file

**From a running standalone CLI:**

```bash
ccdash project list --output json > ~/.ccdash/projects.json
```

**From the repo's existing file:**

```bash
cp projects.json ~/.ccdash/projects.json
```

### Minimal registry example

```json
{
  "projects": [
    {
      "id": "my-project",
      "name": "My Repo",
      "isActive": true,
      "pathConfig": {
        "sessions": {
          "sourceKind": "filesystem",
          "filesystemPath": "/home/user/myrepo/.claude/sessions"
        }
      }
    }
  ]
}
```

The `sourceKind` must be `"filesystem"` with a `filesystemPath` that resolves on the local
machine.  `github_repo` and `project_root` source kinds are not supported in offline mode
(they require network or a resolved workspace root not available without the backend).

---

## The local cache DB

Offline mode maintains its own SQLite cache database separate from the server's
production DB.

| Mode | DB path | Persisted? |
|------|---------|-----------|
| Default | `~/.ccdash/offline-cache.db` | Yes — incremental re-runs are fast |
| `--ephemeral` | temp file (auto-deleted on exit) | No |

On each run the sync engine performs an incremental parse (recent-first, light-mode) so
repeated invocations are fast.  Use `--refresh` to force a full re-parse of all JSONL
files, useful after a large batch of new sessions or if the cache appears stale.

The offline DB is always a **separate file** from the server's DB.  It never shares a
connection with `data/ccdash_cache.db`.

---

## What works offline

| Command | Works? | Notes |
|---------|--------|-------|
| `ccdash status project` | ✓ | Shows session/feature counts from parsed logs |
| `ccdash session search <query>` | ✓ | Full-text search over parsed sessions |
| `ccdash session get <id> --project <id>` | ✓ | `--project` required (cross-project isolation invariant) |
| `ccdash session transcript <id> --project <id>` | ✓ | `--project` required |
| `ccdash feature report <id>` | ✓ (partial) | Works to the extent session→feature links were parsed |
| `ccdash workflow failures` | ✓ (partial) | Tool-error counts from JSONL; rollup KPIs absent |
| `ccdash report aar --feature <id>` | ✓ (partial) | Narrative from parsed data; intelligence facts absent |

> **`session get` and `session transcript` always require `--project <id>`.**  There is no
> active-project fallback for these commands even online; the cross-project isolation
> invariant is enforced in both modes.

---

## What degrades and why (the offline banner)

When offline mode is active, the CLI emits a banner to stderr before every command:

```
⚠  Offline mode: results parsed directly from local session logs.
   Cost, analytics, and cross-run intelligence require the full backend and are
   omitted or shown as zero.
```

The following enrichments are **not available offline** because they are computed by the
worker sync pipeline — not derivable from raw JSONL alone:

| Field category | Examples | Why absent |
|---------------|---------|------------|
| Cost / pricing | `total_cost`, `cost_usd`, `pricing_model_source` | Pricing model resolution is worker-only |
| Analytics KPIs | session-over-session trends, p95 duration | Aggregated by the analytics worker pass |
| Context observability | context-window fill %, pressure score | Computed during worker backfill |
| Intelligence facts | sentiment, churn score, scope-drift | `backfill_session_intelligence=False` offline |
| Commit correlations | linked commits, PR coverage | Require VCS integration run by worker |
| Cross-run comparisons | baseline comparisons, regression deltas | Need prior DB runs to compare against |

These appear as `0`, `0.0`, `""`, or `null` in JSON output — this is a **contract state**,
not a bug.  The banner makes the degradation explicit so downstream consumers know to expect it.

---

## Read-only guarantee

Offline sync always runs with `allow_writeback=False`.  This means:

- No files in the project repository are written or modified
- No progress markers, status files, or sidecar files are created
- The project's JSONL and markdown source files are read-only inputs

The only writes are to the offline cache DB (`~/.ccdash/offline-cache.db` or the ephemeral
temp file), which is isolated from the project tree.

---

## Examples

```bash
# Quick project status check — no server needed
backend/.venv/bin/ccdash --offline status project

# Search sessions in a specific project
backend/.venv/bin/ccdash --offline --project my-project session search "authentication"

# Get a session detail (project required)
backend/.venv/bin/ccdash --offline session get <session-id> --project my-project

# Feature forensics report as JSON (for scripting)
backend/.venv/bin/ccdash --offline --output json feature report FEAT-123

# Force full re-parse (after a large batch of new sessions)
backend/.venv/bin/ccdash --offline --refresh status project

# Throwaway run — no persistent cache file
backend/.venv/bin/ccdash --offline --ephemeral status project

# Custom registry location
backend/.venv/bin/ccdash --offline --config /path/to/projects.json status project

# Same via python -m
python -m backend.cli --offline --project my-project session search "timeout"
```

---

## Troubleshooting

**"Offline registry not found"**
No `projects.json` was found in any of the resolution candidates.  Export one:

```bash
ccdash project list --output json > ~/.ccdash/projects.json
```

Or pass `--config <path>` pointing to a valid registry file.

**"Project not found in the offline registry"**
The `--project` value doesn't match any `id` field in the registry.  Check
`ccdash project list` (if a server is available) or inspect the JSON directly.

**"Sessions directory not found"**
The `filesystemPath` in the registry doesn't exist on this machine.  Update the registry
with the correct local path.

**Stale or incomplete results**
Run with `--refresh` to force a full re-parse.  If the sessions directory is very large,
this may take a minute; subsequent runs will be incremental again.

**Cost / analytics fields show zero**
Expected.  See [What degrades and why](#what-degrades-and-why-the-offline-banner) above.
Start the full backend (`npm run dev`) and worker (`npm run dev:worker`) for enriched results.

---

## See also

- `backend/cli/offline.py` — offline bootstrap implementation
- `docs/guides/cli-user-guide.md` — full repo-local CLI reference
- `docs/guides/query-cache-tuning-guide.md` — cache TTL tuning for the online CLI
