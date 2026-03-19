# CCDash Testing Integration User Guide

This guide explains how to configure a Project so the `/tests` page ingests and displays backend/frontend test artifacts reliably.

## 1) Preconditions

1. Start CCDash backend/frontend (`npm run dev`).
2. Ensure environment kill switches are enabled when you want testing features active:
   - `CCDASH_TEST_VISUALIZER_ENABLED=true`
   - `CCDASH_INTEGRITY_SIGNALS_ENABLED=true` (optional, for integrity alerts)
   - `CCDASH_LIVE_TEST_UPDATES_ENABLED=true` (optional, backend live-update gate)
   - `CCDASH_SEMANTIC_MAPPING_ENABLED=true` (optional, for semantic mapping)
   - `VITE_CCDASH_LIVE_TESTS_ENABLED=true` (optional, frontend live-update rollout)

Effective behavior is `env_flag && project_flag`. If env is `false`, project settings cannot override it.

## 2) Configure Project Testing Settings

Open `Settings` -> `Projects` -> select the project -> `Testing Configuration`.

Configure:

1. Feature flags
   - `Test Visualizer`
   - `Integrity Signals`
   - `Live Updates`
   - `Semantic Mapping`
2. Scan controls
   - `Auto Sync on Startup`
   - `Max Files per Scan`
   - `Max Parse Concurrency`
3. Platform rows (`pytest`, `jest`, `playwright`, `coverage`, `benchmark`, `lighthouse`, `locust`, `triage`)
   - `Enabled`
   - `Watch`
   - `Results Dir` (absolute or project-relative)
   - `Patterns` (comma-separated glob patterns)

Save the project.

## 3) Validate and Sync

After saving:

1. Click `Validate Paths` to check resolved directories and file matches.
2. Review `Source Status` for:
   - `exists`
   - `readable`
   - `matched`
   - `lastError` (if any)
3. Click `Run Sync Now` to ingest current artifacts immediately.

`/tests` should populate after a successful sync.

## 4) Generate and Export Setup Script

For each project, Settings can generate a local bootstrap script from current Testing entries:

1. Click `Generate Setup Script`.
2. Use `Copy` or `Export`.
3. Run locally in your target repository:

```bash
chmod +x <project-id>-test-setup.sh
./<project-id>-test-setup.sh /path/to/your/project
```

Then return to CCDash and run `Validate Paths` and `Run Sync Now`.

## 5) How Discovery Works

CCDash does not execute tests itself. It ingests result artifacts from configured platform sources.

For each enabled platform, CCDash:

1. Resolves `resultsDir`:
   - Absolute path: used directly
   - Relative path: resolved against the project root path
2. Scans files matching configured `patterns` (up to `Max Files per Scan`)
3. Parses supported artifact formats
4. Upserts test runs/results and metrics into cache DB

If no files are found for enabled platforms, `/tests` remains empty by design.

## 6) Supported Artifact Types (Current)

- `pytest`: JUnit XML
- `jest`: JSON results
- `playwright`: JSON results
- `coverage`: coverage artifacts (`coverage.xml`, `coverage.json`, `lcov.info`, etc.)
- `benchmark`: benchmark JSON
- `lighthouse`: report JSON/HTML metrics
- `locust`: HTML/CSV metrics
- `triage`: failure summary artifacts

## 7) SkillMeat Recommended Setup

In SkillMeat, configure scripts/workflows to emit machine-readable outputs into stable directories, then map those directories in CCDash platform settings.

Typical outputs:

1. Backend (`pytest`, `pytest-cov`): JUnit XML + coverage XML/JSON
2. Frontend unit (`jest`): JSON output + coverage output
3. E2E (`playwright`): JSON reporter output
4. Perf/load (`benchmark`, `lighthouse`, `locust`): JSON/HTML/CSV outputs
5. Failure triage: JSON/Markdown/text summaries

## 8) Troubleshooting

### `/api/tests/*` returns `503 Service Unavailable`

1. If error is `feature_disabled`:
   - Enable `CCDASH_TEST_VISUALIZER_ENABLED=true` in environment
   - Enable `Test Visualizer` flag in project settings
2. Refresh `/tests` after changing settings.

