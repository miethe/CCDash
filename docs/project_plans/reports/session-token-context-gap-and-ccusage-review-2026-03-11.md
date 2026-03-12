---
schema_name: ccdash_document
schema_version: 3
doc_type: report
doc_subtype: analysis
status: active
category: data
title: "Session Token Context Gap And ccusage Review"
description: "Current CCDash token/workload data availability, the gap between workload and live context metrics, and reuse candidates from ccusage for deeper token and cost insights."
summary: "Confirms that CCDash persists cache-aware workload families and attribution data, but does not persist live /context window tokens; reviews ccusage logic that could fill the gap."
created: 2026-03-11
updated: 2026-03-11
priority: high
risk_level: medium
report_kind: analysis
scope: session-token-usage-and-cost
owner: data-platform
owners: [data-platform, analytics, session-forensics]
contributors: [codex]
audience: [developers, platform-engineering, analytics]
tags: [report, sessions, tokens, context, cost, claude-code, ccusage]
related_documents:
  - docs/project_plans/reports/claude-code-session-schema-and-token-audit-2026-03-08.md
evidence:
  - backend/models.py
  - backend/routers/api.py
  - backend/parsers/platforms/claude_code/parser.py
  - backend/services/session_usage_analytics.py
  - lib/tokenMetrics.ts
  - /Users/miethe/dev/homelab/development/ccusage/apps/ccusage/src/data-loader.ts
  - /Users/miethe/dev/homelab/development/ccusage/apps/ccusage/src/calculate-cost.ts
  - /Users/miethe/dev/homelab/development/ccusage/apps/ccusage/src/_pricing-fetcher.ts
  - /Users/miethe/dev/homelab/development/ccusage/apps/ccusage/src/_session-blocks.ts
recommendations:
  - Add a first-class live context metric separate from session workload, sourced from Claude hook `context_window` when available and transcript fallback otherwise.
  - Expose cache creation and cache read as separate UI metrics instead of only showing aggregate cache input.
  - Add explicit cost semantics: reported cost, recalculated cost, and confidence/calibration status.
  - Add pricing validation and mismatch audit workflows before changing default cost semantics.
  - Consider a billing-block or burn-rate view for long Claude Code sessions.
---

# Session Token Context Gap And ccusage Review

## Executive Summary

CCDash already captures substantially more token data than the current Forensics card implies. The current system persists model I/O, cache creation, cache read, aggregate cache input, observed workload, tool-reported totals, tool-result usage totals, and event-level attribution overlays.

The main gap is not absence of workload data. The main gap is that CCDash does not currently persist or present a live context-window metric equivalent to Claude Code `/context`. As a result, a user-observed `/context` value such as `91k` tokens will not reconcile with the Forensics `Workload` value of `4,044,790`, because those numbers represent different things.

The `ccusage` project contains directly reusable logic for:

1. live context estimation from transcript or hook payloads
2. context-window percentage calculation using model limits
3. cost-mode separation between reported cost and recalculated cost
4. pricing mismatch validation against raw `costUSD`
5. session block and burn-rate modeling

## Session Evidence

Reviewed session: `S-883b7028-5748-49b3-a6f5-0bd478f643a7`

Persisted session row values:

- `tokens_in`: `74`
- `tokens_out`: `10,463`
- `model_io_tokens`: `10,537`
- `cache_creation_input_tokens`: `221,894`
- `cache_read_input_tokens`: `3,812,359`
- `cache_input_tokens`: `4,034,327`
- `observed_tokens`: `4,044,790`
- `tool_reported_tokens`: `280,112`
- `tool_result_input_tokens`: `10`
- `tool_result_output_tokens`: `4,284`
- `tool_result_cache_creation_input_tokens`: `7,651`
- `tool_result_cache_read_input_tokens`: `268,167`

For this session, the Forensics `Workload` value is expected to show `4,044,790`, because the frontend resolves workload from `observedTokens` first.

This session also contains additional usage detail in `sessionForensics.usageSummary`, including:

