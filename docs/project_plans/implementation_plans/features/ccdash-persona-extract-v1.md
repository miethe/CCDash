---
schema_version: '1.0'
doc_type: implementation_plan
title: "CCDash Persona Extract \u2014 Implementation Plan"
description: "Phased plan for `ccdash persona extract` (P4 of the universal persona\
  \ memory system). Stateless, deterministic, per-session JSONL \u2192 candidate lines\
  \ into the universal bank inbox. Strictly additive."
status: completed
created: '2026-06-16'
updated: '2026-06-16'
feature_slug: ccdash-persona-extract
feature_version: v1
prd_ref: docs/project_plans/PRDs/features/ccdash-persona-extract-v1.md
plan_ref: null
scope: One Typer sub-app, one query service, one rule table, three test files. No
  DB writes. No model calls.
effort_estimate: 5-7 story points
effort_estimate_breakdown: 'Phase 1 (rules+service): 2-3 pts | Phase 2 (CLI+state):
  2 pts | Phase 3 (tests+contract): 1-2 pts'
priority: low
risk_level: low
owner: Backend Engineering
contributors: []
milestone: null
commit_refs: []
pr_refs: []
files_affected:
- backend/cli/commands/persona.py
- backend/cli/main.py
- backend/application/services/agent_queries/persona_extract.py
- backend/application/services/agent_queries/persona_extract_rules.py
- tests/unit/cli/test_persona_extract.py
- tests/unit/services/test_persona_extract_rules.py
- tests/contracts/test_persona_extract_log_shape.py
category: product-planning
tags:
- cli
- persona-memory
- agentic-os
- additive
- no-model
- no-db-writes
related_documents:
- docs/project_plans/PRDs/features/ccdash-persona-extract-v1.md
---

# Implementation Plan: CCDash Persona Extract v1

## Pre-flight (do these before starting)

1. **Read the PRD** (sibling): `docs/project_plans/PRDs/features/ccdash-persona-extract-v1.md`. The §5 candidate-line contract and §6 rule table are inviolable — those are the interop points with agentic_meta_dev.
2. **Read the bank-side contract** (read-only, not in this repo): `/Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/persona.md`. Especially §2 (verified-live SkillMeat surface) and §4 (invariants).
3. **Confirm a session JSONL fixture is available.** Use any small recent session under `~/.claude/projects/<encoded-cwd>/`; copy a redacted/synthetic copy into `tests/fixtures/persona_extract/` (≤50 lines, ≤8 user messages).
4. **No new dependencies.** The verb uses stdlib only (re, json, pathlib, fcntl) plus the existing `backend.parsers.platforms.claude_code.parser` and Typer (already present).

## Phase 1 — Heuristics + service (2-3 pts)

**Files:**
- `backend/application/services/agent_queries/persona_extract_rules.py` (NEW, ~80 LOC)
- `backend/application/services/agent_queries/persona_extract.py` (NEW, ~150 LOC)
- `tests/unit/services/test_persona_extract_rules.py` (NEW, ~60 LOC)

**Tasks:**

1.1. Author `persona_extract_rules.py` as a frozen, table-driven rule list — exactly the 8 rules from PRD §6. Shape:
   ```python
   from dataclasses import dataclass
   import re
   @dataclass(frozen=True)
   class Rule:
       id: str          # "R1", "R2", ...
       pattern: re.Pattern
       category: str    # PRD §5 vocab: preference|goal|constraint|decision|gotcha|TIL|reminder|from-args
       confidence: float
       capture_group: int   # which group in `pattern` is the candidate text (0 = whole match)
   RULES: tuple[Rule, ...] = (...)
   ```
   Each `pattern` is `re.compile(..., re.IGNORECASE)`. Keep this file pure data — no logic, no IO.

