# Journal transcript egress — the exclusion predicate CCDash applies

> **Scope:** every path that turns a Claude Code JSONL transcript into a CCDash row.
> **Node:** `node_01M1YV12EH7AQSXSMSFSKQJXM8` (parent finding `node_01M1YQE73ZT7T4EZSKNYX007ER`).
> **Upstream policy:** `agentic_meta_dev/docs/policies/transcript-exclusions.md`.

## The hazard, in one paragraph

A session transcript is an **egress surface**. Running `op journal write "<text>" --kind felt`
from an *ordinary* chat session records the full private-journal entry in **that session's**
transcript as the Bash `tool_use` input — and again in the paired `tool_result` where the wrapper
echoes it back. The record carries no marker and no `.metis` path, so nothing a path filter or a
marker filter can see. CCDash ingests transcripts into `session_messages` and its lexical FTS, so
those entries became **searchable here**. Measured 2026-09-07: **208 rows across 59 sessions**.

That is not a policy nit. Journal egress is absolute — never a pack, PR, corpus, or index — and
the journal has no lock by design, because Nick vowed not to read it. A searchable index of it is
a trap for that vow.

## What is enforced now

| Where | What | File |
|---|---|---|
| **Raw records — the choke point** | Whole records dropped before anything reads them | `backend/parsers/platforms/claude_code/parser.py` (`parse_session_file`) |
| **Last gate before `session_messages`** | Parsed logs filtered before projection | `backend/services/session_transcript_projection.py` |
| **File ingest path** | Logs filtered before both the canonical and legacy writes | `backend/ingestion/session_ingest_service.py` |
| **Remote `POST /api/v1/ingest/sessions`** | Logs filtered on payloads this process never parsed | `backend/application/services/ingest/session_ingest.py` |
| Integration + reshaping | The only module that calls the predicate | `backend/services/transcript_egress.py` |
| The predicate itself (**vendored, do not edit**) | Five rules, fails closed | `backend/services/transcript_filter.py` |

`parse_session_file` is the single choke point for the two live write paths — the laptop
`worker-watch` sync engine and the node's `ccdash-ingest-daemon` (`ccdash-cli daemon`, which
imports `backend.parsers.sessions`). The other three are backstops for the case the choke point
structurally cannot cover: a **remote client running older code** POSTs an already-parsed
`AgentSession`, whose logs never passed through this process as records.

### The five rules

`metis_cwd` · `journal_marker` · `journal_command` · `journal_command_result` · `journal_entry_id`.
None is redundant; the rationale for each is in the vendored module's own docstring. Two properties
worth knowing before changing anything:

- **Fails closed at whole-record granularity.** A match drops the entire record, never one
  fragment — journal text arrives as ordinary prose and ordinary tool arguments, so partial
  redaction would leave the entry minus a phrase.
- **Taint is registered before the verdict.** A `tool_result` names its `tool_use` only by
  `tool_use_id`, in a *different* JSONL record. If the first matching rule short-circuited before
  tainting, the echo — carrying the same text — would survive.

There is **no opt-out flag**. A switch to disable this is a switch to re-open the egress.

## The resume boundary

Upstream warns that an incremental reader resuming mid-file starts with an empty taint set, so a
`tool_result` echo arriving after the resume point survives on nothing but coincidence.

**CCDash has no mid-file resume.** `parse_session_file` reads the whole file (`read_text()`) and
re-parses from record 0 on every scan; the CLI daemon compares mtimes rather than byte offsets,
and its WAL buffers already-built *events*, not read positions. So a fresh `TranscriptFilter`
always sees the complete record sequence. `filter_transcript_records` accepts a `prime_prefix`
anyway, so that adding an incremental reader later is a deliberate wiring step rather than a
silent regression.

Where the boundary *is* real is the parsed-log backstop: a projected log list has lost the record
framing, and the `tool_use`/`tool_result` pairing survives only as `toolCall.id` /
`relatedToolCallId`. `transcript_egress.log_to_record` rebuilds exactly that pairing and feeds it
through the same `TranscriptFilter`, rather than reimplementing any rule against a second shape.

