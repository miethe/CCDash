---
title: "Feature Contract: Session-Family Residue — Teammate Sidecar Attribution + tool_names Contract Doc"
schema_version: 2
doc_type: feature_contract
it_schema: 1
description: "Parse .meta.json teammate sidecars for team attribution (needed); document SessionRef.tool_names as empty-by-construction on /family (no consumer needs it)."
status: draft
created: 2026-08-03
updated: 2026-08-03
feature_slug: session-family-residue
category: "harden-polish"
estimated_points: 5
tier: 1
owner: null
priority: medium
risk_level: low
changelog_required: false
node_type: work_package
acceptance_criteria: []
definition_of_done: null
execution_mode: autonomous
agent_title: "Session-family residue: teammate-meta attribution + tool_names contract doc"
agent_summary: "Two independent, assess-first backend defects following the 69a5ae2 session-family/team-sidecar fix."
agent_context: null
open_questions: []
decisions:
  - decision: "Item 1 (.meta.json teammate sidecars): BUILD — parse the sidecar."
    rationale: "Assessed live against node PG (10.42.10.76:5440): subagent_parent_id/workflow_id lineage is flat by construction (100% of sampled multi-child roots show COUNT(DISTINCT subagent_parent_id)=1); .meta.json carries the true nested spawn tree (parentAgentId -> sibling agent-hash) plus team identity (taskKind, teamName) that the flat column collapses. See implementation-notes.md 2026-08-03 entry for full evidence."
    status: accepted
  - decision: "Item 2 (SessionRef.tool_names on /family): DOCUMENT ONLY — no implementation."
    rationale: "Searched FE/CLI/MCP for consumers of GET /sessions/{id}/family; none read tool_names by name or branch on emptiness. tool_names=[] is already the accepted default at 2 other SessionRef call sites. Building a batched lookup here solves a problem no consumer has."
    status: accepted
scores: {}
related_documents:
  - .claude/worknotes/session-family-and-team-sidecar/implementation-notes.md
spike_ref: null
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/parsers/platforms/claude_code/parser.py
  - backend/parsers/platforms/claude_code/schema/session_forensics.schema.json
  - backend/tests/test_sessions_parser.py
  - backend/application/services/agent_queries/models.py
  - backend/routers/_client_v1_sessions.py
  - .claude/worknotes/session-family-and-team-sidecar/implementation-notes.md
---

<!--
Autopilot request-log ID: node_01KZ4FFY200ND09X8NX3ABRA9D+node_01KZ4FG6P77GRAZPWXTVW3Z9JV
Base: da73ed6. Branch: autopilot/session-family-residue.
Worktree: .claude/worktrees/autopilot-session-family-residue (this file lives inside the worktree;
lands on the destination branch via the normal worktree -> PR -> squash-merge flow).
-->

