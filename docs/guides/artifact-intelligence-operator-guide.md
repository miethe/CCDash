---
title: Artifact Intelligence Operator Guide
description: Enablement, health checks, export tuning, and troubleshooting for CCDash artifact intelligence
audience: operators, developers
tags: [artifact-intelligence, skillmeat, operations]
created: 2026-05-07
updated: 2026-05-07
category: operations
status: active
related:
  - "../project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md"
  - "artifact-intelligence-privacy-audit.md"
---

# Artifact Intelligence Operator Guide

Artifact intelligence connects CCDash usage attribution with SkillMeat artifact snapshots. Operators use it to rank artifacts, surface advisory recommendations, and export aggregate rollups back to SkillMeat.

## Enablement

Enable the runtime feature flag before expecting snapshot fetches, ranking enrichment, recommendations, or rollup exports:

```bash
export CCDASH_ARTIFACT_INTELLIGENCE_ENABLED=true
```

Keep `CCDASH_SKILLMEAT_INTEGRATION_ENABLED=true` and enable SkillMeat for the project in Settings. The artifact intelligence flag is environment-managed; the Settings panel displays it but does not write it.

## Configuration

| Variable or setting | Default | Scope | Use |
| --- | --- | --- | --- |
| `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED` | `false` | API and worker env | Master gate for snapshot fetch, artifact rankings, recommendations, and rollup export. |
| `CCDASH_SKILLMEAT_INTEGRATION_ENABLED` | `true` | API and worker env | Global SkillMeat integration gate. Leave enabled when artifact intelligence is enabled. |
| Settings: SkillMeat `enabled` | `false` | Project setting | Allows the selected CCDash project to use its SkillMeat mapping. |
| Settings: SkillMeat `baseUrl` | empty | Project setting | SkillMeat API base URL used for project checks, snapshot fetches, and rollup posts. |
| Settings: SkillMeat `projectId` | empty | Project setting | Exact SkillMeat project ID used for snapshot fetches. Required. |
| Settings: SkillMeat `collectionId` | empty | Project setting | Optional SkillMeat collection ID. Leave blank for the default project snapshot. |
| Settings: SkillMeat `requestTimeoutSeconds` | `5` | Project setting | HTTP timeout for SkillMeat calls. Raise only for slow private networks. |
| Settings: SkillMeat `aaaEnabled` / `apiKey` | `false` / empty | Project setting | Enables bearer auth for protected SkillMeat instances. |
| `CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS` | `604800` | API and worker env | Settings health threshold for stale snapshots. |
| `CCDASH_IDENTITY_FUZZY_THRESHOLD` | `0.85` | API and worker env | Minimum fuzzy-match confidence for artifact identity resolution. |
| `CCDASH_ARTIFACT_ROLLUP_EXPORT_INTERVAL_SECONDS` | `3600` | Worker env | Scheduled rollup export interval. Values below 60 seconds are raised to 60. |
| `CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE` | `pseudonym` | Worker env | Local rollup user scope behavior. Use `pseudonym` or `omit`. |
| `CCDASH_LOCAL_USER_SCOPE_PSEUDONYM` | `local-user` | Worker env | Pseudonym emitted when local user scope mode is `pseudonym`. Do not use a real username or email. |

## SkillMeat Snapshot Setup

In Settings, open the project, then configure the SkillMeat section:

1. Turn on `Enable SkillMeat integration`.
2. Set `API Base URL`.
3. Set the exact `SkillMeat Project ID`.
4. Optionally set `Collection ID` if the snapshot should be limited to one SkillMeat collection.
5. Enable AAA and provide the API key only when the SkillMeat instance requires bearer auth.
6. Use `Check Connection`, then save the settings.

Snapshot health uses `CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS`. Recommendation-specific freshness thresholds are listed below; those thresholds control when CCDash suppresses state-changing advice and emits a stale-snapshot advisory instead.

## Rollup Export

Rollup export runs from the worker when artifact intelligence is enabled. Set:

```bash
export CCDASH_ARTIFACT_ROLLUP_EXPORT_INTERVAL_SECONDS=3600
export CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE=pseudonym
export CCDASH_LOCAL_USER_SCOPE_PSEUDONYM=local-user
```

Hosted mode uses the authenticated principal for `userScope`. Local mode should either emit a non-identifying pseudonym or omit `userScope` with `CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE=omit`.

