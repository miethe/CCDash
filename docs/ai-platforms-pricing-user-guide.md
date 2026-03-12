# AI Platforms Pricing Guide

## Overview

`Settings > AI Platforms` manages the global pricing catalog used for display-cost recalculation.

The catalog supports:

- platform defaults
- family defaults such as `Sonnet`, `Opus`, `Haiku`, and `Codex`
- detected exact-model rows synthesized from synced sessions across configured projects
- manual exact-model overrides

## Live Pricing Sync

CCDash can refresh pricing from live provider sources on demand.

Current provider coverage:

- `Claude Code`: Anthropic pricing documentation page
- `Codex`: OpenAI pricing documentation page

To refresh from the UI:

1. Open `Settings > AI Platforms`
2. Choose a platform
3. Click `Sync Provider Prices`

During sync, CCDash:

1. fetches the current provider pricing page with a browser-style user agent
2. parses exact model pricing rows when the provider page exposes them
3. updates global platform and family defaults
4. stores fetched exact-model references when available
5. keeps manual locked overrides in place

## Fallback Behavior

Live sync is best-effort, not required.

If the provider fetch fails or the page format changes:

- CCDash falls back to bundled pricing defaults
- existing manual overrides remain in effect
- cost recalculation continues to work from stored overrides or bundled values

This keeps pricing lookup offline-safe and prevents live-fetch failures from blocking analytics.

## Automating Refresh

CCDash does not currently run scheduled background pricing refresh by itself.

If you want automatic refresh, call the sync API on a schedule:

```bash
curl -X POST "http://localhost:8000/api/pricing/catalog/sync?platformType=Claude%20Code"
curl -X POST "http://localhost:8000/api/pricing/catalog/sync?platformType=Codex"
```

This is the same sync path used by the `Sync Provider Prices` button.

## Override Rules

- exact manual overrides take precedence over family defaults
- family defaults take precedence over platform defaults
- required platform and family defaults can be reset but not deleted
- manual exact-model overrides can be deleted
- detected rows are suggestions until you save them as exact overrides