## `sessions.cwd` — read this before trusting a `metis_cwd = 0`

`sessions.cwd` is populated on only **~15%** of CCDash sessions (4,616 of 29,961 at time of
writing). The acceptance criterion offered "populate it, or document the rule as unenforceable".
Neither is quite the truth, so here is the accurate statement:

- **At ingest time the rule is fully enforced, and does not use that column.** Every JSONL record
  carries its own `cwd`, and `parse_session_file` reads it per record. A `~/.metis` session
  abandons the **whole** transcript (`parse_session_file` returns `None`) — it is a journal
  session, so filtering it record-by-record would keep the rest of it. Note the transcript *path*
  is no help: Claude Code stores every transcript under `~/.claude/projects` regardless of where
  the session ran, and `~/.metis/journal` slugs to `-Users-miethe--metis-journal`.
- **Retrospectively, over rows already stored, the rule is unenforceable** — there is no record to
  re-read, only the sparse column. So `metis_cwd = 0` in the enumeration below is **UNMEASURED,
  never clean.**

Populating `sessions.cwd` for Claude Code sessions was deliberately **not** done in this change:
the column feeds cwd→project attribution, and changing what it contains is a behavioural change
outside this node's scope. It remains an open gap for retrospective counting only.

## Re-counting what is already indexed

```bash
python scripts/journal_egress_enumerate.py --print-sql \
  | ssh agentic-nuc 'podman exec -i ccdash_postgres_1 psql -U ccdash -d ccdash'
```

Read-only, counts only, ~3m20s over ~1.5M rows. **Removal of these rows is Mode-D — Nick's
decision.** The script has no `--delete` flag on purpose.

⚠️ **The instrument trap.** The haystack must be `content || metadata_json`. A first pass scanned
`content` alone and returned **10** — a false clean, because `session_messages.content` averages
11 characters on Bash tool rows (421,313 of them, *zero* carrying a recognizable shell command)
while the tool input lives in `metadata_json` (avg 3,979 chars). The corrected haystack found 20x
as much. Do not "simplify" the query.

| Measurement | Rows | Sessions |
|---|---|---|
| Baseline, 2026-09-07, before the predicate | 208 | 59 |
| Re-count later the same evening, still pre-deploy | **231** | **61** |

The +23 in about an hour is the point: this is a **live lane**, not a closed set. It stops growing
only once the fix is *deployed and the daemons restarted* — merging it changes nothing by itself.

## Deployment — two daemons, both need a restart (neither is done by an agent)

| Daemon | Where | Runs | Restart |
|---|---|---|---|
| `com.ccdash.stream-worker` | **laptop**, launchd | `python -m backend.worker` from `$CCDASH_REPO` | `deploy/local-streaming/ccdash-stream.sh restart` after a `git pull` in that checkout |
| `ccdash-ingest-daemon.service` | **node** (`rocket-fedora`), systemd user unit | `backend/.venv/bin/ccdash-cli daemon start` from `/home/miethe/dev/CCDash` | `git pull` in that checkout, then `systemctl --user restart ccdash-ingest-daemon` |

Both import the patched `parse_session_file`, so both are fixed by this change — **and both keep
running the old code until someone updates their checkout and restarts them.** Configured is not
enforced, and merged is not deployed.

## Changing a rule

Fix it **upstream** in `agentic_meta_dev/scripts/aos_transcript_filter.py` and re-vendor into
`backend/services/transcript_filter.py`, updating the sha256 in its header. A local edit is drift
with a head start, and `backend/tests/test_transcript_egress_predicate.py::VendoredCopyIntegrity`
fails the build if the body no longer hashes to the sha the header claims. CHCW vendored the same
bytes at the same sha (`chcw` `main` `18c5c4e`).

## Tests

`backend/tests/test_transcript_egress_predicate.py` — positive controls for all five rules across
all three shapes, using the fake sentinel `PLANTED-TEST-ENTRY` (no real journal text is in this
repo, and none may be added). Each control was mutation-verified: with the filter stubbed to a
no-op, 7 of them fail. A negative control asserts an ordinary transcript is untouched, so a filter
that simply drops everything cannot pass.