## Snapshot Health In Settings

The Settings SkillMeat panel shows:

| Signal | How to read it |
| --- | --- |
| Snapshot Age / Last fetched | Healthy when recent enough for `CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS`. Stale or unknown means refresh before acting on recommendations. |
| Artifact Count | Number of artifacts in the latest SkillMeat snapshot. Zero usually means the project or collection mapping is wrong. |
| Resolved Count | Number of observed CCDash artifact references mapped to SkillMeat identities. |
| Unresolved Identities | Items CCDash observed but could not map. Review before trusting per-artifact rankings. |
| Export Freshness | Last reported rollup export time. Missing or old values point to worker scheduling, feature flag, or privacy guard issues. |

Use `Fetch Now` after changing SkillMeat settings or freshness thresholds.

## Recommendations

All recommendations are advisory. CCDash does not auto-apply artifact changes.

| Type | Default staleness threshold | Operator meaning |
| --- | --- | --- |
| `disable_candidate` | 7 days | An always-loaded artifact has no observed use; review before disabling or unbundling. |
| `workflow_specific_swap` | 7 days | Another artifact appears better for a specific workflow. |
| `load_on_demand` | 14 days | A narrowly used artifact may not need to be always loaded. |
| `version_regression` | 14 days | A newer version appears to underperform an earlier version. |
| `optimization_target` | 30 days | High-use or costly artifact should be prioritized for optimization. |
| `identity_reconciliation` | 30 days | Observed usage could not be confidently mapped to a SkillMeat artifact. |
| `insufficient_data` | 30 days | CCDash lacks enough sample size, confidence, or freshness for a stronger recommendation. |

Override thresholds with:

```bash
export CCDASH_SNAPSHOT_FRESHNESS_DISABLE_CANDIDATE_SECONDS=604800
export CCDASH_SNAPSHOT_FRESHNESS_WORKFLOW_SPECIFIC_SWAP_SECONDS=604800
export CCDASH_SNAPSHOT_FRESHNESS_LOAD_ON_DEMAND_SECONDS=1209600
export CCDASH_SNAPSHOT_FRESHNESS_VERSION_REGRESSION_SECONDS=1209600
export CCDASH_SNAPSHOT_FRESHNESS_OPTIMIZATION_TARGET_SECONDS=2592000
export CCDASH_SNAPSHOT_FRESHNESS_IDENTITY_RECONCILIATION_SECONDS=2592000
export CCDASH_SNAPSHOT_FRESHNESS_INSUFFICIENT_DATA_SECONDS=2592000
```

## Troubleshooting

### Snapshot Fetch Failures

- Confirm `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED=true` in the API and worker environment.
- Confirm the project has SkillMeat integration enabled in Settings.
- Run `Check Connection`; fix base URL, timeout, AAA, or API key failures first.
- Verify `SkillMeat Project ID` is the SkillMeat ID, not the CCDash project slug.
- Clear or correct `Collection ID` if Artifact Count is zero or SkillMeat returns 404.
- For rate limits, wait for retry/backoff to settle or increase the export/fetch cadence; repeated 429s require SkillMeat-side quota review.
- Check API logs for `ccdash.skillmeat_client` messages when Settings shows no snapshot data.

### Identity Resolution Issues

- Treat a high `Unresolved Identities` count as a mapping problem, not a ranking problem.
- Refresh the snapshot after changing SkillMeat artifact names, versions, collections, or deployment profiles.
- Verify observed CCDash artifact references exist in the configured SkillMeat project and collection.
- Keep `CCDASH_IDENTITY_FUZZY_THRESHOLD` at `0.85` unless operators have reviewed false matches; lowering it can merge unrelated artifacts.
- Use `identity_reconciliation` recommendations as a work queue for fixing missing or ambiguous artifact identities.

### Privacy Guard Rejections

- Rollups that fail the privacy guard are skipped instead of posted to SkillMeat.
- Inspect worker logs for `Artifact rollup skipped by privacy guard`.
- Remove any raw prompt, transcript text, source code, absolute path, email, username, token, or secret from candidate rollup fields.
- In local mode, use `CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE=omit` or a non-identifying `CCDASH_LOCAL_USER_SCOPE_PSEUDONYM`.
- Re-check [Artifact Intelligence Privacy Audit](artifact-intelligence-privacy-audit.md) before adding new recommendation evidence fields or debug logging.
