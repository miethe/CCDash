# Phase 11 — Launch-time Capture Transport Decision (OQ-5 / T11-001)

**Status:** Decided · **Date:** 2026-06-11 · **Owner:** python-backend-engineer
**Scope:** Resolves OQ-5 before any capture code (T11-002/004) is written.

---

## 1. Decision + Rationale

**Chosen transport: (C) sidecar-file convention, WRITTEN by a (B) Claude Code `SessionStart` hook, with the profile env supplied by (A) `~/ica-claude.sh`.**
A pure wrapper around `~/ica-claude.sh` cannot satisfy AC-11.A on its own: the script just runs `exec claude --settings … "$@"`, and the session UUID is minted by Claude Code **after** launch — the wrapper never sees a `session_id` to key a sidecar by. Conversely, the parser's correlation key is unambiguous: `_extract_raw_session_id` (`backend/parsers/platforms/claude_code/parser.py:473-476`) returns `path.stem` for root sessions, i.e. the session is identified by the JSONL filename stem at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. The `SessionStart` hook is the **only** launch-path component that knows both the launch profile (read from env) **and** the `session_id`/`transcript_path` (delivered on the hook's stdin payload), so it is the natural writer. The parser already has a mature, schema-driven per-session sidecar-collection idiom (`_collect_session_env_sidecar`, `_resolve_session_sidecar_root`, parser.py:3849-3853), so ingestion is an additive collector, not new machinery. `~/ica-claude.sh` is reduced to a one-line `export CCDASH_LAUNCH_PROFILE=ica-delegate` (the env contract), keeping it fail-open and trivially reversible. This combination is the minimum that makes the `ica-delegate` path mandatory while leaving effort/model best-effort.

**Why not the alternatives alone:**
- **(A) wrapper-only** — refuted: no `session_id` at launch ⇒ cannot key a sidecar; would force a brittle "newest JSONL" race heuristic. Wrapper is retained *only* as the env source.
- **(B) hook-only writing into the DB/parser directly** — rejected: couples a launch-time hook to the DB/sync layer, violates fail-open isolation, and bypasses the existing pure-parser sidecar idiom.

---

## 2. Sidecar Schema — `<session-id>.capture.json`

Pure JSON object, all metadata fields nullable. Mirrors the `workflow_sidecar.py` resilience contract (malformed/missing ⇒ `None`/null, never raises).

```json
{
  "schemaVersion": 1,
  "sessionId": "3e67572b-dc6b-4750-a09e-14a4e34f67a5",
  "launcher": "ica-claude.sh",
  "profile": "ica-delegate",
  "effortTier": null,
  "modelVariant": "claude-opus-4-8[1m]",
  "capturedAt": "2026-06-11T18:30:00Z"
}
```

| Field | Type | Required | Null semantics |
|-------|------|----------|----------------|
| `schemaVersion` | int | yes | constant `1`; gates future format changes |
| `sessionId` | string | yes | **correlation key**; MUST equal the JSONL stem. Absent/mismatch ⇒ sidecar ignored |
| `launcher` | string \| null | no | identity of the launch path (e.g. `"ica-claude.sh"`). `null` when launched directly |
| `profile` | string \| null | no | MUST be `"ica-delegate"` on the `~/ica-claude.sh` path. `null` otherwise |
| `effortTier` | string \| null | no | Ultracode/effort tier; `null` unless launcher exposes it. **Never defaulted** |
| `modelVariant` | string \| null | no | launch-time model id (e.g. `"claude-opus-4-8[1m]"`); `null` when unknown |
| `capturedAt` | string (ISO-8601 UTC) \| null | no | hook write time; advisory only, not used for correlation |

**Null contract:** absent field == `null` == "not captured". No field is ever synthesized to a default. Partial sidecars are valid — only present fields populate.

---

## 3. Correlation Key + On-disk Location + Parser Hook Point

- **Correlation key:** `session_id` == JSONL filename stem (`_extract_raw_session_id`, parser.py:473-476).
- **On-disk location (primary, co-located by stem):**
  `~/.claude/projects/<encoded-cwd>/<session-id>.capture.json`
  i.e. a **sibling** of `<session-id>.jsonl`. The hook derives this directly from its `transcript_path` payload field as `path.with_name(f"{stem}.capture.json")` — no `claude_root` detection or subdir guess needed.
- **Parser locates it as:** `path.with_name(f"{path.stem}.capture.json")` (root sessions). The parser already resolves `path` for every session, so the lookup is a single `Path` derivation.
- **Parser hook point (ingestion attaches here):**
  - New pure module `backend/parsers/capture_sidecar.py` — `parse_capture_sidecar(path) -> CaptureSidecar | None`, modeled on `backend/parsers/workflow_sidecar.py` (fail-open, DEBUG-log, never raises). **Kept distinct from `workflow_sidecar.py`** per the phase scope boundary.
  - Collection site: `parse_session_file` in `backend/parsers/platforms/claude_code/parser.py`, in the sidecar-collection block at **parser.py:3849-3853** (alongside `_collect_session_env_sidecar`), via a new `_collect_capture_sidecar(path, raw_session_id, forensics_schema)` that wraps the pure parser and returns `{launcher, profile, effortTier, modelVariant}` (all-null on miss).
  - Promotion site: the `AgentSession(...)` constructor at **parser.py:4400** — thread the four fields onto the record (T11-005 adds `launcher`/`profile`/`effortTier`/`modelVariant` to `backend/models.py` + `types.ts`).
  - Persistence: `backend/db/sync_engine.py` writes the four fields to the T11-003 dual-backend columns.
