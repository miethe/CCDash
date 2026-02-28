---
title: "Phase 2: Ingestion Pipeline - Test Visualizer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
phase: 2
phase_title: "Ingestion Pipeline"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1.md
effort_estimate: "16 story points"
duration: "1 week"
assigned_subagents: [python-backend-engineer, backend-architect]
entry_criteria:
  - Phase 1 complete: DB schema and repositories exist
  - SCHEMA_VERSION is 13
  - All repository factory functions exist
exit_criteria:
  - JUnit XML parser handles standard + parameterized + nested suites
  - Optional JSON enrichment for richer metadata
  - POST /api/tests/ingest endpoint accepts and stores test runs
  - Ingestion is idempotent (same run_id + test_id always yields same DB state)
  - Run metadata (git_sha, branch, agent_session_id) captured correctly
  - SyncEngine has a hook to trigger mapping resolution after ingestion
  - Feature flag gates the entire pipeline
tags: [implementation, ingestion, test-visualizer, parsing, api]
---

# Phase 2: Ingestion Pipeline

**Parent Plan**: [Test Visualizer Implementation Plan](../test-visualizer-v1.md)
**Effort**: 16 story points | **Duration**: 1 week
**Assigned Subagents**: python-backend-engineer, backend-architect

---

## Overview

This phase builds the data ingest pipeline: a JUnit XML parser, a JSON enrichment layer, the ingestion REST endpoint, and a SyncEngine hook for post-ingestion processing. The parser follows the same pattern as `backend/parsers/sessions.py` and `backend/parsers/documents.py` — pure functions that take file paths or raw content and return structured dicts.

The ingest endpoint is the primary write surface for the Test Visualizer. It must be idempotent, so re-ingesting the same run does not create duplicate rows or corrupt rollups.

---

## JUnit XML Parser

### File: `backend/parsers/test_results.py`

The parser handles JUnit XML format (pytest, JUnit, xUnit-compatible). It extracts:
- `testsuite` / `testsuites` root elements
- Per-test `testcase` elements with `classname`, `name`, `time`
- Status from child elements: `<failure>`, `<error>`, `<skipped>`, `<system-out>`, `<system-err>`
- Parameterized test detection from `name` patterns (e.g., `test_func[param1-param2]`)
- Optional JSON enrichment sidecar: if `{xml_path}.meta.json` exists, merge its data

```python
# backend/parsers/test_results.py structure

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

def generate_test_id(path: str, name: str, framework: str = "pytest") -> str:
    """Stable SHA-256 hash as test_id."""
    raw = f"{path}::{name}::{framework}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def parse_junit_xml(xml_content: str, project_id: str, run_metadata: dict) -> dict:
    """
    Parse JUnit XML and return ingestion payload.

    Returns:
        {
            "run": {run fields},
            "test_definitions": [{test_def fields}, ...],
            "test_results": [{result fields}, ...],
        }
    """
    ...

def parse_junit_xml_file(xml_path: Path, project_id: str, run_metadata: dict) -> dict:
    """Parse from file path. Loads optional JSON sidecar for enrichment."""
    ...

def _extract_status(testcase_el) -> str:
    """Map XML child elements to canonical status string."""
    # <failure> -> 'failed'
    # <error> -> 'error'
    # <skipped> -> 'skipped'
    # xfail marker in message -> 'xfailed'
    # xpass -> 'xpassed'
    # else -> 'passed'
    ...

def _extract_error_fingerprint(message: str) -> str:
    """
    Create stable fingerprint from error message for grouping recurring failures.
    Strips line numbers, memory addresses, timestamps.
    """
    ...
```

### Supported Formats

| Format | Support Level |
|--------|--------------|
| JUnit XML (pytest) | Full |
| JUnit XML (Maven/Java) | Full |
| xUnit XML (.NET) | Full (same schema) |
| Parameterized tests | Full (name pattern extraction) |
| Nested `<testsuites>` | Full |
| JSON enrichment sidecar | Optional; merged at parse time |
| TAP (Test Anything Protocol) | Out of scope v1 |
| CTRF (Common Test Report Format) | Out of scope v1 |

### JSON Enrichment Sidecar

If a file `{xml_basename}.meta.json` exists alongside the XML, it is parsed and merged:

```json
{
  "run_id": "run-abc-123",
  "git_sha": "abc1234",
  "branch": "feat/my-feature",
  "agent_session_id": "session-xyz",
  "env_fingerprint": "py311-ubuntu22-x86",
  "trigger": "local",
  "test_overrides": {
    "test_id_hash": {
      "tags": ["auth", "slow"],
      "owner": "avery@example.com"
    }
  }
}
```

---

## Ingestion API Endpoint

### Endpoint: `POST /api/tests/ingest`

Accepts either:
1. **Structured payload** (pre-parsed): `IngestRunRequest` JSON body
2. **File upload**: multipart with `xml_file` + optional `meta` JSON

