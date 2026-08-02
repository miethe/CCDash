## Completion Report

### Summary
Implemented Gap 3 of `node_01KZ1RZ0X3T1AGDKN8GW8BVM3C`: the Codex parser now resolves the Codex-native reasoning-effort value from a session's JSONL entries and stores it verbatim on `AgentSession.effortTier`, which flows into the existing (already-nullable, already-schema-present) `sessions.effort_tier` column with no repository/DDL changes. Precedence is `payload.effort` (primary) then `payload.collaboration_mode.settings.reasoning_effort` (secondary fallback, only when primary is absent/empty), resolved first-non-empty-wins in the existing single forward pass over entries — matching the pattern already used for `model`/`cli_version` resolution in that same loop, and matching the Claude Code lane's raw-passthrough storage convention (no case/vocabulary mapping).

### Files Changed
- `backend/parsers/platforms/codex/parser.py` — added `effort_tier = None` session-scoped accumulator (near the existing `model = ""` init), added the precedence-resolution block inside the existing per-entry `payload_dict` loop (immediately after the existing `model_provider` read, before `cli_version`), and added `effortTier=effort_tier` to the `AgentSession(...)` constructor call.
- `backend/tests/test_sessions_codex_parser.py` — added three new test methods: `test_codex_session_effort_field_maps_to_effort_tier` (payload.effort present), `test_codex_session_falls_back_to_reasoning_effort_when_effort_absent` (fallback path), `test_codex_session_effort_absent_on_both_fields_yields_none` (absent -> None). Both effort-present/fallback fixtures are reduced/redacted from a real on-disk `~/.codex/sessions/2026/08/02/rollout-2026-08-02T00-05-01-019fc0a5-8971-77e1-8c1b-005d2c49cd6d.jsonl` `turn_context` record (verified locally before writing the fixture — no shape had to be inferred from the contract's EVIDENCE block).

### Acceptance Criteria Status
- [x] Codex session JSONL with `payload.effort='high'` yields `sessions.effort_tier='high'` after parse. (`test_codex_session_effort_field_maps_to_effort_tier`)
- [x] Codex session JSONL with `payload.effort` absent but `collaboration_mode.settings.reasoning_effort` present yields that value. (`test_codex_session_falls_back_to_reasoning_effort_when_effort_absent`)
- [x] Codex session JSONL with neither field present yields `sessions.effort_tier=NULL`. (`test_codex_session_effort_absent_on_both_fields_yields_none`)
- [x] Claude Code lane's effort_tier capture path (`scripts/hooks/ccdash_capture_session_start.py`, `backend/parsers/platforms/claude_code/parser.py`) is untouched — verified `git diff HEAD~1 -- backend/parsers/platforms/claude_code/parser.py scripts/hooks/ccdash_capture_session_start.py` is empty.
- [x] Precedence rule documented as inline code comment at the resolution point (see the comment block preceding the `if effort_tier is None:` check in `parser.py`).
- [x] No new/changed DDL, no new column, no migration file — confirmed no `db/` files touched.

### Validation Run
| Command | Result | Notes |
|---|---|---|
| `backend/.venv/bin/python -m pytest backend/tests/test_sessions_codex_parser.py -v` | Pass | 8/8 passed (5 pre-existing + 3 new), 0.44s |
| Whole-directory `pytest backend/tests/` | Not run | Per contract Validation Requirements #3 (known collection hang in this repo) — intentionally not run |
| `git diff --stat` | Verified | Only `backend/parsers/platforms/codex/parser.py` (+23) and `backend/tests/test_sessions_codex_parser.py` (+97) changed; diff limited to the two files in `files_affected` |

### Deviations From Contract
None. A real on-disk Codex JSONL file (`~/.codex/sessions/2026/08/02/rollout-2026-08-02T00-05-01-019fc0a5-8971-77e1-8c1b-005d2c49cd6d.jsonl`) was located and inspected via `grep`/`python3 -c` before the fixture was written, so no fallback to the contract's EVIDENCE block was needed.

### Risks and Limitations
- **Precedence across disagreeing entries**: if a session's entries carry different `payload.effort` values (e.g. a mid-session `/effort` change — Gap 1, explicitly out of scope), this implementation keeps the *first* non-empty value seen in forward-pass order and does not re-evaluate later entries. This matches the contract's explicit instruction ("first-non-empty-wins ... do not add a second pass") and mirrors the existing `model`/`cli_version` resolution pattern in the same loop, but it means the stored `effort_tier` reflects the session's *initial* effort setting, not necessarily its final one. This is a known, accepted limitation per the contract, not a defect.
- No other risks identified; change is additive, read-only w.r.t. existing fields, and covered by unit tests for all three specified AC states.

### Follow-Up Recommendations
- Gap 1 (mid-session `/effort` re-capture), Gap 2 (subagent effort inheritance), and Gap 4 (`effortTierSource` provenance column) remain explicitly deferred to separate nodes — not implemented here.
- `payload.model_context_window` -> `context_window` ingestion and provider-capture-not-derived (`payload.model_provider`) are also explicitly out of scope and untouched.

### Memory Candidates Captured
None — this change follows an already-documented convention (`docs/guides/launch-time-capture-convention.md`) rather than discovering a new gotcha or pattern.
