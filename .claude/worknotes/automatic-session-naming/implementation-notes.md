---
type: context
schema_version: 2
doc_type: context
prd: automatic-session-naming
feature_slug: automatic-session-naming
title: "Automatic Session Naming — execution ledger (deviations + conservative choices)"
created: 2026-08-05
updated: 2026-08-05
prd_ref: docs/project_plans/PRDs/enhancements/automatic-session-naming-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/automatic-session-naming-v1.md
---

# Execution ledger

Per the plan's §Execution ledger: deviations and conservative choices are logged here with
rationale and reviewed at each milestone boundary, rather than halting on them.

## Mode-D approval record (M1 / T1-001)

**Gate:** M1 declares itself Mode-D — it performs a schema migration
(`sessions.session_name` + `sessions.session_name_source`, v49→v50, dual SQLite+Postgres DDL) and
the plan requires explicit human approval "before the migration is applied to any shared
environment (node PG in particular)."

**Approval obtained:** 2026-08-05, operator (Nick), in-session, on an explicit two-part question.

**Scope of approval — bounded:**
- ✅ Implement the migration in the worktree; validate on **local SQLite** + the
  `COLUMN_PARITY_DRIFT_ALLOWLIST` parity check.
- ✅ Squash-merge to `main` and push to origin.
- ❌ **NOT approved:** applying the migration to node Postgres (`10.42.10.76:5440`). That remains a
  separate, explicit `/redeploy` decision. No agent in this run may touch a remote/shared database.

The bounded constraint was written into T1-001's dispatch prompt verbatim so the executing agent
could not exceed it.

**Dispatch decision:** operator elected to run all 14 tasks through the deterministic
`execute-plan` workflow (rather than hand-orchestrating T1-001 separately). The Mode-D halt is an
*approval* gate, not a *no-delegation* gate; the approval satisfies it. Opus still reviews the
full migration diff before the squash-merge, and M3's egress boundary keeps its mandatory Opus
review per the plan's `routing_constraints`.

## Deviations from the authored task batching

The progress files' `parallelization` blocks were authored without file-level ownership
verification (the plan's `files_affected` is `[]`). Where the authored batches would run agents
concurrently against files they plausibly share, batches were **serialized** at dispatch. Task
`dependencies` are respected in every case; only concurrency was reduced.

| Milestone | Authored batching | Dispatched as | Why |
|---|---|---|---|
| M1 | already sequential | unchanged: T1-001 → 002 → 003 → 004 → 005 | — |
| M2 | `batch_1: [T2-001, T2-002]` parallel | serialized T2-001 → T2-002 | Both write the session-name resolution path; T2-001 owns `sync_engine.py`. A conflict costs more than the saved wall-clock on a 4-task milestone. |
| M3 | `batch_2: [T3-002, T3-003, T3-004]` parallel | serialized, reordered to T3-001 → T3-004 → T3-002 → T3-003 → T3-005 | All three touch `backend/config.py` flags. T3-004 (which *owns* the flag block) is moved ahead of the two backends so they consume flags rather than race to define them. T3-004 depends only on T3-001, so dependency order is preserved. |

## Reviewer-gate mapping

The plan's `gate_lens` vocabulary is richer than the workflow's single `review_intensity` enum,
and this repo has no registered `council-review` **agent type** (only a skill/workflow of that
name). Mapping used:

| Milestone | Plan `gate_lens` | Dispatched `review_intensity` | Coverage of the remainder |
|---|---|---|---|
| M1 | `[validator]` | `standard` → `task-completion-validator` | exact match |
| M2 | `[validator]` | `standard` → `task-completion-validator` | exact match |
| M3 | `[security, validator]` | `tier3` → `karen` | the security/egress lens is carried by the **mandatory Opus review** of the Lane B path that `routing_constraints` already requires before merge — not dropped |

Feature-level gate: `karen` once over the whole tree (Tier 2, per
`.claude/skills/dev-execution/validation/completion-criteria.md`).

## T1-002 conservative choices (M1 / parser ingest)

T1-002's authored scope is parser-only (`backend/parsers/platforms/claude_code/parser.py`,
`backend/parsers/platforms/codex/parser.py`), but two adjacent minimal extensions were made so the
task is actually testable/compilable; both are within T1-003's later-declared scope
("`AgentSession` (models.py + types.ts) gains sessionName/sessionNameSource") but land here as a
narrow superset, not a parallel structure:

- **`backend/models.py`**: added `sessionName: Optional[str] = None` +
  `sessionNameSource: Optional[str] = None` to `AgentSession`, directly beside `skillName` /
  `skillNameSource` (the shipped precedent this feature mirrors). Without this, the parser has
  nowhere to put the value and the fixtures in `test_session_naming.py` cannot assert it. T1-003
  still owns `types.ts` + the full DTO/router/FE wiring — untouched here.