The frontend includes a circuit breaker for `feature_disabled` responses to prevent retry storms.

### `/tests` is empty but no 503

1. `Validate Paths` and inspect `Source Status`.
2. Confirm `matched` file count is non-zero for enabled platforms.
3. Confirm `Results Dir` and `Patterns` match actual artifact locations.
4. Run `Run Sync Now` and check returned sync summary.

### High CPU or constant polling previously observed

Current behavior uses stream-first invalidation when both backend and frontend live gates are enabled, then falls back to polling on disconnect/backoff. If you still see churn, re-check env/project flags and browser console errors.

## 9) Mapping Coverage and Reuse Workflow

Use this workflow to get high mapping coverage without remapping every run:

1. Bootstrap once per project:
   - Run `POST /api/tests/mappings/backfill` with your target `project_id`.
   - Optionally increase `run_limit` to cover older runs.
2. Let normal ingestion run incrementally:
   - New runs call the resolver with definition-signature caching.
   - Unchanged tests reuse cached primary mappings.
   - Only new/changed tests are remapped.
3. Use full remap only when needed:
   - Set `force_recompute=true` in backfill when mapping logic or feature taxonomy changes.

Backfill response now reports cache and resolver state:

- `tests_considered`
- `tests_resolved`
- `tests_reused_cached`
- `resolver_version`
- `cache_state`

## 10) Domain and Sub-domain Mapping

Mapping providers now support hierarchical domains:

1. `RepoHeuristicsProvider`
   - derives domain path segments from test file location.
   - creates parent/child domain rows (`core` -> `support` -> `leaf`).
   - automatically maps deeper sub-domains when a top-level domain contains many tests.
2. `TestMetadataProvider`
   - honors explicit `@pytest.mark.domain(...)` or `domain:<token>` tags.
   - supports hierarchical markers (for example `auth/api`).
   - falls back to adaptive path-derived domain hierarchy if no explicit domain marker is present.

## 11) Extensible Mapping Methods

The resolver is provider-driven to support future mapping strategies:

1. Built-in providers:
   - `test_metadata`
   - `repo_heuristics`
   - `path_fallback` (baseline coverage for previously unmapped tests)
2. External/semantic provider path:
   - use `POST /api/tests/mappings/import` with a precomputed mapping file (`semantic_llm` source).
3. Provider selection for bulk backfill:
   - use `provider_sources` in `POST /api/tests/mappings/backfill` to constrain enabled providers.
4. Domain hygiene:
   - backfill automatically prunes stale unmapped leaf domains so old orphaned domains do not persist in the Mapped Domains pane.

## 12) Session Transcript Test Run Correlation

CCDash also correlates test activity from Session tool calls (for example Claude/Codex shell execution logs) to improve session-level test insights.

What is captured when test signals are detected:

1. Invocation metadata
   - framework (`pytest`, `jest`, `vitest`, `go test`, `cargo test`, etc.)
   - command segment
   - targets
   - inferred domain(s)
   - flags and timeout hints
   - optional description from tool-call payloads
2. Parsed result metadata (when output is available)
   - total tests
   - status counts (`passed`, `failed`, `error`, `skipped`, `xfailed`, `xpassed`, `deselected`, `rerun`)
   - duration
   - pass rate
   - runner/session metadata (for example worker counts, rootdir, pytest/python version)
3. Session correlation
   - run details are persisted in `sessionForensics.testExecution`
   - linked artifacts are captured for traceability
   - Session Inspector transcript cards and detail panes use this data for test run formatting
   - Session Inspector `Test Status` uses this data to render:
     - all modified test files touched in-session (read/create/update/delete), with scrollable history
     - all parsed test runs in-session (one row per run) with framework/status/targets/domains/flags/counts

Important behavior:

- CCDash only labels transcript entries as test runs when explicit test signals exist.
- Non-test shell commands (for example generic Bash scripts, Git commands, or skill helper scripts) are not classified as test runs.
- Test artifact cards in `Session > Artifacts` include parsed run details from correlated logs so run-level outcomes can be reviewed directly from artifact details.
- Pytest parsing supports truncated output captures (for example `| tail -20`) and still extracts summary/failure metrics when sufficient pytest signals are present.