- `messageTotals.allInputTokens`: `4,034,327`
- `messageTotals.allTokens`: `4,044,790`
- `relayMirrorTotals.allInputTokens`: `4,106,907`
- `relayMirrorTotals.allTokens`: `4,107,836`
- `relayMirrorTotals.policy`: `excluded_from_observed_tokens_until_attribution`
- `toolResultReportedTotals.totalTokens`: `280,112`
- `toolResultUsageTotals.allTokens`: `280,112`

This confirms a second important nuance: CCDash is already capturing relay-mirror token families separately, but intentionally excludes them from `observedTokens` until attribution logic determines how they should be counted.

## What CCDash Captures Today

### Session-level token families

The current `AgentSession` model and API payloads expose:

- `tokensIn`
- `tokensOut`
- `modelIOTokens`
- `cacheCreationInputTokens`
- `cacheReadInputTokens`
- `cacheInputTokens`
- `observedTokens`
- `toolReportedTokens`
- `toolResultInputTokens`
- `toolResultOutputTokens`
- `toolResultCacheCreationInputTokens`
- `toolResultCacheReadInputTokens`
- `cacheShare`
- `outputShare`

These are first-class fields in the session model and API response shape.

### Parser-level usage summary

Claude Code parser output already preserves structured usage families under `sessionForensics.usageSummary`, including:

- message totals
- relay mirror totals
- cache creation tier totals
- service tier counts
- speed counts
- inference geo counts
- server tool use counts
- tool-result reported totals
- tool-result usage totals

This means CCDash is not limited to `tokensIn + tokensOut`; it already has richer token-family capture in the parser output.

### Event-level usage attribution

For sessions where attribution is enabled, CCDash also exposes:

- `usageEvents`
- `usageAttributions`
- `usageAttributionSummary`
- `usageAttributionCalibration`

For the reviewed session, current attribution-state evidence is:

- `89` usage events
- `947` attribution rows
- `49` attributed entities
- supporting coverage: `100%`
- primary coverage: `37.08%`

This is enough to power drill-downs and calibration analysis, but not enough to claim full exclusive attribution fidelity yet.

## What CCDash Does Not Capture Today

### 1. Live `/context` tokens

No current CCDash session field represents the live context window occupancy shown by Claude Code `/context`.

Not found as persisted first-class fields:

- current context tokens
- context window size
- context utilization percentage
- latest prompt-window occupancy snapshot

This is the clearest explanation for the user-facing mismatch between `91k` `/context` and `4.04M` workload.

### 2. Cache split in the main UI

CCDash captures both:

- cache creation input tokens
- cache read input tokens

But the current high-level Forensics UI compresses that into one displayed value:

- `Cache Input`

This is a display gap rather than a raw-data gap.

### 3. Cost confidence semantics

CCDash currently stores a single `totalCost` field and uses a rough parser-side estimate based only on model input/output pricing. The current estimate does not incorporate modern model metadata, cache pricing families, or explicit validation against reported costs.

### 4. Context window limits by model

CCDash does not currently expose:

- model context limit
- percent of context window consumed
- threshold-based context warnings

These are useful for understanding prompt pressure and are separate from total workload.

## Current CCDash Semantics

### Workload

Frontend workload resolution currently prefers:

1. `observedTokens`
2. `modelIOTokens + cacheInputTokens`
3. `toolReportedTokens`
4. `modelIOTokens`

This is the right semantic for total observed workload, but it should not be labeled or interpreted as current context occupancy.

### Cost

Current cost estimation inside the Claude parser is a rough fallback based on hardcoded model I/O rates and does not account for:

- cache creation pricing
- cache read pricing
- fast-mode multipliers
- dynamic model pricing tables
- provider-reported `costUSD` comparisons

## ccusage Review

### High-value logic to repurpose

### 1. Live context capture and fallback

`ccusage` has the most directly relevant missing logic in this area.

Strong candidate behaviors:

1. Prefer hook-provided `context_window.total_input_tokens` and `context_window.context_window_size` when available.
2. Fall back to transcript parsing by scanning backward to the latest assistant message with usage.
3. Define context as:
   `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`
4. Exclude output tokens from context occupancy.
5. Compute `percentage = inputTokens / contextLimit`, clamped to `0-100`.

