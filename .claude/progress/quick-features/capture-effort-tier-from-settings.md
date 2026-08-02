---
doc_type: quick_feature
slug: capture-effort-tier-from-settings
title: Capture effort_tier from Claude Code settings.json as an env-var fallback
status: completed
tier: 0
created: 2026-08-02
completed: 2026-08-02
reviewer_verdict: APPROVE (codex gpt-5.6-terra, read-only; 1 re-pass)
intenttree_node: node_01KZ0CJN57C6C6HGMQJNSK0NQT
owner: opus-orchestrator
files_affected:
  - scripts/hooks/ccdash_capture_session_start.py
  - backend/tests/test_capture_session_start_hook.py
  - docs/guides/launch-time-capture-convention.md
routing:
  leg_1_implementation:
    task_class: implementation
    chosen_plugin_id: ica
    model: claude-sonnet-5[1m]
    agent_type_id: ica-executor
    fallback_chain: ["claude/claude-sonnet-5"]
  leg_2_review:
    task_class: code_review
    chosen_plugin_id: codex
    model: gpt-5.6-terra
    agent_type_id: codex-executor
    scope_flags: ["--sandbox read-only"]
    fallback_chain: ["claude/claude-sonnet-5"]
---

# Capture `effort_tier` from Claude Code settings

## Problem (verified, not assumed)

`scripts/hooks/ccdash_capture_session_start.py:180` sources `effortTier` from exactly one place:

```python
"effortTier": _nullable_str(env, "CCDASH_LAUNCH_EFFORT"),
```

`CCDASH_LAUNCH_EFFORT` is **never exported by any launcher**:

- `~/ica-claude.sh` exports `CCDASH_LAUNCHER` (L73), `CCDASH_LAUNCH_PROFILE` (L74),
  `CCDASH_LAUNCH_MODEL` (L90) — and **no** `CCDASH_LAUNCH_EFFORT`.
- The subscription lane has no wrapper at all, so it exports none of them.

Result: `effortTier` is structurally dead on **both** lanes — consistent with the observed
`0/14,399` population of `sessions.effort_tier`.

Meanwhile `~/.claude/settings.json` carries a top-level `effortLevel` (currently `'medium'`),
written by the `/effort` slash command. That is a readable, real signal the hook ignores.

## Change

Add a **settings fallback** for `effortTier` only. Resolution order, first non-empty wins:

1. `CCDASH_LAUNCH_EFFORT` env var — explicit launcher intent, always highest.
2. `effortLevel` from Claude Code settings files, in Claude Code's own precedence order
   (highest first):
   1. `<project>/.claude/settings.local.json`
   2. `<project>/.claude/settings.json`
   3. `$CLAUDE_CONFIG_DIR/settings.json`, else `~/.claude/settings.json`
3. `null`.

`<project>` resolves from the SessionStart payload's `cwd` field when present, else `Path.cwd()`.

## Invariants that must not regress

| Invariant | Requirement |
|---|---|
| Fail-open | Process always exits 0; `write_capture_sidecar` never raises. |
| Isolated failure | Settings read has its **own** inner try/except. Malformed JSON nulls *only* `effortTier` — `launcher`/`profile`/`modelVariant` still get written. |
| No defaulting | Absent / empty / unreadable → `null`. Never a default like `"medium"`. |
| Forward-compatible | **No allowlist.** Any non-empty stripped string passes through, so a future tier (`ultra`, …) is captured, not silently nulled. |
| Contract stability | Sidecar schema unchanged — `schemaVersion` stays `1`, no new keys. Writer↔parser contract (`backend/parsers/capture_sidecar.py`) untouched. |
| No schema work | No new DB columns; no dual SQLite/Postgres DDL; no `COLUMN_PARITY_DRIFT_ALLOWLIST` change. |
| Read-only | Hook never writes to any settings file. |

## Deliberate non-goals (deferred, not overlooked)

- **No `effortTierSource` provenance field.** Distinguishing "explicit launcher intent" from
  "static global default" has real value for the routing-feedback loop, but it would bump the
  pinned sidecar contract *and* require a new nullable column in both SQLite and Postgres DDL.
  Out of proportion to a hook tweak. Recoverable later.
- **No settings fallback for `modelVariant` / `profile`.** The same reader would support it
  (`settings.json` also carries `model`), but the named scope here is `effort_tier`.
- **Mid-session `/effort` changes are not reflected.** The hook fires once at SessionStart, so it
  captures launch-time effort. This is launch-time-capture semantics working as designed, not a
  bug — documented, not fixed.

## Acceptance criteria

