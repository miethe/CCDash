---
title: "Codex Session Ingestion v1 \u2014 implementation plan"
doc_type: implementation_plan
feature_slug: codex-session-ingestion-v1
category: features
status: completed
schema_version: 2
created: 2026-06-28
updated: '2026-06-28'
tags:
- codex
- parser
- sync
- multi-platform
- watcher
- attribution
prd_ref: ''
---

# Codex Session Ingestion v1

> Ingest OpenAI Codex CLI session logs into CCDash and **merge them into the same project**
> as Claude Code sessions, so a project's Session board shows both agents side-by-side.

## Bottom line up front

This is **wiring + attribution + validation, not a greenfield parser**. A substantial Codex
parser already exists and **works on current real files** (verified 2026-06-28 against
`~/.codex/sessions/2026/06/28/rollout-…jsonl`: parsed OK, `platformType="Codex"`, 33 logs,
full forensics). The registry already dispatches to it. The reason no Codex data appears today
is purely that **nothing feeds Codex files to the parser** — the worker only watches
`~/.claude/projects`, and project attribution is path-derived (Codex files live under a date
tree with no project in the path).

## Current state (verified, with anchors)

| Piece | State | Anchor |
|---|---|---|
| Codex parser | **Exists, functional** (1,277 lines) | `backend/parsers/platforms/codex/parser.py` — `parse_session_file()` :448, `_looks_like_codex()` :423 |
| Parser dispatch | **Already wired** (Codex first, Claude fallback) | `backend/parsers/platforms/registry.py:18-21` |
| Session id scheme | `S-rollout-<stem>` (unique; no collision with Claude `S-<uuid>`) | parser output (verified) |
| `platform_type` column | Exists, default `'Claude Code'`; parser emits `'Codex'` | `backend/db/postgres_migrations.py:141`, `sqlite_migrations.py` mirror |
| `source_provenance` | Exists on `session_messages` | `postgres_migrations.py:294` |
| Sessions source chip / `_derive_session_source` | Claude/remote/entire/unknown — **no codex variant** | `backend/application/services/agent_queries/session_detail.py` |
| Codex sessions on disk | **~1,769** active (+~1,985 incl. archived) | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` |

### The gaps (the actual work)

1. **No watch/scan root for `~/.codex/sessions`.** The worker derives watch dirs from each
   project's `sessions_path` (under `~/.claude/projects`). Codex files are never enumerated.
2. **No cwd→project attribution.** The sync engine assigns `project_id` from the path/project a
   file lives under. Codex files carry their project only *inside* the file
   (`session_meta.payload.cwd`, e.g. `/Users/miethe/dev/homelab/development/skillmeat`). There is
   no resolver from a raw repo cwd to a CCDash `project_id`.
3. **Source not surfaced.** `_derive_session_source` has no `codex` branch; UI has no Codex chip/filter.
4. **Title empty** on parsed Codex sessions (cosmetic) — derive from first user message.

## Open design decisions (need your call before build)

### D1 — cwd → project attribution strategy  ⟵ the crux
Claude projects store `sessions_path = ~/.claude/projects/<encoded-cwd>`, and Claude Code encodes
both `/` and `_` as `-`, so the encoded dir is **lossy** — you cannot reliably decode it back to a
real repo path. Options:

- **D1-a (recommended): store canonical repo path on the project.** Add a `repo_path` (or reuse an
  existing `path`) column populated at registration time (the registration script and `/api/projects`
  POST both know the real cwd). Resolve a Codex `cwd` to a project by **exact, then longest-prefix**
  match against `repo_path`. Deterministic, robust to nested worktrees.
- **D1-b: heuristic suffix match** on the encoded `sessions_path` (decode best-effort, match by
  trailing path segments). No schema change, but fragile for names containing `_` or `-`.
- **D1-c: a standalone `source_roots`/`cwd_map` registry** mapping cwd globs → project_id, seeded by
  the register script.

### D2 — unattributable Codex sessions (cwd matches no registered project)
- **D2-a (recommended): skip + count.** Don't ingest; log a one-line summary of skipped cwds so you
  can decide whether to register that project. (No orphan rows; matches "no silent caps" by logging.)
- **D2-b: ingest with `project_id = NULL`** (an "Unattributed" bucket). Note: `sessions.project_id`
  has no FK, so this is allowed, but the UI would need an unattributed view.

### D3 — backfill scope for the first run
~1,769 files. **D3-a (recommended):** backfill all under a bounded, recent-first pass (reuse the
existing recent-first sync knobs). **D3-b:** last-N-days only, then live-watch forward.

## Phases

### Phase 1 — Attribution resolver + project repo_path (depends on D1)
- Add/confirm `projects.repo_path` (dual DDL: SQLite + Postgres `CREATE TABLE` + `_ensure_column`;
  `COLUMN_PARITY_DRIFT_ALLOWLIST` check per CLAUDE.md). Populate from `scripts/register_claude_projects.py`
  and the `/api/projects` create path.
- New `resolve_project_for_cwd(cwd: str) -> str | None` (longest-prefix match) in the sync layer.
- Tests: exact match, nested-worktree longest-prefix, no-match → None.

### Phase 2 — Codex source root + sync attribution
- Add `~/.codex/sessions` as a watch/scan root (config-gated, e.g. `CCDASH_CODEX_INGEST_ENABLED`,
  `CCDASH_CODEX_SESSIONS_PATH` default `~/.codex/sessions`).
- In the sync path, when a parsed session is Codex (`platformType=='Codex'`), set `project_id` via
  `resolve_project_for_cwd(payload.cwd)` instead of path-derived attribution. Apply D2 for misses.
- Ensure `cwd` is captured onto the session row (surface from parser forensics).
- Tests: a Codex fixture attributes to the right project; an unmatched cwd follows D2.

### Phase 3 — Source surfacing (backend + FE)
- `_derive_session_source`: add `codex` branch (from `platform_type`/`source_provenance`).
- FE: Codex chip on session cards + a source filter value. Reuse existing chip styling.
- Title derivation for Codex sessions (first user message) — cosmetic.

### Phase 4 — Worker wiring + verification
- Wire the Codex root into the persistent worker-watch fan-out (launchd streamer env).
- Backfill per D3; verify on the node UI: Codex sessions appear **in the same projects** as Claude
  (e.g. skillmeat shows both), transcripts render, source chip shows Codex.
- Runtime smoke gate (per CLAUDE.md): browser check on `http://10.42.10.76:3010` before phase-complete.

