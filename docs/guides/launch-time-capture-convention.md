---
title: "Launch-time Capture Convention"
description: "Sidecar metadata for session launch context (profile, model, effort tier)"
nav_order: 70
parent: Guides
---

# Launch-time Capture Convention

The **launch-time capture sidecar** (`<session-id>.capture.json`) records metadata available only at Claude Code startup — launcher identity, deployment profile, effort tier, and model variant — that cannot be recovered from transcript logs. It is the canonical mechanism for all launch-context attributes.

## Transport & Location

- **Format:** Single JSON object sidecar file.
- **Primary location:** `~/.claude/projects/<encoded-cwd>/<session-id>.capture.json` — sibling of the session JSONL, co-located by stem.
- **Fallback location:** `data/capture/<session-id>.capture.json` (checked only if co-location unavailable).
- **Correlation key:** `sessionId` MUST equal the JSONL filename stem; missing or mismatched ⇒ sidecar ignored.

## Schema

| Field | Type | Null Semantics | Notes |
|-------|------|---|---|
| `schemaVersion` | int | constant `1` | Gates future format changes |
| `sessionId` | string | **correlation key** | MUST equal JSONL stem; absent/mismatch ⇒ ignored |
| `launcher` | string \| null | absent == `null` | Identity of launch path (e.g. `"ica-claude.sh"`); never defaulted |
| `profile` | string \| null | absent == `null` | Deployment profile (e.g. `"ica-delegate"`); never defaulted |
| `effortTier` | string \| null | absent == `null` | Effort/quality tier; never defaulted. `CCDASH_LAUNCH_EFFORT` env wins; falls back to settings.json `effortLevel` — see "`effortTier` settings.json fallback" below |
| `modelVariant` | string \| null | absent == `null` | Launch-time model (e.g. `"claude-opus-4-8[1m]"`); never defaulted |
| `capturedAt` | string (ISO-8601 UTC) \| null | absent == `null` | Hook write time; advisory only, not used for correlation |

**Null contract:** All fields except `schemaVersion` may be `null` or absent (equivalent semantics). No field is ever synthesized to a default value. Partial sidecars are valid.

## Environment Contract

| Variable | Set by | Maps to | Notes |
|----------|--------|---------|-------|
| `CCDASH_LAUNCH_PROFILE` | Wrapper script (e.g. `~/ica-claude.sh`) | `profile` field | Required for `ica-delegate` path; must export before `exec` |
| `CCDASH_LAUNCHER` | Wrapper script | `launcher` field | Descriptive; optional |
| `CCDASH_LAUNCH_EFFORT` | Launcher (conditionally) | `effortTier` field | Only when known; never defaulted |
| `CCDASH_LAUNCH_MODEL` | Launcher | `modelVariant` field | May read from `$ANTHROPIC_MODEL` at launch time |

**Writer:** `SessionStart` hook registered in `~/.claude/settings.json`, `~/.claude/ica-settings.json`, and `~/.claude/ica-gpt-shim-settings.json` (see "Activation" below for the live, verified registration — as of 2026-08-01 this is no longer a proposal, it is shipped). The hook:
- Reads the four env vars + `session_id`/`transcript_path` from stdin payload.
- Writes the sidecar to the primary location (co-located by stem).
- **Always exits 0** (fail-open: any serialization/I/O error ⇒ no sidecar written, session carries `null` capture fields).

## Fail-open & Reversibility

- **Launch impact:** Zero. Environment exports are non-fatal. Hook errors never block session start.
- **Parser behavior:** Missing or malformed sidecar ⇒ all four fields `null` (DEBUG log, never raises). Mirrors `workflow_sidecar.py` resilience.
- **Idempotency:** Re-parse reads the sidecar fresh. `sync_engine` uses COALESCE-on-null upsert for the four columns — a missing sidecar on re-parse MUST NOT overwrite a previously-captured value with stale `null`.
- **No retrospective backfill:** This is strictly launch-time capture. Capture-annotated sessions created in Phase 11+ forward only; pre-Phase-11 sessions carry `null` capture fields.
- **Disable cost:** Remove hook from settings.json, drop three export lines from wrapper. Existing sidecars become inert; columns remain nullable and harmless.

## Distinction: Not `workflow.json`

This sidecar is **distinct from** the Phase 5 `workflow.json` orchestration sidecar. The two differ in schema, correlation (stem-keyed vs `run_id`/`task_id` time-window join), and purpose. Capture is launch metadata; workflow is orchestration state. Both may use parser-module conventions but never overlap schemas.

## Backend Integration

- **Ingestion:** `backend/parsers/capture_sidecar.py` — pure, fail-open parser. Modeled on `workflow_sidecar.py`.
- **Collection site:** `parse_session_file` in `backend/parsers/platforms/claude_code/parser.py` (existing sidecar-collection block), via `_collect_capture_sidecar()`.
- **Promotion:** `AgentSession(...)` constructor attaches the four fields to the in-memory record.
- **Persistence:** `backend/db/sync_engine.py` writes four new nullable columns (T11-003).
- **Frontend surface:** the four fields reach `types.ts` + the session-detail contract (`api.py` `list_sessions`/`get_session`, `session_detail.py`) and render inside `SessionInspector.tsx`'s **`SessionForensicsView`** panel (not the top-level session header) — null/absent fields show an explicit muted "Not captured" row (T11-005).

