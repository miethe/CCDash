---
title: 'Feature Contract: Ingest Codex payload.effort into sessions.effort_tier'
schema_version: 2
doc_type: feature_contract
it_schema: 1
description: 'Codex parser reads payload.effort (fallback: collaboration_mode.settings.reasoning_effort)
  into the existing sessions.effort_tier column, matching the Claude Code lane''s
  null-safe, no-invented-vocabulary storage convention.'
status: completed
created: 2026-08-02
updated: '2026-08-02'
feature_slug: codex-effort-tier-ingestion
category: enhancements
estimated_points: 3
tier: 1
owner: null
priority: medium
risk_level: low
changelog_required: false
node_type: work_package
acceptance_criteria:
- Codex session JSONL with payload.effort='high' yields sessions.effort_tier='high'
  after parse.
- Codex session JSONL with payload.effort absent but collaboration_mode.settings.reasoning_effort
  present yields that value.
- Codex session JSONL with neither field present yields sessions.effort_tier=NULL
  (never a guessed/defaulted value).
- Claude Code lane's effort_tier capture path (scripts/hooks/ccdash_capture_session_start.py,
  backend/parsers/platforms/claude_code/parser.py) is untouched.
definition_of_done: backend/tests/test_sessions_codex_parser.py extended with effort-present
  and effort-absent cases, both green; no new columns, no schema/migration changes,
  no Gap 1/2/4 work, no context_window/provider changes.
execution_mode: unassigned
agent_title: Codex effort_tier ingestion (Gap 3)
agent_summary: Read payload.effort (fallback reasoning_effort) in the Codex parser
  and store it verbatim (stripped) on AgentSession.effortTier, matching the existing
  DB write path used by the Claude Code lane.
agent_context: null
open_questions: []
decisions:
- decision: 'Precedence: payload.effort primary; payload.collaboration_mode.settings.reasoning_effort
    secondary, used only when payload.effort is absent/empty.'
  rationale: payload.effort is the authoritative, directly-set reasoning effort per
    verified real Codex JSONL; reasoning_effort is a settings echo, used only as fallback.
  status: accepted
- decision: "Store the value verbatim after str().strip() \u2014 no case normalization,\
    \ no vocabulary mapping/invention."
  rationale: The Claude Code lane (scripts/hooks/ccdash_capture_session_start.py _settings_effort_level)
    stores the raw stripped effortLevel string with no transformation; matching that
    convention avoids inventing a new vocabulary the node's DoD explicitly forbids.
  status: accepted
- decision: Absent on both fields -> None, never a default/guessed tier.
  rationale: 'CLAUDE.md launch-time capture invariant: unknown == null, never defaulted.
    sessions.effort_tier is nullable in both SQLite and Postgres DDL already.'
  status: accepted
scores: {}
related_documents:
- docs/guides/launch-time-capture-convention.md
spike_ref: null
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
files_affected:
- backend/parsers/platforms/codex/parser.py
- backend/tests/test_sessions_codex_parser.py
---

# Feature Contract: Ingest Codex `payload.effort` into `sessions.effort_tier`

## 1. Goal

The Codex parser reads the authoritative per-session reasoning-effort value already present in Codex JSONL (`payload.effort`, with `payload.collaboration_mode.settings.reasoning_effort` as fallback) and sets it on `AgentSession.effortTier`, so it lands in the existing `sessions.effort_tier` column — closing Gap 3 of `node_01KZ1RZ0X3T1AGDKN8GW8BVM3C` with zero schema changes.

---

## 2. User / Actor

- **Primary user**: CCDash operators/analysts querying session effort-tier breakdowns across Claude Code and Codex sessions in one place.
- **Secondary users**: Downstream consumers of `sessions.effort_tier` (analytics rollups, IntentTree/AOS correlation) that today only see non-null values for the Claude Code lane.

---

## 3. Job To Be Done

When a Codex session JSONL is parsed, the system wants to **extract the reasoning-effort value Codex already recorded on disk**, so it can **populate `sessions.effort_tier` without any hook, guess, or new column** — matching what already works for the Claude Code launch-capture lane.

---

## 4. Scope

### In Scope

