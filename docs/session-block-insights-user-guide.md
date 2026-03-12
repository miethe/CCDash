# Session Block Insights User Guide

Last updated: 2026-03-12

Session Block Insights adds optional burn-rate and billing-block views to `Session Inspector > Analytics` for longer Claude Code sessions.

## What it shows

- rolling blocks based on the main session start time
- per-block observed workload totals
- per-block display-cost totals
- token burn rate and cost burn rate
- projected end-of-block totals for the latest active or partial block

These views are additive only. They do not change the canonical `Observed Workload`, `Current Context`, or `Display Cost` values shown elsewhere in CCDash.

## Where to enable it

Use `Settings > Projects > SkillMeat Integration > Session Block Insights`.

If the global rollout gate is disabled, the toggle remains ineffective until the backend is restarted with:

```bash
CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED=true
```

## How to use it

1. Open a Claude Code session in `Session Inspector`.
2. Switch to the `Analytics` tab.
3. Use the `1h`, `3h`, `5h`, or `8h` buttons to change the block window.
4. Read the latest block summary for:
   - block workload
   - token burn rate
   - cost burn rate
   - projected end-of-block totals
5. Use the chart and recent-block cards to compare earlier blocks against the latest one.

## Interpretation notes

- `Observed workload` follows the same semantics used elsewhere in CCDash:
  - model input
  - model output
  - cache creation input
  - cache read input
- block analytics use the main session only, not linked subthreads
- short sessions show a notice instead of forcing a misleading block breakdown

## Data availability

CCDash prefers persisted `usageEvents` when they are available. If those are missing, it falls back to transcript message usage metadata.

If neither source is present, Session Inspector shows a data-availability notice instead of synthetic values.