```json autopilot-graph
{
  "tier": 1,
  "effort_points": 5,
  "wave_count": 1,
  "phase_count": 1,
  "file_count": 6,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/feature_contracts/harden-polish/session-family-residue.md",
  "execution_target": "execute-contract",
  "slug": "session-family-residue",
  "category": "harden-polish",
  "review_intensity": "standard",
  "files_affected": [
    "backend/parsers/platforms/claude_code/parser.py",
    "backend/parsers/platforms/claude_code/schema/session_forensics.schema.json",
    "backend/tests/test_sessions_parser.py",
    "backend/application/services/agent_queries/models.py",
    "backend/routers/_client_v1_sessions.py",
    ".claude/worknotes/session-family-and-team-sidecar/implementation-notes.md"
  ],
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Teammate-meta sidecar parsing + tool_names contract doc",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-1.1",
                "prompt": "Mode C: Autonomous Feature Sprint.\n\nImplement the Feature Contract at docs/project_plans/feature_contracts/harden-polish/session-family-residue.md in full (both Item 1 and Item 2 below). Work ONLY inside this worktree checkout (you are already cd'd into it; do not touch the main repo root). Use the interpreter at /Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python (absolute path; this worktree has no venv of its own).\n\nItem 1 (BUILD -- verdict already recorded, do not re-derive): add `_collect_teammate_meta_sidecar` to backend/parsers/platforms/claude_code/parser.py, placed near `_collect_capture_sidecar` (same root-session-vs-subagent contract shape). For a subagent session, read the adjacent `agent-<hash>.meta.json` next to the subagent's own `.jsonl` (`path.with_suffix('.meta.json')`) and extract `taskKind`, `teamName`, `parentAgentId`, `spawnDepth` (str/str/str/int, default '' / '' / '' / 0). Root sessions and any subagent missing the sidecar file both resolve to the same absent/empty contract shape (`exists: False` + the 4 defaults) -- never raise, mirror `_load_team_config`'s benign-on-missing convention. Wire the result into the existing `sidecars` dict (~parser.py L4319-4325) as `sidecars['teammateMeta']`, computed alongside the other sidecar collector calls (~L4026-4033). Add a matching declarative entry under `sidecars` in backend/parsers/platforms/claude_code/schema/session_forensics.schema.json (key `teammateMeta`, note it is adjacent-file-keyed, not dir-scanned, unlike `tasks`/`teams`). Add ONE new test in backend/tests/test_sessions_parser.py (model the fixture layout on `test_team_sidecar_resolves_short_dir_layout_and_reads_config_membership` and the root/subagent path derivation in `_extract_raw_session_id`/`_resolve_session_sidecar_root`): write a subagent jsonl at `<claude_root>/<root_id>/subagents/agent-<hash>.jsonl` with an adjacent `agent-<hash>.meta.json` carrying all 4 fields, call `parse_session_file` on the subagent path, assert `session.sessionForensics['sidecars']['teammateMeta']` matches; also assert the absent-contract shape for (a) a root session and (b) a subagent with no adjacent .meta.json. Run ONLY this named file: `/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py -v` (never an unscoped `pytest backend/tests/` -- it hangs in this repo).\n\nItem 2 (DOCUMENT ONLY -- verdict already recorded, do not build a batched lookup or any tool_names population): add a `description=` to `SessionRef.tool_names` in backend/application/services/agent_queries/models.py stating it is empty-by-construction on responses built directly from the sessions row (e.g. GET /sessions/{id}/family) and that populating it requires a dedicated per-session transcript scan (point at feature_forensics.py's `_enrich_session_refs`) -- absent/empty here is a documented contract state, not evidence the session used no tools. Expand the `get_session_family_v1` docstring in backend/routers/_client_v1_sessions.py to state explicitly, in the docstring itself (not just the existing inline code comment at ~L333-337), that `tool_names` is always `[]` on this endpoint's response today. No behavioral change, no test required for this half.\n\nBoth items: append your evidence-free implementation summary (what changed, not a re-assessment -- the assessment is already recorded in .claude/worknotes/session-family-and-team-sidecar/implementation-notes.md's 2026-08-03 entry, read it first for the verdicts) to that same worknotes file as a short 'Implemented' addendum under each item's existing 2026-08-03 section. Do not clobber existing content -- append only.\n\nProduce the Completion Report per contract section 13. Do NOT git add/commit/push/stash.",
                "assigned_to": "feature-sprint-executor",
                "effort": 5,
                "files_affected": [
                  "backend/parsers/platforms/claude_code/parser.py",
                  "backend/parsers/platforms/claude_code/schema/session_forensics.schema.json",
                  "backend/tests/test_sessions_parser.py",
                  "backend/application/services/agent_queries/models.py",
                  "backend/routers/_client_v1_sessions.py",
                  ".claude/worknotes/session-family-and-team-sidecar/implementation-notes.md"
                ]
              }
            ]
          }
        ]
      }
    ]
  },
  "escalation_recommendation": "None expected -- if Item 1's parser change turns out to need a new DB column (it should not; sidecars live inside the existing session_forensics_json blob), STOP and escalate to Opus as a Mode D boundary per the repo's schema-change rule rather than proceeding autonomously."
}
```

---

# How To Use This Template

This is a Tier 1 feature contract (5 points, single autonomous sprint). Delegate the entire
contract to `feature-sprint-executor`; `task-completion-validator` reviews the completion report
against the acceptance criteria before Opus commits (per the worktree -> PR -> squash-merge
protocol; commits happen outside this Mode B pass).

---

# Feature Contract: Session-Family Residue

## 1. Goal

Close two follow-up gaps left explicitly out-of-scope by the 69a5ae2 session-family/team-sidecar
fix: parse the per-teammate `.meta.json` provenance sidecar (needed, confirmed by evidence — see
Decision Gates below), and resolve whether `SessionRef.tool_names` needs real population on the
session-family endpoint (it does not — document the contract instead).

---

## 2. User / Actor

- **Primary user**: CCDash operators/agents inspecting subagent session provenance and family
  responses (via API, CLI `ccdash session family`, or future MCP tools) who need to know which
  team a given subagent session belongs to, and what `tool_names: []` actually means on a family
  response.
- **Secondary users**: future contributors extending `SessionRef`-producing call sites, who will
  read the new field docstring instead of re-discovering the empty-by-construction gap.

---

## 3. Job To Be Done

When **a subagent session was launched as an in-process teammate**, an operator wants to
**attribute that specific session row to its team and spawn position**, so they can **reconstruct
the real multi-agent collaboration tree instead of a flattened root-only lineage**.

