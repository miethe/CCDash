---
schema_version: "1.0"
doc_type: prd
title: "CCDash Persona Extract — universal persona memory capture"
description: "Add a `ccdash persona extract` CLI verb that mines a single Claude Code session's JSONL post-session and emits high-signal persona-candidate lines into the universal persona memory bank's _inbox/capture.jsonl queue. Zero per-turn cost, additive third capture source for the agentic_meta_dev persona system (P4)."
status: pending
created: "2026-06-16"
updated: "2026-06-16"
feature_slug: "ccdash-persona-extract"
feature_version: "v1"
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/features/ccdash-persona-extract-v1.md
owner: "Backend Engineering"
contributors: []
priority: low
risk_level: low
category: "product-planning"
tags: ["cli", "persona-memory", "agentic-os", "universal-persona-bank", "zero-per-turn", "additive"]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/cli/commands/persona.py
  - backend/cli/main.py
  - backend/application/services/agent_queries/persona_extract.py
  - tests/unit/cli/test_persona_extract.py
related_documents:
  - docs/project_plans/implementation_plans/features/ccdash-persona-extract-v1.md
external_references:
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/persona-memory/00-PERSONA-MEMORY-DESIGN.md
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/persona.md
  - ~/.claude/memory/MEMORY.md
---

# PRD: CCDash Persona Extract v1

## 1. Feature brief & metadata

**Feature name:** CCDash Persona Extract
**Filepath:** `docs/project_plans/PRDs/features/ccdash-persona-extract-v1.md`
**Owner / dispatch home:** the agentic_meta_dev launchpad team — the universal persona memory bank lives at `~/.claude/memory/` and is owned there, not in CCDash. CCDash is the **producer**; agentic_meta_dev/operator_core is the **consumer + reconciler**.

This is **P4 of the universal persona memory plan** authored in agentic_meta_dev. P0 (file canonical bank + SessionStart inject) and P1 (the file↔DB bridge + `op remember`/`op recall`/`op persona reconcile` verbs) shipped 2026-06-16. P2 (live-session capture hooks at `~/.claude/hooks/persona_capture*.sh`) and P3 (delegation-context contract + classify/synthesize wiring) are the next two phases. P4 — this feature — is **purely additive**: the bank works without it. CCDash already parses every Claude Code session JSONL into typed `AgentSession` models; persona extract is one tiny additional pass over a single recently-changed session.

## 2. Why this exists (the problem)

The universal persona bank captures from two sources today:

1. **`op remember "<fact>"`** — explicit in-session, high-quality, low-volume.
2. **`UserPromptSubmit` / `Stop` hooks (P2)** — automatic, regex-filtered, appended to `_inbox/capture.jsonl` at <50ms per fire.

Both sources see only the user's *prompt* and a transcript-path pointer. They miss the much richer **post-hoc signal** sitting in every session JSONL: assistant decisions the user explicitly endorsed, recurring constraints surfaced as `<system-reminder>`s, errors-and-fixes pairs, named preferences ("from now on", "going forward", "stop doing X"), and any `op remember` call that was made interactively. CCDash already has a complete JSONL parser (`backend/parsers/platforms/claude_code/parser.py`, ~4500 lines) that turns every session into a typed `AgentSession` with logs, tool-usage, and message-level structure. Re-using that parser to emit persona-candidate lines is **strictly cheaper and richer** than asking the bank to re-parse JSONL itself.

> **Why CCDash and not agentic_meta_dev:** the bank explicitly does not own JSONL parsing — the persona contract calls for an external producer (constraint 7: "the CLIs are the contract; shell out and parse structured output; never re-implement"). CCDash's `claude_code/parser.py` is the canonical Claude Code parser in this homelab; rewriting it elsewhere would violate constraint 8 ("borrow concepts, not frameworks") and constraint 7 ("don't re-implement").

## 3. Out of scope

