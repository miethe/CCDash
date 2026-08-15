---
type: aar
schema_version: 2
doc_type: report
report_category: aar
feature_slug: are-we-winning-dashboard
title: "AAR — are-we-winning dashboard v1 execution"
status: completed
created: 2026-08-15
updated: 2026-08-15
plan_ref: docs/project_plans/implementation_plans/features/are-we-winning-dashboard-v1.md
prd_ref: docs/project_plans/PRDs/features/are-we-winning-dashboard-v1.md
itt_node_id: node_01M009H6DGAKD5VCC8QCM0KP0K
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
ccdash_session_id: "S-0a2c5479-4dda-4163-822f-0ef73f8f9129"
commit_refs: [0fabfe8, adef955, 6b0c0f4, 22f97f7, 7b454db, fd6c953, 317025f]
---

# AAR — are-we-winning dashboard v1

Tier 2 plan, 3 milestones, executed via `/dev:execute-plan` with aggressive offload to ICA and
Codex per an explicit operator instruction to minimise primary/subscription spend.

## The headline number, and why it is misleading

Wall clock from first commit to last was **~13.5 hours**. Actual work was **~1 hour**.

| Window | Duration | What |
|---|---|---|
| 08-14 22:55 → 23:53 | **58 min** | All four implementation legs: M1 ingestion, M1 gate fixes, M2-A rollups/REST, M3 dashboard, M2-B derivations, scheduler wiring |
| 08-14 23:57 → 08-15 11:54 | **~12h** | **Dead. A hung process.** |
| 08-15 11:54 → 12:40 | ~45 min | Runtime browser smoke, evidence capture, M2/M3 gate |

Four milestones of real backend + frontend work, gated and fixed, in under an hour. Then a stall
longer than the entire rest of the run.

## Root cause of the 12-hour stall (measured, not inferred)

A seeding script that populates the local cache for the browser smoke **completed its work and then
hung on shutdown**, and while hung it held the SQLite connection, so every subsequent script blocked
in `get_connection()`.

The diagnosis is precise because the same failure was still live 12 hours later and could be
examined directly:

- `seed_ingest.py` — 42 min elapsed, zero output.
- `seed_derive.py` — 29 min elapsed, zero output, **running under `python -u`**. It had not emitted
  even its first flushed `print`, which is the second statement in the function. So it was blocked
  inside `get_connection()`, not doing slow work.
- The derived rows those scripts were meant to write (**33** reopened events, **4,005** self-caught
  buckets) were **already in the database and queryable**. The work finished; the process did not.
- Killing both PIDs produced their completion notifications *immediately*.

Mechanism: `asyncio.run(main())` over a module-singleton DB connection that is never closed. The
loop will not exit with the connection outstanding, the process never terminates, the SQLite lock is
never released, and **nothing anywhere has a timeout**. The next script then blocks forever on
connect, and looks identical to "slow".

This is the SQLite sibling of the Postgres lock-convoy hazard already known in this repo. The
generalisable lesson is not "close your connections" — it is that **a hang and slow work are the
same observable**, and the only cheap discriminator is an unbuffered first-line print: if a `-u`
process has not printed its first statement, it is blocked, not busy. That check cost seconds and
would have caught this in minute one.

## What worked

**Offload economics.** Five of seven routed legs ran off the subscription — 3× ICA Sonnet 5, 2×
Codex `gpt-5.6-terra` — with only the MUST-stay-primary derivation leg and the final verdict on
Claude. The plan's own `routing_constraints` made this decidable without judgement calls: it named
which failure modes were "silently plausible" and therefore un-offloadable, and everything else was
fair game. Routing constraints written at plan time are worth more than any dispatch-time heuristic.

**The adversarial gate earned its cost, unambiguously.** The M1 Codex gate returned
CHANGES_REQUESTED with four concrete `file:line` defects, three of which were failure modes the
brief had explicitly told it to hunt for:

1. a stable/cyclic `next_cursor` looping forever — would have pinned a worker;
2. a blanket `except Exception` converting programming errors into reported success;
3. an **event id written into a timestamp column** (`last_ingest_at`);
4. the v55 entry missing from the lockstep schema-version histories.

None of these would have been caught by the tests that already passed. Naming the specific
failure modes in the gate prompt is what made the gate productive rather than decorative.