## Risks / notes
- **Format drift:** parser verified on a 2026-06-28 file (cli 0.64.x); pin a couple of fixture files
  spanning older/newer rollouts to guard against Codex format changes.
- **Dedup:** id scheme is distinct from Claude; no collision. Confirm re-sync is idempotent (replace,
  not append) as with Claude.
- **No new migration for `platform_type`/`source_provenance`** (exist). Only D1 may add `repo_path`.
- **Remote streaming:** since attribution is by cwd and the Mac worker writes straight to node PG, no
  node-side change is required beyond a redeploy that includes Phase 2/3 code.

## Acceptance criteria
- AC1: With `CCDASH_CODEX_INGEST_ENABLED=1`, Codex rollout files under `~/.codex/sessions` are parsed
  and stored with `platform_type='Codex'`.
- AC2: A Codex session whose `cwd` matches a registered project's `repo_path` is attributed to **that
  same project_id** (merged with Claude sessions). [D1]
- AC3: Unmatched cwds are handled per D2 (skipped+counted, or NULL bucket) — explicit, never a crash.
- AC4: The node UI shows Codex sessions in the correct projects with rendered transcripts and a Codex
  source indicator. (runtime smoke)
- AC5: Re-running sync is idempotent (no duplicate sessions/messages).
- AC6: Codex ingestion is fully gated; with the flag off, behavior is unchanged for Claude.
