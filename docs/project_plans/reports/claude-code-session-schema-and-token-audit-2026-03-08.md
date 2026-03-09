---
doc_type: report
status: active
category: data
title: "Claude Code Session Schema And Token Audit"
description: "Recursive schema inventory for Claude Code sessions, current mapping coverage, and token accounting recommendations."
author: codex
created: 2026-03-08
updated: 2026-03-08
tags: [sessions, claude-code, schema, tokens, analytics, forensics]
---

# Claude Code Session Schema And Token Audit (2026-03-08)

## Scope

This audit adds a repeatable schema inventory step and compares the detected Claude Code session schema against current CCDash parsing and analytics behavior.

- Inventory script added: `backend/scripts/claude_session_schema_inventory.py`
- NPM entry added: `npm run discover:claude-schema -- <paths...>`
- Primary corpus scan command used for this report:

```bash
python3 backend/scripts/claude_session_schema_inventory.py \
  examples/skillmeat/claude-sessions/-Users-miethe-dev-homelab-development-skillmeat \
  --max-files 25 \
  --max-examples 4 \
  --write /tmp/claude-session-schema-inventory-25.json
```

## Sample Size

- Files scanned: `25`
- Entries scanned: `2,494`
- Distinct nested paths detected: `316`
- Parse errors: `0`

## Confidence Check

- Duplicate implementation check: pass. There was no existing recursive nested-path inventory tool.
- Architecture compliance: pass. The changes stay inside the current parser/script/report flow.
- Root cause clarity: pass. Session and analytics token totals currently use only `tokens_in + tokens_out`.
- External docs requirement: not needed for this audit. The schema source of truth is the observed Claude Code session corpus.

## Detected Schema Families

### 1. Message usage payloads

Observed under `$.message.usage.*` with `15` distinct nested paths in the sample.

Representative fields:

- `$.message.usage.input_tokens`
  - count: `728`
  - samples: `2`, `3`, `1`, `5`
- `$.message.usage.cache_creation_input_tokens`
  - count: `728`
  - samples: `21000`, `13253`, `4239`, `35634`
- `$.message.usage.cache_read_input_tokens`
  - count: `728`
  - samples: `19115`, `40115`, `53368`, `0`
- `$.message.usage.service_tier`
  - count: `728`
  - samples seen: `standard`
- `$.message.usage.inference_geo`
  - count: `728`
  - samples seen: `not_available`, empty string
- `$.message.usage.server_tool_use.web_search_requests`
  - count: `298`
  - sample: `0`
- `$.message.usage.server_tool_use.web_fetch_requests`
  - count: `298`
  - sample: `0`
- `$.message.usage.speed`
  - count: `298`
  - sample: `standard`
- `$.message.usage.iterations`
  - count: `298`
  - sample shape: array

### 2. Stop and caller flags

- `$.message.stop_reason`
  - count: `728`
  - samples: `null`, `tool_use`, `end_turn`
- `$.message.stop_sequence`
  - count: `728`
  - sample: `null`
- `$.message.content[].caller`
  - count: `450`
  - sample: `{ "type": "direct" }`
- `$.message.content[].caller.type`
  - count: `450`
  - sample: `direct`

### 3. Tool result operational payloads

Observed under `$.toolUseResult.*` with `79` distinct nested paths in the sample.

Representative fields:

- `$.toolUseResult.status`
  - count: `12`
  - samples: `completed`, `async_launched`
- `$.toolUseResult.isAsync`
  - count: `3`
  - sample: `true`
- `$.toolUseResult.outputFile`
  - count: `3`
  - sample: `/private/tmp/claude-501/.../tasks/<id>.output`
- `$.toolUseResult.durationMs`
  - count: `12`
  - samples: `1990`, `1182`, `1283`, `1478`
- `$.toolUseResult.totalDurationMs`
  - count: `9`
  - samples: `98753`, `93438`, `196195`, `121255`
- `$.toolUseResult.totalToolUseCount`
  - count: `9`
  - samples: `54`, `44`, `26`, `28`
- `$.toolUseResult.totalTokens`
  - count: `9`
  - samples: `85728`, `73536`, `81836`, `92115`

### 4. Tool result usage payloads

Observed under `$.toolUseResult.usage.*` with `15` distinct nested paths in the sample.

Representative fields:

- `$.toolUseResult.usage.input_tokens`
- `$.toolUseResult.usage.output_tokens`
- `$.toolUseResult.usage.cache_creation_input_tokens`
- `$.toolUseResult.usage.cache_read_input_tokens`
- `$.toolUseResult.usage.server_tool_use.web_search_requests`
- `$.toolUseResult.usage.server_tool_use.web_fetch_requests`
- `$.toolUseResult.usage.service_tier`
- `$.toolUseResult.usage.inference_geo`
- `$.toolUseResult.usage.speed`
- `$.toolUseResult.usage.iterations`

