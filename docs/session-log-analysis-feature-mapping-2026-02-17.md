# Session Log Analysis: Feature Mapping + Session Metadata

Date: 2026-02-17
Project analyzed: SkillMeat
Session log source: `/Users/miethe/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat`

## Scope
This analysis used real SkillMeat session logs (root session logs and subagent logs) to identify robust patterns for:

1. Linking Sessions to Features with confidence scoring.
2. Extracting additional metadata (commits, PRs, summaries, command/task details).
3. Improving session naming (descriptive titles) from command arguments and log outcomes.

## Dataset Snapshot
- JSONL files analyzed: 2,081
- Root session logs: 465
- Subagent logs: 1,616
- Non-empty files: 2,080
- Total parsed entries: 228,016
- Timestamp range: 2025-12-22T19:33:30.755Z to 2026-02-17T00:15:37.313Z

## High-Value Findings (Strong Signal)

### 1) Feature linkage can be highly reliable when path and command signals are combined
Root sessions with any feature slug/path signal: 251/465.

Among sessions with slug signals:
- Clear majority candidate (>=50% of slug evidence): 227 sessions
- Strong majority candidate (>=70%): 180 sessions

Implication:
- In most feature-related sessions, one feature candidate dominates the evidence.
- Ambiguous multi-feature sessions do exist and need confidence downgrade logic.

### 2) `dev:execute-phase` is a high-confidence feature-link source
Observed: 98 `dev:execute-phase` commands.

Argument structure:
- Single phase token (`0`, `1`, `2`, `all`): 73
- Range with dash (`1-3`): 19
- Range with ampersand (`1 & 2`): 6

Current parser-style extraction that expects single phase misses range formats. This is fixable and materially improves mapping and naming.

Additional behavioral signals in these sessions:
- `read_plan`: 84/97 actionable sessions
- `read_progress`: 69/97
- `write_progress`: 49/97
- `bash_git`: 88/97
- `bash_test`: 74/97

Implication:
- `dev:execute-phase` sessions are usually implementation-heavy and tightly feature-bound.
- Parsing range phases should be treated as first-class.

### 3) `dev:quick-feature` and `plan:plan-feature` are useful but heterogeneous
`dev:quick-feature` (103 total; 99 actionable in sequence analysis):
- Freeform args: 84
- Args containing md path: 15
- Args starting with path: 3
- Args starting with REQ id: 1
- Sessions writing quick-feature progress docs: 60/99

`plan:plan-feature` (35 total; 31 actionable in sequence analysis):
- Args starting with path: 13
- Args starting with REQ id: 10
- Freeform: 7
- Path present later in arg text: 5

Implication:
- `quick-feature` needs multi-stage inference (command + first progress write + plan/doc writes).
- `plan-feature` should parse first path/REQ when available; fallback to generated plan/report writes.

### 4) Important metadata types exist in logs but are not fully exploited
Rare but valuable entry types found:
- `summary`: present in 226/465 root sessions (1,505 entries total)
- `pr-link`: present in 14 root sessions
- `custom-title`: present in 1 root session
- `agent-setting`: present in 2 root sessions
- `queue-operation` with task notifications: 24 sessions

Implication:
- Session naming and entity linking can leverage these directly (especially `summary` and `pr-link`).

### 5) Bash output is available in `progress.bash_progress` and linked to tool calls
Observed:
- `bash_progress` entries: 14,020
- Non-empty outputs: 2,187
- `parentToolUseID` links to originating tool call id in essentially all cases.

Current parser behavior does not fully exploit this correlation for transcript enrichment and commit/test/lint result extraction in this log format.

Implication:
- You can recover richer Bash metadata (and some commit ids) by joining `bash_progress.parentToolUseID` to `assistant.tool_use.id`.

## Feature Mapping: Proposed Confidence Model

### Candidate feature extraction sources
1. Command args feature path (implementation plan path) or progress path slug.
2. Tool input/output file refs (Read/Write/Edit/Grep/Glob/Bash).
3. Subagent evidence (subagent file refs linked to root session).
4. Existing task/session frontmatter links (if present).

### Suggested confidence buckets
- 1.00 `definitive`
  - Explicit task/session frontmatter link or exact `dev:execute-phase` parse with single feature plan path and supporting writes.
- 0.90 `very_high`
  - Explicit command with parseable feature slug (`dev:execute-phase`, `plan:plan-feature` with canonical path) and consistent tool evidence.
- 0.75 `high`
  - No explicit command slug, but dominant file evidence (majority >=70%) with write/read consistency.
- 0.55 `medium`
  - Dominant evidence >=50%, but multiple competing feature slugs.
