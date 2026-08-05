---
schema_version: 2
doc_type: spike
title: "Codex Session Naming — Availability Spike"
status: completed
created: 2026-08-04
feature_slug: automatic-session-naming
leg_id: tech-codex
confidence: 0.9
feasibility: feasible-with-constraints
---

# Codex Session Naming — Availability Spike

Codex is installed locally with a substantial real corpus: **3,427** rollout JSONL files under
`~/.codex/sessions/**`. All measurements below are full-corpus scans (no sampling), run against
this machine's actual data. No web documentation was substituted for any measured claim; docs are
cited only where explicitly marked "documented, not measured."

## Method (commands actually run)

```bash
# Layout discovery
find ~/.codex/sessions -type f -name "*.jsonl" | wc -l                 # 3427
find ~/.codex/sessions -type f | sed 's/.*\.//' | sort | uniq -c        # all .jsonl, no other type

# Shape inspection (single sample file, then full-corpus python scans)
head -3 <sample>.jsonl | python3 -c '...'                              # entry/payload type dump
python3 <full-corpus scan over ~/.codex/sessions/**/*.jsonl>           # coverage / timing / mutability
  # scanned every line of every file, classified payload.type == "thread_name_updated"

# Config check
grep -ni "name\|title\|thread" ~/.codex/config.toml                    # 1 unrelated hit (MCP gateway "name")

# Existing parser inspection
Read backend/parsers/platforms/codex/parser.py (1343 lines, full file)
grep -rn "thread_name" backend/ (excluding .venv)                       # zero hits — confirms discard
grep -n "codex" backend/parsers/platforms/discovery_profiles.json      # confirms ~/.codex/sessions is a discovery root
```

Three full-corpus Python scans were run (source scripts at `/tmp/codex_name_scan*.py`, not
committed — throwaway analysis code): (1) coverage + timing + mutability, (2) coverage by
`originator` / line-count bucket / subagent-vs-root, (3) whether `codex_exec` subagents inherit a
named parent thread. A fourth scan checked `session_meta.payload.git` coverage as a fallback
candidate.

## Findings

### 1. Location + exact shape

Path pattern: `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<ISO8601>-<uuid>.jsonl` — one file per
Codex "thread" (root session or subagent). This is **already** a discovery root in
`backend/parsers/platforms/discovery_profiles.json` (`"codex".roots: ["${HOME}/.codex/sessions",
"${HOME}/.codex/projects"]`).

Each line is a JSON object `{"timestamp", "type", "payload"}`. Per-file entry types observed
(one sample, 70 lines): `response_item` (49), `event_msg` (19), `session_meta` (1),
`turn_context` (1). The name-bearing record is an `event_msg` whose `payload.type` is
`thread_name_updated` — a **top-level sibling event type**, not nested inside `session_meta` or
`turn_context`:

```json
{
  "timestamp": "2026-04-20T17:53:39.070Z",
  "type": "event_msg",
  "payload": {
    "type": "thread_name_updated",
    "thread_id": "019dac06-b5db-7b32-ba8b-09a89947d206",
    "thread_name": "Harden frontend nginx runtime"
  }
}
```

Real (redacted-by-nature — these are already just short task titles, not secrets) example values
observed: `"Implement Planning drawer reskin"`, `"Execute phases 0 and 7"`, `"Commit deployment
plan docs"`, `"Align docker compose scripts"`. These are fluent, human-meaningful, task-scoped
titles — qualitatively they read as model-generated (client-side), not templated.

### 2. Coverage — 15.79% overall, sharply originator-dependent

Of **3,427** local Codex sessions, **541** (15.79%) carry at least one non-empty `thread_name`.
**2,886** (84.2%) never emit the event. Zero parse errors across the full corpus.

Coverage segmented by `session_meta.payload.originator` (the Codex client that created the
thread):

| Originator | Total | Named | Coverage |
|---|---|---|---|
| `Codex Desktop` | 2,059 | 284 | 13.8% |
| `codex_vscode` | 355 | 257 | **72.4%** |
| `codex_exec` (headless CLI) | 960 | 0 | **0.0%** |
| `codex_cli_rs` | 43 | 0 | 0.0% |
| (missing) | 10 | 0 | 0.0% |

**`codex_exec` — the headless/scripted invocation path, and the one most likely to match how this
AOS environment's automated agent workflows actually run Codex — never emits a name.** Confirmed
also that `codex_exec` subagent threads (412 of the 960 have a `parent_thread_id`, i.e. were
spawned from another thread) do not inherit a name via their parent either: 0 of those 412 parents
carry a name. There is no cross-session correlation path that recovers a name for this client.

Root-vs-subagent split (independent of originator): subagent threads (spawned via
`source.subagent.thread_spawn`, 1,993 total) are named at 21.7% (432/1,993); root threads (1,434
total) at 7.6% (109/1,434) — subagent threads skew more toward the higher-coverage clients
(Desktop/VS Code) in this corpus, which explains the gap; it is not an independent effect.

