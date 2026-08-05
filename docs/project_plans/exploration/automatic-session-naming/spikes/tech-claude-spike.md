---
schema_version: 2
doc_type: spike
title: "Claude Code Session Naming — Availability Spike"
status: completed
created: 2026-08-04
feature_slug: automatic-session-naming
leg_id: tech-claude
confidence: 0.9
feasibility: feasible
---

# Claude Code Session Naming — Availability Spike

**Recovery note**: the delegated agent for this leg terminated on an API timeout before writing
output. The leg was re-run as a direct scripted measurement by the orchestrator. Every number below
is a full-corpus count (no sampling) over **7,531** session JSONL files under
`~/.claude/projects/**/*.jsonl`. Probe scripts were written to `/tmp` and are reproducible from the
Method section.

---

## Verdict for this leg

**Claude Code persists an auto-generated, human-meaningful session name on disk, inside the session
JSONL that CCDash already parses, and it is safely self-attributed.** The hypothesised mechanism
(a compaction `summary` record) does **not** exist in this corpus. The real mechanism is a
dedicated `ai-title` record type.

---

## Method

Four scripted passes over the full corpus:

1. `cc_name_probe.py` — enumerate all record `type` values; count name-ish top-level keys per type;
   count `summary`-typed records and test whether `leafUuid` resolves within the same file.
2. `cc_aititle.py` — `ai-title` per-file coverage, record shape, records-per-file, relative position
   in file, and value-change detection across repeated records.
3. `cc_decisive.py` — attribution test (`ai-title.sessionId` vs containing filename) and coverage
   bucketed by file mtime week.
4. `cc_split.py` — coverage split by `isSidechain` (subagent vs top-level) and by file size.

Store inventory: `~/.claude/__store.db` **does not exist**. `~/.claude/history.jsonl` exists (6.9 MB)
but was not the naming source — the name is in the per-session JSONL.

---

## Findings

### 1. Location and exact shape

The record is a top-level line in the session JSONL:

```json
{"type": "ai-title", "aiTitle": "phase-6 validation corpus squash", "sessionId": "c783f44a-…"}
```

Exactly three keys, present on all 12,746 occurrences: `type`, `aiTitle`, `sessionId`. No nesting,
no schema variance. Sample values are short, lowercase, task-descriptive phrases — precisely the
label a human would want in place of a UUID.

**The hypothesised `summary` record does not exist**: `files_with_>=1_summary_record: 0 (0.00%)`
across all 7,531 files. The charter's compaction-summary theory is refuted. Related record types
that do exist and were checked: `last-prompt` (25.51% of files), `agent-name` (4.34%),
`frame-link::title` (4 occurrences, unrelated). The `slug` key on `assistant`/`user` records is a
model slug, not a session name.

### 2. Coverage — the headline number is a denominator artifact

All-files coverage is **850/7,531 = 11.29%**, which looks disqualifying. Segmenting explains it
completely:

| Segment | Files | With `ai-title` | Coverage |
|---|---:|---:|---:|
| Subagent (`isSidechain`) — **all sizes** | 5,462 | 0 | **0.0%** |
| Top-level | 2,069 | 850 | **41.1%** |
| Top-level, large (500+ lines) | 288 | 251 | **87.2%** |
| Top-level, medium (50–500 lines) | 1,033 | 381 | 36.9% |
| Top-level, small (<50 lines) | 748 | 218 | 29.1% |

**Subagent sessions are never titled — 0 of 5,462, at every size band** — and they are 72.5% of the
corpus. This is not a gap; subagent sessions have their own identity mechanism (`agent-name`) and do
not want a human-facing title. Excluding them, coverage on substantive top-level sessions is
**87.2%**.

This mirrors the `tech-codex` leg exactly: `codex_vscode` 72.4% vs `codex_exec` headless 0.0%. Both
providers title interactive/substantive work and skip automation. The pattern is consistent and
explainable, not a defect in either provider.