The endpoint is gated by `CCDASH_TEST_VISUALIZER_ENABLED`.

```python
# In backend/routers/test_visualizer.py (stub router created in Phase 2)

@router.post("/ingest", response_model=IngestRunResponse)
async def ingest_test_run(
    request: Request,
    payload: IngestRunRequest,
) -> IngestRunResponse:
    """
    Idempotent ingestion of test results.

    ON CONFLICT (run_id, test_id) DO NOTHING — re-ingestion of same run is safe.
    Returns counts of inserted vs skipped.
    """
    ...
```

### Response Model

```python
class IngestRunResponse(BaseModel):
    run_id: str
    status: str  # 'created' | 'updated' | 'skipped'
    test_definitions_upserted: int
    test_results_inserted: int
    test_results_skipped: int
    mapping_trigger_queued: bool
    integrity_check_queued: bool
    errors: list[str] = Field(default_factory=list)
```

### Idempotency Rules

- If `run_id` already exists in `test_runs`: return `status: 'skipped'` without re-inserting results.
- If `run_id` exists but some `(run_id, test_id)` pairs are missing: insert only the missing ones.
- `test_definitions` always use `upsert()` (stable `test_id` hash prevents duplicates).
- Integrity check and mapping resolution are queued as background tasks regardless of duplicate status.

---

## Post-Ingestion Background Tasks

After a successful ingest, two async background tasks are queued via `asyncio.create_task()`:

### Task 1: Mapping Resolution Trigger
```python
async def _trigger_mapping_resolution(run_id: str, project_id: str, db):
    """Queue domain mapping for all new test_definitions in this run."""
    # Calls mapping_resolver.resolve_for_run(run_id, project_id)
    # Implemented in Phase 7
    pass  # no-op stub in Phase 2
```

### Task 2: Integrity Signal Detection
```python
async def _trigger_integrity_check(run_id: str, git_sha: str, project_id: str, db):
    """Queue integrity signal detection for this run's git_sha."""
    # Calls integrity_detector.check_run(run_id, git_sha, project_id)
    # Implemented in Phase 7
    pass  # no-op stub in Phase 2
```

Both tasks are gated by feature flags:
- Mapping: `CCDASH_TEST_VISUALIZER_ENABLED`
- Integrity: `CCDASH_INTEGRITY_SIGNALS_ENABLED`

---

## SyncEngine Integration

The `SyncEngine` in `backend/db/sync_engine.py` currently handles sessions, documents, and features. For Phase 2, we add a lightweight hook for file-based test result ingestion:

### File Watcher Extension

If `CCDASH_TEST_VISUALIZER_ENABLED` is set, the `FileWatcher` watches a configurable directory for new JUnit XML files:

```python
# In backend/config.py
TEST_RESULTS_DIR = os.getenv("CCDASH_TEST_RESULTS_DIR", "")  # e.g., "test-results/"
```

When a new `.xml` file appears in `TEST_RESULTS_DIR`, the `SyncEngine` auto-ingests it:

```python
# New method in SyncEngine
async def sync_test_results(self, project_id: str, results_dir: Path) -> dict:
    """Scan results_dir for new JUnit XML files and ingest them."""
    ...
```