- **Bulk re-scan of historical sessions.** The CCDash production cache currently holds ~1.6 GB of session data (`~/.local/share/ccdash/offline-cache.db`); a full rescan is wasteful and would flood the persona inbox. v1 is **strictly per-session**: pass an explicit `--session <id>` (or `--latest`) and extract one. No `--all`. No batch.
- **Reconciliation, dedup, gating, model calls.** The bank's reconcile path (`op persona reconcile`) is the sole owner of model calls and the writeback gate. CCDash never calls a model and never edits canonical `.md` files; it only **emits candidate JSONL lines** to the inbox and exits.
- **CCDash-internal persona storage.** No new tables, no `persona_extract` cache. The output is one append-only JSONL file outside CCDash's data dir. CCDash remains stateless wrt the persona bank.
- **A long-running daemon.** This is a one-shot CLI. The agentic_meta_dev nightly launchd entry (P2) decides when to invoke it.
- **Persona quality classification.** The candidate lines carry a `source` and a coarse `category`; semantic classification is the bank's job (Haiku via `skillmeat memory extract apply`).

## 4. Goals & success criteria

| # | Goal | Measure |
|---|---|---|
| G1 | One CLI verb adds a third additive capture source | `ccdash persona extract --session <id>` exits 0 and writes one or more lines to `~/.claude/memory/_inbox/capture.jsonl` |
| G2 | Zero per-turn cost (post-session only) | Verb runs only when invoked; nothing fires during an active session |
| G3 | Same candidate shape as the hooks emit | Candidate JSON line schema **byte-identical** to what `persona_capture.sh` writes (one `text`, one `ts`, one `source`, one `session_id`, one `cwd`) so `op persona reconcile` treats them identically |
| G4 | Strictly per-session (no full rescan) | The CLI requires `--session <id>` xor `--latest` xor `--since <iso>` (the last bounded to a small N); `--all` is rejected |
| G5 | Additive — bank works without it | The agentic_meta_dev test suite never imports CCDash; `persona_inject.sh`, `op remember`, `op persona reconcile` work exactly as today when CCDash is uninstalled |
| G6 | Honors the file→DB constraint | Output is `.jsonl` to a path under `~/.claude/memory/`, not a SQL write; the bank's `op persona reconcile` can drain it via the existing path |
| G7 | Idempotent on rerun for the same session | A second invocation for the same session_id appends 0 new candidates (a `_meta/cccdash-extract-state.json` records what's been emitted) |

## 5. The candidate-line contract (the canonical interop point)

This is the **inviolable interop contract** — it must match what `persona_capture.sh` (P2) writes. Field names and types are frozen. Adding a new optional field is allowed; renaming or changing types is a breaking change to the bank.

```jsonl
{"ts":"2026-06-16T04:13:22Z","source":"ccdash_persona_extract","text":"<the candidate fact, one statement>","session_id":"<claude-code session id>","cwd":"<absolute path>","category":"<preference|goal|constraint|decision|gotcha|TIL|reminder>","confidence":0.0-1.0,"transcript_path":"<absolute path to source jsonl>","origin_msg_index":<int>}
```

- `source` is the discriminator the reconciler uses; `ccdash_persona_extract` is **new and reserved** (the hooks use `UserPromptSubmit` / `Stop` / `op_remember`).
- `category` is a coarse human-readable label, NOT the SkillMeat DB type vocabulary — the bank maps it later (the persona contract §5 documents the mapping; we deliberately do not enforce it here so the file→DB bridge stays the single owner of the type CHECK).
- `confidence` is a heuristic (regex-rule match strength), not a model probability.
- `origin_msg_index` and `transcript_path` together let `op persona reconcile` deep-link back to evidence without re-parsing.

The output file path is fixed: `${OP_PERSONA_HOME:-$HOME/.claude/memory}/_inbox/capture.jsonl`. The verb opens it `O_APPEND` with `flock -x -w 1`, just like the P2 hooks.

## 6. The extraction heuristics (deterministic only — no model)

CCDash never calls a model in this verb. Heuristics live in `backend/application/services/agent_queries/persona_extract.py` as a small ranked rule set:

| Rule | Trigger (case-insensitive regex over user-message text only — assistant text is ignored) | Category | Confidence |
|---|---|---|---|
| R1 explicit-remember | `op remember\\s+["']?(.+)` (the literal `op remember` invocation) | from-args | 0.95 |
| R2 going-forward | `(from now on|going forward|always|never|stop doing|don't .* again)\\b\\s+(.+)` | preference | 0.85 |
| R3 hard-preference | `\\bI (always|never|prefer|hate|love)\\s+(.+)` | preference | 0.80 |
| R4 goal | `\\bgoal:\\s+(.+)` OR `\\bI want to\\s+(.+)` | goal | 0.75 |
| R5 decision | `\\bdecision:\\s+(.+)` OR `\\bdecided to\\s+(.+)` | decision | 0.70 |
| R6 constraint | `\\bconstraint:\\s+(.+)` OR `\\bmust (always|never)\\s+(.+)` | constraint | 0.75 |
| R7 TIL | `\\b(TIL|today I learned|note to self|remember (that|this))\\b\\s*[:,]?\\s+(.+)` | TIL | 0.70 |
| R8 reminder-reinforce | system-reminder content the user explicitly endorsed (`yes\\b`/`agreed`/`right`) within ±2 messages | reminder | 0.60 |

Rules fire **per user message**, are deterministic, and emit at most one candidate per match (longest-match wins). The rule table is the file [`backend/application/services/agent_queries/persona_extract_rules.py`](#) — easy to tune without touching CLI plumbing.

**Anti-spam:** within one session, dedup by `(category, normalized_text_hash)` so a user repeating "always X" three times yields one candidate. The state file `~/.claude/memory/_meta/ccdash-extract-state.json` records the last `(session_id, max_msg_index)` pair processed, so reruns of the same session never re-emit.

## 7. CLI surface (Typer, mirrors the existing CCDash pattern)

```
ccdash persona extract --session <id> [--out <path>] [--dry-run] [--json]
ccdash persona extract --latest [--out <path>] [--dry-run] [--json]      # default
ccdash persona extract --since <iso> [--limit N] [--out <path>] [--dry-run]
                                                                          # bounded backfill (N≤25)
ccdash persona extract status                                             # show state file contents
```

- `--session <id>`: the canonical, per-session form (recommended for the launchd nightly job).
- `--latest`: pick the most recent JSONL across all `~/.claude/projects/<encoded-cwd>/`. Convenience for ad-hoc capture.
- `--since <iso> --limit N`: the only multi-session form, **hard-capped at N≤25**, never reaches into the cache DB; uses `mtime` on the JSONL files. Reserved for "I forgot to run this for a few days" — never a routine path.
- `--out <path>`: override the default capture file. Honors `OP_PERSONA_HOME` for tests.
- `--dry-run`: print candidates to stdout (or stderr when `--json`) without appending; used by the P2 install smoke test.
- `--json`: machine-readable output: `{ session_id, candidates_emitted, candidates_skipped, transcript_path, state_file }`.

Hard rejections (exit 2 with usage error):
- `--all` (no such option — a guard against the production cache).
- `--session` AND `--latest` AND `--since` are mutually exclusive.
- A `--session` that resolves to no JSONL (typo / wrong project).

## 8. Acceptance tests

| # | Test | Pass criterion |
|---|---|---|
| AT1 | `ccdash persona extract --session <fixture> --dry-run --json` on a synthetic 12-message JSONL containing 3 R1+R2+R3 matches | stdout JSON has `candidates_emitted=3, skipped=0`; no inbox write |
| AT2 | Same fixture, no `--dry-run` | inbox file gains 3 lines whose `source="ccdash_persona_extract"` and shape matches §5 byte-for-byte (a fixture comparison) |
| AT3 | Run AT2 a second time | `candidates_emitted=0, skipped=3`; state file's `(session_id, max_msg_index)` advanced |
| AT4 | A session with no high-signal user messages | exits 0 with `candidates_emitted=0`; no inbox write |
| AT5 | Tool absent: `~/.claude/memory/_inbox/` does not exist | the verb creates `_inbox/`, writes the candidate, exits 0 (matches P2 hook discipline) |
| AT6 | `OP_PERSONA_HOME=/tmp/test-bank` redirects | output goes to `/tmp/test-bank/_inbox/capture.jsonl`, state file lives under `/tmp/test-bank/_meta/` |
| AT7 | Bank-side: a fresh `op persona reconcile --run-log <jsonl>` accepts the candidates | (cross-repo manual test) the reconcile run treats `ccdash_persona_extract` lines identically to `op_remember` lines |
| AT8 | `ccdash persona extract --all` | exits 2 with a usage error referencing `--session`/`--latest`/`--since`; nothing written |
| AT9 | Concurrent run: two `extract --latest` invocations against the same session | one wins the `flock`, the other's append blocks ≤1s; both exit 0; state file consistent |
| AT10 | Performance: 5 MB JSONL fixture | extraction completes in <500 ms wall-clock on a baseline machine (heuristics are linear over user messages only) |

## 9. Risks & mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| Heuristics emit noise | M | Categories + confidence let the bank's reconcile threshold filter; rule set is small + tunable; AT3 ensures dedup; the bank's writeback gate is the final filter |
| Schema drift between hooks (P2) and CCDash (P4) | M | §5 contract is frozen; AT2 is a byte-for-byte fixture comparison; the persona contract gains a `## 6.` section listing every recognized `source` value (separate doc PR in agentic_meta_dev) |
| User runs `extract --since` with an unbounded N | L | Hard-capped at N≤25 in argparse; impossible to exceed |
| The CCDash session parser changes shape | L | The persona-extract service consumes only `AgentSession.logs[].messages[]` — the most stable surface. Add a contract test under `tests/contracts/test_persona_extract_log_shape.py` that fails loudly on a parser change |
| Reading 1.6 GB cache DB by mistake | L | The verb **never opens** `~/.local/share/ccdash/offline-cache.db`. It reads a single JSONL by path. Static check in `persona_extract.py`: assert no `OfflineCache` import. |
| Persona inbox grows unbounded | L | The bank's reconcile drains it; the inbox is append-only and rotated by `op persona reconcile` (a separate concern, owned by agentic_meta_dev) |

## 10. Cross-repo coordination

This PRD lives in CCDash; the consumer/contract lives in agentic_meta_dev. The full story:

1. **CCDash (this PRD):** ship `ccdash persona extract --session <id>`.
2. **agentic_meta_dev (separate, already planned in P2):** the nightly launchd entry calls `ccdash persona extract --latest` (or iterates Stop-hook-recorded transcript paths), THEN runs `op persona reconcile`. The launchd plist lives at `~/Library/LaunchAgents/com.miethe.persona-reconcile.plist` — the user adjusts the wrapper script `infra/persona-hooks/persona_reconcile_nightly.sh` to add the `ccdash persona extract` step once this verb ships.
3. **agentic_meta_dev (one-line doc PR):** add `ccdash_persona_extract` to the recognized `source` values in `docs/agentic-operator/contracts/persona.md` §2 (alongside `UserPromptSubmit`, `Stop`, `op_remember`).

No code changes are required in agentic_meta_dev for v1 — the existing `op persona reconcile` does not discriminate by `source`, and the inbox file is the existing `_inbox/capture.jsonl`.

## 11. Out-of-scope follow-ups (future versions)

- **v1.1 — server-driven sweep.** A `ccdash persona sweep` REST endpoint that returns the JSON the CLI would emit, so a remote launchd job (e.g., on a desktop where the bank lives) can drive extraction. Adds zero per-turn cost. No new heuristics.
- **v1.2 — origin-anchor lineage.** The candidate carries a stable `(transcript_path, origin_msg_index)` already; v1.2 makes the bank surface a clickable evidence link in the reconcile UI (a Workspace Command Center concern, not CCDash's).
- **v2 — Codex parser parity.** The same heuristics over the Codex JSONL parser at `backend/parsers/platforms/codex/parser.py`, gated behind `--platform codex`. Non-trivial because Codex framing differs.

## 12. Appendix — file map (where the work lands)

| File | Role | Created/Modified |
|---|---|---|
| `backend/cli/commands/persona.py` | Typer sub-app (`ccdash persona extract`, `ccdash persona extract status`) | NEW |
| `backend/cli/main.py` | Register the persona sub-app | MOD (one line) |
| `backend/application/services/agent_queries/persona_extract.py` | The pure-function service consumed by the CLI (and a future REST endpoint) | NEW |
| `backend/application/services/agent_queries/persona_extract_rules.py` | The rule table (§6) | NEW |
| `tests/unit/cli/test_persona_extract.py` | AT1–AT10 | NEW |
| `tests/unit/services/test_persona_extract_rules.py` | Rule-table table-driven tests | NEW |
| `tests/contracts/test_persona_extract_log_shape.py` | Locks the `AgentSession.logs[].messages[]` shape (Risk row) | NEW |
| `docs/project_plans/implementation_plans/features/ccdash-persona-extract-v1.md` | The phased build plan (sibling to this PRD) | NEW |

---

**Sign-off:** This PRD is hand-authored from the agentic_meta_dev launchpad as the P4 hand-off; the build is owned by the CCDash backend-engineering team. Open questions go to the launchpad's open-seam tracker (`docs/seams.yaml` in agentic_meta_dev).