When **an operator reads `tool_names: []` on a `/sessions/{id}/family` response**, they want to
**know whether that means "no tools used" or "not populated here"**, so they can **avoid drawing a
false conclusion from a documented contract gap**.

---

## 4. Scope

### In Scope

- **Item 1 (build)**: New `_collect_teammate_meta_sidecar` parser collector; wiring into the
  existing `sidecars` dict inside `session_forensics_json` (no new DB column); a matching
  declarative schema entry; one new named test.
- **Item 2 (document only)**: `description=` on `SessionRef.tool_names`; docstring expansion on
  `get_session_family_v1`; no behavior change.
- Append-only additions to `.claude/worknotes/session-family-and-team-sidecar/implementation-notes.md`.

### Out of Scope

- Any DB schema change (no new column — both items are achievable inside the existing
  `session_forensics_json` blob / existing model field).
- A batched tool-usage lookup for `tool_names` — the decision gate concluded no consumer needs it;
  do not build it "for completeness."
- Cross-referencing `.meta.json`'s `parentAgentId` back to the root's `config.json` roster
  (`team-lead@session-<id>` namespace) — `.meta.json`'s own `teamName` field is already
  self-contained for AC2; a full agentId-to-session join is a separate, unscoped future task.
- Any FE, CLI, or MCP surface change — backend only, per the request's hard constraint.
- Backfilling historical sessions — this is parse-time only, applies going forward.

---

## 5. UX / Behavior Requirements

- N/A — backend-only, no user-facing UX. Observable behavior: a subagent session parsed after this
  change carries `sessionForensics.sidecars.teammateMeta` with `exists`, `taskKind`, `teamName`,
  `parentAgentId`, `spawnDepth`; a root session or a subagent with no adjacent `.meta.json` carries
  the same shape with `exists: False` and the field defaults — never a missing key, never a raise.

---

## 6. Data Requirements

- **Entities affected**: none at the DB-column level. `sessions.session_forensics_json` (existing
  JSON blob column, both SQLite and Postgres) gains one new key inside its existing `sidecars`
  object — no migration, no `COLUMN_PARITY_DRIFT_ALLOWLIST` entry needed.
- **New fields**: `sessionForensics.sidecars.teammateMeta` = `{exists: bool, taskKind: str,
  teamName: str, parentAgentId: str, spawnDepth: int}`.
- **State changes**: none.
- **Storage implications**: none — if implementation reveals a genuine need for a new column,
  STOP per the contract's hard constraint and escalate to Opus as a Mode D boundary; do not add one
  autonomously.

---

## 7. API / Integration Requirements

**New or modified endpoints**: none. The new sidecar rides inside the existing
`sessionForensics` payload wherever it is already surfaced (session detail, etc.) — no router
change for Item 1.

**Internal service dependencies**:
- Item 1: `backend/parsers/platforms/claude_code/parser.py` (new collector), schema file for the
  declarative sidecar description.
- Item 2: `backend/application/services/agent_queries/models.py` (`SessionRef`),
  `backend/routers/_client_v1_sessions.py` (`get_session_family_v1` docstring).

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `_collect_capture_sidecar` (root-vs-subagent absent-contract shape, adjacent-file read) —
  `backend/parsers/platforms/claude_code/parser.py`.
- `_load_team_config` (benign-on-missing/malformed, never raises on the parser hot path) — same
  file.
- The `sidecars` dict assembly at ~L4319-4325 and its collector-call block at ~L4026-4033.

**Must not change** (protected areas):
- `subagent_parent_id` / `workflow_id` derivation (flat-by-design per T5-004's own comment; this
  contract does NOT change that lineage, it adds a parallel, more granular signal alongside it).
- No new DB column — see Data Requirements.
- `SessionRef.tool_names`'s default value/shape (`Field(default_factory=list)`) — only its
  `description` changes.

**New dependencies**: No new dependencies expected.

---

## 9. Acceptance Criteria

**Item 1**
- [ ] AC1: `.meta.json` sidecars are parsed for `taskKind`/`teamName`/`parentAgentId`/`spawnDepth`
      via `_collect_teammate_meta_sidecar`, wired into `sidecars.teammateMeta`.
- [ ] AC2: A subagent session launched as an `in_process_teammate` can be attributed to its team
      directly from `sessionForensics.sidecars.teammateMeta.teamName` (no join to `config.json`
      required) — proven by the new test.
- [ ] AC3: Decision gate recorded BEFORE this sprint (see `decisions[]` in frontmatter and the
      2026-08-03 worknotes entry) — workflow_id lineage does NOT already cover this attribution
      (flat by construction, proven against node PG). No re-assessment needed.
