# Testing Page Performance Guardrails

Updated: 2026-03-03

## Scope

This guardrail set covers `/api/tests` hot paths and the Testing page run-detail/result-table interaction flow.

## Budget Targets

Backend (local SQLite benchmark):

- `ingest_run(100 tests)`: `< 500ms`
- `get_domain_rollups(100 domains, 1000 tests)`: `< 500ms`
- `list_by_run_filtered(7000-test run)`: `< 1500ms`
- `list_filtered(feature_id)` for runs list: `< 1000ms`
- `list_history_for_test(500 runs)`: `< 800ms`
- `list_filtered(integrity alerts)` with 5000 rows: `< 800ms`

Frontend (browser Performance timeline):

- `tests.ui.runDetail.load`: stable under repeated run switches
- `tests.ui.runResults.firstPage`: stable under filter/sort changes
- `tests.ui.runResults.loadMore`: stable under paginated expansion

## Regression Test Entry Point

Run:

```bash
uv run --project backend pytest backend/tests/test_test_visualizer_performance.py -v
```

The performance suite seeds realistic large data (including a `7000` test-case run fixture) and enforces the backend budget thresholds above.

## Observability Markers

Backend markers:

- OpenTelemetry spans on test visualizer endpoints annotate `query_mode=db_native` where DB-native filtering/pagination is used.

Frontend markers:

- The Testing page emits browser performance measures:
  - `tests.ui.runDetail.load`
  - `tests.ui.runResults.firstPage`
  - `tests.ui.runResults.loadMore`

These measures are visible in browser DevTools Performance recordings.
