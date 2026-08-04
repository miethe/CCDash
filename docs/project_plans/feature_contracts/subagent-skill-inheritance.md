---
schema_version: 2
doc_type: feature_contract
title: "Subagent Skill Inheritance \u2014 Feature Contract"
description: "Attribute a parent session's detected skill to its subagent sessions\
  \ when the subagent's own skill_name is NULL, recording provenance so an inherited\
  \ skill is never mistaken for an observed one. Session-detail correctness and per-skill\
  \ analytics only \u2014 explicitly not a routing-feedback unblocker."
owner: nick
status: completed-pending-verification
created: '2026-08-03'
updated: '2026-08-03'
feature_slug: subagent-skill-inheritance
tier: 1
estimated_points: 5
priority: medium
risk_level: medium
category: enhancements
changelog_required: true
related_documents:
- docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-feasibility-brief.md
- docs/project_plans/exploration/routing-key-skill-attribution/spikes/capture-path/capture-path-findings.md
- docs/project_plans/exploration/routing-key-skill-attribution/spikes/null-population/null-population-findings.md
files_affected:
- backend/parsers/skill_provenance.py
- backend/db/postgres_migrations.py
- backend/db/sqlite_migrations.py
- backend/db/repositories/sessions.py
- backend/db/repositories/postgres/sessions.py
- backend/db/repositories/base.py
- backend/db/sync_engine.py
- backend/tests/test_skill_name_source_provenance.py
commit_refs:
- cf44ac5
- 848deae
- fb9f65d
---

# Subagent Skill Inheritance — Feature Contract

> **Design block authored by Opus 2026-08-03.** Sections below the `--- EXPAND BELOW ---` marker are
> to be filled in by the contract writer. Do not alter the design block.

## Provenance — why this exists, and what it is NOT for

This is the one honest, zero-lead-time fix surfaced by the DI-4f exploration (verdict: **no-go**,
signed off 2026-08-03). Read the boundary carefully, because it was mis-framed once already:

- **It is justified on session-detail correctness and per-skill analytics grounds only.**
- **It is NOT a routing-feedback unblocker.** It converts only **10 of 113** NULL `routing_rollup`
  keys — the fix repairs sessions at row level but fragments one large NULL bucket into many small
  per-skill buckets that individually miss `min_sample=5`. DI-4e (`routing_rollup.success_rate`)
  must **not** be gated on this work, and this work must not claim credit for it.

## Goal

When a subagent session's own `skill_name` is NULL but its parent session has a genuinely-detected
skill, attribute the parent's skill to the subagent — **and record that the value was inherited
rather than directly observed.**

## User / Actor

An operator inspecting a session family in CCDash, and any per-skill analytics consumer
(`effectiveness_rollups`, session search, the planning session board).

## Job To Be Done

Today a skill-driven session shows its skill, but the subagents it spawned to do the actual work
show nothing — so the session family reads as though the skill did no work. Close that gap without
inventing a skill for any session that never had one.

## Measured starting point (do not re-derive; verify and extend)

Established against node Postgres `10.42.10.76:5440`, 2026-08-03:

| Quantity | Value |
|---|---|
| Subagent→parent skill inheritance success rate, system-wide, where parent has a known skill | **51.3%** |
| NULL-`skill_name` sessions in the DI-4f cohort attributable by inheritance | **1,504** (~31% of the 5,117-session cohort) |
| NULL `routing_rollup` keys this converts | **10 of 113** — deliberately small; see boundary above |

## Scope

**In scope**
- Derive `skill_name` for subagent sessions from the parent's detected skill.
- Add a provenance column distinguishing a directly-detected skill from an inherited one.
- Backfill historical rows (this is a state-**b** derivation over retained data — no new capture
  instrumentation, zero lead time).

**Out of scope**
- Any change to Codex skill capture. 100% of all 3,482 Codex sessions ever recorded carry zero
  skill-adjacent signal (`backend/parsers/platforms/codex/parser.py:953` has never fired). That is a
  total capture absence requiring new instrumentation — a separate, larger piece of work.
- Any `routing_rollup` key change. DI-4f measured every alternative; the key stays
  `(project_id, skill_name, model)`.
- Touching `routing_rollup.success_rate` (DI-4e) or router-side merge behaviour (DI-1).

## Architecture Constraints