### 3. Timing — mid-session, not at open

Mean relative position in file **0.577**, median **0.600** (min 0.000, max 0.999). The title is
written after the session has accumulated real content, not at session open. Records are
re-emitted continuously: mean **15.0** `ai-title` records per file, median 8, max 150.

**Ingest consequence**: a session that is currently live may not have a title yet. `session_name`
must be nullable and populated on re-sync, not treated as available at first-parse. This is the
normal CCDash watcher/re-sync path, not new machinery.

### 4. Mutability — stable in practice

Of 800 files carrying more than one `ai-title` record, only **17 (2.1%)** ever changed the value.
The other 783 re-emit an identical title. So the repeated records are idempotent re-emission, and
last-write-wins is a safe and near-free ingest rule.

### 5. Attribution — clean, verified

| Test | Result |
|---|---:|
| `ai-title.sessionId` **matches** containing filename | **12,746** |
| `ai-title.sessionId` points at a **different** session | **1** |

The single exception is `0eac19af-….orphaned-1785631141454-be039dde.jsonl`, whose base session ID
*does* match the record — a filename-suffix artifact of orphan recovery, not a cross-session
pointer.

**This refutes the charter's primary attribution risk.** Unlike a compaction summary (which would
describe a pre-compaction ancestor), `ai-title` is self-referential. Ingest can trust the record in
the file it appears in. A parser should still assert `sessionId == <file's session id>` and skip on
mismatch, to stay safe against the orphan-suffix case and any future change.

### 6. Coverage is not a ramp

Bucketed by file mtime week, `ai-title` first appears in 2026-W26 and then oscillates rather than
climbing: W26 3.0% → W27 8.1% → W28 20.6% → W29 6.8% → W30 12.4% → W31 13.0% (all-files
denominator). So the feature is recent but its all-files rate is at steady state; do not expect the
11% figure to grow on its own. The segmented 87.2% figure is the one that matters.

---

## No-Name Fallback Options (all zero-model-call)

For the ~13% of top-level-large and larger share of small sessions with no `ai-title`:

| Rank | Source | Coverage (all files) | Notes |
|---|---|---:|---|
| 1 | `ai-title.aiTitle` | 11.3% all / **87.2%** top-level-large | Provider-generated; highest trust |
| 2 | `agent-name` record | 4.34% | Correct label for subagent sessions specifically |
| 3 | `last-prompt` record | 25.51% | Deterministic, already in the JSONL |
| 4 | First user message, truncated | ~100% | Current de facto behaviour |

This is a provenance-tagged chain, not a single source — which is exactly what the `integration`
leg's recommended `session_name_source` column exists to distinguish.

---

## Open Questions

- **OQ-C1**: What triggers `ai-title` generation? Coverage rises steeply with session size (29.1% →
  36.9% → 87.2%), suggesting a turn-count or content threshold, but the trigger was not identified
  from on-disk data alone. Does not block implementation — it only bounds the expected coverage
  ceiling.
- **OQ-C2**: Is `ai-title` operator-influenceable (a rename affordance) or purely model-generated?
  Not determinable from the record shape. Affects whether `operator_set` provenance is reachable
  today or stays reserved.
- **OQ-C3**: Should subagent sessions inherit the parent's `ai-title`, use their own `agent-name`,
  or stay null? A product decision for the PRD. Note CCDash already has one-hop subagent inheritance
  machinery from `skill_name_source` (`2cb0df4`) if inheritance is wanted.

---

## Confidence Rationale

**0.9.** Every claim is a full-corpus count over 7,531 real files, with the two decisive risks
(attribution, coverage denominator) directly tested rather than reasoned about. Confidence is not
1.0 because OQ-C1 leaves the coverage *ceiling* unexplained — the trigger is inferred from a size
correlation, not observed — and because a mid-session write time means live-session behaviour was
characterised statistically rather than by watching a session get titled in real time.
</content>