**Parallel legs with disjoint file ownership.** M2-B (primary) and M3 (ICA) ran concurrently on
backend vs frontend files with zero conflicts, verified by checking the changed-path sets rather
than assuming. This roughly halved the critical path.

**M2-B caught a cross-milestone integration defect on its own.** M3's "Nodes Reopened" click called
the generic drill-through with `event_type=node.reopened`, which would have silently returned an
empty page the moment `reopened` stopped being null. Because M3 shipped before M2-B, this was a real
seam, and the executor found and fixed it rather than staying inside its brief.

**Honest-by-construction shipped intact.** The self-caught ratio renders `unknown` at 4,005 (100%)
with explicit `0 (0.0%)` entries beside it. Nothing was inferred, defaulted, or redistributed. The
build also produced a sharper result than the survey it started from: `meta.origin`'s real
vocabulary (`bug`, `imported_plan`, `decision`, `human_gate`) is node **provenance**, not actor
attribution — so the proxy route is not weak, it is the wrong axis entirely.

## What did not work

**Delegated legs could not verify their own work.** Every ICA leg was blocked from running the
commands that would prove its claims — `npx tsc --noEmit`, `vitest`, `npm run typecheck`, and even
`backend/.venv/bin/python` — by harness approval gates with no approval path in a `-p` session. Two
executors said so plainly rather than claiming success, which is the right behaviour and the reason
this was caught. The orchestrator then ran everything itself. But the failure mode is obvious: a
less scrupulous leg reports green.

**Delegated legs could not write their own deviation log.** Every ICA `Edit` against
`.claude/worknotes/**` was auto-denied. The execution doctrine's "log the deviation and keep going"
therefore degrades, under offload, to *neither halting nor recording*. The orchestrator transcribed
each leg's notes by hand. Note the asymmetry: the same lane successfully **created** that file
earlier — creation passed, append did not.

**A delegated leg left an environment landmine.** One executor worked around the sandboxed venv path
by building a disposable `backend/.venv` **inside the worktree**. It is gitignored, so `git status`
showed nothing, and it silently shadowed the real venv — `npm run dev` then failed with
`ModuleNotFoundError: No module named 'ccdash_contracts'`.

**The provisioning gate never ran.** `provision-artifacts.sh` is documented as on-by-default and
mechanically enforced; it is not executable, so the documented invocation dies with `permission
denied` — and the caller still observes exit 0. When invoked via `bash` it then hangs >120s with no
timeout.

**A standalone script resolved the wrong repo.** Running a script from outside the tree put the
script's own directory on `sys.path`, so `backend` resolved to the **main checkout**, not the
worktree. Caught by an explicit assertion; the pytest runs were cwd-based and unaffected, verified
rather than assumed.

## Changes worth making

1. **Give every delegated seeding/verification script a first-line unbuffered print and a timeout.**
   The hang/slow ambiguity is the single most expensive thing in this run by an order of magnitude.
2. **Move the deviation-log write to the orchestrator by contract**, not by accident. Ask delegated
   legs to *return* deviations; the orchestrator records them. This matches the single-committer
   rule already in force.
3. **Have briefs state the verification commands the lane can actually run**, or state up front that
   the orchestrator will verify. Right now briefs ask for verification the lane cannot perform.
4. **Fix the provisioning gate's executable bit and add a timeout** — an always-silently-skipped gate
   is worse than no gate, because it reads as coverage.

## Filed

| Finding | Tree | Node |
|---|---|---|
| provision-artifacts.sh not executable — gate silently no-ops at exit 0 | agentic_meta_dev | `node_01M01MBKAAPZ21SS3S38FSW6NV` |
| provision-artifacts.sh has no timeout — 120s+ pre-flight stall | agentic_meta_dev | `node_01M01MC2FE7S7YS1TBW6XFHBF6` |
| ICA legs cannot append to `.claude/worknotes/**` in `-p` sessions | agentic_meta_dev | `node_01M01PG9EY4DHC5BW8ARHDKJ7N` |
| dual-DDL parity gate already red on `main` (4 tables) | CCDash | `node_01M01NCB6AFSDZQS5QQM3NAC79` |
| self-caught drill-through backend ships uncalled by the FE | CCDash | `node_01M01R99RTVZFGJT1708VT057M` |
| per-actor IntentTree tokens — the durable upstream fix | intenttree | `node_01M01R8QY47TEPVQG53B6ASTJY` |