This is exactly the missing semantic CCDash needs if it wants to show a live context card alongside workload.

### 2. Dynamic pricing and cost modes

`ccusage` separates cost behavior into three modes:

1. `display`: trust reported `costUSD`
2. `calculate`: recompute from pricing tables
3. `auto`: prefer reported cost, otherwise calculate

This is a better contract than the current CCDash single-cost model because it preserves provenance and lets the UI explain whether a cost is reported, estimated, or recalculated.

### 3. Pricing mismatch audit

`ccusage` includes a mismatch-debug path that compares reported `costUSD` against recalculated cost from pricing tables and records discrepancy rates by model and version.

This is useful for CCDash because it would let us:

1. validate parser cost assumptions against real Claude data
2. flag model/version pricing drift
3. present a confidence indicator on estimated cost

### 4. Message-level deduplication

`ccusage` deduplicates entries using `message.id + requestId`, processed in chronological file order.

This logic may be useful in CCDash for:

1. ingestion backfills across overlapping corpora
2. avoiding duplicate accounting when the same message appears in multiple file sets
3. validating relay or mirror handling

This should be adapted carefully, because CCDash already has explicit relay-mirror handling and linked subthread semantics.

### 5. Billing/session blocks and burn-rate views

`ccusage` groups entries into configurable session blocks, defaulting to a `5` hour billing period, and computes burn rate and projected usage.

This is not required for core correctness, but it is a strong candidate for higher-order insights:

- spend burn rate
- token burn rate
- active billing block cost
- projected end-of-block cost

### 6. Usage limit reset extraction

`ccusage` extracts usage limit reset time from specific API error content. This could become an operational signal in CCDash if we want session-level or timeline-level visibility into hitting Claude usage limits.

## Lower-value or non-portable pieces

These parts are less directly reusable inside CCDash:

- `ccusage` CLI-oriented directory discovery and globbing
- report aggregation formats built for terminal usage
- app-specific statusline cache/semaphore logic
- most of `calculate-cost.ts`, which is mainly a thin token-total aggregation wrapper around already-separated token families

The useful part is the semantic logic, not the surrounding CLI implementation.

## Implications For CCDash

### Correctness implications

1. CCDash should continue to treat workload and context as different metrics.
2. CCDash should not redefine `observedTokens` to mean live context.
3. Cost calculations should not continue to rely solely on rough parser estimates if deeper cost fidelity is a goal.

### UX implications

Recommended top-level token display model:

1. `Current Context`
   - live prompt-window occupancy
   - tokens and percent of model context limit
2. `Observed Workload`
   - accumulated session workload
   - model I/O plus cache input families
3. `Cache Input`
   - broken into creation and read
4. `Cost`
   - show provenance: reported, recalculated, or estimated

### Data-model implications

If CCDash adopts the `ccusage` logic, it likely needs new persisted fields such as:

- `current_context_tokens`
- `context_window_size`
- `context_utilization_pct`
- `cost_mode`
- `reported_cost_usd`
- `recalculated_cost_usd`
- `cost_confidence`
- `cost_mismatch_pct`

These should remain distinct from `observedTokens`.

## Recommended Next Steps

### Priority 1

Add a first-class context metric to session forensics, sourced from:

1. Claude hook `context_window` if present
2. transcript fallback if absent

### Priority 2

Expose the existing cache split in the UI:

- cache creation
- cache read
- aggregate cache input

### Priority 3

Replace the rough parser-only cost estimate with explicit cost provenance:

- reported cost
- recalculated cost
- estimated fallback cost

### Priority 4

Add a calibration report or admin/debug view for pricing mismatches by:

- model
- model version
- Claude Code version

### Priority 5

Consider importing billing-block and burn-rate logic after the core context and cost semantics are corrected.

## Bottom Line

CCDash already has rich workload token capture. The missing piece is not cache-awareness; it is context-awareness.

The `ccusage` codebase provides directly relevant logic for:

1. live context-window metrics
2. dynamic cost calculation
3. cost provenance and validation
4. operational usage insights

The most valuable repurpose path is to add a separate context metric rather than trying to force workload totals to correlate with `/context`.