- AC1 — `CCDASH_LAUNCH_EFFORT` set → that value wins, settings ignored.
- AC2 — env absent, user `settings.json` has `effortLevel` → captured.
- AC3 — precedence: project-local > project-shared > user.
- AC4 — `CLAUDE_CONFIG_DIR` honored for the user-settings location.
- AC5 — malformed / unreadable settings JSON → `effortTier` null **and** the other three capture
  fields still written to the sidecar.
- AC6 — no settings file anywhere → `effortTier` null.
- AC7 — `effortLevel: ""` (or whitespace) → null, not empty string.
- AC8 — a novel value (`"ultra"`) passes through unchanged (no allowlist).
- AC9 — sidecar keys and `schemaVersion` byte-identical to today for a given input; existing
  `test_capture_session_start_hook.py` and `test_capture_sidecar_ingestion.py` still pass.
- AC10 — hook exits 0 in every case above.

## Validation

```bash
backend/.venv/bin/python -m pytest backend/tests/test_capture_session_start_hook.py \
  backend/tests/test_capture_sidecar_ingestion.py -v
```

Plus a live end-to-end check: run the hook with a synthetic payload and confirm the sidecar
carries `effortTier: "medium"` from the real `~/.claude/settings.json`.

## Progress

| Task | Status |
|---|---|
| T0-001 Implement settings fallback in hook | completed |
| T0-002 Add unit tests (AC1–AC10) | completed |
| T0-003 Update `docs/guides/launch-time-capture-convention.md` | completed |
| T0-004 Reviewer gate (codex gpt-5.6-terra, read-only) | completed — APPROVE after 1 re-pass |
| T0-005 Live sidecar smoke | completed |
| T0-006 Commit + squash to main | completed |

## Validation record

`backend/.venv/bin/python -m pytest backend/tests/test_capture_session_start_hook.py
backend/tests/test_capture_sidecar_ingestion.py backend/tests/test_sessions_parser.py -q`
→ **82 passed** (46 in the two capture files).

Live smokes against the real machine state, all `exit=0`:

| Case | Result |
|---|---|
| env `SENTINEL_ENV_WINS` vs settings | `SENTINEL_ENV_WINS` — env wins (AC1) |
| user settings only | live `effortLevel` value picked up (AC2) |
| project `.claude/settings.json` vs user | `PROJ_WINS` (AC3) |
| project `settings.local.json` vs `settings.json` | `LOCAL_WINS` (AC3) |
| malformed settings, only candidate | `effortTier: null`, launcher/profile/modelVariant intact (AC5) |

**Mutation-verified**: appending the home candidate unconditionally (i.e. reintroducing the
"consults both locations" regression) makes `test_ac4b_claude_config_dir_set_excludes_home_settings`
fail with `assert 'HOME_SHOULD_BE_IGNORED' is None`. The exclusion test is load-bearing, not
tautological. Mutation reverted; hook byte-identical afterward.

## Reviewer gate record

Round 1 — `codex exec --sandbox read-only --model gpt-5.6-terra`: **REQUEST_CHANGES**.
All AC1–AC10 PASS on the implementation; 4 findings, all in tests/docs:

1. *major* — the AC4 test did not prove `~/.claude` is excluded when `CLAUDE_CONFIG_DIR` is set;
   a regression consulting both would have passed. Fixed with `ac4b` (exclusion) + `ac4c`
   (restores coverage of the plain `Path.home()` branch the autouse fixture had removed).
2. *minor* — AC9 non-string parameterization omitted lists. Added `[]` and `["high"]`.
3. *minor* — key test named "six keys" while asserting seven, and compared a set (blind to
   reordering). Renamed; now asserts `list(data.keys()) == [...]`.
4. *nit* — docs said a malformed file "nulls only `effortTier`"; actually the malformed candidate
   is *skipped* and resolution continues down the chain. Reworded.

Round 2 (delta only): **APPROVE** — all 4 FIXED, no new issues, confidence high.

## Corrections to the original plan

- **The sidecar has 7 keys, not 6** (`schemaVersion`, `sessionId`, `launcher`, `profile`,
  `effortTier`, `modelVariant`, `capturedAt`). The planning note said 6; that error propagated into
  a test name before the reviewer caught it.
- **`CCDASH_LAUNCH_EFFORT` is unset on *both* lanes, not just the subscription lane.**
  `~/ica-claude.sh` exports `CCDASH_LAUNCHER` (L73), `_PROFILE` (L74), `_MODEL` (L90) — never
  `_EFFORT`. The original framing ("dead on the subscription lane") understated the gap.
- **The staleness caveat was observed live, not just theorized.** `~/.claude/settings.json` read
  `medium` early in the implementing session and `xhigh` later — `/effort` changed it mid-session.
  A launch captures whatever the file says at `SessionStart`; a mid-session change is never
  re-captured. This is exactly the documented limitation, demonstrated.