Session-length bucket also correlates (more turns → more likely to have accumulated a name):
`<5 lines`: 0/17 named; `5–19`: 9/149; `20–99`: 111/940; `>=100`: 421/2,321. Coverage rises with
session length but plateaus around 18%, it does not converge toward the client-level rates above.

### 3. Timing — shortly after the first turn, not at session start

Across the 541 named sessions, the first `thread_name_updated` event lands at file-line index
2–62 (avg 9.72, median-equivalent ≈9), i.e. **after** `session_meta` + the first
`event_msg:task_started` + the first user/assistant message pair, at an average relative depth of
**8.4%** into the eventual file length. 5 of 541 land at line ≤2 (essentially immediate); 77 land
after line 10 (later in a longer thread). It is not written at session-open time and not
exclusively at first-turn time — it fires once the client has enough context to title the thread,
which for most sessions is within the first few turns.

### 4. Mutability — yes, in place, and clustered

4 of the 541 named sessions (0.74%) show a **second** `thread_name_updated` event that replaces
the earlier value with a different, more specific one, hours later:

```
"Execute ccdash reskin plan"          (t+few min)  -> "Execute ccdash reskin plan: 5-6"       (~17h later)
"Enhance planning page"               (t+few min)  -> "planning-reskin-v2-addendum: plan"     (~4h later)
"Execute ccdash reskin plan"          (t+few min)  -> "Execute ccdash reskin plan: 8-10"       (~5h later)
"Execute phase 11-12"                 (t+few min)  -> "planning-reskin-v2-addendum: 11-12"     (~19-20 min later)
```