- [ ] Root sessions and subagents missing the sidecar file resolve to the absent/empty contract,
      never raise.

**Item 2**
- [ ] AC1: Decision gate recorded BEFORE this sprint — no FE/CLI/MCP consumer of
      `GET /sessions/{id}/family` reads `tool_names`. No re-assessment needed.
- [ ] AC2: N/A (verdict is "no" — no batched lookup is built).
- [ ] AC3: The empty-by-construction contract is documented on `SessionRef.tool_names`
      (`description=`) AND in `get_session_family_v1`'s docstring, so a future reader sees it in
      both the schema (OpenAPI) and the endpoint contract.

---

## 10. Validation Requirements

- [ ] **Tests**: named-file run only —
      `/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py -v`.
      Never an unscoped `pytest backend/tests/` collection (hangs in this repo).
- [ ] **No dev server start** — do not run `npm run dev` / uvicorn; not needed for this backend
      parser + docstring change, and `test_runtime_bootstrap` hangs with a server up.
- [ ] **Docs updated**: worknotes file appended (not clobbered) with an "Implemented" addendum per
      item.
- [ ] **No unrelated changes** introduced — this is BACKEND ONLY; do not touch any `.tsx`/`.ts`
      file.

---

## 11. Risk Areas

- **Parser hot path**: `_collect_teammate_meta_sidecar` runs on every subagent parse. Must be
  benign-on-missing/malformed (never raise) — same discipline as every other sidecar collector in
  this file. Low risk if the existing pattern is followed exactly.
- **Schema drift**: the new `teammateMeta` schema entry in
  `session_forensics.schema.json` is declarative documentation for the sidecar shape, not a
  runtime-enforced contract — a wrong key name here doesn't break parsing, it just documents the
  wrong thing. Cross-check against the two real on-disk field-name samples cited in the worknotes
  entry (`taskKind`, `teamName`, `parentAgentId`, `spawnDepth` — exact casing).
- **Item 2 scope creep**: the strongest risk here is the executor deciding to "just add the batched
  lookup anyway since it's not much more work." The decision gate already concluded no consumer
  needs it — do not build it. If a NEW consumer need surfaces during the sprint, stop and note it in
  the Completion Report as a deviation; do not silently expand scope.

---

## 12. Implementation Notes

**Suggested approach:**
1. Read the 2026-08-03 entry in `.claude/worknotes/session-family-and-team-sidecar/implementation-notes.md`
   first — both verdicts and their evidence are already recorded there; do not re-derive them.
2. Item 1: write `_collect_teammate_meta_sidecar`, wire it in, add the schema entry, add the test,
   run the named test file.
3. Item 2: add the two docstrings.
4. Append "Implemented" addenda to the worknotes file for both items.

**Similar existing code**:
- `_collect_capture_sidecar` and `_load_team_config` — both in
  `backend/parsers/platforms/claude_code/parser.py` — are the closest structural analogs for
  Item 1 (adjacent-file read, benign-on-missing, root-vs-subagent contract split).

**Known gotchas**:
- For a subagent session, `raw_session_id` (as returned by `_extract_raw_session_id`) is the ROOT
  session's directory name, NOT the subagent's own `agent-<hash>` identity — the new collector
  should key off `path` directly (the subagent's own `.jsonl` file path), not `raw_session_id`.
- `.meta.json` files observed on disk do NOT always carry all 4 fields (e.g. many carry only
  `agentType`/`description`/`toolUseId`/`spawnDepth` with no `taskKind`/`teamName` at all — that is
  the ordinary, non-team subagent case). Default missing fields to their documented empty values;
  do not treat a missing `taskKind`/`teamName` as an error.

---

## 13. Completion Report Required

Per `.claude/skills/dev-execution/validation/completion-criteria.md`: files changed, tests run +
results, validation results table, deviations from contract (if any), risks/limitations, follow-up
recommendations.

---

## Metadata & References

**Tier**: 1 (5 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents**:
- `.claude/worknotes/session-family-and-team-sidecar/implementation-notes.md` (assessment evidence
  for both items, 2026-08-03 entry — read before implementing)
- Prior fix this contract follows up on: commit `69a5ae2` (`fix(sessions,parser): include
  subagents in session family; revive dead team sidecar`)

---

## Notes for Agents

Both decision gates were already resolved during planning (Mode B) with recorded evidence — do not
re-run the assessment. Item 1 is a real, scoped build (parse + wire + test). Item 2 is
documentation-only; resist the urge to "finish the job" by populating `tool_names` — that was
explicitly rejected by the decision gate. Stay within the file list in this contract's frontmatter.
Do NOT git add/commit/push/stash.