- Reading `payload.effort` (primary) and `payload.collaboration_mode.settings.reasoning_effort` (secondary/fallback, used only if primary is absent/empty) from Codex session JSONL entries in `backend/parsers/platforms/codex/parser.py`.
- Setting the resolved value on the `AgentSession` object's `effortTier` field so it flows through the existing `backend/db/repositories/sessions.py` write path (`session_data.get("effortTier")` -> `effort_tier` column) with no repository/DB changes.
- Extending `backend/tests/test_sessions_codex_parser.py` with a real-JSONL-derived fixture covering both the present-effort case and the absent-effort -> NULL case.

### Out of Scope

- Gap 1 (mid-session `/effort` re-capture), Gap 2 (subagent effort inheritance), Gap 4 (new `effortTierSource` provenance column) — separate nodes, do not implement.
- `payload.model_context_window` -> `context_window` column.
- Making provider captured-not-derived from `payload.model_provider` (parser already reads `model_provider` at ~L778 for `models_seen` only — leave that behavior as-is).
- Any DDL/migration change. `sessions.effort_tier` already exists (nullable) in both SQLite and Postgres DDL.
- Any change to `backend/parsers/platforms/claude_code/parser.py` or `scripts/hooks/ccdash_capture_session_start.py` behavior (read-only reference for vocabulary matching).

---

## 5. UX / Behavior Requirements

- A Codex JSONL entry whose `payload.effort` is a non-empty string (e.g. `"high"`) results in `AgentSession.effortTier == "high"` (stripped, unmodified case/value).
- If `payload.effort` is missing/empty/non-string, but some entry's `payload.collaboration_mode.settings.reasoning_effort` is a non-empty string, that value is used instead.
- If neither is present across any entry in the session, `AgentSession.effortTier` is `None` — not `""`, not a guessed tier.
- The precedence/normalization decision must be documented inline in code (a short comment at the point of resolution), matching the "decide and document the precedence in code" requirement from the request.
- No change in behavior for sessions parsed by the Claude Code lane.

---

## 6. Data Requirements

- **Entities affected**: `AgentSession` (in-memory Pydantic model, `backend/models.py` — `effortTier: Optional[str] = None`, already exists); `sessions.effort_tier` DB column (already exists, nullable, both backends).
- **New fields**: none.
- **State changes**: none beyond the existing effort_tier write-on-sync path already exercised by the Claude Code lane (`backend/db/repositories/sessions.py` around L97/L163/L243).
- **Storage implications**: none — no migration required or permitted.

---

## 7. API / Integration Requirements

**New or modified endpoints**: none.

**External service calls**: none.