1.2. Author `persona_extract.py` with one public function:
   ```python
   def extract_candidates(session: AgentSession, *, prior_max_msg_index: int = 0) -> list[CandidateLine]:
       """Run RULES over the user-message text of `session`, dedup by
       (category, normalized_text_hash), and return CandidateLine dicts that
       byte-match PRD §5. Pure function; no IO."""
   ```
   Where `CandidateLine = TypedDict(...)` matches PRD §5 verbatim. The function MUST:
   - Iterate `session.logs[*].messages[*]` and process **only** messages whose `role == "user"` (and `msg.index > prior_max_msg_index`).
   - For each rule, on match, append a candidate.
   - Dedup pass: hash `(category, re.sub(r'\\s+', ' ', text.strip().lower())[:200])` and drop later occurrences within this call.
   - Return ordered by `(msg.index, rule.id)` for stable diffs.

1.3. Tests in `test_persona_extract_rules.py` — table-driven, 8 rules × ≥2 cases each. Use `parametrize`. Cover: positive match, near-miss negative match, longest-match-wins tie-break, ALL_CAPS variant, multi-line capture truncation. **No mocking** — pure functions only.

**Phase-1 acceptance:** `pytest tests/unit/services/test_persona_extract_rules.py -q` is green; the service has no imports from `backend.cli`, no Typer, no IO.

## Phase 2 — CLI + state file (2 pts)

**Files:**
- `backend/cli/commands/persona.py` (NEW, ~180 LOC)
- `backend/cli/main.py` (MOD — one line: `app.add_typer(persona_app, name="persona")`)

**Tasks:**

2.1. Implement the Typer sub-app per PRD §7. Mirror `backend/cli/commands/artifact.py` for option-parsing + output-mode handling. The four entry points:
   - `extract` — the verb. Mutually-exclusive `--session` / `--latest` / `--since`. Argparse-level reject `--all`.
   - `extract status` — print the state file (or `{}` if absent). Always JSON when `--json`.