## Activation (2026-08-01)

**Status: ACTIVE.** Before 2026-08-01 this convention was wired end-to-end but never actually fired: 0 of 17,292 rows on the live node Postgres carried a non-null `launcher`/`profile`/`effort_tier`/`model_variant` value, because nothing exported the `CCDASH_LAUNCH_*` env vars and the `SessionStart` hook was never registered in any settings file. Activation closed both gaps — hook registration in three settings files plus env exports in the ICA gateway launcher — with no code change to the hook writer, model-identity module, or any parser/repository path (docs + config only).

### Hook registration (verbatim, shipped)

Registered as a `SessionStart` hook, matcher `"startup|resume|clear|compact"`, `"timeout": 5`, command:

```
/usr/bin/python3 /Users/miethe/dev/homelab/development/CCDash/scripts/hooks/ccdash_capture_session_start.py
```

in all three of:

| File | Additional `env` block |
|------|------------------------|
| `~/.claude/settings.json` | `{"CCDASH_LAUNCHER": "subscription"}` |
| `~/.claude/ica-settings.json` | `{"CCDASH_LAUNCHER": "ica-claude.sh", "CCDASH_LAUNCH_PROFILE": "ica-delegate"}` |
| `~/.claude/ica-gpt-shim-settings.json` | `{"CCDASH_LAUNCHER": "ica-gpt-shim", "CCDASH_LAUNCH_PROFILE": "ica-gpt-shim"}` |

`~/ica-claude.sh` (the ICA gateway launcher — a plain file in `$HOME`, **not** a symlink, with no copy under `agentic_meta_dev`) now exports before its `exec claude` line:

```bash
export CCDASH_LAUNCHER="ica-claude.sh"
export CCDASH_LAUNCH_PROFILE="ica-delegate"
export CCDASH_LAUNCH_MODEL="<explicit --model from \"$@\" if present, else $ANTHROPIC_MODEL>"
# CCDASH_LAUNCH_EFFORT is not set here — effort is a per-session concept on this lane (see Limitation 3 below).
```

Both `--model X` and `--model=X` forms are parsed when resolving `CCDASH_LAUNCH_MODEL`.

### Precedence (empirically settled)

The main pre-activation risk was mislabeling: would a subscription-lane default (`CCDASH_LAUNCHER=subscription` in `~/.claude/settings.json`) leak into an ICA-launched session? Verified answer: no. A session launched via `~/ica-claude.sh` records `launcher="ica-claude.sh"`, never `"subscription"` — the `--settings ica-settings.json` env block plus the shell's own `export CCDASH_LAUNCHER=...` both take precedence over the base settings file's env block. Settings-file layering does not introduce a mislabeling risk.

### Launcher → provider-channel mapping (observed)

Captured via the real parser (`parse_session_file`) and `derive_provider_identity` run against live sessions launched through each path:

| Launch path | `launcher` | `profile` | `effortTier` | `modelVariant` | `providerChannel` | `providerLabel` |
|---|---|---|---|---|---|---|
| `~/ica-claude.sh` | `ica-claude.sh` | `ica-delegate` | `None` | `claude-haiku-4-5[1m]` | `ica` | `Anthropic · Claude Code · ICA` |
| `claude` (direct) | `subscription` | `None` | `None` | `None` | `subscription` | `Anthropic · Claude Code` |

The channel rule itself (`backend/model_identity.py:188-194`): a non-empty `launcher` containing `"ica"` → `"ica"`; containing `"api"` → `"api"`; any other non-empty value → `"subscription"`; an empty/absent `launcher` falls through to the `model_variant` `"[1m]"` heuristic.

### Verification recipe (reproducible)

1. Launch a session through the path you want to verify (e.g. `~/ica-claude.sh` or plain `claude`).
2. Confirm the sidecar landed next to the transcript: `ls ~/.claude/projects/<encoded-cwd>/<session-id>.capture.json`.
3. Run the real parser plus provider-identity derivation against it — no server, no DB, no mocks:

```python
from pathlib import Path
from backend.parsers.sessions import parse_session_file
from backend.model_identity import derive_provider_identity

jsonl = Path("~/.claude/projects/<encoded-cwd>/<session-id>.jsonl").expanduser()
session = parse_session_file(jsonl)
identity = derive_provider_identity(
    getattr(session, "model", None),
    getattr(session, "platformType", None),
    getattr(session, "launcher", None),
    getattr(session, "modelVariant", None),
)
print(session.launcher, session.profile, session.effortTier, session.modelVariant,
      identity["providerChannel"], identity["providerLabel"])
```

A non-null `launcher` on the printed line confirms both halves of the contract: the hook fired at `SessionStart`, and the parser's primary co-located probe (`path.with_name(f"{path.stem}.capture.json")`, `parser.py:853`) found it.

### Known limitations and horizons

These are real, permanent characteristics of the design — not open bugs to fix:

1. **Re-sync mtime gate.** `backend/db/sync_engine.py:4967-4973` short-circuits before reparse when a JSONL's mtime matches the cached value from the last sync. Writing a capture sidecar does not touch the JSONL's own mtime, so a sidecar that appears *after* a session was already ingested is invisible to ordinary incremental sync — only a forced re-sync (reparse via `parse_session_file` then delete/reinsert, `sync_engine.py:4985-5001`) picks it up. This does **not** affect newly-launched sessions: the hook writes the sidecar at `SessionStart`, before the JSONL is written, so the first sync of that session already sees it.
2. **Fallback-path mismatch.** When the hook's stdin payload carries no `transcript_path`, the writer falls back to `<cwd>/data/capture/<session_id>.capture.json` (`scripts/hooks/ccdash_capture_session_start.py::_resolve_sidecar_path`), while the parser's fallback probe looks under `<jsonl_parent>/../data/capture/<raw_session_id>.capture.json` (`backend/parsers/platforms/claude_code/parser.py:865-866`). These two paths generally do not coincide, so a launch without `transcript_path` can silently produce an unfindable sidecar. In practice Claude Code always supplies `transcript_path` (confirmed empirically — every capture sidecar produced during activation landed co-located), so this is a latent risk, not an active one.
3. **`effortTier` is not capturable at launch on the subscription lane — partially superseded, see "`effortTier` settings.json fallback" below.** `CCDASH_LAUNCH_EFFORT` is still not exported by any launcher, so a *launch-time* effort tier is never directly observed. The fallback below closes most of the gap by reading the `/effort` slash command's persisted value instead, but it is a **snapshot at `SessionStart`, not a live launch signal** — see the staleness caveat.
4. **`modelVariant` is the requested launch model, not the effective one.** A mid-session `--fallback-model` hop or a `/model` switch is never reflected retroactively — best-effort by design, captured once at `SessionStart`.
5. **Subagent sessions carry `null` capture fields by contract.** `backend/parsers/platforms/claude_code/parser.py:849-850`: `if is_subagent or not raw_session_id: return _null`. The `SessionStart` hook only fires for root (interactive) sessions; family-root propagation is out of scope.
6. **Backfill horizon — permanent, not queued.** The ~17,292 pre-activation rows can never be enriched, for two independent reasons: the launch environment that would have populated a sidecar is unrecoverable (no sidecar was ever written, and none can be reconstructed after the fact), and Limitation 1 means even a manufactured sidecar would still need a forced re-sync to be picked up. Treat this as a permanent known horizon in any historical analytics, not a backlog item.

### `effortTier` settings.json fallback

`CCDASH_LAUNCH_EFFORT` is exported by no known launcher. As a fallback, the hook also reads the top-level `effortLevel` key that the `/effort` slash command persists to Claude Code settings files. Resolution is first-non-empty-string-wins:

1. `CCDASH_LAUNCH_EFFORT` env var — explicit launcher intent, always highest priority.
2. `effortLevel` from settings files, checked in this order:
   a. `<project>/.claude/settings.local.json`
   b. `<project>/.claude/settings.json`
   c. `$CLAUDE_CONFIG_DIR/settings.json` if `CLAUDE_CONFIG_DIR` is set and non-empty, else `~/.claude/settings.json`
3. `null` — no defaulting, no allowlist. Any non-empty stripped string (including a future tier name) passes through as-is; a non-string, empty, or whitespace-only value is treated as absent.

`<project>` is the SessionStart payload's `cwd` field when present, else the hook process's working directory. Each candidate file in the precedence chain above is independent: a missing, unreadable, or malformed candidate (or one with no usable `effortLevel`) is skipped, and resolution continues to the next-lower-precedence candidate — so, for example, a malformed project-local `settings.json` plus a valid user-level `settings.json` still yields the user tier, not `null`. `effortTier` resolves to `null` only when every candidate in the chain is exhausted without producing a non-empty string. Separately, this whole settings lookup runs inside its own isolated failure path: however it fails, it only nulls `effortTier` — `launcher`, `profile`, and `modelVariant` are written from the env vars regardless. Implementation: `_settings_effort_level()` in `scripts/hooks/ccdash_capture_session_start.py`.

**Staleness caveat:** `effortLevel` is whatever `/effort` last set for that settings scope — it reflects the last time the user (or a config sync) changed the tier, not necessarily the tier in effect for *this* session if it was changed mid-session or the settings file predates the session by a long margin. Treat it as "the tier this launch environment was configured for," not a verified live value. Limitation 3 above (no direct launch-time effort signal) still holds in spirit — this fallback is a best-effort proxy, not a fix for the underlying gap.

## For Subagents

Subagent records legitimately carry `null` capture fields — a valid contract state, not a defect. The `SessionStart` hook fires only for root (interactive) sessions. Family-root propagation is out of scope.

---

**Phase 12 CLAUDE.md rollup bullet:**
- **Launch-time capture convention**: `docs/guides/launch-time-capture-convention.md` — sidecar metadata for session profile/model/effort; see "Env Contract" for `CCDASH_LAUNCH_*` settings.json hook registration.