Example values from the sample:

- `input_tokens`: `3`, `6`, `1`, `0`
- `cache_creation_input_tokens`: `1513`, `645`, `176`, `3460`
- `cache_read_input_tokens`: `80479`, `67445`, `80749`, `79484`
- `output_tokens`: `3733`, `5440`, `910`, `9171`

### 5. Embedded wrapped message mirrors

The corpus also contains a second message shape under `$.data.message.message.*`, including the same `usage`, `stop_reason`, `stop_sequence`, and `caller` families.

Observed in the 25-file sample:

- `$.data.message.message.usage.*`: `168` nested-path observations
- `$.data.message.message.content[].caller.type`: `168`

Observed in the wider local linked corpus:

- lines containing `data.message.message`: `45,069`
- files containing `data.message.message`: `233`

These appear to be wrapped relay records, usually inside `progress.data.message`.

## Current Mapping Status

### Already mapped and actively used

These fields already feed session rows and downstream analytics:

- `$.message.usage.input_tokens`
  - mapped to `session.tokensIn`
  - persisted to `sessions.tokens_in`
  - used by session APIs, feature summaries, analytics breakdowns/correlations, telemetry rollups
- `$.message.usage.output_tokens`
  - mapped to `session.tokensOut`
  - persisted to `sessions.tokens_out`
  - used by the same downstream paths
- `$.message.stop_reason`
  - stored on message log metadata as `stopReason`
  - aggregated into `sessionForensics.entryContext.messageStopReasonCounts`
- `$.toolUseResult.*` scalar fields
  - copied into related tool log metadata as `toolUseResult_<field>`
  - used opportunistically for task/subagent linking and Bash result enrichment

### Newly mapped in this patch

These fields are now parsed into normalized forensics payloads, but are not yet consumed by analytics endpoints:

- `$.message.usage.cache_creation_input_tokens`
- `$.message.usage.cache_read_input_tokens`
- `$.message.usage.cache_creation.ephemeral_5m_input_tokens`
- `$.message.usage.cache_creation.ephemeral_1h_input_tokens`
- `$.message.usage.service_tier`
- `$.message.usage.inference_geo`
- `$.message.usage.server_tool_use.*`
- `$.message.usage.speed`
- `$.message.usage.iterations`
- `$.message.stop_sequence`
- `$.message.content[].caller.type`
- `$.toolUseResult.totalTokens`
- `$.toolUseResult.totalDurationMs`
- `$.toolUseResult.totalToolUseCount`
- `$.toolUseResult.usage.*`

New parser outputs:

- `sessionForensics.usageSummary.messageTotals`
- `sessionForensics.usageSummary.cacheCreationTotals`
- `sessionForensics.usageSummary.serverToolUseTotals`
- `sessionForensics.usageSummary.toolResultReportedTotals`
- `sessionForensics.usageSummary.toolResultUsageTotals`
- `sessionForensics.entryContext.messageStopSequenceCounts`
- `sessionForensics.entryContext.toolCallerTypeCounts`
- structured tool log metadata:
  - `caller`
  - `callerType`

### Mapped but not fully normalized

These fields are detected and partially preserved, but still only as opaque log metadata rather than stable structured contracts:

- `$.toolUseResult.file.*`
- `$.toolUseResult.structuredPatch.*`
- `$.toolUseResult.originalFile`
- `$.toolUseResult.newString`
- `$.toolUseResult.oldString`
- `$.toolUseResult.replaceAll`
- `$.toolUseResult.userModified`
- `$.toolUseResult.content[]`

Current behavior:

- the parser copies many of these into `toolUseResult_<field>` metadata strings on the related tool log
- there is no dedicated session/table-level schema for these fields
- they are not queryable via analytics or facets

### Not yet mapped or policy-incomplete

- `$.data.message.message.*`
  - detected in large volume
  - not normalized into a dedicated relay/session model
  - not included in `usageSummary`
  - likely needs attribution policy before use because it may mirror subagent traffic
- `$.message.usage.iterations[]`
  - only the count is preserved
  - iteration payload details are not retained
- `$.toolUseResult.usage.server_tool_use.*`
  - aggregated only at session forensics level
  - not wired into analytics

## Token Accounting Findings

## Current Token Semantics In CCDash

Current session and analytics totals use only:

```text
message.usage.input_tokens + message.usage.output_tokens
```

They do **not** include:

- `cache_creation_input_tokens`
- `cache_read_input_tokens`
- nested `cache_creation.*`
- `toolUseResult.totalTokens`
- `toolUseResult.usage.*`

Primary code paths still using only `tokens_in + tokens_out`:

- `backend/parsers/platforms/claude_code/parser.py`
- `backend/db/repositories/sessions.py`
- `backend/db/repositories/postgres/sessions.py`
- `backend/db/sync_engine.py`
- `backend/routers/analytics.py`
- `backend/services/workflow_effectiveness.py`
- frontend rollups in `components/SessionInspector.tsx`, `components/FeatureExecutionWorkbench.tsx`, and `components/Analytics/AnalyticsDashboard.tsx`

## Concrete Example: Referenced Session File

From:

`examples/skillmeat/claude-sessions/-Users-miethe-dev-homelab-development-skillmeat/baa40f63-92aa-4a64-8ac0-8480f56c1553.jsonl`

Current parsed totals:

- `tokensIn`: `272`
- `tokensOut`: `19,720`
- `sessionTotalTokens`: `19,992`

New usage summary totals for the same parsed session:

- `usageSummary.messageTotals.cacheCreationInputTokens`: `281,609`
- `usageSummary.messageTotals.cacheReadInputTokens`: `7,215,459`
- `usageSummary.messageTotals.allInputTokens`: `7,497,340`
- `usageSummary.messageTotals.allTokens`: `7,517,060`
- `usageSummary.toolResultReportedTotals.totalTokens`: `417,829`

Implication:

- current CCDash "session tokens" undercount observed Claude session tokens by roughly `376x` on this file if the intended metric is total observed token load
- the gap is almost entirely cache-read volume, which is currently invisible to session, feature, and analytics totals

## Recommended Token Model

To avoid ambiguity, CCDash should track **multiple token metrics**, not one overloaded total:

### 1. Model IO Tokens

Definition:

```text
input_tokens + output_tokens
```

Use for:

- direct model completion cost estimates
- continuity with existing `tokensIn` / `tokensOut`

### 2. Cache Input Tokens

Definition:

```text
cache_creation_input_tokens + cache_read_input_tokens
```

Use for:

- measuring context pressure and cache dependence
- identifying sessions dominated by replayed context rather than fresh prompting

### 3. Observed Session Tokens

Definition:

```text
input_tokens + output_tokens + cache_creation_input_tokens + cache_read_input_tokens
```

Recommended use:

- default "total tokens" metric in session dashboards
- feature rollups when discussing total workload
- analytics correlations with latency and orchestration efficiency

### 4. Tool-Reported Subtask Tokens

Definition:

```text
toolUseResult.totalTokens
or
toolUseResult.usage allTokens
```

Recommended use:

- fallback when a subagent transcript is missing
- separate operational metric for Task/subagent work

Do **not** blindly add this to session observed tokens when linked subagent sessions are also parsed, or CCDash will double count.

### 5. Server Tool Request Counts

Definition:

```text
usage.server_tool_use.*
```

Use for:

- measuring retrieval/search pressure
- correlating web/tool activity with token burn

These are not token metrics and should stay separate.

## Recommended Aggregation Policy

### Session Views

- Keep `tokensIn` and `tokensOut` as the current model-IO fields for backward compatibility.
- Add a new derived session metric for `observedTokens`.
- Surface cache totals separately so users can tell whether high usage came from prompt growth or cache replay.

### Feature Views

- Root-only feature totals:
  - sum root-session `observedTokens`
- Full-thread feature totals:
  - sum root-session `observedTokens`
  - plus linked subagent session `observedTokens`
- Fallback rule:
  - only use `toolResultReportedTotals.totalTokens` when a linked subagent session is missing

### Analytics

- Replace current "totalTokens" rollups with:
  - `modelIOTokens`
  - `cacheInputTokens`
  - `observedTokens`
  - `toolReportedTokens`
- Add ratios:
  - `cacheShare = cacheInputTokens / observedTokens`
  - `outputShare = outputTokens / modelIOTokens`

## Implementation Completed In This Patch

- Added recursive inventory tool:
  - `backend/scripts/claude_session_schema_inventory.py`
- Added runnable alias:
  - `npm run discover:claude-schema`
- Extended Claude parser to emit:
  - `sessionForensics.usageSummary`
  - structured `caller` / `callerType`
  - `messageStopSequenceCounts`
  - `toolCallerTypeCounts`
- Added parser coverage in:
  - `backend/tests/test_sessions_parser.py`

## Next Recommended Work

1. Persist normalized usage summary fields as first-class session columns or a derived rollup table.
2. Backfill historical sessions so analytics stop depending on legacy `tokens_in + tokens_out` only.
3. Update analytics endpoints and frontend charts to default to `observedTokens`.
4. Decide attribution policy for `data.message.message.*` relay records before counting them anywhere.
5. Add a cache-efficiency panel:
   - model IO tokens
   - cache read tokens
   - cache creation tokens
   - cache share