2.2. Implement the inbox writer:
   - Resolve bank dir: `bank = Path(os.environ.get("OP_PERSONA_HOME") or Path.home() / ".claude" / "memory")`.
   - Resolve inbox: `bank / "_inbox" / "capture.jsonl"`. `mkdir(parents=True, exist_ok=True)` matches the P2 hook discipline.
   - Acquire `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `bank / "_inbox" / ".capture.lock"` with up to 1.0 s of polling-retry. On lock failure, retry up to 5×; on persistent failure, exit 4 with a clear stderr message (matches BaseAdapter.UNSUPPORTED semantics).
   - Append one JSON line per candidate (`json.dumps(line, separators=(',',':'))` + `\n`). Flush + fsync.
   - Update the state file `bank / "_meta" / "ccdash-extract-state.json"` atomically (temp-file + `os.replace`).

2.3. Implement the resolver:
   - `--session <id>`: resolve via `backend.parsers.platforms.claude_code.parser` to find the JSONL whose name is `<id>.jsonl` under `~/.claude/projects/*/`. If multiple, prefer the latest mtime.
   - `--latest`: glob all `~/.claude/projects/*/*.jsonl`, pick the highest mtime (cap globbing at 5000 entries to be safe; if more, log + truncate — never error).
   - `--since <iso> --limit N`: filter the same glob by `mtime >= iso`, sort desc, hard-cap at `min(N, 25)`. **Hard-cap is enforced at the argparse level (a callback that clamps).**

2.4. JSON output (PRD §7): when `--json` is set, every code path emits exactly one JSON document on stdout; never mix human + JSON. When `--dry-run`, candidates go to stderr (so a piped `--json` consumer reads only the summary).

**Phase-2 acceptance:** `ccdash persona extract --latest --dry-run --json` runs end-to-end against a real session, no inbox write, exits 0; the structured output validates against a JSON schema you author at `tests/fixtures/persona_extract/output-schema.json`.

## Phase 3 — Acceptance tests + cross-repo coordination (1-2 pts)

**Files:**
- `tests/unit/cli/test_persona_extract.py` (NEW, ~250 LOC) — AT1–AT10 from PRD §8.
- `tests/contracts/test_persona_extract_log_shape.py` (NEW, ~40 LOC) — locks `AgentSession.logs[*].messages[*]` shape so a parser refactor breaks loudly.
- A `tests/fixtures/persona_extract/` dir with: `synthetic-session.jsonl` (12 messages, 3 R1+R2+R3 matches), `noise-session.jsonl` (no high-signal messages), `output-schema.json` (the §5 line schema).

**Tasks:**

3.1. Implement AT1–AT10 verbatim. Use `OP_PERSONA_HOME=tmp_path` (pytest fixture) to redirect IO. AT9 (concurrency) uses `multiprocessing.Process` to fire two extractors at the same fixture; assert no torn writes (line-count after = line-count from one + line-count from the other; no JSON parse errors).

3.2. The contract test asserts `AgentSession.logs[0].messages[0]` has `role`, `content`/`text`, `index`/`timestamp` — names exactly as the persona service consumes them. If the parser renames a field, this test must fail with a message pointing the dev at the persona-extract service.

3.3. **Cross-repo doc PR** (out-of-band, the dev opens this in agentic_meta_dev — not in this CCDash branch):
   - Add a one-line note to `agentic_meta_dev/docs/agentic-operator/contracts/persona.md` §2 that lists `ccdash_persona_extract` alongside the other recognized `source` values for capture lines.
   - Add a one-line note to `agentic_meta_dev/infra/persona-hooks/persona_reconcile_nightly.sh` (when P2 lands) that runs `ccdash persona extract --latest` before `op persona reconcile`.

**Phase-3 acceptance:** `pytest tests/unit/cli/test_persona_extract.py tests/unit/services/test_persona_extract_rules.py tests/contracts/test_persona_extract_log_shape.py -q` is green. The full CCDash suite stays green (no flakiness, no ordering deps). Manual smoke test on a real session writes lines to `~/.claude/memory/_inbox/capture.jsonl` that `op persona reconcile --run-log <jsonl>` accepts without error.

## Out-of-scope safety rails (do NOT do these in v1)

- **No** import of `backend.db.cache.OfflineCache` or any 1.6 GB cache surface from this code path.
- **No** model calls. The PRD's §6 rules are deterministic regex; `--use-llm` is rejected (not even a hidden flag).
- **No** edits to canonical `~/.claude/memory/*.md` files. Only `_inbox/capture.jsonl` and `_meta/ccdash-extract-state.json`.
- **No** new Typer top-level command. The verb lives under `ccdash persona ...`, mirroring the existing sub-app pattern.
- **No** new REST endpoint in v1 (deferred to v1.1 — see PRD §11).

## Risk register (mirrors PRD §9 with implementation-level mitigations)

| PRD risk | Mitigation in code |
|---|---|
| Heuristic noise | Confidence floor in §6; bank-side reconcile gate is the final filter |
| Schema drift hooks ↔ CCDash | `tests/fixtures/persona_extract/output-schema.json` is the byte-for-byte spec; both producers must match |
| `--since` runs unbounded | Argparse callback clamps `--limit` to ≤25 BEFORE any glob; an `--all` flag is explicitly absent |
| Parser shape change | `tests/contracts/test_persona_extract_log_shape.py` is the contract |
| Cache DB read by accident | `# fmt: off` comment-block at top of `persona_extract.py` listing the forbidden imports; a CI grep job (optional) |
| Inbox write races | `flock`-guarded with retry; AT9 covers two-process race |

## Sign-off & hand-back

When all three phases land:
- Update `docs/CHANGELOG.md` with `feature/ccdash-persona-extract-v1`.
- Notify the agentic_meta_dev launchpad team: the cross-repo doc PR (Phase 3.3) can land, and the nightly wrapper script can include the `ccdash persona extract` step.
- Mark this plan `status: completed` and link the PR(s).