- **Subagent note:** capture targets the **root** session (the `SessionStart` hook fires for the interactive launch). Subagent records (`is_subagent`, stem-derived from `path.parent.parent.name`) legitimately carry `null` capture fields — a contract state, not a defect. Family-root propagation is out of scope (best-effort null is acceptable per AC-11.A/E).
- **Fallback location (only if co-location proves infeasible on any host):** a dedicated dir under CCDash data, `data/capture/<session-id>.capture.json`. The collector checks the co-located sibling first, then this fallback dir by stem. Documented as a secondary path; co-location is primary.

---

## 4. Env Contract

| Variable | Set by | Maps to sidecar field | Notes |
|----------|--------|-----------------------|-------|
| `CCDASH_LAUNCH_PROFILE` | `~/ica-claude.sh` (`export CCDASH_LAUNCH_PROFILE=ica-delegate`) | `profile` | **Required** for AC-11.A on the ica path |
| `CCDASH_LAUNCHER` | `~/ica-claude.sh` (`export CCDASH_LAUNCHER=ica-claude.sh`) | `launcher` | Descriptive; `null` when unset |
| `CCDASH_LAUNCH_EFFORT` | launcher, **only when known** (e.g. an Ultracode path) | `effortTier` | Best-effort; unset ⇒ `null`. Never defaulted |
| `CCDASH_LAUNCH_MODEL` | launcher (`export CCDASH_LAUNCH_MODEL="$ANTHROPIC_MODEL"`) | `modelVariant` | Real launch-time fact (ica-claude.sh already sets `ANTHROPIC_MODEL=claude-opus-4-8[1m]`); unset ⇒ `null` |

**Writer:** the `SessionStart` hook (registered in `~/.claude/settings.json`; ica runs use `~/.claude/ica-settings.json`, so the hook must be present in BOTH settings files, or in the user-global block both inherit). The hook reads the four env vars + `session_id`/`transcript_path` from its stdin payload and emits the sidecar. The hook holds **no** defaults — any var it cannot read is written as `null`/omitted.

---

## 5. Fail-open Behavior + Reversibility Cost

**Fail-open (capture must never block or alter launch):**
- `~/ica-claude.sh`: env exports are non-fatal additive lines before `exec`; an `export` cannot fail the launch. No new `exit` paths.
- `SessionStart` hook: wraps all work in a catch-all and **always exits 0**; any error (missing payload, unwritable dir, serialization failure) ⇒ no sidecar written ⇒ session simply carries `null` capture fields. The hook never emits blocking output.
- Parser: missing/malformed sidecar ⇒ all four fields `null` (DEBUG log, never raises), per the `workflow_sidecar.py` contract.
- Idempotency (AC-11.C): re-parse reads the sidecar fresh; if the sidecar later disappears, `sync_engine` MUST NOT clobber a previously-captured value with a stale `null` (COALESCE-on-null upsert for the four columns).

**Reversibility cost: LOW.**
- Disable = remove the hook entry from `settings.json`/`ica-settings.json` and drop the `export` lines from `~/ica-claude.sh` (≤3 lines). Existing sidecars are inert.
- Schema columns are nullable and additive — no data migration to roll back; leaving them unused is harmless.
- No retrospective backfill, so there is no historical state to unwind. Pre-capture and post-disable sessions are identical (`null` capture fields).

---

## 6. ADR-note (sets a lasting convention)

This establishes the **launch-time capture sidecar** convention: a small JSON sidecar `<session-id>.capture.json`, co-located by stem next to the session JSONL, written fail-open by a Claude Code `SessionStart` hook that reads a `CCDASH_LAUNCH_*` environment contract populated at the launch path (e.g. `~/ica-claude.sh`). It is the canonical mechanism for any attribute that exists **only at launch time** and cannot be recovered from transcript logs (launcher identity, launch profile such as `ica-delegate`, effort tier, model variant). It is deliberately **distinct from** the Phase 5 `workflow.json` orchestration sidecar (different schema, different correlation: stem-keyed vs `run_id`/`task_id` ±1-min join) — the two may share parser-module conventions but never schemas. Correlation is always the session_id/JSONL stem; ingestion is a pure, fail-open parser collector attaching at `parse_session_file`; all fields are nullable with strict no-default semantics (unknown == absent == null). Future launch-time attributes SHOULD extend this sidecar (bump `schemaVersion`) rather than introduce new transports. Recommend recording as a short ADR alongside ADR-006/007 in `docs/project_plans/adrs/` during the Phase 12 rollup.