This is **optional** for v1 — direct API ingestion is the primary path. File watching is a convenience for local test runs.

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------------|---------------------|--------------|
| ING-1 | JUnit XML Parser Core | Implement `parse_junit_xml()` in `backend/parsers/test_results.py`. Handle `<testsuites>`, `<testsuite>`, `<testcase>`. Extract status, duration, error messages. Generate stable `test_id` via SHA-256 hash. | Parser handles pytest JUnit XML output. All status types (`passed`, `failed`, `skipped`, `error`) mapped correctly. Parameterized test names parsed. | 3 | python-backend-engineer | Phase 1 complete |
| ING-2 | Parameterized + Nested Suite Handling | Extend parser to handle: nested `<testsuites>` (flatten hierarchy), parameterized test name extraction (`test_func[param1]` -> base name + params), `classname` used for path inference when `file` attr absent. | Tests with parameters produce separate `test_id` per parameter set. Nested suites produce flat list with correct paths. | 2 | python-backend-engineer | ING-1 |
| ING-3 | JSON Enrichment Sidecar | Implement sidecar detection: check for `{xml_basename}.meta.json` alongside XML. Merge run metadata (git_sha, branch, session_id, env_fingerprint). Allow per-test tag/owner overrides. | Sidecar fields override XML-derived fields. Missing sidecar is graceful (no error). Unit tests cover both cases. | 2 | python-backend-engineer | ING-1 |
| ING-4 | Error Fingerprint Generation | Implement `_extract_error_fingerprint()`. Strip line numbers, memory addresses, timestamps from error messages. Produce stable short hash for recurring failure grouping. | Same error at different line numbers produces same fingerprint. Different errors produce different fingerprints. | 1 | python-backend-engineer | ING-1 |
| ING-5 | Stub Router File | Create `backend/routers/test_visualizer.py` with router declaration and `POST /api/tests/ingest` endpoint. Wire to ingest service. Register router in `backend/main.py`. Gate with `CCDASH_TEST_VISUALIZER_ENABLED` flag. | Router imported and registered. Endpoint returns 200 on valid payload. Feature flag returns 503 when disabled. | 2 | python-backend-engineer | ING-1, Phase 1 |
| ING-6 | Ingest Service | Implement `backend/services/test_ingest.py` with `ingest_run(payload: IngestRunRequest, db) -> IngestRunResponse`. Orchestrates: validate payload, upsert test_run, upsert test_definitions, upsert test_results. Returns counts. | Idempotency: same run_id second call returns `status: 'skipped'` without DB writes. Partial re-ingest fills only missing `(run_id, test_id)` pairs. Validation rejects unknown `agent_session_id`. | 3 | python-backend-engineer | ING-5 |
| ING-7 | Background Task Hooks | Add `_trigger_mapping_resolution()` and `_trigger_integrity_check()` as async stubs called after successful ingest via `asyncio.create_task()`. Gate each by its feature flag. Log task creation. | Tasks are created after ingest (not blocking). No-op stubs don't crash. Integration ready for Phase 7 implementations. | 1 | python-backend-engineer | ING-6 |
| ING-8 | File Watcher Extension | Add `sync_test_results()` to `SyncEngine`. Configure `TEST_RESULTS_DIR` in `config.py`. Extend `FileWatcher` to watch for `*.xml` files in that directory and call `sync_test_results()`. Guard with `TEST_RESULTS_DIR != ""`. | New XML in watched directory triggers auto-ingest within 5s. Existing XMLs at startup are processed once. Already-processed files (by mtime/hash in sync_state) are skipped. | 2 | backend-architect | ING-6 |

---

## Quality Gates

- [ ] `parse_junit_xml()` handles empty test suites without error
- [ ] `parse_junit_xml()` handles malformed XML gracefully (returns empty results + error log)
- [ ] `generate_test_id()` produces consistent hash for same inputs across Python restarts
- [ ] `POST /api/tests/ingest` returns 200 on valid `IngestRunRequest`
- [ ] `POST /api/tests/ingest` returns 400 on missing required fields (`run_id`, `project_id`, `timestamp`)
- [ ] `POST /api/tests/ingest` is idempotent: posting same `run_id` twice returns `status: 'skipped'`
- [ ] `POST /api/tests/ingest` returns 503 when `CCDASH_TEST_VISUALIZER_ENABLED=false`
- [ ] Unit tests cover: standard XML, parameterized tests, nested suites, missing sidecar, existing sidecar
- [ ] Integration test: ingest -> query `test_runs` -> verify row exists
- [ ] File watcher triggers ingestion when XML dropped in `TEST_RESULTS_DIR` (manual test)

---

## Key Files Created / Modified

| File | Action | Notes |
|------|--------|-------|
| `backend/parsers/test_results.py` | Created | JUnit XML parser + JSON sidecar |
| `backend/services/test_ingest.py` | Created | Ingest orchestration service |
| `backend/routers/test_visualizer.py` | Created | Stub router with ingest endpoint |
| `backend/db/sync_engine.py` | Modified | Add `sync_test_results()` method |
| `backend/db/file_watcher.py` | Modified | Watch `TEST_RESULTS_DIR` for XML files |
| `backend/config.py` | Modified | Add `TEST_RESULTS_DIR`, `CCDASH_TEST_VISUALIZER_ENABLED`, `CCDASH_INTEGRITY_SIGNALS_ENABLED` |
| `backend/main.py` | Modified | Import and register `test_visualizer_router` |
| `backend/models.py` | Modified | Add `IngestRunRequest`, `IngestRunResponse` |
| `backend/tests/test_test_results_parser.py` | Created | Unit tests for parser |
| `backend/tests/test_test_ingest_service.py` | Created | Unit tests for ingest service |

---

## Run Metadata Capture

The `IngestRunRequest` requires these metadata fields to support correlation:

| Field | Source | Required |
|-------|--------|----------|
| `run_id` | Caller-generated UUID or CI job ID | Yes |
| `project_id` | CCDash project ID | Yes |
| `timestamp` | ISO 8601 string | Yes |
| `git_sha` | `git rev-parse HEAD` at run time | Recommended |
| `branch` | `git branch --show-current` | Recommended |
| `agent_session_id` | CCDash session ID from active session | Optional |
| `env_fingerprint` | Hash of Python version + OS + key deps | Optional |
| `trigger` | `"local"` or `"ci"` | Optional (default: `"local"`) |

If `agent_session_id` is provided, it is validated against the `sessions` table before storing. Invalid IDs are logged but not rejected (to avoid blocking ingestion when session data is delayed).