**Internal service dependencies**: `backend/parsers/platforms/codex/parser.py` -> `AgentSession(effortTier=...)` -> `backend/db/repositories/sessions.py` upsert path (unchanged code, now receiving a populated field for Codex sessions too).

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/parsers/platforms/codex/parser.py` — the existing per-entry `payload_dict` walk (around L762-L800, where `model`, `model_provider`, `cli_version` are already read) is the natural place to add effort resolution; follow the same `str(...).strip()` idiom used throughout that loop.
- The `AgentSession(...)` constructor call around L1247 — add `effortTier=<resolved value>` alongside the other already-passed fields.
- Value storage convention: raw, stripped string, no vocabulary invention — mirrors `scripts/hooks/ccdash_capture_session_start.py:_settings_effort_level` (reads `effortLevel`, strips, returns as-is; no case/vocabulary mapping) and `backend/parsers/platforms/claude_code/parser.py` capture-field handling (`effortTier=capture_sidecar.get("effortTier")`, passthrough).

**Must not change** (protected areas):
- `backend/parsers/platforms/claude_code/parser.py` behavior.
- `scripts/hooks/ccdash_capture_session_start.py` behavior.
- `sessions.effort_tier` column definition/DDL (both SQLite and Postgres) — already exists, do not touch.
- Any other Codex parser field (`model`, `model_provider`, `models_seen`, etc.).

**New dependencies:**
- Allowed? **No**. No new dependencies expected.

---

## 9. Acceptance Criteria

- [ ] A Codex session fixture (reduced/redacted from a real `~/.codex/sessions/2026/08/02/rollout-*.jsonl` record) with a `payload.effort` value of `"high"` parses to `AgentSession.effortTier == "high"`.
- [ ] A Codex session fixture with `payload.effort` absent, but `payload.collaboration_mode.settings.reasoning_effort` present, parses to that fallback value.
- [ ] A Codex session fixture with neither field present parses to `AgentSession.effortTier is None`.
- [ ] The precedence rule (payload.effort primary, reasoning_effort secondary-only-if-primary-absent) is documented as an inline code comment at the resolution point.
- [ ] `backend/parsers/platforms/claude_code/parser.py` and `scripts/hooks/ccdash_capture_session_start.py` have zero diff.
- [ ] No new/changed DDL, no new column, no migration file.

---

## 10. Validation Requirements

- [ ] **Tests**: new/extended cases in `backend/tests/test_sessions_codex_parser.py` (do NOT create a parallel test module).
- [ ] **Test run**: `/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python -m pytest backend/tests/test_sessions_codex_parser.py -v` — all green.
- [ ] **No whole-directory pytest collection** — this repo's pytest hangs on `backend/tests/` collection; run the named file only.
- [ ] **No unrelated changes** — diff limited to the two files in `files_affected`.
- [ ] **Docs**: none required (no flag, no new column, no new API surface — `docs/guides/launch-time-capture-convention.md` already documents the storage convention this change matches).

---

## 11. Risk Areas

- **Fixture fidelity**: the mandatory test fixture must be derived from an actual `~/.codex/sessions/2026/08/02/rollout-*.jsonl` record, reduced/redacted — not hand-invented JSONL shape. Low risk if the executing agent reads a real file first; flag in the Completion Report if no real Codex session file was locally available and a shape had to be inferred from the EVIDENCE block in this contract instead.
- **Precedence ambiguity across multiple entries**: a session has many JSONL entries; if `payload.effort` appears on one entry and differs from another, resolve using first-non-empty-wins during the existing single forward pass over `entries` (same pattern as `model`/`cli_version` resolution already in the loop) — do not add a second pass.
- **Over-normalization temptation**: do not lowercase, do not map to an enum, do not invent a tier vocabulary (e.g. do not coerce to `low/medium/high/max`) — store verbatim stripped string, consistent with the Claude Code lane's stored-value convention.

---

## 12. Implementation Notes

**Suggested approach** (agent may improve):
1. Locate a real Codex JSONL file under `~/.codex/sessions/2026/08/02/rollout-*.jsonl` (or nearby dates) and extract one record's `payload.effort` (and, if present in another sample, one `collaboration_mode.settings.reasoning_effort` record) to seed the fixture faithfully.
2. In `backend/parsers/platforms/codex/parser.py`, inside the existing per-entry loop (around L762-L800), add a small resolution step: track a session-scoped `effort_tier: Optional[str] = None` (or similar), set from `payload_dict.get("effort")` if non-empty and not yet set; else from `payload_dict.get("collaboration_mode", {}).get("settings", {}).get("reasoning_effort")` if non-empty and not yet set. Add the inline precedence comment here.
3. Pass `effortTier=effort_tier` into the `AgentSession(...)` constructor call (~L1247), alongside `modelSlug`, etc.
4. Extend `backend/tests/test_sessions_codex_parser.py` with two new test methods (or parametrized cases) following the existing `_write_jsonl` helper pattern already in the file.
5. Run the named-file pytest command from Validation Requirements and confirm green.

**Similar existing code**:
- Reference: `scripts/hooks/ccdash_capture_session_start.py:_settings_effort_level` — the exact "read raw string, strip, return as-is, no transform" pattern to mirror.
- Reference: `backend/parsers/platforms/claude_code/parser.py` around L4566 (`effortTier=capture_sidecar.get("effortTier")`) — confirms `effortTier` is the correct AgentSession kwarg name and that passthrough (no re-derivation) is the established convention.

**Known gotchas**:
- `backend/parsers/platforms/codex/parser.py` already reads `payload_dict.get("model_provider")` at ~L778 but only adds it to `models_seen` — do not extend that line's behavior; effort resolution is a separate, independent read.
- Do not touch `payload.model_context_window` / `context_window` — explicitly out of scope per the request.
- Run pytest against the **named test file only** (`test_sessions_codex_parser.py`), never bare `pytest backend/tests/` (known collection hang in this repo).
- Use the main-repo venv by absolute path: `/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python`.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified/new files with brief reason (expect exactly 2: parser.py, test file).
- **Tests run**: New/extended test names in `test_sessions_codex_parser.py` and pass/fail results.
- **Validation results**: Table including the mandatory named-file pytest run.
- **Deviations from contract**: Note explicitly if the fixture could not be derived from a real on-disk Codex JSONL file and had to be constructed from the EVIDENCE block instead.
- **Risks / Limitations**: Any remaining risk (e.g. precedence behavior when a session's entries disagree).
- **Follow-up recommendations**: Note that Gap 1/2/4, context_window ingestion, and provider-capture-not-derived are explicitly deferred to separate nodes.

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (3 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase orchestration

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents**:
- `docs/guides/launch-time-capture-convention.md`
- `backend/parsers/platforms/claude_code/parser.py` (vocabulary/pattern reference, read-only)
- `scripts/hooks/ccdash_capture_session_start.py` (vocabulary/pattern reference, read-only)

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass validation. If you find:

- **Scope ambiguity**: Ask one focused question or make a conservative assumption and note it in the Completion Report.
- **Impossible constraints**: Flag in the Completion Report before attempting workarounds.
- **Better implementation path**: Document the deviation in the Completion Report with justification.

Stay within scope. Do NOT implement Gap 1 (mid-session re-capture), Gap 2 (subagent effort inheritance), Gap 4 (`effortTierSource` provenance column), `context_window` ingestion, or provider-capture-not-derived — these are separate nodes. If you believe one is required to complete this contract, STOP and report rather than widening scope. Avoid cleanup, refactors, or feature expansion beyond this contract. The reviewer will check for scope drift.

```json autopilot-graph
{
  "tier": 1,
  "effort_points": 3,
  "wave_count": 1,
  "phase_count": 1,
  "file_count": 2,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/feature_contracts/enhancements/codex-effort-tier-ingestion.md",
  "execution_target": "execute-contract",
  "slug": "codex-effort-tier-ingestion",
  "category": "enhancements",
  "review_intensity": "standard",
  "files_affected": [
    "backend/parsers/platforms/codex/parser.py",
    "backend/tests/test_sessions_codex_parser.py"
  ],
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Codex effort_tier ingestion sprint",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-1.1",
                "prompt": "Mode C: Autonomous Feature Sprint.\n\nImplement docs/project_plans/feature_contracts/enhancements/codex-effort-tier-ingestion.md in full (Gap 3 of node_01KZ1RZ0X3T1AGDKN8GW8BVM3C). Files: backend/parsers/platforms/codex/parser.py, backend/tests/test_sessions_codex_parser.py.\n\nRead the contract file first -- it is your full specification (goal, scope, AC, precedence decisions, implementation notes). Summary: in the Codex parser's existing per-entry payload_dict loop (around L762-L800), resolve a session-scoped effort_tier value with precedence payload.effort (primary) then payload.collaboration_mode.settings.reasoning_effort (secondary, only if primary absent/empty); store the first non-empty str().strip() value found across all entries, matching the Claude Code lane's raw-passthrough storage convention (see scripts/hooks/ccdash_capture_session_start.py:_settings_effort_level and backend/parsers/platforms/claude_code/parser.py L4566 for the pattern to mirror -- read-only references, do not edit them). Add an inline comment documenting the precedence. Pass effortTier=<resolved value> into the AgentSession(...) constructor call (~L1247). No match on either field -> None, never a default.\n\nExtend backend/tests/test_sessions_codex_parser.py (do not create a parallel test module) with: (1) a fixture derived from a real ~/.codex/sessions/2026/08/02/rollout-*.jsonl record (reduced/redacted) asserting payload.effort lands in effort_tier; (2) an absent-effort case asserting NULL/None. Use the existing _write_jsonl helper pattern in that file.\n\nRun: /Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python -m pytest backend/tests/test_sessions_codex_parser.py -v -- must be green. Never run bare `pytest backend/tests/` (known collection hang).\n\nOut of scope, do not touch: Gap 1 (mid-session /effort re-capture), Gap 2 (subagent effort inheritance), Gap 4 (effortTierSource column), payload.model_context_window/context_window, provider capture-not-derived, any DDL/migration, backend/parsers/platforms/claude_code/parser.py, scripts/hooks/ccdash_capture_session_start.py. If you believe any of these is required, STOP and report instead of widening scope.\n\nProduce the Completion Report per contract section 13. Do NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 3,
                "files_affected": [
                  "backend/parsers/platforms/codex/parser.py",
                  "backend/tests/test_sessions_codex_parser.py"
                ]
              }
            ]
          }
        ]
      }
    ]
  },
  "escalation_recommendation": "If implementation reveals the effort value cannot be resolved from a single forward pass over entries (e.g. genuine need for a second parsing pass or schema touch), stop and escalate to Tier 2 with a PRD + milestone plan rather than stretching this contract."
}
```
