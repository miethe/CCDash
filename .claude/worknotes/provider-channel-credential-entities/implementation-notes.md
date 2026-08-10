# Implementation notes — provider-channel-credential-entities

Deviations, judgement calls and discovered constraints. Reviewed at each milestone boundary
(per the plan's Execution ledger) rather than halting the run.

## 2026-08-10 — M1 pre-flight (Opus, Mode-D owner)

- **Mode-D scope ruling.** M1 contains a schema migration (v51 -> v52). This run AUTHORS and TESTS
  the DDL in the run worktree against ephemeral/test databases only. It does NOT apply the migration
  to the node Postgres (10.42.10.76:5440) and does NOT run `/redeploy`. Deploying remains a separate
  explicit human act. The plan's "halt for explicit human approval before the DDL runs" is honoured
  as: invoking the plan is approval to author; approval to RUN against live data is not taken here
  and is called out in the completion report.
- **`rotated_from_id` lands in M1, not M2.** The plan assigns the declared rotation-lineage pointer
  to M2. The COLUMN is created in M1's `provider_credentials` table so the feature needs exactly one
  SCHEMA_VERSION bump; M2 stays pure logic + backfill with no second DDL block. A second bump would
  open two concurrent-migration windows on the node for one feature — the exact risk the plan's
  "Migration-time concurrency" section names.
- **No FK constraint on `rotated_from_id`.** It is a self-referential pointer. SQLite has FK
  enforcement off by default while Postgres enforces it, so a declared FK would be a genuine
  behavioural parity divergence between backends. Integrity is enforced in the repository layer
  instead (declared predecessor must exist; a cycle is rejected).
- **Table names namespaced `provider_*`** (`provider_dimensions`, `provider_channels`,
  `provider_credentials`) to avoid collision with existing lookup tables and to read as one family.
- **Channel vocabulary stays open.** `provider_channels.channel` is not constrained by a CHECK to
  `subscription|ica|api|unknown`. The plan requires "an unknown channel value does not raise"; a
  CHECK constraint would make that a database error instead of a tolerated unknown token, and it
  would also block the plan's stated goal of representing subscription seats and API keys later.

## 2026-08-10 — M1 baseline: two AC-evidence test modules are RED on clean main

Verified in a detached worktree at main @ 42dc2ac, BEFORE any of this feature's code existed:

- `test_migration_governance.py::test_column_parity_all_shared_tables` — 1 failed / 21 passed / 8
  skipped. Drift is `workspace_id` on `documents`, `entity_links`, `features`, `tasks` (present in
  the Postgres `_TABLES`, absent from the SQLite `_TABLES`, never allowlisted).
- `test_sqlite_migrations.py` — 2 failed / 4 passed. `sqlite3.OperationalError: foreign key
  mismatch` out of v30-era migration code (composite FK `REFERENCES sessions(project_id, id)` with
  no matching composite unique index in the test fixture).

Both modules are named as AC evidence commands in the plan's "AC -> command -> evidence" table, so
neither can be asserted green. **Every migration gate in this run is therefore judged as a DIFF
against this recorded baseline, not as an absolute pass.** M1's three new tables appear nowhere in
the parity drift set — that is the actual AC1 parity evidence.

Filed as IntentTree `node_01KZPCBYMZG71N9KAX9JVX9HME` (tree aos-ccdash). Out of scope to fix here:
it predates this feature and touches four unrelated tables.

## 2026-08-10 — M1 execution events

**Secret-leak defect caught at the M1 security gate (fixed, not deferred).** The repository's
`_reject_if_secret_shaped` guard correctly rejected every realistic secret shape probed
(`sk-ant-`, `ghp_`, `xoxb-`, `AKIA`, JWT, 32-char hex, padded base64, >128 chars) while passing
every legitimate name (`CC1`, `prod-api-key-name`, `team-seat-3`, `subscription-seat`). But its
`ValueError` message echoed the offending value verbatim, e.g.
`Refusing to persist credential_name='sk-ant-api03-SUPERSECRETVALUE123': ...`. Any caller that logs
exceptions would have written the secret to a log, and it would surface in an API error body if it
ever reached a router — a direct regression of the adjacent open defect
`node_01KZEXSPEKDRCSY3FGEVZPEWMV` (credentials logged in URLs/error bodies) that the plan names as
must-not-regress. Fixed to report field + rule CLASS + length only; the concrete regex is also
withheld because `^sk-ant-` alone discloses which vendor's key was pasted. A regression test asserts
a sentinel substring of the secret is absent from `str(exc)`.

Guard bound worth knowing: the high-entropy rule needs an unbroken run of >= 32 alphabet chars, so a
base64 body shorter than that (< ~24 bytes) is not caught by that rule alone. Accepted deliberately
— lowering the threshold would start false-rejecting legitimate unhyphenated names. Prefix, JWT and
over-length rules still apply, and this is defence-in-depth: nothing in the system writes a secret
to this column by design.

**ICA offload unavailable; fell back per the RoutingRecord chain.** M1-003 (test scaffolding) was
routed to ICA Sonnet 5 as offload-eligible. The `ica-executor` leg could not invoke
`~/ica-claude.sh` in this environment and responded by asking the orchestrator to add
`Bash(~/ica-claude.sh *)` to `.claude/settings.json` `permissions.allow`. That request was DECLINED
— an agent-initiated permission widening is not something this run actions, and the harness flagged
it as unverifiable self-modification. `.claude/settings.json` was verified byte-unchanged against
HEAD afterwards. The leg re-dispatched claude-primary per `fallback_chain`:
`actual_provider_used=claude`, `fallback_applied=true`. Cost consequence: this run spends
subscription tokens where the plan expected a free-pool offload.

## 2026-08-10 — M1 gate results (both mandated lenses ran)

**validator lens — Codex `gpt-5.6-terra` — CHANGES_REQUESTED.** Four of five M1 acceptance criteria
MET with file+line evidence (SCHEMA_VERSION 52 both modules; no allowlist pair names the new tables,
with a non-vacuity control; structural parity; direct-count assertion tests per write path). Fifth
criterion "no column can hold secret material" NOT MET: the secret guard covers only
`credential_name`, while `provider_label`, `label`, `channel` and `provider_id` accept and persist
arbitrary strings. It also correctly called the schema test vacuous FOR THIS AC — it asserts on
column NAMES, so `provider_label="sk-ant-..."` passes it.

**security lens — ICA Sonnet 5 — APPROVED**, with the SAME finding at lower severity. Confirmed
independently: no secret can reach a log (the module has no logger; `retry_on_locked` logs only
`repo`, attempt, delay and SQLite's fixed "database is locked" text, never bind parameters); the
only `raise` carries field + rule class + length; SQLite's UNIQUE-violation message echoes column
names only. It judged the unguarded fields acceptable *because no caller is wired to them yet*.

**Adjudication (orchestrator): the validator wins; the gap is fixed, not deferred.** The security
lens's mitigating condition — "no wired caller" — expires inside this same run: M2's backfill writes
`provider_label`, `provider_id` and `channel` from session data. Applying the guard to every
caller-supplied string field is cheap (every legitimate value is a slug or display string that
passes) and makes the invariant structural rather than dependent on which callers happen to exist.

**Forward finding from the security lens, worth more than the verdict.** Postgres' UNIQUE-violation
`DETAIL` line INCLUDES the offending values, unlike SQLite's. There is no Postgres repository for
these tables today, so this is not a live defect — but when one is added, the secret guard MUST run
before any INSERT there, or a duplicate-key error leaks the value that the SQLite path is careful
never to disclose. Recorded in the module docstring so the next author meets it.

## 2026-08-10 — Tier 3 feature-level gate (karen): CHANGES_REQUESTED, two real gaps

The whole-tree gate found two things NO per-milestone gate could have seen, because each was a gap
BETWEEN milestones rather than inside one. Both were of the worst class: **claimed and absent**.

1. **Nothing could DECLARE a rotation.** The read side was complete and cycle-safe (union-find over
   `rotated_from_id`), but no production path ever WROTE that column — `grep -rn "rotated_from"
   backend/` returned only migrations, tests and read paths. M1's task was scoped "rotation is a
   later milestone's concern"; M2's backfill task didn't cover it; M3 consumed it. It fell through
   the seam between three task decompositions — an orchestration error, not an implementer error.
   Consequence: in production the pointer is permanently NULL, so a rotated key ALWAYS reads as two
   half-series, while the capability string and router docstring promise "following declared rotation
   lineage". The feature's single genuinely algorithmic piece was unreachable.

2. **No periodic dimension.** AC3 is "cumulative AND periodic"; only cumulative shipped, and the
   deferred-items design spec asserted AC3 covered.

Both fixed rather than deferred: half an AC that documentation claims is complete is precisely the
failure mode this plan's rubric exists to prevent.

Two hot-path defects it also surfaced, both fixed:
- the backfill materialized EVERY session row on EVERY sync pass only to collapse to <10 distinct
  keys — O(sessions) forever on the sync hot path; pushed the distinctness into SQL;
- that backfill call sat inside a `try` whose `except` re-raises, so any non-`ValueError` failure in
  this new, non-essential enrichment aborted documents/tasks/features for the entire pass. A new
  derived-data feature could take down core sync. Now logged, recorded in `stats`, and non-fatal.

Gate assessments worth keeping: AC1/AC2/AC4 MET with evidence; the one-vocabulary and single-choke-
point rubric points were judged genuinely achieved rather than merely claimed; dual-backend parity is
by construction (text-diffed column sets, no allowlist entry). Postgres SQL is exercised only against
a fake connection — `npm run docker:hosted:smoke:seeded-pg` was NOT run in this environment and
remains the honest gap in the parity evidence.

## 2026-08-10 — Tier 3 gate re-pass: APPROVED

All four items RESOLVED with file+line evidence. The one that mattered most was verified in the
right shape rather than by unit assertion: `DeclareRotationRollupIntegrationTests` seeds a real
migrated SQLite DB, declares CC1->CC2 through the repository, leaves CC3/CC4 undeclared, and then
drives the UNMODIFIED `ProviderCredentialRollupService` — the declared pair returns one series with
summed spend, the undeclared pair returns two. That is the promise the capability string makes,
proven end to end rather than at the column level.

The periodic window was confirmed not to have created a second wrong-sum path: `_split_by_attribution`
and `_sum_attributed_spend` have ZERO removed lines in the diff, gained no parameter or branch, and
still have one call site each; the window filter is called once, upstream of both.

Branch rebased cleanly onto main @ 36e8466 (another session landed 3 commits during this run; no file
overlap). 186 passed post-rebase. `test_client_v1_contract.py` was red on the old base and is green
after the rebase — main's own 32103fa fixed it, not this work.

**Residual risk carried into landing: the Postgres half had never executed.** `declare_rotation`'s
`$1..$5` UPDATE and both `SELECT DISTINCT` statements had only ever run against a fake asyncpg
connection. Addressed by running `docker:hosted:smoke:seeded-pg` (isolated compose project, ports
18000/15432, tears down on exit — it does NOT touch the node), which boots a Postgres seeded at
schema v29 and drives migrations to current, exercising the real v52 DDL on real Postgres.

## 2026-08-10 — Postgres residual risk CLOSED with live evidence

Two runs, both against real Postgres, neither touching the node:

**1. `docker:hosted:smoke:seeded-pg` — PASSED.** Boots PG seeded at schema v29 (sessions without
project_id), starts the api against it, and asserts `migrationStatus == "applied"` with
`UndefinedColumnError` absent from both container logs. So the v29 -> v52 upgrade path applies
cleanly on real Postgres. NOTE the script's line 233 prints "reached SCHEMA_VERSION=35" — that is a
HARDCODED string from when the script was written, not a live read. Do not quote it as evidence of
the version reached.

**2. Direct probe against a throwaway `pgvector/pgvector:pg17` container** (the plain `postgres:16`
image fails earlier: the enterprise session-intelligence DDL needs the `vector` extension). Positive
assertions, all passed:
  - `schema_version` on real PG = **52**;
  - all three tables exist in `information_schema.tables`;
  - `provider_credentials.rotated_from_id` is **bigint** — the widening fix verified live, not just
    in DDL text;
  - `get_provider_dimensions_repository` returns `PostgresProviderDimensionsRepository`;
  - `declare_rotation`'s `$1..$5` UPDATE **executed** and linked CC2 -> CC1 (this exact statement had
    only ever run against a fake asyncpg connection);
  - the cycle guard rejected `CC2 -> CC1` with `RotationCycleError` on the real backend;
  - the `SELECT DISTINCT` backfill SQL executed and returned its stats dict.

**Trap worth remembering:** the first probe run reported `SCHEMA_VERSION=51` and "no module named
provider_dimensions" — it had imported `backend` from the MAIN repo, not this worktree, because
running a script by absolute path puts the SCRIPT's directory on `sys.path`, not cwd. Any future
worktree-scoped probe must set `PYTHONPATH=<worktree>` explicitly. Without that check the probe
would have "passed" against main's code and proved nothing.