1. **Provenance is mandatory, not optional polish.** An inherited skill and an observed skill have
   different trust levels, and collapsing them into one column repeats a mistake this repo has
   already paid for and fixed once: `effort_tier` needed `effort_tier_source` (schema v44,
   `backend/parsers/effort_provenance.py`) for exactly this reason. Follow that precedent —
   add `skill_name_source` with a closed vocabulary (at minimum: directly-detected vs
   inherited-from-parent), nullable, never defaulted. **Unknown token == unknown provenance; a
   consumer MUST NOT hard-fail on one.**
2. **Dual DDL in the same change set.** Per CLAUDE.md, every new session column requires both the
   SQLite and Postgres `CREATE TABLE` plus `_ensure_column` ALTER, and a
   `COLUMN_PARITY_DRIFT_ALLOWLIST` check. A column added to one backend only is a defect.
3. **`sessions.id` is NOT globally unique** — 19,260 rows / 17,844 distinct ids; unique only per
   project. Every parent/root join MUST be scoped to `(id, project_id)`. A naive
   `s.subagent_parent_id = p.id` join fans out and silently inflates counts by hundreds — this bit
   two DI-4f legs, and the failure is silent because the numbers come back plausible.
4. **Never fabricate.** If the parent's `skill_name` is also NULL (an orphaned subagent), the child
   stays NULL. A session that genuinely had no skill is correctly attributed as having none — that
   is a right answer, not a gap. Do not walk to a sentinel.
5. **Decide and document transitivity.** Subagents can nest. State explicitly whether inheritance
   walks one hop or to the family root, and guard against cycles / unbounded walks. Do not leave
   this implicit.
6. **Backfill must be idempotent and re-runnable**, and must not overwrite a directly-detected
   `skill_name` with an inherited one. Direct detection always wins.
7. **The precedent already reserves a token for this exact pattern — reconcile with it, don't
   collide** (added at Opus sanity review 2026-08-03, from reading
   `backend/parsers/effort_provenance.py:26-29`). `effort_tier_source` already declares
   **`inherited_parent`** — "Derived from a parent session rather than observed... **reserved for
   Gap 2** — no code path writes it yet." Two consequences the executor must handle deliberately:
   - **Token naming.** The expansion proposes `inherited_from_parent`. Either match the existing
     `inherited_parent` spelling, or diverge and say why in the module docstring. Two
     near-identical tokens for one concept across two provenance vocabularies is the kind of drift
     that costs a future reader an hour. Recommendation: **match the existing spelling.**
   - **The parent-walk is shared machinery.** The `(id, project_id)`-scoped parent join built here
     is precisely what Gap 2 needs to populate `effort_tier`'s reserved `inherited_parent`. Write it
     so it is reusable, and note in the Completion Report that Gap 2 could adopt it. **Do NOT
     populate `effort_tier` in this contract** — that is scope creep and a separate decision about
     effort-tier trust. Just don't build a walk that only works for one column.

## Acceptance Criteria

1. A subagent session whose parent has a detected skill reports that skill, with
   `skill_name_source` marking it inherited.
2. A subagent session whose parent's `skill_name` is NULL remains NULL — verified by a direct-count
   assertion, not by absence of error.
3. A session with a directly-detected skill is never overwritten by inheritance; its
   `skill_name_source` marks it directly-detected.
4. `skill_name_source` exists in both SQLite and Postgres DDL, passes the column-parity check, and
   is nullable with no default. Rows predating the column have non-null `skill_name` + null source.
5. Backfill is idempotent: running it twice changes no rows on the second pass (direct-count
   assertion).
6. System-wide subagent inheritance success rate rises materially from the measured 51.3% baseline;
   the achieved figure is measured and stated, not assumed.
7. No `routing_rollup` behaviour change is introduced by this work, and the contract's Completion
   Report states the observed effect on NULL key count (expected ≈10/113 — report the real number).
8. Every parent/root join in the shipped code is scoped to `(id, project_id)`.

## Risk Areas

| Risk | Severity | Note |
|---|---|---|
| Inheritance is semantically wrong for some subagents | medium | A subagent may do work unrelated to the parent's skill. Provenance (constraint 1) is the mitigation — it keeps the inference auditable and reversible rather than baked in. Do not attempt to classify relatedness in this contract. |
| Silent join fan-out inflating counts | **high** | Constraint 3. Already burned two prior legs. Any count reported without a `(id, project_id)`-scoped join should be treated as wrong. |
| Downstream consumers assume `skill_name` means "observed" | medium | Inheritance changes that meaning for some rows. Audit `skill_name` readers and note any that need the provenance distinction; fixing them may be out of scope but the list must exist. |
| Backfill write volume on the node PG | low–medium | Use the repo's `retry_on_locked` write discipline (ADR-007) and batch. |

## Validation Requirements

