# Handoff: Enabling SkillMeat Integration Across All Projects

**Status:** handoff / not-yet-done. Requires operator input (endpoint + per-project
collection mappings). This is **not** a single global flag — do not expect a one-liner.

## TL;DR

The `stack_observations` backfill (2026-07-27) populated `session_stack_observations`
(≈16.3k) and `effectiveness_rollups` (≈14.5k) across all 20 projects, so **workflow
effectiveness/cost no longer reads all-zero** — those metrics are derived from session
data and do **not** need SkillMeat.

What is still empty is `external_definitions` (0 rows). That table is only populated by the
**SkillMeat definition sync**, which is **disabled per-project** (`SkillMeatProjectConfig.enabled`
defaults to `False`). During the backfill every project logged
`warning: [config] SkillMeat integration is disabled for this project`.

Enabling SkillMeat adds **stack-component resolution**: observed stack components get mapped
to known SkillMeat artifacts/workflows/context-modules (via `resolve_stack_components()` in
`backend/services/stack_observations.py`), which is what powers artifact-level attribution and
recommendations. Without it, components remain `unresolved`.

## Why it isn't a global flag

Two independent gates:

1. **Global machinery flag** — `CCDASH_SKILLMEAT_INTEGRATION_ENABLED` (default **true**,
   `backend/config.py:87`). Already on. This only decides whether the sync machinery is allowed
   to run at all (`require_skillmeat_integration_enabled()`).
2. **Per-project source config** — `project.skillMeat` (`SkillMeatProjectConfig`,
   `backend/models.py:1550`). This is what's missing. If it's absent or `enabled=False`,
   `sync_skillmeat_definitions()` (`backend/services/integrations/skillmeat_sync.py:67`) records
   the source as `skipped` and returns 0 definitions.

Blanket-enabling therefore requires **per-project data** (which SkillMeat collection maps to each
of the 20 CCDash projects) plus a **reachable SkillMeat API endpoint** — neither can be safely
guessed, so it's a deliberate operator step, not a config default.

## Required per-project config (`SkillMeatProjectConfig`)

Persisted on each project record. Fields (`backend/models.py:1550`):

| Field | Meaning | Needed |
|---|---|---|
| `enabled` | Master per-project switch | **Yes → set `true`** |
| `baseUrl` | SkillMeat **API** base URL | **Yes** (the SkillMeat service, e.g. on the NUC) |
| `webBaseUrl` | SkillMeat web UI base (deep links) | Optional |
| `projectId` | SkillMeat project id for this CCDash project | **Yes** (mapping) |
| `collectionId` | SkillMeat collection id (legacy `workspaceId` auto-migrates) | **Yes** (mapping) |
| `aaaEnabled` | Whether the SkillMeat instance requires AAA auth | If instance is authed |
| `apiKey` | API key | If `aaaEnabled` / instance requires it |
| `requestTimeoutSeconds` | Per-request timeout (default 5.0) | Optional |
| `featureFlags` | `stackRecommendationsEnabled` / `workflowAnalyticsEnabled` / `usageAttributionEnabled` / `sessionBlockInsightsEnabled` (all default `true`) | Optional |

## Persistence path (ADR-006: registry is DB-authoritative)

`projects.json` is **import-seed / export only** — production code reads the DB, not the JSON
(`backend/project_manager.py:343`). Two ways to write `skillMeat` onto projects:

- **Edit + re-import the registry**: `import_from_json()` / `export` roundtrip
  (`backend/project_manager.py:547` / `:636`). The `skillMeat` block is carried through
  (`:695`). Export current registry → add `skillMeat` per project → import-seed back.
- **Project-update surface**: set `skillMeat` via the project registry update path
  (project-management REST/CLI) so it lands directly in the DB registry.

Before flipping `enabled`, validate a candidate config with the SkillMeat probe/validate
surfaces (`SkillMeatConfigValidationRequest`/`Response`, `SkillMeatProbeResult` in
`backend/models.py`) to confirm the endpoint + collection resolve.

## Steps to enable across all 20 projects

1. **Obtain the SkillMeat API base URL** (the deployment CCDash should read from — likely the
   NUC SkillMeat instance). Note whether it requires auth (`aaaEnabled` + `apiKey`).
2. **Build the mapping**: for each of the 20 CCDash projects, decide its SkillMeat
   `projectId` + `collectionId`. **This is the human decision that blocks automation** — there is
   no reliable auto-mapping from CCDash project → SkillMeat collection.
3. **Write `skillMeat` config** per project into the DB registry (via re-import or the update
   surface), with `enabled=true`, `baseUrl`, `projectId`, `collectionId`, and auth as needed.
4. **Re-run the rollout** (same command as the backfill, sync leg now active):
   ```bash
   CCDASH_DB_BACKEND=postgres \
   CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@10.42.10.76:5440/ccdash \
   CCDASH_SKILLMEAT_INTEGRATION_ENABLED=true \
   backend/.venv/bin/python -m backend.scripts.agentic_intelligence_rollout --all-projects
   ```
   (On this machine the DB env is already the default via gitignored `.env`; shown explicit for a
   clean/remote shell.)
5. **Verify**: `external_definitions` count > 0; `session_stack_components.status='resolved'`
   rows appear; per-project sync log shows `total_definitions>0` instead of the `disabled` warning.

## Open questions for the operator

- Which SkillMeat deployment/URL should CCDash sync from, and does it require auth?
- The 20-project → SkillMeat `collectionId` mapping (the gating decision).
- Should all projects be enabled, or only the high-value ones (skillmeat, CCDash,
  agentic-meta-dev, research-foundry, intenttree)?

## Reference

- Gate: `backend/services/integrations/skillmeat_sync.py:67` (`enabled` check at `:109`).
- Config model: `backend/models.py:1550` (`SkillMeatProjectConfig`), `:1543` (feature flags),
  attached to the project at `:1845`.
- Global flag: `backend/config.py:87` (`CCDASH_SKILLMEAT_INTEGRATION_ENABLED`).
- Rollout/sync entrypoint: `backend/scripts/agentic_intelligence_rollout.py`.
- Component resolution consumer: `backend/services/stack_observations.py`
  (`resolve_stack_components`).
