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
| `effortTier` | string \| null | absent == `null` | Effort/quality tier; never defaulted or inferred |
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

**Writer:** `SessionStart` hook registered in both `~/.claude/settings.json` and `~/.claude/ica-settings.json` (or inherited via user-global settings block). The hook:
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

## For Subagents

Subagent records legitimately carry `null` capture fields — a valid contract state, not a defect. The `SessionStart` hook fires only for root (interactive) sessions. Family-root propagation is out of scope.

---

**Phase 12 CLAUDE.md rollup bullet:**
- **Launch-time capture convention**: `docs/guides/launch-time-capture-convention.md` — sidecar metadata for session profile/model/effort; see "Env Contract" for `CCDASH_LAUNCH_*` settings.json hook registration.