- 0.35 `low`
  - Weak/indirect references only, or conflicting evidence.

### Confidence penalties (important)
- Multiple feature candidates near tie (top candidate <50% share).
- References appear only as reads with no writes/progress updates.
- Wildcard/template-like paths (`*`, placeholders, malformed slug captures).

## Session Naming Strategy (Descriptive Titles)

### Goal
Generate stable, human-readable session titles without manual naming.

### Priority title sources
1. `custom-title` entry if present.
2. Latest `summary` entry for the root session.
3. Command-derived title template.
4. Fallback to feature candidate + action.
5. Final fallback: first user message snippet.

### Command-specific title templates
- `dev:execute-phase`
  - `Execute Phase {phase} - {feature_slug}`
  - Also support range phase tokens (`1-3`, `1 & 2`).
- `dev:quick-feature`
  - Prefer first progress write slug: `Quick Feature - {progress_slug}`
  - Fallback to referenced plan/doc basename or REQ id.
- `plan:plan-feature`
  - `Plan Feature - {basename_or_req}`
- `fix:debug`
  - `Debug - {feature/doc basename}` or controlled snippet.

### Measured coverage of title heuristics on actionable sessions
Actionable sessions tested (`dev:execute-phase`, `dev:quick-feature`, `plan:plan-feature`, `fix:debug`): 289

Heuristic confidence outcomes:
- High: 143
- Medium: 54
- Low: 92

Breakdown highlights:
- `dev:execute-phase`: high 86/97
- `dev:quick-feature`: high 53/99 (mostly from quick-feature progress writes)
- `plan:plan-feature`: medium/high 25/29
- `fix:debug`: mostly low/medium due freeform input

Implication:
- A command-aware naming system is immediately useful.
- Biggest improvement opportunity is freeform `quick-feature` and `fix:debug` naming.

## Additional Metadata Worth Capturing

### Obvious high-value adds
- PR metadata from `pr-link` entries.
  - `prNumber`, `prUrl`, `prRepository` on session and roll up to linked features.
- Session summary trail from `summary` entries.
  - Keep latest summary as display title candidate.
  - Optionally keep full summary timeline for audit/history.
- Task notification metadata from `queue-operation` content.
  - Parse `<task-id>`, `<status>`, `<summary>`.
  - Useful for subthread outcomes and partial failure signals.
- Bash execution details from `progress.bash_progress` joined to tool call.
  - Command, elapsed time, output line count, output digest, category (`git/test/lint/build/deploy`).

### High-value but requires validation
- Use `slug` field (ephemeral codename) as optional breadcrumb for sub-session continuity.
- Use command pair patterns (for example `clear -> dev:execute-phase`) to improve session intent classification.
- Infer “primary vs secondary linkage” from write intensity + progress writes + subagent task completion density.
- Infer session health score from repeated failed task notifications and repeated debug command loops.

## Parsing Improvements Suggested (Concrete)

### `dev:execute-phase` parsing
Support these phase tokens:
- single: `0`, `1`, `all`
- ranges: `1-3`, `1 & 2`

Then parse:
- primary implementation plan path
- optional phase progress doc paths
- optional additional notes/handoff text

### Path normalization before feature extraction
Normalize and reject noisy captures:
- Trim punctuation and markdown artifacts
- Reject wildcard/path templates (`*`, `${...}`, placeholders)
- Canonicalize `-v1` suffix variants (store canonical + raw)

### Bash/tool output linkage
Join `progress.data.type == bash_progress` via:
- `progress.parentToolUseID` -> `assistant.tool_use.id`

Then capture:
- command category (`git`, `test`, `lint`, `build`, `deploy`, `other`)
- duration and output stats (`elapsedTimeSeconds`, `totalLines`)
- parse pass/fail and notable output markers
- parse commit hashes when present

## Suggested Implementation Order
1. Extend command argument parser for `dev:execute-phase` ranges.
2. Add robust path normalization and slug canonicalization.
3. Add `summary`, `pr-link`, `custom-title`, `queue-operation` ingestion.
4. Add `bash_progress` join and command-result metadata extraction.
5. Introduce confidence scoring with ambiguity penalties.
6. Enable derived session title generation with source attribution (`titleSource`, `titleConfidence`).

## Notes on Data Quality / Caveats
- Not all sessions are feature-work sessions (214/465 root sessions had no feature slug signal).
- Freeform command args are common, especially for `dev:quick-feature` and `fix:debug`.
- Some logs contain malformed or placeholder path artifacts; normalization is required.
- Commit hash extraction from command results is sparse unless output contains explicit hashes.