All four second-update timestamps cluster within the same ~2-minute window across different
threads and different dates (`20:22:47`–`20:23:28` UTC), which reads as a background/batch
re-titling pass rather than a per-turn model call — the mechanism is not directly observable
(closed-source client), so this is inference from timing evidence, not a confirmed fact (see OQ-3).
The semantics observed are **replace-in-place**: the later event supersedes the earlier value; the
earlier value is not retained anywhere in the file once superseded (a consumer must track "latest
wins by timestamp" the same way `effort_tier`/`skill_name` resolution already does elsewhere).
Resume behavior (does a resumed thread's rollout file get a fresh name or keep appending to the
same file) was not separately observable — Codex appears to append continuously to the same
per-thread file across a multi-day span (the 4 mutability examples span up to 19+ hours between
first and second name), consistent with one file persisting across resumed work, not a fresh file
per resume.

### 5. Already-in-reach? Yes — and currently discarded

`backend/parsers/platforms/codex/parser.py` already iterates every JSONL line for every
`~/.codex/sessions/**` file (this discovery root is already active). Its `event_msg` handling
(lines ~1148–1173) is:

```python
if entry_type_lower == "event_msg":
    summary_text = str(payload_dict.get("summary") or payload_dict.get("message") or payload_dict.get("text") or "").strip()
    if payload_type in {"task_started", "task_complete", "turn_aborted", "context_compacted", "item_completed", "thread_rolled_back"}:
        append_log(...)
    if timestamp and (summary_text or payload_type):
        impacts.append(ImpactPoint(timestamp=timestamp, label=(summary_text or payload_type)[:200], ...))
```

`thread_name_updated` is not in the whitelisted `payload_type` set for `append_log`, and it has no
`summary`/`message`/`text` key — only `thread_id` and `thread_name` — so `summary_text` is always
empty for this event. The `impacts.append` branch still fires (because `payload_type` itself is
truthy) but uses `payload_type` as the label, i.e. it silently emits an `ImpactPoint` labeled
literally `"thread_name_updated"` and **the actual `thread_name` string is read into memory and
then discarded**, never reaching `AgentSession` or any DB column. Confirmed via
`grep -rn "thread_name" backend/` (excluding `.venv`): zero hits anywhere in CCDash's own code.

**Secondary discard, same file**: `session_meta.payload.git` (containing `branch`, `commit_hash`,
`repository_url`) is present in 3,312/3,427 (96.6%) of sessions, with a non-empty `branch` in
3,256/3,427 (95.0%) — yet the parser's returned `AgentSession` hardcodes `gitBranch=None`,
`gitAuthor=None`, `gitCommitHash=None` unconditionally (never reads `payload_dict.get("git")`).
This is a second, independent discard finding relevant to the "no-model-call derivation" question
below, though branch names (frequently just `"main"`) are lower-specificity than `thread_name`.

`~/.codex/config.toml`: no naming-related settings — the only `name`-keyed line in the file is an
unrelated MCP server entry (`name = "IBM ICA Gateway"`). `~/.codex/history.jsonl` is a separate,
small (131-line total) prompt-history log (`{session_id, ts, text}`), not a per-session name/title
store — it does not scale as a naming source and was not designed as one.

## Existing Parser Gap

Concretely, closing this gap requires exactly one new branch in the `event_msg` handling block:
detect `payload_type == "thread_name_updated"`, capture `payload_dict.get("thread_name")` keyed by
"latest wins" (overwrite on each occurrence, matching the observed replace-in-place mutability),
and surface the final value on the returned `AgentSession` (a new field, following the
`badgeLatestSummary`/`skill_name` precedent already in this file). No new file discovery, no new
read surface — the bytes are already being read and thrown away.

## No-Name Fallback Options (ranked, all zero-model-call, all already in the payload)

For the 84.2% of sessions with no `thread_name` — dominated by `codex_exec` at 0% coverage:

1. **First-user-message truncation** (current baseline) — already implemented as
   `badgeLatestSummary = first_user_message_text[:200]` (line ~1341 of the parser). This is the
   counterfactual the charter asks to beat. Coverage: effectively 100% of sessions with any user
   message.
2. **Git branch** (`session_meta.payload.git.branch`) — 95.0% coverage, zero model call, currently
   discarded (see Finding 5). Lower specificity than `thread_name` (frequently `"main"`), but
   materially better than a raw UUID and available for exactly the `codex_exec` population where
   `thread_name` is absent. Cheapest possible fallback tier.
3. **Extracted slash-command invocation** — the parser already extracts `/command:name` tokens
   from message text into `type: "command"` log entries (`_extract_command_invocations`). Coverage
   not separately measured in this leg (would require a second scan); likely materially lower than
   git branch, but higher specificity when present (e.g. `/dev:execute-plan`).
4. **Cross-session `taskDescription`/`taskName`** from the *parent's* Task/Agent tool-call metadata
   — only recoverable when this session is itself a spawned subagent AND the parent session is
   also ingested and correlatable (via `workflowId`/`parentSessionId`), i.e. not self-contained in
   the child's own file. Not separately measured; flagged as a candidate, not a validated tier.

Recommended provenance ordering for a `session_name_source` column (highest to lowest trust):
`codex_thread_name` (provider-generated, persisted) > `git_branch` > `slash_command` >
`first_message_truncated` (current fallback, lowest specificity but near-100% coverage).

## Open Questions

- **OQ-1**: Is `thread_name_updated` produced by a client-side model call (Codex Desktop / VS Code
  extension backend) or a deterministic heuristic? Not directly observable (closed-source client);
  inferred to be model-generated from the fluency of the values (Finding 1). This does not affect
  AOS constraint 4 for CCDash — the value is already computed and persisted upstream of CCDash's
  read path; CCDash only reads it, never generates it.
- **OQ-2**: Will a future `codex_exec`/headless mode ever populate `thread_name`? Unmeasurable
  locally (would require watching Codex's own roadmap/changelog); the integration leg's
  "conditional" path should name this as the concrete precondition for closing the `codex_exec`
  gap if a `go`/`conditional` verdict is reached.
- **OQ-3**: The 4 observed renames cluster within a ~2-minute window across different threads and
  dates — read as a background/batch re-titling pass, not per-turn. Not confirmed; would need
  Codex client instrumentation or vendor docs (documented-not-measured territory) to settle
  definitively.
- **OQ-4**: The 72.4% `codex_vscode` coverage and 13.8% `Codex Desktop` coverage are measured on
  one machine/user's real corpus (3,427 sessions, real production usage over ~9 months per the
  directory's `2025/08`–`2026/08` date range) — not a synthetic sample, but still single-environment;
  generalization to other users' Codex configurations is not verified here.

## Confidence Rationale

0.9 confidence. Every quantitative claim in this document is a full-corpus scan (3,427/3,427
files, zero parse errors, zero sampling) using the actual local `~/.codex/sessions/**` data and the
actual shipped `backend/parsers/platforms/codex/parser.py` source — not documentation, not
inference from a partial sample. The 0.1 discount is entirely for OQ-1/OQ-3 (client-side mechanism
is inferred from timing/fluency evidence, not directly observable) and OQ-4 (single-environment
measurement). Feasibility is **feasible-with-constraints**: a real, human-meaningful,
already-persisted, already-in-reach, backfillable (re-parse recovers all 541 historical rows — no
launch-time-capture-style forward-only limitation) name exists, but at 15.79% overall coverage it
falls well short of the charter's 50% "go" coverage bar on its own, and is effectively absent
(0%) for the `codex_exec` headless path that most automated/scripted Codex usage in this
environment goes through. The tiered fallback chain above (git branch at 95% coverage) is the
concrete, zero-model-call mitigation that keeps this leg's contribution to the exploration's overall
verdict from being a flat no — but the `session_name_source` provenance column the integration leg
designs must treat `codex_thread_name` as a minority-coverage, high-trust tier, not the default
path for Codex sessions.
