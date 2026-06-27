---
type: report
schema_version: 2
doc_type: report
report_category: after-action-review
prd: ccdash-core-remediation
feature_slug: ccdash-core-remediation
wave: 4
title: "Wave 4 AAR — session exposure (P3), external API (P10), Postgres/container convergence (P9)"
status: completed
created: 2026-06-11
updated: 2026-06-11
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
commit_refs: [ca5a557, 9d5b29f]
---

# Wave 4 — After-Action Review

## 1. What was attempted

Execute **Wave 4 only** (phases P3, P10, P9) of the CCDash Core Remediation Tier-3 plan in a worktree
off the epic branch, with phased commits and a squash-merge back to epic. All implementation delegated
(Agent tool overflows on this repo's CLAUDE.md → ICA `--bare` bash delegation), Opus orchestrating.

## 2. What shipped

- **P3** — `session_detail` exposed across MCP + repo-CLI + standalone CLI; MCP/CLI/REST parity with
  byte-budget + cursor pagination. Read-only; no new write paths.
- **P10** — Documented external `/api/v1`: capability endpoint, cross-project surface, additive CORS/LAN
  bind, OPTIONAL bearer auth (none-on-LAN default, single injectable identity dep), checked-in OpenAPI
  (byte-identical to its regen script), envelope contract test, runnable example client + LAN smoke.
- **P9** — Operable-on-Postgres: api+worker+postgres compose stack, durable-queue coalescing, `/readyz`
  fail-loud (api + worker), dual-backend column parity governance.

Landed on epic as `ca5a557` (squash) + `9d5b29f` (bookkeeping). Worktree removed, branch deleted.

## 3. The headline finding — the live smoke gate earned its keep

A **passing unit suite (63+ tests) masked five Postgres/container defects** that only a live boot
surfaced. CCDash had, in effect, **never successfully initialized its Postgres schema** before this wave:

1. functional-index IMMUTABLE violation (`(captured_at::date)` on TEXT is STABLE) — migrations aborted.
2. plain `postgres:15` lacks `pgvector` — enterprise session-intelligence `CREATE EXTENSION` crashed.
3. `@dataclass(slots=True)` `RuntimeJobState` rejected `setattr(_drain_task)` — startup AttributeError.
4. asyncpg `Pool` has no `.transaction()` — durable queue claim path broke (and would silently split the
   `FOR UPDATE SKIP LOCKED` lock across pooled connections even if it hadn't).
5. worker crash-loop: pinned project `smoke-stack` unresolved on a fresh DB (registry is lookup-only).

Each was invisible to the test suite, fatal at runtime, and fixed + re-verified against a live
`pgvector/pgvector:pg15` stack. **Lesson re-confirmed:** for backend infra/DB phases, "green unit tests"
is not evidence of operability — the CLAUDE.md runtime-smoke gate is the real gate, and it must boot the
actual target (Postgres + compose), not a SQLite stand-in.

## 4. The second-order finding — review depth matters, and reviewers can be fooled by transport

- The read-only **senior-code-reviewer** returned **CHANGES_REQUESTED** after the live stack was already
  green, catching a genuine HIGH security default (Postgres published on `0.0.0.0` with trivial creds)
  plus 7 more hardening items. Functional correctness ≠ safe defaults; a code-quality lens after the
  behavioral gate is worth its cost.
- **karen** independently PASSED all three phases but flagged that the live-PG numbers are unreproducible
  without a Postgres URL (the PG-gated tests skip) — a fair caveat that now lives in the completion report
  and the compose-smoke runbook.

## 5. Process experience — what worked / what bit us

**Worked**
- ICA `--bare` + `--append-system-prompt-file CLAUDE.md` for every delegate kept conventions in scope
  without the monorepo CLAUDE.md auto-discovery overload.
- Orchestrator (Opus) drove the *live, mutating* compose stack directly rather than via a capped delegate
  — avoided the "killed mid-cutover" failure mode the ica-delegate skill warns about. Delegates stayed
  read-only (reviews) or idempotent (bounded edits in a worktree).
- Tight, file-anchored fix specs written to `/tmp/w4/*.md` → delegates applied surgically; every fix
  re-verified on disk + live, never trusted from the transcript.
- Phased commits in the worktree → clean squash; explicit `git add <paths>` every time kept the
  `backend/.venv` symlink and unrelated branch-aware `.txt` files out of every commit.

**Bit us (process lessons)**
- **macOS has no `setsid`.** `nohup setsid ica-claude.sh` died instantly ("setsid: No such file or
  directory"); plain `nohup … & disown` is the correct backgrounding idiom here. Cost one wasted reviewer
  relaunch.
- **`tail -f` follows inodes, not names.** After truncating/recreating a reviewer log, the monitor kept
  reporting the *old* inode's output — which briefly showed a stale "APPROVED" while the real run was
  still producing "CHANGES_REQUESTED". Lesson: don't truncate+recreate a file a monitor is tailing; use a
  fresh path, or `tail -F`.
- **ICA gateway drops** ("socket connection closed unexpectedly") are real and mid-edit. The file-writing
  delegate had applied ~half its edits; recovery was: verify on disk → re-delegate only the remainder
  (never blind-retry the whole batch). `--fallback-model` added on the retry.
- **The completion gate is strict (correctly).** Batch-flipping tasks to `completed` left them without
  per-task timestamps/evidence; `validate-phase-completion.py` blocked it until a scripted `update-status`
  loop added `commit:ca5a557` evidence + reviewer `verified_by`. Worth budgeting for.
- **A 6-line test-fixture fix was done by Opus directly**, not delegated — proportionate given repeated
  gateway flakiness and a fully-diagnosed FK-seeding bug (`analytics_entries.metric_type` FK to
  `metric_types`). The delegation rule's intent (avoid token-heavy implementation) didn't apply.

## 6. Test-vs-product defect split (a useful signal)

Of the failures encountered, the split was instructive: **5 product defects** (PG/container, §3) all
surfaced only live; the **3 test failures** (2 live-coalescing constructor-arg, 1 upgrade-path FK seed)
were test-harness bugs that the *new* tests exposed in themselves. New tests authored blind against a
live backend tend to carry their own fixture bugs — they need a live run too, not just authoring review.

## 7. Recommendations forward

- **Make `scripts/compose_smoke.sh` the canonical P-gate for any DB/infra phase** in the remaining waves;
  treat unit-only green as "not validated."
- **Add the ADR-007 equivalence note** (PG `job_queue` satisfies the write-failure standard via
  transactional `FOR UPDATE SKIP LOCKED`, not `retry_on_locked`) so a future reviewer doesn't re-flag it.
- **CI: add a pgvector Postgres service** and un-skip the PG-gated tests there, so the live evidence is
  reproducible without a developer's local PG (karen's caveat).
- **Default-secure compose is now the baseline** (loopback binds); keep that posture for any future
  service added to the stack, and document LAN exposure as an explicit, password+token-gated opt-in.
- **Delegation runbook:** prefer `nohup … & disown` (no `setsid`) on macOS; never tail a file you intend
  to truncate; on gateway drop, verify-on-disk then re-delegate the remainder only.