- Direct-count assertion tests for AC 2, 3, 5 (per ADR-007: every new write path in
  `backend/db/repositories/` ships a direct-count assertion test).
- Measured before/after inheritance rate against real rows, not fixtures, for AC 6.
- Column-parity check for AC 4.
- Backend tests only for correctness — no frontend file changes are in scope.
- **One browser spot-check IS required** (amended at Opus sanity review 2026-08-03). The expansion
  correctly found that no frontend code changes, but ~1,504 subagent cards that render **no** skill
  badge today will begin rendering one (`components/SessionInspector.tsx:5415-5422`). No code
  changed, yet the observable surface did. Load a session family with inherited subagent skills and
  confirm the badges render without breaking card layout. This is a spot-check, not a full smoke
  gate, and it does not license fixing the missing provenance affordance.

## Completion Report Required

Yes. Must state: achieved inheritance rate vs the 51.3% baseline, rows backfilled, observed effect
on `routing_rollup` NULL key count, and the transitivity decision taken under constraint 5.

--- EXPAND BELOW ---

## UX / Behavior Requirements

This contract has no UI surface in scope (per the design block's Validation Requirements). **One
existing surface's meaning changes as a side effect, and it must be named rather than silently
expanded into scope:**

- `components/SessionInspector.tsx:5415-5422` renders a skill badge
  (`title={\`Skill: ${session.skillName}\`}`) whenever `session.skillName` is non-null, identical
  in style to every other detection badge on the card. `components/SessionInspector/TranscriptView.tsx:828-844`
  does the same for transcript skill-mention tokens. Neither surface distinguishes a directly
  detected skill from an inherited one — there is no `skillNameSource` field on the frontend
  `AgentSession` type (`types.ts:581` has only `skillName?: string | null`).
- **Effect after this ships**: a subagent card that previously showed no skill badge will begin
  showing one, styled identically to a directly-observed skill, for every session the backfill or
  forward inheritance touches. This is a genuine, visible behavior change — not a bug, but not
  cosmetically neutral either.
- **Decision: do not fix this UI surface in this contract.** Adding a provenance affordance (e.g.
  a distinct badge style or a tooltip suffix for inherited skills) requires a `skillNameSource`
  field on `types.ts` and the session DTO (`backend/routers/api.py:889,1311`), which are themselves
  out of scope per the design block's Architecture Constraints. Flagging this here satisfies the
  requirement to surface it explicitly rather than let it expand scope.
- **Follow-up recommendation** (record in the Completion Report's "Follow-up recommendations", do
  not implement): once `skill_name_source` exists, add `skillNameSource` to `AgentSession` and a
  minimal visual distinction (e.g. a small "inherited" glyph or `title` suffix) on both badge
  render sites above.
- No runtime smoke gate is required for this contract (backend-only change, per Validation
  Requirements). If the executor finds any other UI surface reading `skill_name`, treat it the same
  way — name it in the Completion Report, do not fix it.

## Data Requirements

**New column**: `sessions.skill_name_source`

| Property | Value |
|---|---|
| Type | `TEXT` (matches `effort_tier_source`'s type token exactly) |
| Nullable | Yes, no default, never backfilled onto pre-existing rows without a real derivation |
| Vocabulary | Closed: `directly_detected`, `inherited_from_parent` |
| Schema version | **49** (current max is 48 — `SCHEMA_VERSION = 48` at `backend/db/postgres_migrations.py:46` and `backend/db/sqlite_migrations.py:68`) |

**Vocabulary module**: new `backend/parsers/skill_provenance.py`, mirroring
`backend/parsers/effort_provenance.py` (the Gap 4 / schema v44 precedent) shape-for-shape:

- `SKILL_SOURCE_DIRECT: Final[str] = "directly_detected"` — the session's own transcript produced a
  non-None `_primary_skill_name` result.
- `SKILL_SOURCE_INHERITED_PARENT: Final[str] = "inherited_from_parent"` — copied from the parent's
  `skill_name` (one hop only — see Implementation Notes §6 for the transitivity decision).
- `SKILL_SOURCE_TRUST_ORDER: Final[tuple[str, ...]] = (SKILL_SOURCE_DIRECT, SKILL_SOURCE_INHERITED_PARENT)`
  — direct always outranks inherited, mirroring `EFFORT_SOURCE_TRUST_ORDER`.
- `KNOWN_SKILL_SOURCES: Final[frozenset[str]]` for validation/tests.
- Contract note in the module docstring, copied from `effort_provenance.py:34-37`: `skill_name_source`
  is written only where `skill_name` itself is; a non-null `skill_name` with a null `source` means
  the row predates this column (unknown provenance, not backfilled/guessed). A null `skill_name`
  always carries a null `source`. Consumers MUST treat an unrecognized token as "unknown
  provenance," never hard-fail.

**Dual-DDL touch points** (both backends, same change set, per CLAUDE.md's "DB write paths" rule):

- `backend/db/postgres_migrations.py`: add `skill_name_source TEXT` to the `sessions` `CREATE TABLE`
  block immediately after `effort_tier_source TEXT` (line 226), with a comment mirroring the
  existing `effort_tier_source` comment (lines 220-225: token vocabulary location, NULL semantics,
  no backfill). Add a new `# ── v49 migrations` block calling
  `await _ensure_column(db, "sessions", "skill_name_source", "TEXT")`, following the `_ensure_column`
  pattern at line 3980 (the v44 block). Bump `SCHEMA_VERSION` from 48 to 49 (line 46).
- `backend/db/sqlite_migrations.py`: identical shape — `CREATE TABLE` addition after
  `effort_tier_source TEXT` (line 248), `_ensure_column(db, "sessions", "skill_name_source", "TEXT")`
  in a v49 block following the pattern at line 4445, `SCHEMA_VERSION` 48→49 (line 68).
- `COLUMN_PARITY_DRIFT_ALLOWLIST`: add **no entry**. This column must be identical in both backends
  with zero drift, mirroring the zero-entries pattern asserted for `aar_reviews` and `routing_rollup`
  in `backend/tests/test_aar_reviews_repo.py:89-98`.
- New test: `backend/tests/test_skill_name_source_provenance.py`, mirroring
  `backend/tests/test_effort_tier_source_provenance.py` (referenced at `effort_provenance.py:44-46`)
  — asserts the column exists identically in both DDLs and that the vocabulary constants used by
  any standalone script (if one repeats the literals) stay in sync with `skill_provenance.py`.

## API / Integration Requirements

No new endpoints, no external service calls — this is a pure backend derivation + backfill. The
audit below enumerates every existing `skill_name` reader found via grep across
`backend/application/services/agent_queries/`, `backend/routers/`, and `types.ts`, per the design
block's requirement that this list exist even though fixing these consumers is out of scope.

| Reader | file:line | Inherited meaning-change impact |
|---|---|---|
| Session DTO mapping | `backend/routers/api.py:889`, `:1311` (`skillName=s.get("skill_name")`) | Emits `skillName` to the frontend with no `skillNameSource` companion field; a consumer cannot tell direct from inherited from this payload alone. |
| AAR review enrichment | `backend/application/services/agent_queries/aar_review_enrichment.py:362-364` (`skill_name = str(session_payload.get("skill_name") ...)`) | Folds `skill_name` into a human-readable summary string (`skill={name}`); will now sometimes summarize an inherited value as if observed. |
| Routing rollup (the routing-feedback key itself) | `backend/application/services/agent_queries/routing_rollup.py:578,602` (`skill_name AS source_skill_name`, `GROUP BY project_id, skill_name, model`) | **Explicitly unchanged by this contract** (see Provenance boundary in the design block). AC 7 requires reporting the real observed NULL-key delta (expected ≈10/113), not claiming a routing-feedback fix. |
| Client-v1 routing transport | `backend/routers/_client_v1_routing_rollup.py:147,221` | Re-derives `source_skill_name` from the rollup row; inherits the same non-change as `routing_rollup.py`. |
| Frontend session type | `types.ts:581` (`skillName?: string \| null`) | No `skillNameSource` field exists; the frontend has no way to distinguish inherited from observed even after this ships. |
| Session detail rendering | `components/SessionInspector.tsx:5415-5422`, `components/SessionInspector/TranscriptView.tsx:828-844` | Renders the badge/token with no provenance indicator — see UX section above. |
| Per-skill feature analytics | `components/Planning/FeatureAnalyticsPanel.tsx:567` (`valuesFromRecords(sessionRows, ['skill', 'skills', 'skillName', 'skillsUsed'])`) | This is the analytics beneficiary the Goal cites — after this ships, `observedSkills` for a feature mixes directly-observed and inherited attributions with no way to separate them. Beneficiary-with-caveat, not a defect. |

## Implementation Notes

Change sites, in dependency order:

1. **Provenance vocabulary module** — new `backend/parsers/skill_provenance.py`, per Data
   Requirements above. No behavior yet; this is the shared vocabulary both the write path and the
   backfill import.

2. **The parser cannot do this at parse time.** `backend/parsers/platforms/claude_code/parser.py:1400-1412`
   (`_primary_skill_name`) and its two feeders — `:4604` (fork sessions) and `:4670`
   (root/subagent sessions) — each derive `skillName` purely from that *one session's own*
   `session_context["skillLoads"]`, itself populated only by `process_skill_payload_from_message`
   (`:2288-2333`) firing on that session's own transcript marker. The parser has no cross-session
   state during a single-file parse pass, and sibling sessions in a sync batch may parse in either
   order — the parent's row is not guaranteed to exist in the DB yet when a subagent file parses.
   **Do not attempt to patch inheritance into the parser.** It belongs downstream, where both rows
   are guaranteed to exist.

3. **Repository / post-sync write path.** `backend/db/repositories/sessions.py:96,155` and
   `backend/db/repositories/postgres/sessions.py:43,96` upsert `skill_name` verbatim from parser
   output today (no coalesce — capture-path-findings.md:52). Add an inheritance step after upsert
   (in the same repository method, or in `sync_engine.py`'s per-project post-sync hook — whichever
   already owns a natural "sync pass just finished for this project" boundary) that runs, per
   project:

   ```sql
   UPDATE sessions AS child
   SET skill_name = parent.skill_name,
       skill_name_source = 'inherited_from_parent'
   FROM sessions AS parent
   WHERE parent.id = child.subagent_parent_id
     AND parent.project_id = child.project_id
     AND child.project_id = :project_id
     AND child.skill_name IS NULL
     AND parent.skill_name IS NOT NULL
   ```

   **The join is scoped to `(id, project_id)` on both sides — non-negotiable per Architecture
   Constraint 3.** Two prior legs got this exact join wrong and silently inflated counts
   (capture-path-findings.md:23-28; null-population-findings.md:55-61). Also stamp
   `skill_name_source = 'directly_detected'` at the ordinary upsert whenever `skill_name` comes from
   the parser itself (not from this UPDATE), so every non-null `skill_name` written going forward
   carries a source — this closes AC 3/AC 4 going forward, not just for the backfill.

4. **Migration (schema v49)** — see Data Requirements for the exact dual-DDL edits
   (`backend/db/postgres_migrations.py`, `backend/db/sqlite_migrations.py`).

5. **Backfill.** Same UPDATE...FROM statement as step 3, run once against all historical rows,
   gated by `child.skill_name IS NULL` — a second run therefore touches zero rows by construction
   (direct-count assertion for AC 5). Must never touch a row where `skill_name_source` is already
   `directly_detected`, and must never stamp a source onto a row that already has a non-null
   `skill_name` and a null `source` (that is legitimate pre-column legacy state, per the
   `effort_tier_source` precedent — leave it alone, do not guess).

6. **Transitivity decision — one hop only. Recommendation, not left implicit** (Architecture
   Constraint 5 requires this be decided and documented):

   **Decision: inheritance walks exactly one hop — a child inherits only its direct
   `subagent_parent_id`'s `skill_name`, never a grandparent or the family root.**

   Rationale:
   - The measured 51.3% system-wide baseline (AC 6's comparison point) is itself a one-hop join
     (`null-population-findings.md:210-224`); adopting a different transitivity would invalidate the
     baseline this contract is scored against.
   - Both spikes tested and reported only the one-hop yield (1,504 sessions / 10 of 113 keys); a
     multi-hop walk was neither measured nor found necessary to capture that opportunity — walking
     further finds no additional documented yield, only additional risk.
   - A multi-hop walk requires a cycle guard and an unbounded-depth guard that this dataset's
     nesting depth was never characterized against; adding that complexity for an unmeasured gain is
     not justified at Tier 1.
   - Consequence: an orphaned subagent whose immediate parent is also NULL stays NULL even if a
     grandparent has a skill (constraint 4 — never fabricate, and one-hop-only is the concrete
     enforcement of "do not walk to a sentinel" via unbounded search). This is a known, accepted
     boundary, not a gap this contract closes.

7. **Testing.** Direct-count assertion tests (per ADR-007) for: AC 2 (orphaned subagent — parent
   `skill_name` also NULL — stays NULL after backfill), AC 3 (a directly-detected `skill_name` is
   never overwritten, and its `skill_name_source` reads `directly_detected`), AC 5 (backfill run
   twice changes 0 rows on the second pass), and AC 8 (every join in the shipped code is
   `(id, project_id)`-scoped — assert via a fixture with a duplicate `id` across two projects, the
   exact shape that fooled two prior spike legs). Add `test_skill_name_source_provenance.py` per
   Data Requirements.