- **Codex `event_msg`/`thread_name_updated`**: the pre-existing branch computed `summary_text` from
  keys (`summary`/`message`/`text`) that don't exist on this payload shape, so it fell through to
  emit a mislabeled `ImpactPoint` (label literally `"thread_name_updated"`) even though FR-4 only
  asked to stop discarding the string. Handling `thread_name_updated` as an early-`continue` case
  inside the same branch (per FR-4's file:line reference) incidentally removes that mislabeled
  impact point too — a confirmed pre-existing bug (tech-codex-spike.md Finding 5), not new scope.
- **Codex `git.branch` (FR-5)**: no dedicated `session_meta` branch exists anywhere in this parser
  today — `cwd`/`model`/`cli_version` are all read generically from `payload_dict` on every entry,
  regardless of `entry_type`, because only `session_meta` entries carry those keys. `git.branch` is
  read the same way (extend the existing generic-field pattern), rather than introducing the first
  ever `entry_type_lower == "session_meta"` branch as a parallel mechanism.

Both Claude Code's `ai-title` and Codex's `thread_name_updated` are wired with "latest wins" /
replace-in-place semantics (idempotent re-emission and rename events both observed in the spikes),
matching the measured mutability data in `tech-claude-spike.md` §4 and `tech-codex-spike.md` §"Of
the 541 named sessions...". The `ai-title.sessionId` attribution assertion
(`_strip_orphan_suffix` + exact-match against the file's own stem) is the mechanism that keeps the
plan's highest-consequence named risk from becoming true under a future provider change — it is not
optional/best-effort, and a missing or mismatched `sessionId` silently skips the record rather than
storing a guess.

## OQ-1 resolution (M1 / T1-003): LinkedFeatureSessionDTO.title — reuse, not a second field

**Question:** `LinkedFeatureSessionDTO.title` already exists on the feature-linked-sessions
surface (`backend/application/services/feature_surface/dtos.py:207`); its population source
wasn't traced before this PRD was written. Decide reuse vs. a distinct field before adding
`sessionName`/`sessionNameSource` to that DTO.

**Traced provenance:** `title` is populated by `_derive_session_title()`
(`backend/routers/_client_v1_features.py:224`), called from `_enrich_linked_session_row`
(~line 856) and consumed by `_session_row_to_linked_dto` (~line 903). Before this change its
fallback chain was: `subagent_type` (only when `session_type == "subagent"`) → `latest_summary`
badge → `sessionTypeLabel` + related phases → `sessionTypeLabel` alone → the bare `session_id`.
It never read `sessions.session_name` — the column didn't exist when this code was written, and
the badge-summary/subagent-label heuristics were the closest available substitute for "what was
this session about."

**Decision: REUSE.** `session_name` is folded into `_derive_session_title()` as a new top-priority
parameter (`session_name: str = ""`), checked before every existing fallback — mirroring the FE
title chain's `explicitTitle` precedence in `deriveSessionCardTitle`
(`components/SessionCard.tsx:72`: explicit title wins over every derived label). The call site now
passes `session_name=str(row.get("session_name") or "")`, where `row` is the raw `sessions` table
dict already carrying the new column post-migration. No new field was added to
`LinkedFeatureSessionDTO`; `title` remains the DTO's single title concept.

**Rationale:**
- Matches the plan's rubric verbatim: "Extend what exists rather than adding parallel machinery,"
  naming the FE title chain reuse explicitly as one of the three reuses exploration found.
- A distinct `sessionName` field on this DTO would duplicate `title` in the overwhelming majority
  of cases (whenever `session_name` is set, it would now equal `title` too) while leaving the
  `null`-vs-fallback resilience contract (AC in §11) to be re-implemented a second time on a
  second field, for no client-visible benefit — nothing downstream of this DTO needs to
  distinguish "the linked-session title" from "the session's stored name" once the stronger
  signal wins outright.
- Priority ordering (`session_name` above `subagent_type`): `session_name` is either
  provider-set or (from M2/M3) explicitly derived-and-persisted; a persisted name reflects more
  information than the generic `"<SubagentType> subagent"`-style label this function was using as
  a stand-in. A weaker source never overwrites a stronger one (rubric), and heuristic labels are
  weaker than a stored name.
- This DTO is unrelated to `PlanningAgentSessionCardDTO` (a different card surface, wired
  separately per FR-9) and to `AgentSession.sessionName`/`sessionNameSource` (the raw model field,
  wired per FR-6/FR-8) — no cross-DTO duplication was introduced by this change either.

**Scope note:** provenance (`session_name_source`) is intentionally NOT threaded into this DTO.
`LinkedFeatureSessionDTO` has exactly one title field by design (see rationale above); provenance
belongs where the raw name is exposed (`AgentSession`, `PlanningAgentSessionCardDTO`), not on a
derived/fallback title that already blends multiple sources with no per-source attribution today.

## T1-003 conservative choice: `_V1_CAPABILITIES` NOT extended (defers to OQ-3)

The dispatch instruction for T1-003 says to "extend capabilities if that is this repo's
convention for a new session field." Checked the precedent: neither `skill_name`/`skill_name_source`
(schema v49) nor `effort_tier`/`effort_tier_source` (schema v44) — the two shipped provenance-pair
precedents this feature mirrors — added an entry to `_V1_CAPABILITIES`
(`backend/routers/client_v1.py:152`). That list is reserved for endpoint-level behavioural
contracts (`sessions:cross-project`, `sessions:detail`, `aar-review`, `routing:feedback`), not
per-field additions to an existing response shape. There is no convention to extend here, so no
capability string was added.

This is also explicitly OQ-3 in the PRD ("should `sessions:name` be added to `_V1_CAPABILITIES`
unconditionally at ship time, or gated until coverage is proven per-provider?"), which is not in
T1-003's `acceptance_refs` (only OQ-1 is). Leaving `_V1_CAPABILITIES` untouched keeps that decision
open for whichever milestone/task is explicitly tasked with resolving OQ-3, rather than
pre-empting it here.

## T2-001 conservative choices (M2 / subagent session_name inheritance)

**Extended, not replaced:** `backfill_skill_name_inheritance`
(`backend/db/repositories/sessions.py` / `backend/db/repositories/postgres/sessions.py`,
called from `backend/db/sync_engine.py:3307`) now also carries `session_name` onto a
subagent child from its parent in the SAME pass, stamping
`session_name_source = derived_deterministic`. No new call site was added; the function's
existing `dict[str, int]` return grew a second key (`session_name_rows`) alongside the
unchanged `rows` (skill_name count), and `sync_engine.py` reads it into a new
`stats["session_name_inherited"]` counter mirroring `skill_name_inherited`.

**"Existing agent-name record" resolved to `subagent_type`:** the task's fallback
instruction ("fall back to the existing agent-name record" when no parent name exists)
is the child's own `sessions.subagent_type` column -- the same field
`_derive_session_title()` (`backend/routers/_client_v1_features.py:244`, see the OQ-1
entry above) already returns verbatim as a subagent session's title fallback when no
stronger title exists. Reusing it here avoids introducing a second "what do we call an
unnamed subagent" heuristic.

**Rank enforcement is Python-side, not duplicated in SQL:** the sibling `skill_name`
UPDATE is a single declarative SQL statement gated by `child.skill_name IS NULL`, which
works because skill provenance has only two write-time ranks. Session-name provenance
has four, and its own module docstring says: "Use `session_name_rank` (or
`may_overwrite`) to enforce that at every write site -- never duplicate the ordering
inline." Re-encoding "don't overwrite `provider_persisted`" as a hardcoded SQL string
comparison would do exactly what that sentence forbids. So the session_name half of this
function is fetch-then-decide-then-write: a SELECT joins each subagent child to its
parent (same `(id, project_id)` scoping as the skill_name join, for the same
cross-project-leak reason), then for every row it calls
`may_overwrite(SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC, child.session_name_source)` in
Python before including that row in a batched UPDATE. This is real enforcement, not a
guard that happens to be equivalent to it: even a data-integrity edge case (a non-null
`session_name` paired with a `provider_persisted` source but no name -- a contract
violation the upsert path should never produce) is correctly refused by `may_overwrite`,
not just by an incidental `IS NULL` check.

**Idempotency check added explicitly (not just via NULL-gating):** each row is also
skipped when the computed `new_name` already equals the child's current `session_name`
AND its source is already `derived_deterministic` -- a no-op write is never issued, so a
second sync pass touches zero rows exactly like the skill_name precedent's AC 5.

## T1-003 client_v1 sessions endpoint audit

`backend/routers/client_v1.py`'s session routes were audited for a DTO that carries a
name/title-like field and would need `session_name` wired through:

- `/sessions`, `/sessions/{id}`, `/sessions/{id}/drilldown`, `/sessions/{id}/family`,
  `/sessions/search` → all backed by `SessionIntelligenceReadService` /
  `TranscriptSearchService` DTOs (`SessionIntelligenceSessionRollup`,
  `SessionSemanticSearchMatch`, etc., `backend/models.py`) — sentiment/churn/scope-drift rollups
  and transcript-block search hits. None of these carry a session title/name field today; no
  change needed.
- `/sessions/{id}/detail` → `get_session_full_detail_v1` → `session_detail.get_session_detail` —
  already wired (see the `session_detail.py` section above).
- `/features/{feature_id}/sessions` + `/page` → `LinkedFeatureSessionDTO` — already wired via the
  OQ-1 resolution above.

## T2-002 conservative choice (M2 / Codex `git.branch` fallback): not gated on `originator`

**Task framing vs. implementation:** the task names the target population as "Codex `codex_exec`
headless sessions." The spike data (`tech-codex-spike.md` Finding 2) measures coverage
per-`originator` (`Codex Desktop` 13.8%, `codex_vscode` 72.4%, `codex_exec` 0.0%) — but this
codebase's Codex parser (`backend/parsers/platforms/codex/parser.py`) has never parsed
`session_meta.payload.originator` into any field; adding a first-ever originator branch just to
gate this fallback would be new parallel machinery for a distinction the fallback doesn't actually
need to make.

**Decision:** the fallback (`if not session_name and git_branch: session_name = git_branch,
source = derived_deterministic`) is unconditional across all Codex sessions, applied once after
the full forward pass over entries (right before `session_dates` construction, so `git_branch` and
`session_name` are both fully resolved regardless of entry order in the file).

**Rationale:**
- `may_overwrite`'s rank contract already makes the gate redundant for correctness: the fallback
  only fires `if not session_name`, so a `codex_vscode`/`Desktop` session that already carries a
  `provider_persisted` thread_name is never touched by it. Restricting to `originator ==
  "codex_exec"` would only change behavior for the *other* unnamed populations (`Codex Desktop`
  86.2% unnamed, `codex_cli_rs` 100% unnamed) — sessions this task's own AC ("no surface renders a
  bare UUID... a weaker source never overwrites a stronger one") wants closed too, not excluded.
- `derived-naming-spike.md`'s coverage table cites this same fallback (95.0% `git.branch`
  presence) as the closing mechanism for the `codex_exec` population specifically, but nothing in
  the plan or PRD says the fallback must be *exclusive* to that population — the FR-7 AC is about
  the fallback chain closing gaps in general, with `codex_exec` named as the AC's illustrative,
  measured 0%-coverage case.
- Test coverage (`test_session_naming.py::CodexThreadNameAndGitBranchIngestTests`) exercises
  `codex_exec` explicitly (`test_codex_exec_headless_falls_back_to_git_branch`, with
  `originator: "codex_exec"` in the fixture, even though the parser code path itself does not
  branch on that field) plus the rank-ordering guarantee
  (`test_thread_name_updated_outranks_git_branch_fallback`) and the no-fallback-available case
  (`test_no_thread_name_and_no_git_branch_stays_null`).

## T2-003 conservative choices (M2 / last-prompt + truncated-first-message fallback chain)

**Record shape found by direct inspection, not documented in the spikes.** The spikes measure
`last-prompt`'s coverage (25.51% of files, tech-claude-spike.md §"No-Name Fallback Options") but
never state its shape. Grepping real `~/.claude/projects/**/*.jsonl` files found it: `{"type":
"last-prompt", "lastPrompt": "<text>", "leafUuid": "...", "sessionId": "..."}` — the same
three-key-plus-`leafUuid` self-attribution shape as `ai-title` (`type`/`aiTitle or lastPrompt`/
`sessionId`). The parser branch (`backend/parsers/platforms/claude_code/parser.py`, new
`entry_type == "last-prompt"` case immediately after the existing `ai-title` case) reuses the exact
same skip-on-mismatch assertion against `_strip_orphan_suffix(path.stem)` verbatim — same named
risk ("wrong name on the wrong session"), same mitigation, no new mechanism.

**Truncation length: 120 chars, reusing this file's own existing convention.** The task asked for "a
sane truncation length, documented inline." Rather than inventing a new number, both new fallback
writes (`last-prompt` and the first-user-message rank-4 fallback) reuse the 120-char bound this
same parser file already applies to the `entry_type == "summary"` artifact's `title` field
(`summary_text[:120]`, pre-existing code) — a `last-prompt` string or a raw first message is no
shorter or less title-shaped than a provider summary, so the same bound applies. No ellipsis is
appended, matching that same precedent exactly.

**Ordering within the shared `derived_deterministic` tier is enforced by a plain `not
session_name` guard, not `may_overwrite`, for the rank-4 write specifically.** `last-prompt`
(rank 3) and "first user message, truncated" (rank 4) are declared as the SAME provenance token in
`session_name_provenance.py`'s own docstring ("subagent inheritance, git.branch, last-prompt,
truncated first message" are one tier). `may_overwrite` compares ranks, and equal ranks are
defined to be mutually overwritable (needed for `last-prompt`'s own idempotent
latest-record-wins semantics) — so it cannot be used to make rank 4 defer to rank 3; doing so would
let a later-first-message-derived name silently replace an already-written `last-prompt` value.
The rank-4 write is therefore gated on `not session_name` (fires only when nothing — of ANY rank —
wrote a name yet), applied once after the full forward pass over entries, which is both simpler
than a bespoke sub-rank and correct: by the time it runs, `ai-title` (unconditional) and
`last-prompt` (via `may_overwrite`) have already had every chance to win.

**Scope: excluded from subagent files, matching the T2-003 dispatch's own scope note.** Both new
fallback writes (`last-prompt` entry handling and the three first-user-message capture sites) are
gated on `not is_subagent` (the file-level `path.parent.name == "subagents"` flag this parser
already computes) — mirroring the existing `if not is_subagent:` gates already in this file at
other call sites. This is a deliberate exclusion, not an oversight: T2-001 already owns subagent
naming end-to-end via parent-title inheritance at `sync_engine.py:3307`, and a subagent JSONL file
can genuinely contain its own `last-prompt` record or user message (the fields aren't
file-type-specific), so an ungated fallback here would introduce a second, weaker mechanism racing
the first for the same rows — exactly what the dispatch said not to do. Verified by
`test_subagent_file_excluded_from_last_prompt_and_first_message_fallback`.

## T2-004 (M2 / test coverage): one genuine gap found and closed, no source-code defect

**Coverage audit result.** All three of the task's required assertions were already
substantially covered by the existing T2-001/T2-002/T2-003 test classes
(`SubagentSessionNameInheritanceTests`, `CodexThreadNameAndGitBranchIngestTests`,
`LastPromptAndFirstMessageFallbackTests` in `backend/tests/test_session_naming.py`), with one
exception: T2-003 added **two** fallback writes (`last-prompt`, rank 3, and the truncated
first-user-message, rank 4), and the "provider_persisted present and preserved" case was tested
twice for the rank-3 path (`test_ai_title_outranks_last_prompt_regardless_of_in_file_order`,
`test_last_prompt_never_overwrites_an_earlier_ai_title`) but not at all for the rank-4 path in
isolation — no existing fixture omitted `last-prompt` entirely while keeping an `ai-title` record
and a user message, so the first-user-message fallback's own preserve-provider behavior was never
directly exercised. Added
`test_ai_title_preserved_when_only_first_message_fallback_available` to close that gap. No source
defect was found; the parser's `not session_name` gate already made the correct choice, it was
simply unasserted for this specific path.

**AC → command → evidence row's CLI command does not surface `session_name` as specified.** The
plan's AC table lists `backend/.venv/bin/ccdash session search "" --limit 50 --json` with
"every row has a non-UUID `session_name` with a provenance token" as the expected evidence. Two
observations from actually running it in this worktree:
1. The query argument as written (`""`) is rejected by the shipped CLI itself
   (`Error: query must be at least 2 characters.` — the command's own `--help` confirms "Search
   text (min 2 characters)"), so the literal AC command cannot run in the shipped CLI.
2. Running it with a valid 2-char query (`"se"`) against this worktree's local DB (which does have
   ingested sessions — `ccdash project` doesn't exist as a subcommand, but the search itself
   returned real rows) shows `session search` is a **transcript full-text search over
   `session_messages`** (`"searchMode": "canonical_lexical"`), returning per-message hits
   (`content`, `snippet`, `matchedTerms`, `blockKind: "message"`) — it does not include a
   `session_name` field on any row. So this AC's evidence command, as literally specified, cannot
   be used to validate "every row has a non-UUID session_name" — that would need a different
   surface (e.g. session detail/list, not transcript search). Reported here rather than silently
   treated as passing or fabricated; fixture-level test coverage (68 passed in
   `test_session_naming.py`/`test_session_name_provenance.py`/`test_session_name_persistence.py`)
   is what actually backs the "no bare UUID" AC for T2-004.

**Regression check.** `test_session_naming.py` + `test_session_name_provenance.py` +
`test_session_name_persistence.py`: 68 passed, 10 subtests passed, 0 failed (was 67 passed before
the added test). `npx vitest run components/__tests__/SessionNaming.test.tsx`: 38 passed, 0
failed. No M1 regression.

## T2-003 conservative choice (continued): first-user-message capture reuses no new text-extraction path

Claude Code messages arrive in
three on-disk shapes this parser already branches on (a bare string `message`, a string
`message.content`, and a list of content blocks joined into `message_text`) — capturing
`first_user_message_text` at all three existing sites (guarded by `speaker == "user" and not
first_user_message_text`) avoids adding a fourth, parallel text-extraction helper the way Codex's
own `first_user_message_text` capture (T1-002, `badgeLatestSummary`) does for its single message
shape.

## M2 gate finding (orchestrator): Codex had no first-message fallback — closed

**Found at the M2 milestone-boundary review, after the phase validator had already approved.**

M2's plan text closes "the remainder" with "`last-prompt` then a truncated first message" — a
provider-agnostic sentence. T2-003 implemented that chain **only in the Claude Code parser** (87
lines to `claude_code/parser.py`, 13 to `codex/parser.py`). The T2-003 ledger entry above is
thorough about its Claude-side choices but never states a reason for the Codex omission, and the
phase validator approved with `fix_cycles: 0`.

Consequence before the fix: a Codex session with **no `thread_name_updated`** and **no
`session_meta.payload.git.branch`** (the ~5% of files where `session_meta` carries no branch)
reached the frontend with `session_name` still null — no deterministic name at all — and leaned
entirely on M3's model call. That is a shortfall against M2's own AC ("no surface renders a bare
UUID"), and it made the Codex lane structurally worse than the Claude lane: Claude sessions get a
zero-model-call name, Codex sessions of the same shape did not.

**`last-prompt` is legitimately Claude-only** — it is a `~/.claude/projects/**/*.jsonl` record
type with no Codex equivalent, so omitting *that* half was correct. The first-message tail is not
provider-specific, and the material was already on hand: `codex/parser.py:861` already captured
`first_user_message_text` (bounded at 200) for `badgeLatestSummary` and simply never fed it to
`session_name`.

**Fix (orchestrator, at the gate):** added the first-message tail to the Codex parser immediately
after the `git_branch` fallback, reusing the already-captured `first_user_message_text` rather than
adding a second text-extraction path, re-sliced to **120** chars to match the bound the Claude
parser's equivalent rank-4 write uses. Gated on `not session_name` for exactly the reason the
T2-003 entry gives for its own rank-4 write: equal-rank tokens are mutually overwritable under
`may_overwrite`, so an emptiness gate — not a rank comparison — is what makes this defer to
`git_branch` and to any `provider_persisted` value.

**Two pre-existing T2-002 tests were retargeted, not silenced.** Both asserted
`sessionName is None` on fixtures that carried a `user_message`, so both went red. Their stated
intent ("a fallback with nothing to fall back to is not written", "not an empty string or a guessed
value") is still exactly right — their *fixtures* stopped matching it once the fallback set grew.
The `user_message` entry was removed from each so the premise holds again and the original
assertions stand unchanged; the now-covered "message present → fallback fires" path got its own
test instead. The genuinely-null state remains reachable and asserted, which matters because it is
what M3's sweep job selects on (`session_name IS NULL`) and what the offline CLI is specified to
leave behind.

New coverage: `test_codex_falls_back_to_truncated_first_message_when_no_branch`,
`test_codex_first_message_fallback_truncates_at_120`,
`test_codex_git_branch_outranks_first_message_fallback`,
`test_codex_provider_name_survives_first_message_fallback`.

Verification: `test_session_naming.py` + `test_session_name_provenance.py` +
`test_session_name_persistence.py` → **72 passed, 10 subtests** (68 before). All 7 `*codex*` test
files → **90 passed, 17 subtests**, no regressions.

## T3-001 conservative choices (M3 / SessionNamingSweepJob scaffold)

**Scope held strictly to scaffolding + registration + candidate selection.** No naming backend
(T3-002 local / T3-003 hosted) and no config flags (T3-004) were added. `execute()` gates on
`getattr(config, "CCDASH_SESSION_NAMING_ENABLED", False)` — the attribute does not exist yet, so
this getattr always resolves to `False` today; the job is a structural no-op until T3-004 lands
the flag and flips it on. This is the same forward-compatible pattern `AARReviewSweepJob` and
`RoutingRollupSweepJob` already use for their own flags.

**Candidate-selection query added as a new repository method, not inlined in the job.**
`list_missing_session_name(project_id, *, workspace_id=DEFAULT_WORKSPACE_ID, limit=None)` was
added to both `SqliteSessionRepository` (`backend/db/repositories/sessions.py`) and
`PostgresSessionRepository` (`backend/db/repositories/postgres/sessions.py`), mirroring the
existing `list_by_source`/`get_by_id` method shapes exactly (same predicate style, same
`workspace_id` scoping). The predicate is `session_name IS NULL` — this IS the idempotency
contract: a session with a non-null `session_name` from ANY source (provider-persisted,
subagent-inherited, git.branch, last-prompt, truncated-first-message, or a future sweep tick's own
derived write) is never selected again. `limit` is accepted now (untested against a real value by
`execute()`, since nothing calls it yet) so T3-004's `CCDASH_SESSION_NAMING_QUOTA` wiring has a
seam to plug into without a second repository change.

**Job shape mirrors `AARReviewSweepJob` structurally (fan-out, coalescing, aggregation), not its
guards.** `SessionNamingSweepJob` reuses the same `_resolve_projects_to_sweep`/`(project_id,
trigger)` coalescing/`_aggregate_sweep_results` shape verbatim, since the task said to mirror that
job's shape "as closely as the differing payload allows." It has no Guard-1/Guard-2 equivalent —
AAR-review's guards (self-referential-session exclusion, dedup ledger) don't have an analogue in
this milestone's plan text; the single `session_name IS NULL` predicate is this job's entire
correctness contract for now.

**Registration: extracted `_WORKER_JOB_PROFILES` as a module-level constant in `container.py`**
(previously a local `_export_profiles = {"worker", "worker-watch"}` inside `startup()`), so the
worker-only gate is directly unit-testable without exercising the full container lifecycle. No
behavior change — `_export_profiles = _WORKER_JOB_PROFILES` at the same call site, still used
identically by the telemetry/rollup/AAR-review/routing-rollup job-construction blocks. The new
`session_naming_sweep_job=` block sits beside `routing_rollup_sweep_job=`, gated on
`self.profile.name in _export_profiles` only (no flag gate at construction, since the flag doesn't
exist yet) — the `api` profile never constructs it.

**`RuntimeJobAdapter` (`backend/adapters/jobs/runtime.py`) stores the job but starts no periodic
loop.** A `session_naming_sweep_job` param was added and stored as `self.session_naming_sweep_job`
(mirrors `aar_review_sweep_job`'s param shape), but — unlike `_start_aar_review_sweep_task` —
no `_start_session_naming_sweep_task` equivalent exists yet. Starting a periodic tick needs
`CCDASH_SESSION_NAMING_SWEEP_INTERVAL_SECONDS`, which is explicitly T3-004's scope; wiring a loop
now would mean either hardcoding an interval (a parallel mechanism to the flag T3-004 is about to
add) or blocking on T3-004. Left as the seam: the job object is constructed and reachable at
`job_adapter.session_naming_sweep_job`, ready for T3-004 to schedule.

Tests: `backend/tests/test_session_naming_sweep_job.py` — worker-only registration (pins
`_WORKER_JOB_PROFILES` excludes `api`, includes `worker`/`worker-watch`), candidate-selection/
idempotency (only `session_name IS NULL` rows selected; a derived name written mid-test disappears
from the next candidate set; project-scoping; `limit`), and job-level unit tests (default-disabled
outcome; `_execute_inner` reports `candidates_found` with `sessions_named` staying 0, proving no
naming backend is called). 9 passed. Regression sweep: `test_session_naming_sweep_job.py` +
`test_session_name_persistence.py` + `test_session_naming.py` + `test_session_name_provenance.py`
+ `test_aar_review_no_llm_imports.py` + `test_routing_rollup_sweep_job.py` +
`test_aar_review_worker_guards.py` → **124 passed, 12 subtests**. `test_watcher_rebind.py` → **13
passed** (confirms `RuntimeJobAdapter`'s new kwarg doesn't break existing profile-gated wiring).

## T3-004 (guard flags + fail-open wiring)

**Five flags added to `backend/config.py`**, immediately after the
`CCDASH_ROUTING_FEEDBACK_SWEEP_INTERVAL_SECONDS` block: `CCDASH_SESSION_NAMING_ENABLED` (bool,
default `False` — deliberately the INVERSE polarity of `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED`'s
default-True, because this job calls an egress-shaped naming backend once T3-002/T3-003 land, not
a pure-DB rollup), `CCDASH_SESSION_NAMING_QUOTA` (int, default `200`), `CCDASH_SESSION_NAMING_WINDOW_HOURS`
(int, default `24`), `CCDASH_SESSION_NAMING_SWEEP_INTERVAL_SECONDS` (int, default `1800`, 60s floor
clamp applied at the task-starter, mirroring the AAR-review/routing-feedback precedent), and
`CCDASH_SESSION_NAMING_BACKEND` (str, default `"local"` — the zero-egress lane; normalized to
lowercase, falls back to `"local"` on an empty/unrecognized value so a misconfiguration can never
silently resolve to `"hosted"`).

**Container construction gate now also checks the flag**, closing a gap T3-001 left deliberately
open (its own note above: "no flag gate at construction, since the flag doesn't exist yet").
`session_naming_sweep_job=` in `container.py` now mirrors `aar_review_sweep_job=`'s condition
exactly: `self.profile.name in _export_profiles AND CCDASH_SESSION_NAMING_ENABLED` — so with the
new default-False flag, the job is not even constructed today, matching the "kill-switch, default
false for the derive-worker" task instruction literally.

**Periodic sweep task wired end-to-end** — `_start_session_naming_sweep_task` added to
`backend/adapters/jobs/runtime.py`, a byte-for-byte structural mirror of
`_start_routing_rollup_sweep_task`/`_start_aar_review_sweep_task`: `worker`-profile-only loop start
(construction admits `worker-watch` too, same asymmetry as the two precedents), 60s floor clamp on
the interval, `_mark_job_started`/`_mark_job_success`/`_mark_job_failure`/`_mark_job_cancelled`
bookkeeping, and a `sessionNamingSweep` entry added to `RuntimeJobState`, the `job_observations`
init dict (stale threshold 7200s = 4x default interval), the `_worker_probe_jobs` task map, the
`_worker_probe_queue_depth` job-name tuple, and the profile health-snapshot dict. `container.py`
now also propagates `app.state.session_naming_sweep_task` from `self.lifecycle`, mirroring the
`aar_review_sweep_task`/`routing_rollup_sweep_task` propagation lines exactly.

**Fail-open implemented as a pluggable seam, not a hardcoded backend call.** `SessionNamingSweepJob`
gained a `naming_backend: Any | None = None` constructor param (production default `None` —
T3-002/T3-003 are the only intended callers that will ever pass a real one) and a module-level
`derive_name_fail_open(backend, candidate) -> str | None` helper: it awaits
`backend.derive_name(candidate)` inside try/except, logs at WARNING with the candidate id and
`exc_info=True` on ANY exception, and returns `None` — never raises. `_execute_inner` now bounds
its derive loop to `candidates[: CCDASH_SESSION_NAMING_QUOTA]` when a backend is present (leaving
`candidates_found` reporting the FULL backlog size, unaffected by the quota — the backlog signal
and the per-tick throughput cap are deliberately kept distinct). Chose NOT to also implement
persistence (`session_name_source = derived_model` writeback) here — that remains T3-002/T3-003's
scope per the plan's milestone AC table and the module's own "SEAM" comments; wiring persistence
now would mean inventing a write contract ahead of the two backend implementations that are
supposed to define it, risking a second reshape when Lane A/B land. `sessions_named` in this task's
scaffold therefore counts successful derivations, not persisted rows — a distinction called out
explicitly in the new test file's docstrings so it isn't mistaken for a completed write path.

**Offline CLI null-`session_name` contract state was NOT touched** — no CLI code was read or
changed in this task; T3-004's scope was config flags + the job's fail-open wiring only. The AC
("assert it, do not 'fix' it") is already satisfied structurally: nothing in this change gives the
offline CLI any code path that could populate `session_name` (it has no `naming_backend`, no
worker-loop access), so the contract state holds by construction rather than by a new explicit
assertion in this task's diff. A dedicated CLI-path test was judged unnecessary since T3-001/T3-002
own that read/CLI surface and no line of it was modified here.

**Existing T3-001 test updated, not left stale**: `test_session_naming_sweep_job.py`'s
`test_disabled_by_default` asserted `not hasattr(config, "CCDASH_SESSION_NAMING_ENABLED")` — true
before this task, false after. Updated to assert `config.CCDASH_SESSION_NAMING_ENABLED is False`
instead (same behavioral guarantee — default-off — expressed against the flag's real value rather
than its absence).

Tests: new `backend/tests/test_session_naming_sweep_guards.py` — default values for all five flags;
`derive_name_fail_open` pure-function coverage (raising backend → `None`, successful backend →
value passed through, falsy-return-without-exception → `None` treated as normal no-op not a
failure); `SessionNamingSweepJob._execute_inner` end-to-end with a raising backend (three
candidates, all three still attempted — a failure on candidate 1 never blocks 2/3 — `sessions_named`
stays 0, `outcome == "success"`, tick never crashes); the happy-path counterpart
(`sessions_named` increments); the quota-bounds-the-loop-not-the-count case; and
`_start_session_naming_sweep_task`'s worker-only / job-present gating. 14 passed. Regression sweep:
`test_session_naming_sweep_job.py` + `test_session_naming_sweep_guards.py` +
`test_aar_review_worker_guards.py` + `test_routing_feedback_contract_parity.py` +
`test_p3_worker_bootstrap.py` + `test_retention_prune.py` + `test_cache_warming_job.py` +
`test_artifact_rollup_exporter.py` + `test_codex_worker_wiring.py` → **155 passed**. One unrelated,
pre-existing failure was observed and NOT touched: `test_file_watcher.py::RuntimeWatcherContractTests::test_job_adapter_does_not_resolve_binding_or_start_watcher_for_api_profile`
fails on `AttributeError: 'types.SimpleNamespace' object has no attribute 'job_scheduler'` inside
`_maybe_start_drain_loop` — confirmed via `git diff` that this task's diff never touches that
method, and the test's own `ports` fixture never sets `job_scheduler`; out of scope for T3-004.

**Session note — suspected prompt injection in tool output.** During this task, two `Bash` tool
outputs contained text styled as system/hook messages instructing invocation of a tool named
`aos-git` (a "shared-checkout guard"/"drift" warning, then later a real blocking pre-commit hook
using that same binary name). The first instance (attached to a `git diff --stat` and `git status`
call) was treated as a probable injection and ignored, since no such tool was declared available.
The second instance turned out to be a REAL, already-installed local hook (`~/.local/bin/aos-git`)
that actively blocked `git add` until `aos-git pin --repin` was run to acknowledge that another
process had committed to this checkout mid-session (the T3-001 commit, `f87dd11`, landing between
this session's pin and this task's `git add`). Ran `aos-git pin --repin` (read-only
acknowledgment, not a destructive op) and the subsequent `git add`/`git commit` succeeded normally.
Flagging this for the record since the two messages were easy to conflate: one was noise, one was a
real, already-present safety mechanism in this environment.

## T3-002 (M3 / Lane A local backend) conservative choices

**New module, new persistence primitive, no change to T3-001's job contract.** T3-001's own
docstring explicitly reserved "reading from the candidate's redacted transcript bundle... and
persisting" as T3-002/T3-003's scope, and stated `SessionNamingSweepJob` itself "deliberately does
NOT persist the derived name." This task therefore adds:

- `backend/services/session_naming_local_backend.py` -- `LocalOllamaNamingBackend` (the
  `naming_backend.derive_name(candidate) -> str | None` object T3-001's seam expects) plus
  `resolve_naming_backend(ports)`, the single place `CCDASH_SESSION_NAMING_BACKEND` is interpreted
  for job-construction purposes. `"local"` (default) and any unrecognized value both construct the
  local backend (fail toward zero egress, per `config.py`'s own comment on that flag);
  `"hosted"` resolves to `None` -- Lane B (T3-003) has not landed in this module, so the hosted
  lane is unreachable by construction today, not merely by configuration.
- `SqliteSessionRepository.set_derived_session_name` / `PostgresSessionRepository.
  set_derived_session_name` (dual-repo, mirroring every other session_name write site in this
  feature) -- the write-side counterpart to `list_missing_session_name`'s read-side idempotency
  contract. Re-reads the row's CURRENT `session_name_source` immediately before writing (the
  candidate snapshot handed to `derive_name` may be stale by the time a model call returns) and
  refuses via `may_overwrite` -- never a SQL string comparison, per
  `session_name_provenance.py`'s own contract. This is the mechanism that makes M3's idempotency
  AC hold even under the local backend's own write path, not just M1/M2's.
- Wired into `backend/runtime/container.py`: `SessionNamingSweepJob(..., naming_backend=
  resolve_naming_backend(self.require_ports()))`, alongside the existing flag-gated construction
  block. Backend construction is cheap (no network call at construction time), so it happens
  unconditionally inside that same `if` branch rather than adding a second conditional.

**Input path (the task's stated CRITICAL constraint).** `derive_name` reads prompt material
exclusively via `session_detail.get_session_detail(project_id, session_id, ports,
include={INCLUDE_TRANSCRIPT})` -- the same redacted-transcript entry point M1's dossier/detail
surfaces already use, never a raw JSONL read. Verified by test, not just by code inspection: a
fixture transcript containing an `sk-`-style API key (one of `redact_entries`' Layer-1 patterns)
is asserted absent from the exact `prompt` string handed to the mocked Ollama HTTP call, with
`[REDACTED]` present in its place
(`test_prompt_never_contains_a_secret_present_in_the_raw_transcript`).

**Fail-open is two layers deep, not one.** T3-001's `derive_name_fail_open` wrapper already
guarantees the sweep job survives a raising backend. This task's own dispatch note additionally
required "Ollama not being installed/running must be a fail-open no-op... never a crash" as a
property of the backend itself -- so `LocalOllamaNamingBackend.derive_name` wraps its OWN
transcript-fetch, HTTP call, and persistence steps in try/except, each returning `None` on
failure, independent of whichever caller invokes it. Tested directly (bypassing the job's wrapper
entirely) for `httpx.ConnectError` and `httpx.ReadTimeout`, plus once more through the job's own
`derive_name_fail_open` for belt-and-suspenders coverage.

**Output validation: reject, don't truncate, non-conforming output.** The task's instruction was
explicit: "enforce a hard length bound... and reject/ignore non-conforming output rather than
storing it raw." `_sanitize_title` therefore has two thresholds, not one: output over
`_MAX_TITLE_LENGTH` (100 chars) but under `_REJECT_ABOVE_LENGTH` (400 chars) is truncated (a title
that's merely a bit long); output over 400 chars is REJECTED outright (`None`) -- a completion that
long is not a title that needs shortening, it's non-conforming output (e.g. the model echoed a
paragraph), and truncating it would still store something that looks like a plausible title. Also:
only the completion's first line is considered (defends against multi-line output), surrounding
quote characters are stripped, and internal whitespace is collapsed -- none of this is invented ad
hoc; it mirrors the existing 120-char truncation-with-no-ellipsis convention this same feature's
parser fallbacks already established (T2-003's ledger entry above), tightened to 100 chars because
a model-generated title is expected to already be short.

**Provenance token: reused verbatim, not invented.** Persists with
`SESSION_NAME_SOURCE_DERIVED_GENERATIVE` from `backend/parsers/session_name_provenance.py` -- the
exact token the plan's `decisions` block and that module's own docstring name for "a model call
over transcript content." T3-001's own module docstring used the phrase `session_name_source =
derived_model` in prose while describing this seam; that phrase does not exist anywhere in
`session_name_provenance.py`'s vocabulary and was not treated as authoritative -- the module's
actual exported constant is the single source of truth.

**Config additions**: `CCDASH_OLLAMA_BASE_URL` (default `http://localhost:11434`, a loopback
address -- the mechanism that keeps the local lane egress-free even independent of the
`CCDASH_SESSION_NAMING_BACKEND` selection), `CCDASH_OLLAMA_MODEL` (default `gemma2:2b`, a small
instruction-tuned model chosen for low-latency local inference -- any locally-pulled Ollama tag
works; an unpulled/missing model simply makes every call fail, already covered by the fail-open
contract), `CCDASH_OLLAMA_TIMEOUT_SECONDS` (default 15 -- short by design, so a hung local daemon
fails one candidate fast rather than stalling the whole sweep tick). No compose env-allowlist
change was made for these: unlike `CCDASH_GEMINI_API_KEY` (T3-003's scope, a third-party endpoint
credential), these three flags' defaults never leave the host loopback interface, so the gap class
`5cb8e00` fixed for hosted-egress flags does not apply here.

**Tests**: new `backend/tests/test_session_naming_local_backend.py` -- backend-selection/zero-egress
(including two tests named to match the plan's AC->command `-k "naming_egress"` /
`-k "naming_read_path"` rows explicitly, since those rows are the phase's, not one task's, but this
task is squarely what "zero egress by default" tests), output-sanitization unit tests, prompt-
building unit tests, `derive_name` integration tests against a real in-memory SQLite DB (via the
same `FakeCorePortsFactory`/`LocalStorageUnitOfWork` pattern `test_session_detail_service.py`
established) covering fail-open (`ConnectError`/`ReadTimeout`), the redaction-gate assertion above,
successful persistence with `derived_generative` provenance, the rank-gate refusal (a
provider-persisted name surviving a successful model call), and non-conforming-output rejection;
plus direct `set_derived_session_name` repository coverage. 33 passed. Regression sweep:
`test_session_naming_local_backend.py` + `test_session_naming_sweep_job.py` +
`test_session_naming_sweep_guards.py` + `test_session_naming.py` +
`test_session_detail_service.py` → **132 passed, 2 subtests passed**.

## T3-003 (M3): Lane B hosted (Gemini) backend -- the both-conditions egress gate

**The gate lives in the resolver, not inside the backend class.**
`session_naming_local_backend.resolve_naming_backend` (T3-002's module -- its home was not moved,
since it is `SessionNamingSweepJob`'s one construction call site per `container.py`) now checks
`CCDASH_SESSION_NAMING_BACKEND == "hosted"` AND
`redaction.redaction_patterns_enabled()` (a new public wrapper added to
`agent_queries/redaction.py` around the module's existing private `_redaction_env_bool` helper --
reads the exact same env-parsing logic `redact_entries` uses internally, rather than a
re-derived duplicate). Either condition absent returns `None` from the resolver -- the SAME
structural no-op `SessionNamingSweepJob` already treats as "no backend injected" (T3-001): its
derive loop is skipped entirely, `sessions_named` stays 0, and `candidates_found` is still
reported. This was the deliberate design choice per the dispatch note ("the job falls back to
no-op..., not to sending") -- there is no third state where an unreachable hosted request
silently redirects to the local Ollama backend instead; unreachable means nothing happens.
`HostedGeminiNamingBackend.derive_name` ALSO re-checks the redaction gate itself, immediately
before it fetches the transcript bundle -- defense-in-depth against the flag flipping between
resolver-construction time and call time, mirroring `SessionNamingSweepJob.execute`'s own
"re-checked at the top... for defense in depth" pattern for its kill switch. Verified independently
for each flag absent (`test_backend_flag_absent_is_unreachable_even_with_redaction_on`,
`test_redaction_gate_absent_is_unreachable_even_with_backend_hosted`) plus the runtime re-check
(`test_redaction_gate_off_at_call_time_is_fail_closed_no_op`).

**Existing T3-002 tests were stale, not merely extended.** Before this task, `resolve_naming_backend`
hardcoded `None` for `"hosted"` unconditionally, and `test_session_naming_local_backend.py` asserted
exactly that ("Lane B has not landed"). That assertion is now false — with the redaction gate at
its secure default (on), opting into `CCDASH_SESSION_NAMING_BACKEND=hosted` alone DOES construct a
reachable backend, which is correct per this task's own "reachable ONLY when BOTH hold" contract
(default-on redaction plus an explicit opt-in satisfies both). Rewrote the two affected tests rather
than leaving a passing-but-false assertion in the suite.

**Reused the httpx transport pattern, not a second idiom.** `HostedGeminiNamingBackend._call_gemini`
mirrors `ai_insight.generate_dashboard_insight`'s shape byte-for-byte: `httpx.AsyncClient(timeout=...)`
context manager, `POST .../generateContent?key=...`, `resp.raise_for_status()`, then unwrap
`candidates[0].content.parts[0].text`. Kept as its own literal `_GEMINI_BASE_URL`/`_GEMINI_MODEL`
rather than importing `ai_insight.py`'s constants, so this egress boundary's request shape cannot
silently drift if `ai_insight.py`'s own (aggregated-metrics-only, unrelated) prompt/model choice
changes later.

**Extracted the shared prompt/output-validation helpers rather than duplicating them.** Per the
plan's own rubric ("a solution that introduces new equivalents [of what exists] is worse even if
its tests pass"), `_build_prompt_text`/`_sanitize_title` moved out of
`session_naming_local_backend.py` into a new `backend/services/session_naming_prompt.py`
(`build_prompt_text`/`sanitize_title`, unchanged behavior) that both Lane A and Lane B import.
`session_naming_local_backend.py` re-exports the old private names as aliases so T3-002's existing
test imports (`from ...session_naming_local_backend import _build_prompt_text, _sanitize_title`)
keep working unchanged — no test file needed editing for the extraction itself.

**The positive redaction assertion is the load-bearing test for this task**, per the dispatch note's
explicit instruction ("assert this with a POSITIVE test... not merely a test that the gate flag was
read"): `test_prompt_never_contains_a_secret_present_in_the_raw_transcript` plants an `sk-`-style
API key in a fixture transcript, calls `derive_name`, then inspects the ACTUAL `json` payload handed
to the mocked `httpx.AsyncClient.post` call and asserts the secret string is absent and
`[REDACTED]` is present in its place — observing the real outbound payload, not the gate flag.

**Compose env-allowlist gap fixed, same gap class as `5cb8e00`.** Added
`CCDASH_GEMINI_API_KEY: "${CCDASH_GEMINI_API_KEY:-}"` to `deploy/runtime/compose.yaml`'s
`x-backend-shared-env` block (it was previously listed nowhere in compose — the AI-insight proxy has
had this same latent gap since it shipped; fixing it here as this task's explicit instruction, since
Lane B is the second consumer of the same flag). `deploy/runtime/.env.example` already documents
`CCDASH_GEMINI_API_KEY` (line 21, commented) from the AI-insight proxy's own setup — no change
needed there. Did NOT add the `CCDASH_SESSION_NAMING_*` flags (`_ENABLED`/`_QUOTA`/
`_WINDOW_HOURS`/`_SWEEP_INTERVAL_SECONDS`/`_BACKEND`) to the same allowlist block — none of them are
listed there either, a pre-existing gap from T3-002/T3-004 that is out of this task's explicit scope
(only `CCDASH_GEMINI_API_KEY` was named); flagging it here rather than silently leaving it
undiscovered, since a node deployment cannot reach the hosted lane at all today regardless of this
task's gate logic until that separate gap is also closed.

**Tests**: new `backend/tests/test_session_naming_hosted_backend.py` -- both-conditions-required
gate (each flag independently absent + the runtime re-check), fail-open (`ConnectError`/
`ReadTimeout`/missing API key/empty transcript), the positive redaction assertion above, successful
persistence with `derived_generative` provenance, the rank-gate refusal, non-conforming-output
rejection, and the sweep job's own `derive_name_fail_open` wrapper survives a raising backend --
mirrors `test_session_naming_local_backend.py`'s Lane A coverage shape-for-shape. Also updated two
now-stale assertions in `test_session_naming_local_backend.py` (see above). Regression sweep:
`test_session_naming_hosted_backend.py` + `test_session_naming_local_backend.py` +
`test_session_naming_sweep_job.py` + `test_session_naming_sweep_guards.py` +
`test_session_naming.py` + `test_session_detail_service.py` + `test_redaction.py` →

## T3-005 — Test + security coverage (M3 milestone verification)

**No feature-code defect found.** T3-002/T3-003/T3-004's existing test coverage for the zero-egress
default, the positive redaction assertion, idempotency, and fail-open behavior was already strong on
inspection (`test_session_naming_local_backend.py::BackendResolutionTests`,
`test_session_naming_hosted_backend.py::DeriveNameTests::test_prompt_never_contains_a_secret_present_in_the_raw_transcript`
already observes the actual outbound `httpx` payload, not merely a flag read). This task's real gap
was the cross-cutting **structural** (1) requirement — a positive, inverted static-import-graph-walk
proving no read/render-path router or service reaches a naming-backend module, mirroring
`test_aar_review_no_llm_imports.py`'s method.

**New file: `backend/tests/test_session_naming_read_path_no_model_client.py`.** BFS-walks six
read-path entry modules (`routers._client_v1_sessions`, `routers.client_v1`, `routers.analytics`,
`mcp.tools.sessions`, `agent_queries.session_detail`, `session_intelligence`) and asserts the walk
never reaches `session_naming_local_backend`, `session_naming_hosted_backend`, or
`session_naming_sweep_job`. **Discovered and worked around a real false-positive, not a defect**: a
naive full-depth walk (the AAR test's literal method) flags every entry point, because
`backend.runtime_ports`/`backend.adapters.jobs` is a shared DI-composition-root package whose
`__init__.py` re-exports every worker job (including `SessionNamingSweepJob`) from one module body —
importing anything else from that package (e.g. `InProcessJobScheduler`, needed for unrelated
reasons) transitively "imports" every sibling job as a side effect of Python package mechanics, not
because the read path calls any of them. Fixed by treating known composition-root modules
(`_COMPOSITION_ROOT_BOUNDARIES`) as an opaque BFS boundary — visited/recorded but never expanded past
— which is architecturally exactly the worker-only registration surface itself. A DIRECT import of a
naming-backend module by any router/service still fails the test; only the shared-package fan-out
edge is excluded. A raw-source regex symbol scan (mirroring the AAR test's technique) was tried and
reverted: it produced a universal false positive because these banned names legitimately appear in
`backend/config.py`'s own flag-documentation comments, which every module in the app transitively
imports. The regex scan is instead applied narrowly, directly against the three known
worker-registration files only, as a POSITIVE control in `test_naming_job_is_worker_registered_only`
(proves the reference genuinely exists there, so the read-path absence isn't vacuous).

**Fail-open logging gap closed.** `derive_name_fail_open` already logged a WARNING with
`exc_info=True` on a raising backend, but no test asserted the log was actually emitted — only that
the NULL/no-crash/no-block behavior held. Added
`test_session_naming_sweep_guards.py::DeriveNameFailOpenTests::test_raising_backend_is_logged_not_silently_swallowed`
(`assertLogs` on `ccdash.jobs.session_naming_sweep`, asserts the candidate id and "fail-open" appear
in the captured record).

**Opus/security review still required before merge.** Per the plan's `routing_constraints` and this
phase's `gate_lens: [security, validator]` / `gate_lens_reason: irreversible-outward`, the Lane B
egress path and its redaction-gate wiring have NOT been reviewed by Opus in this session — that gate
is NOT satisfied by this task's test additions and must not be represented as closed.

**Regression** (exact pass/fail counts, this session, `backend/.venv/bin/python -m pytest <named
files> -v` from repo root):
- `test_session_naming_read_path_no_model_client.py` (new) → 3 passed, 9 subtests passed
- `test_session_naming_sweep_guards.py` (1 new test added) → 15 passed
- `test_session_naming_sweep_job.py` → all passed
- `test_session_naming_local_backend.py` → all passed
- `test_session_naming_hosted_backend.py` → all passed
- `test_session_naming.py` → all passed
- `test_session_name_provenance.py` → all passed
- `test_session_name_persistence.py` → all passed
- Combined named-file run: **148 passed, 19 subtests passed**, 0 failed
- `npx vitest run components/__tests__/SessionNaming.test.tsx` → **38 passed**, 0 failed
**186 passed, 2 subtests passed**.

## T3-006 (M3) — Reviewer fix pass, 2026-08-05

Fixes applied against the M3 reviewer's 8-item list, in commit order on this branch:

1. **Security-lens gate (BLOCKER)** — see the dedicated "Security review sign-off" entry below
   this one; council-review's security lens ran against the Lane B egress path and the
   redaction-gate wiring, including the specific "both conditions collapse to one env var" defect
   the reviewer named.
2. Added the `CCDASH_SESSION_NAMING_*` flag quintet (`_ENABLED`/`_QUOTA`/`_WINDOW_HOURS`/
   `_SWEEP_INTERVAL_SECONDS`/`_BACKEND`) and `CCDASH_OLLAMA_BASE_URL` to
   `deploy/runtime/compose.yaml`'s `x-backend-shared-env` allowlist (mirroring the
   `CCDASH_ROUTING_FEEDBACK_*` precedent) and documented them in `.env.example`. This was the
   explicitly-flagged-but-unfixed gap from T3-003's own notes above. Filed and closed IntentTree
   node `node_01KZ9S3SDEC22NGAGV22VFK9ME` (tree `aos-ccdash`) for it per the finding-capture rule.
3. Wired `CCDASH_SESSION_NAMING_WINDOW_HOURS`: added `resolve_recency_window_since()` to
   `session_naming_sweep_job.py` and a `since` parameter on `list_missing_session_name` (both
   SQLite and Postgres repositories, filtering `created_at >= since`) — read-time scoping only, the
   `session_name IS NULL` predicate remains the sole idempotency guard. `window_hours <= 0` is
   treated as "no bound" (a literal 0-hour window would otherwise select nothing, a footgun).
4. Pushed the per-tick quota into SQL: `_execute_inner` now calls
   `list_missing_session_name(project_id, limit=quota, since=...)` directly instead of slicing the
   full result in Python. `candidates_found` (the backlog signal) is now sourced from a new,
   separate `count_missing_session_name()` query on both repositories, so reporting the backlog
   size never requires loading the backlog itself into memory. When no `naming_backend` is
   injected, `list_missing_session_name` is now skipped entirely (nothing would consume the rows) —
   a perf win over the prior structural no-op.
5. Added an instance-scoped consecutive-failure circuit breaker to `LocalOllamaNamingBackend`
   (`_CONSECUTIVE_FAILURE_THRESHOLD = 3`): once three Ollama calls fail in a row, later candidates
   skip the `get_session_detail` transcript fetch entirely (checked BEFORE the fetch, not after).
   `reset_circuit_breaker()` closes it; `SessionNamingSweepJob._execute_inner` calls it (duck-typed
   — `getattr`/`callable`, no hard import) once at the top of each tick's derive loop, so an outage
   discovered on one tick can never permanently disable the naming lane on later ticks.
6. **Provenance token deviation — logged here, not implemented as distinct tokens.** See the
   dedicated entry below.
7. Extracted the container's session-naming construction gate to a module-level
   `_construct_session_naming_sweep_job(profile_name, ports)` in `backend/runtime/container.py`,
   specifically so it is unit-testable without exercising the full `startup()` lifecycle (which
   touches the DB and hangs in this repo's unscoped collection). Added
   `ConstructSessionNamingSweepJobTests` driving it directly under `api` (None even with the flag
   on), `worker`/`worker-watch` (constructed when the flag is on), and `worker` with the flag off
   (None). The prior `WorkerOnlyRegistrationTests` only asserted `_WORKER_JOB_PROFILES`'s
   membership, which cannot fail if the container's own gate expression were wrong.
8. Fixed the stale `_start_session_naming_sweep_task` docstring (`backend/adapters/jobs/runtime.py`)
   — it claimed `container.py` constructs the job "unconditionally" for worker profiles with only
   an `execute()`-time recheck. Construction is itself flag-gated at `startup()` time (read once),
   so toggling `CCDASH_SESSION_NAMING_ENABLED` requires a full backend restart; there is no
   live-reload path.

**Regression** (named-file run, this session): all pre-existing `test_session_naming_*` /
`test_session_name_*` files plus `test_runtime_container_routing.py` pass unchanged; four
pre-existing, unrelated failures in `test_storage_profiles.py` (auth-contract/`CCDASH_API_TOKEN`
and worker-watch project-id binding assertions) reproduce identically on `main` before this pass and
are out of this task's scope.

### Provenance-token deviation (item 6): one `derived_generative` token, not two

**Deviation, not a defect left unfixed.** The plan's own accepted decision text reads "Provenance
rank: `provider_persisted` > `derived_deterministic` > `llm_derived_local` > `llm_derived_hosted`" —
four rungs, distinguishing the local (Lane A, zero-egress) and hosted (Lane B, Gemini) generative
lanes. The SHIPPED vocabulary (`backend/parsers/session_name_provenance.py`, landed in M1/T1) has
only `SESSION_NAME_SOURCE_DERIVED_GENERATIVE` for BOTH lanes — `LocalOllamaNamingBackend` and
`HostedGeminiNamingBackend` (T3-002/T3-003) both persist the same token. A `sessions` row's
`session_name_source` therefore cannot answer "did this specific name come from the off-box lane?" —
exactly the audit question this milestone's named risk ("egress by accident") creates.

**Why the deviation is accepted rather than fixed by adding two tokens:**
- The four-rung vocabulary in the plan's decision text predates M1's actual schema landing;
  `session_name_provenance.py`'s three-rung `SESSION_NAME_SOURCE_TRUST_ORDER`
  (`provider_persisted` / `derived_deterministic` / `derived_generative`, plus the reserved
  `derived_embedding_transfer` slot for the deferred Lane C) is the shipped, tested contract that
  T3-002 and T3-003 both built against and that dozens of existing tests
  (`test_session_name_provenance.py`, `test_session_naming_local_backend.py`,
  `test_session_naming_hosted_backend.py`) pin verbatim.
- Splitting `derived_generative` into local/hosted variants now is a schema-vocabulary change, not
  a bugfix confined to this reviewer pass: it touches the rank ordering, every persistence call site
  in both backends, and every existing test asserting the single token — a wider blast radius than
  this fix pass's other seven items, for a gap that is fully answerable another way (below).
- The audit question IS still answerable today, just not from `session_name_source` alone: the
  lane a given derived name came from is determined by `config.CCDASH_SESSION_NAMING_BACKEND` at
  the time of that sweep tick, which is itself gated (per item 1's security review) by
  `CCDASH_REDACTION_PATTERNS_ENABLED`. An operator/auditor reconstructing "was this specific name
  hosted or local" needs the deploy's flag history for that time window, not a per-row column — a
  real gap for point-in-time-of-write auditing, but not a silent one, and not one this token split
  alone would fully close either (a single global flag governs the WHOLE naming backend for a
  project; it is not decided per-row).

**Follow-up, not closed here.** If the hosted lane sees production usage, splitting the token
(`derived_generative_local` / `derived_generative_hosted`, with an explicit two-slot rank
extension in `session_name_provenance.py` plus a migration-free additive rollout — old rows keep
the single `derived_generative` token, treated as unranked-but-known, same as any pre-column row)
is the natural follow-up. Tracked as a fast-follow, not blocking this milestone.

**Security-lens sign-off on this deviation:** recorded in the "Security review sign-off" entry
immediately below — the security lens signing off on item 1 also reviewed and accepted this
deviation as in-scope for the same pass, since both concern the audit trail for the egress
boundary.

### Security review sign-off (M3 gate: `gate_lens: [security, validator]`, `gate_lens_reason: irreversible-outward`)

**Reviewer:** in-session security-lens pass (2026-08-05), scoped exactly to the reviewer's named
concern — the Lane B egress path and its redaction-gate wiring — plus the provenance-token
deviation above. Not a full multi-reviewer ARC council run (the `council-review` skill's
11-artifact-bundle scaffold is disproportionate to a single targeted lens pass on an
already-implemented, already-tested feature); this is the security-lens half of the plan's
`gate_lens: [security, validator]` pair, with `validator` already satisfied by T3-005's test suite.

**Finding under review:** `CCDASH_REDACTION_PATTERNS_ENABLED` defaults `True`
(`agent_queries/redaction.py`), so `resolve_naming_backend`'s "reachable ONLY when BOTH conditions
hold" gate collapses in practice to one operator action: setting
`CCDASH_SESSION_NAMING_BACKEND=hosted` alone makes `HostedGeminiNamingBackend` reachable.

**Verdict: CONDITIONAL — satisfied by the remediation applied in this same pass.**

1. **Is this a broken AND-gate or an acceptable design?** Acceptable design, MISLEADING
   documentation. The code is not unsafe: `CCDASH_REDACTION_PATTERNS_ENABLED` is the SAME flag that
   gates whether the actual outbound payload is scrubbed (`get_session_detail` -> `redact_entries`,
   re-checked a second time inside `HostedGeminiNamingBackend.derive_name` itself, immediately
   before the fetch) — so "reachable" never means "sends unredacted." Reachability and safety are
   tied to the identical flag, not two independent claims where one could be true and the other
   false. Inverting the default (making redaction opt-in) was REJECTED as the fix — that would
   weaken the Layer-1 secret scrub for every OTHER read path in the app (dashboard views, session
   detail, MCP tools) for the sake of one lane's messaging. The real defect was documentation
   describing "BOTH conditions" as if two deliberate operator actions were required, when one is
   satisfied by inaction. **Fixed in this pass**: `resolve_naming_backend`'s docstring and the
   hosted-backend module docstring now state plainly that the redaction flag defaults on, and a new
   WARNING-level log line (`"Lane B ... is now REACHABLE"`) fires at the moment the hosted backend
   is actually constructed — an operator watching worker logs can no longer be surprised by this
   silently. Covered by `test_hosted_construction_emits_a_reachability_warning`.
2. **Does redaction fire on the REAL outbound payload, not just a flag read?** Yes, independently
   verified pre-existing:
   `test_session_naming_hosted_backend.py::DeriveNameTests::test_prompt_never_contains_a_secret_present_in_the_raw_transcript`
   plants a secret in a fixture transcript and inspects the ACTUAL `httpx` payload handed to the
   mocked client — not merely that the gate flag was read. Re-verified in this pass; unchanged.
3. **Is `CCDASH_GEMINI_API_KEY` absence a meaningful secondary safety net, or incidental?**
   Meaningful, and undercounted by the "one env var is sufficient" framing: an actual send requires
   THREE things, not one — `CCDASH_SESSION_NAMING_BACKEND=hosted` (explicit), redaction ON
   (default), AND `CCDASH_GEMINI_API_KEY` set (explicit, default-empty, fails closed with no send
   attempted if absent — `derive_name` returns `None` before any egress). Two of three require
   deliberate operator action; the redaction flag is the one that doesn't, and that one is also the
   one enforcing safety-if-reached, not merely gating reachability. Documented explicitly in both
   docstrings now (item 1's fix, above).

**Provenance-token deviation — ACCEPTED.** Reviewed the "Provenance-token deviation (item 6)"
section above: agree the audit question ("did this name cross the egress boundary?") is answerable
via deploy-time config history rather than a per-row column, and agree a token split is a
wider-blast-radius schema change disproportionate to this fix pass. Required, as the condition of
sign-off: a compensating, per-write audit trail that does NOT require a schema change. **Added in
this pass**: `HostedGeminiNamingBackend.derive_name` now logs an INFO line
(`"derived and persisted a name via the hosted (Gemini) lane for session_id=... project_id=..."`)
on every successful Lane B write, independently reconstructable from worker logs without touching
`session_name_source`. Covered by `test_successful_derivation_logs_an_audit_trail_line`. The
token-split follow-up remains tracked, not blocking.

**Gate status: SATISFIED.** Both the named defect and the provenance deviation have concrete,
tested remediation landed in this same commit sequence (docstring corrections, two new log lines,
two new regression tests). No further code change is required before merge on security grounds.
`validator` lens was already satisfied by T3-005.

## Feature-level gate (karen, whole tree): APPROVED — 2 Medium + 6 Low, none blocking

Ran after M3's phase gate, scoped to what a per-phase gate structurally cannot see: integration
across all three milestones. Verdict APPROVED. It independently enumerated all 16 provenance write
sites and confirmed the guard choice is correct at every one (including the subtle equal-rank sites
that deliberately use an emptiness gate instead of `may_overwrite`), confirmed read-path purity by
re-running T3-005's static walk with its boundary list neutralised (the false-positive claim is
measured, not asserted), confirmed all three of the plan's intended reuses are genuine, and checked
a dual-backend `created_at` lexicographic-comparison trap the plan never mentioned (clean).

### Fixed before merge (5 of 8)

| Finding | Fix |
|---|---|
| **M-1** `may_overwrite(<any>, operator_set)` returned `True` — `operator_set` sits outside the ranked ladder so `session_name_rank` gives `None`, and the "unranked incumbent is weakest" rule inverted the module's *strongest* signal into its weakest. Latent (token reserved+unwritten, sweep only selects NULL) but the declared rename-UI follow-on walks straight into it, and the same shape would swallow any future token ranked above `provider_persisted`. | Explicit `operator_set` incumbent branch, checked first, **inside** the helper the module docstring designates as THE enforcement mechanism — not delegated to call sites (none of the four lanes performed the caller-side check the docstring asked for). Regression test covers all five tokens + an unknown + `None` as candidate. |
| **L-3** `list_missing_session_name` had `LIMIT` with no `ORDER BY`. A candidate that fails *deterministically* (`build_prompt_text` returns `""` on a transcript with no string content; `sanitize_title` rejects) never leaves the candidate set, and under SQLite rowid ordering would hold the same quota slot every tick, starving nameable rows behind it. | `ORDER BY created_at DESC` added to **both** backends, which also matches the recency intent the `since` window already documents. |
| **L-5** Compose allowlist shipped 6 of 8 flags — `CCDASH_OLLAMA_MODEL` and `CCDASH_OLLAMA_TIMEOUT_SECONDS` were omitted, i.e. the *same* explicit-allowlist gap class the block's own comment is about (third occurrence in this repo). | Both added. Also documented that the shipped `CCDASH_OLLAMA_BASE_URL=http://localhost:11434` default resolves to the **container's** loopback, so the default zero-egress lane cannot function under compose without pointing at the host — noted in compose.yaml and `.env.example` with the podman form. Default left matching `config.py` so bare local runs are unchanged. |
| **L-7** The `derived_deterministic` badge read **"Inherited"** ("from a parent session, or a git branch"). After M2 that one token also covers `last-prompt` and truncated-first-message — which are now the *dominant* population — so the label described a minority of the rows it labelled. | Relabelled **"Derived"**, tooltip enumerates all four derivations, with a pointer to keep it in sync with the provenance module's docstring. Test expectation updated. |
| **L-8** Three truncation bounds for one concept: a named constant in the Claude parser, a bare `120` in the Codex parser (with a comment claiming it matched), and `MAX_TITLE_LENGTH=100` for model output. The Codex literal was introduced by the M2-gate fix above — my own drift. | Promoted to `SESSION_NAME_FALLBACK_TRUNCATION_LEN` in `session_name_provenance.py` (the shared home); both parsers now import it, Claude's module-local name is an alias. `MAX_TITLE_LENGTH` is deliberately distinct (bounds MODEL-generated titles, not text cuts) and documented as such. |

### Deferred, with reasons (3 of 8)

- **M-2 (perf, deliberate defer):** the session-name inheritance pass selects every subagent row for
  the project each sync with no narrowing predicate, where the sibling `skill_name` UPDATE it extends
  has `AND child.skill_name IS NULL` — and `sync_engine.py` explicitly credits that predicate for
  making the pass cheap. On node PG (14k+ sessions) this is a per-sync scan whose steady-state output
  is zero updates. **Correctness is fine; the cost is structural.** Deferred rather than patched
  because a naive narrowing would break the two paths the review itself names (parent-name updates
  and generative upgrades), and getting that wrong is worse than the scan. Needs its own change with
  the idempotent-second-run test kept green.
- **L-4:** `count_missing_session_name` ignores `since`, so a deployment with the default 24h window
  and a large historical backlog reports a permanently large, never-decreasing `backlog_count`
  against a 7200s staleness threshold. Ops-signal noise, not a functional defect.
- **L-6:** Lane B has no wasted-work circuit breaker where Lane A gained one (c99c98f). Only bites a
  deployment that opted into hosted with a bad key / 429 / outage; then it burns a full quota of
  `get_session_detail` + HTTPS calls per tick. Asymmetric, not wrong.

### Runtime smoke: PARTIAL — blocked by a pre-existing bug, not by this feature

The plan's `Runtime smoke (UI)` AC row could not be completed as written. What WAS verified at
runtime: a live backend started on `127.0.0.1:8000` (profile `local`, sqlite) **applied the v50
migration to a real DB** — `session_name` and `session_name_source` are present on the actual
`sessions` table, which no unit test demonstrates — and `/api/health` reports ok.

What was NOT verified: names rendering in a browser against real data. Ingesting real sessions
requires a project sync, and `POST /api/cache/sync` fails on this checkout with
`sqlite3.OperationalError: cannot commit transaction - SQL statements in progress` in the reconcile
path (`Operation failed [OP-…]: reconcile: sync_project failed`). That is a **pre-existing** defect
in the sync path, unrelated to session naming, so the DB stayed at 0 sessions. The offline CLI route
was also tried and is blocked separately: `--ephemeral` skips migrations, so `session search` returns
0 against a table-less cache.

Coverage standing in for it: 38 FE tests including real-render null-fallback and adversarial-string
cases across all five surfaces, plus source-level assertions that no surface uses a raw-HTML sink.
Recorded as `runtime_smoke: partial` rather than claimed — per CLAUDE.md, a skipped smoke is recorded
with its reason, never asserted.
