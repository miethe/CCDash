---
title: "Phase 7: Domain Mapping & Integrity Signals - Test Visualizer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
phase: 7
phase_title: "Domain Mapping & Integrity Signals"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1.md
effort_estimate: "10 story points"
duration: "1 week"
assigned_subagents: [python-backend-engineer, backend-architect]
entry_criteria:
  - Phase 1 complete: test_feature_mappings and test_integrity_signals tables exist
  - Phase 2 complete: ingestion pipeline and background task hooks exist (stubs)
exit_criteria:
  - MappingProvider protocol defined with pluggable interface
  - RepoHeuristicsProvider maps tests based on folder structure and naming patterns
  - TestMetadataProvider maps tests based on pytest markers and tags parsed from test source
  - SemanticLLMProvider imports externally-generated JSON mapping file
  - Provider conflict resolution and confidence scoring implemented
  - Mapping snapshots versioned with hash in test_feature_mappings
  - IntegrityDetector implements all 5 signal types with Git CLI integration
  - Async integrity check background task wired from Phase 2 stubs
  - CCDASH_INTEGRITY_SIGNALS_ENABLED flag gates integrity pipeline
tags: [implementation, mapping, integrity, test-visualizer, python, git]
---

# Phase 7: Domain Mapping & Integrity Signals

**Parent Plan**: [Test Visualizer Implementation Plan](../test-visualizer-v1.md)
**Effort**: 10 story points | **Duration**: 1 week
**Assigned Subagents**: python-backend-engineer, backend-architect

---

## Overview

This phase implements the intelligence layer: the pluggable Domain Mapping Provider system and the integrity signal detection pipeline. Both systems can run as background tasks triggered after ingestion (Phase 2 stubs are filled in here).

The mapping system answers: "Which features does this test belong to?" The integrity system answers: "Did someone weaken this test?"

Both are designed to fail gracefully — if providers conflict, confidence scores resolve it. If Git is unavailable, integrity detection is skipped with a log message.

---

## Pluggable Mapping Provider System

### Interface: `backend/services/mapping_resolver.py`

```python
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

@runtime_checkable
class MappingProvider(Protocol):
    """Protocol for domain/feature mapping providers."""

    @property
    def name(self) -> str:
        """Provider identifier: 'repo_heuristics' | 'test_metadata' | 'semantic_llm' | 'user_override'"""
        ...

    @property
    def priority(self) -> int:
        """Lower number = higher priority in conflict resolution. Range: 1-100."""
        ...

    async def resolve(
        self,
        test_definitions: list[dict],
        project_id: str,
        context: dict,
    ) -> list[MappingCandidate]:
        """
        Returns a list of MappingCandidate objects.
        Each candidate has: test_id, feature_id, domain_id, confidence (0.0-1.0).
        """
        ...
```

### `MappingCandidate` dataclass

```python
from dataclasses import dataclass, field

@dataclass
class MappingCandidate:
    test_id: str
    feature_id: str
    domain_id: str | None
    confidence: float
    provider_source: str
    metadata: dict = field(default_factory=dict)
```

### `MappingResolver` orchestrator

```python
class MappingResolver:
    """Orchestrates multiple providers, merges with conflict resolution."""

    PROVIDERS: list[MappingProvider] = []  # registered at startup

    def __init__(self, db, providers: list[MappingProvider] | None = None):
        self.db = db
        self.providers = providers or self._default_providers()

    async def resolve_for_run(self, run_id: str, project_id: str) -> MappingResolutionResult:
        """
        1. Fetch test_definitions for this run
        2. Run each provider (in priority order)
        3. Merge candidates with conflict resolution
        4. Compute is_primary for highest-confidence mapping per (test_id, feature_id)
        5. Upsert to test_feature_mappings
        6. Return result summary
        """
        ...

    def _merge_candidates(
        self, all_candidates: list[MappingCandidate]
    ) -> list[MappingCandidate]:
        """
        Conflict resolution rules:
        1. If providers agree on (test_id, feature_id): average confidence, keep both records
        2. If providers disagree: lower-priority provider's mapping stored but NOT is_primary
        3. is_primary = True for highest confidence mapping per test_id
        4. Confidence < 0.5 stored but never is_primary (requires human review)
        """
        ...
```

---

## Provider Implementations

### `RepoHeuristicsProvider`

Maps tests based on repo folder structure and naming conventions. No external tools needed.

**Algorithm:**

1. **Path-based mapping**: `tests/auth/test_login.py` -> domain "auth", feature "login"
   - Strip `tests/` prefix
   - Remaining path segments = domain hierarchy
   - Test file name (stripped of `test_` prefix) = feature hint

2. **Naming convention**: `test_{feature_name}_*` -> feature hint from function name prefix

3. **CCDash feature matching**: Fuzzy-match extracted feature hint against `features.name` in DB
   - Exact match: confidence 0.9
   - Fuzzy match (>80% similarity): confidence 0.7
   - Prefix match: confidence 0.5
   - No match: confidence 0.0 (not stored)

```python
class RepoHeuristicsProvider:
    name = "repo_heuristics"
    priority = 50  # medium priority (overridden by user_override, test_metadata)

    async def resolve(
        self, test_definitions: list[dict], project_id: str, context: dict
    ) -> list[MappingCandidate]:
        candidates = []
        features = await self._load_features(project_id)

        for test_def in test_definitions:
            path_parts = self._extract_path_parts(test_def["path"])
            feature_hint = self._extract_feature_hint(test_def["name"])
            domain_hint = self._extract_domain_hint(path_parts)

            # Match against features
            matched_feature, confidence = self._fuzzy_match_feature(
                feature_hint, features
            )
            if matched_feature and confidence > 0.3:
                candidates.append(MappingCandidate(
                    test_id=test_def["test_id"],
                    feature_id=matched_feature["id"],
                    domain_id=await self._get_or_create_domain(domain_hint, project_id),
                    confidence=confidence,
                    provider_source=self.name,
                ))
        return candidates
```

### `TestMetadataProvider`

Maps tests based on pytest markers, tags, and annotations found in test source code.

**Marker extraction algorithm:**

1. Scan test file content for `@pytest.mark.{marker}` decorators
2. Markers matching feature slug patterns -> feature mapping
3. Markers matching domain patterns -> domain mapping
4. Custom marker format: `@pytest.mark.feature("my-feature-slug")` -> direct feature mapping

```python
class TestMetadataProvider:
    name = "test_metadata"
    priority = 30  # higher priority than heuristics (lower number = higher priority)

    FEATURE_MARKER_PATTERN = re.compile(
        r'@pytest\.mark\.feature\(["\']([^"\']+)["\']\)'
    )
    DOMAIN_MARKER_PATTERN = re.compile(
        r'@pytest\.mark\.domain\(["\']([^"\']+)["\']\)'
    )

    async def resolve(
        self, test_definitions: list[dict], project_id: str, context: dict
    ) -> list[MappingCandidate]:
        """
        For each test_definition, read the source file and extract markers.
        If CCDASH_PROJECT_ROOT is set, read from filesystem.
        Otherwise, use tags_json already in test_definition.
        """
        ...
```

### `SemanticLLMProvider`

Imports an externally-generated JSON mapping file. No in-app LLM calls — accepts pre-computed mapping from an external agent or tool.

**Expected import format:**

```json
{
  "version": "1",
  "generated_at": "2026-02-28T00:00:00Z",
  "generated_by": "semantic-mapping-agent-v1",
  "mappings": [
    {
      "test_id": "sha256hash...",
      "test_path": "tests/auth/test_login.py",
      "test_name": "test_login_valid",
      "feature_id": "feature-auth-login",
      "domain_id": "domain-auth",
      "confidence": 0.92,
      "rationale": "Test directly exercises login feature by testing..."
    }
  ]
}
```

**Import API endpoint** (added to `test_visualizer.py` router):

```
POST /api/tests/mappings/import
Content-Type: application/json
{
  "project_id": "...",
  "mapping_file": { ...above format... }
}
```

```python
class SemanticLLMProvider:
    name = "semantic_llm"
    priority = 20  # high priority (externally generated is likely accurate)

    def __init__(self, mapping_data: dict):
        self.mapping_data = mapping_data  # pre-loaded from import payload

    async def resolve(
        self, test_definitions: list[dict], project_id: str, context: dict
    ) -> list[MappingCandidate]:
        """Match mapping_data entries to test_definitions by test_id or (path, name)."""
        ...
```

---

## Integrity Signal Detection Pipeline

### `backend/services/integrity_detector.py`

Detects 5 signal types by combining Git blame/diff with test result changes.

```python
class IntegrityDetector:
    """Async integrity signal detector. Runs after test ingestion."""

    SIGNAL_TYPES = [
        "assertion_removed",
        "skip_introduced",
        "xfail_added",
        "broad_exception",
        "edited_before_green",
    ]

    def __init__(self, db, git_repo_path: str | None = None):
        self.db = db
        self.git_path = git_repo_path or os.getenv("CCDASH_PROJECT_ROOT", "")
        self.integrity_repo = get_test_integrity_repository(db)

    async def check_run(
        self, run_id: str, git_sha: str, project_id: str
    ) -> list[TestIntegritySignalDTO]:
        """
        Main entry point. Called from background task after ingestion.
        Returns list of signals generated (also stored to DB).
        """
        if not self.git_path or not self._git_available():
            logger.info("Git not available; skipping integrity check for run %s", run_id)
            return []

        signals = []
        try:
            diff = await self._get_git_diff(git_sha)
            test_file_changes = self._extract_test_file_changes(diff)

            for file_path, change_data in test_file_changes.items():
                signals.extend(await self._analyze_file_changes(
                    file_path, change_data, git_sha, run_id, project_id
                ))
        except Exception as e:
            logger.warning("Integrity check failed for run %s: %s", run_id, e)

        return signals
```

### Signal Detection Rules

#### `assertion_removed`
- Check diff for removed lines containing: `assert `, `assertEqual`, `assertRaises`, `assertTrue`, `assertFalse`, `assert_called`
- Added lines do NOT trigger (only removed)
- Minimum: 1 assertion line removed
- Confidence: high if whole assertion block removed; medium if single assert removed

#### `skip_introduced`
- Check diff for added lines containing: `pytest.skip(`, `@pytest.mark.skip`, `unittest.skip(`, `@skip(`
- Any skip introduction triggers signal (confidence: high)

#### `xfail_added`
- Check diff for added lines containing: `@pytest.mark.xfail`, `pytest.xfail(`
- Confidence: medium (xfail can be legitimate for known bugs)

#### `broad_exception`
- Check diff for added lines containing exception catches that catch base classes: `except Exception:`, `except BaseException:`, `except:` in a test context
- Must be inside a function starting with `test_`
- Confidence: medium

#### `edited_before_green`
- Temporal correlation: test file modified in the same git_sha or within 5 minutes before test went green
- Requires: test_result status changed from `failed` -> `passed` in this run vs prior run
- Check git blame for file modification timestamp vs run timestamp
- Confidence: high if test was failing in prior run and passes now with file changes

### Git Integration

```python
async def _get_git_diff(self, git_sha: str) -> str:
    """Get diff for git_sha relative to its parent."""
    try:
        result = await asyncio.create_subprocess_exec(
            "git", "diff", f"{git_sha}^", git_sha,
            cwd=self.git_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()
        if result.returncode != 0:
            logger.warning("git diff failed: %s", stderr.decode())
            return ""
        return stdout.decode()
    except FileNotFoundError:
        logger.warning("git command not found; integrity detection disabled")
        return ""
```

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------------|---------------------|--------------|
| MAP-1 | MappingProvider protocol + MappingResolver | Define `MappingProvider` protocol. Implement `MappingResolver` orchestrator with provider registration, conflict resolution, and upsert to `test_feature_mappings`. Implement `_merge_candidates()` with confidence-based `is_primary` logic. | Protocol defined. Resolver merges candidates correctly. is_primary set to highest-confidence per test_id. Unit tests cover conflict scenarios. | 2 | python-backend-engineer | Phase 1 (mappings repo) |
| MAP-2 | RepoHeuristicsProvider | Implement path-based and name-based heuristic mapping. Fuzzy feature name matching against DB features. Domain creation/lookup. | Maps tests in `tests/{domain}/{feature}/` structure with > 70% accuracy on sample project. Unit tests with mock feature DB. | 2 | python-backend-engineer | MAP-1 |
| MAP-3 | TestMetadataProvider | Implement marker/tag extraction from test source files. Support: `@pytest.mark.feature(...)`, `@pytest.mark.domain(...)`, inline tag lists. Read from `CCDASH_PROJECT_ROOT` if available, else fall back to tags_json. | Extracts markers from real pytest files. Tags_json fallback works. High-confidence (0.9) for explicit feature markers. | 2 | python-backend-engineer | MAP-1 |
| MAP-4 | SemanticLLMProvider + import endpoint | Implement provider that accepts pre-loaded mapping dict. Add `POST /api/tests/mappings/import` endpoint that accepts JSON mapping file, runs SemanticLLMProvider, and stores results. Gate with `CCDASH_SEMANTIC_MAPPING_ENABLED`. | Import endpoint accepts valid JSON mapping file. Mappings stored with `provider_source: 'semantic_llm'`. Invalid format returns 400. Feature flag blocks endpoint when disabled. | 2 | python-backend-engineer | MAP-1 |
| MAP-5 | Wire background task | Fill in Phase 2's `_trigger_mapping_resolution()` stub with actual call to `MappingResolver.resolve_for_run()`. Wrap in try/except to prevent ingestion failures from mapping errors. Log resolution summary. | Background task runs after ingest. Resolution summary logged. Mapping errors don't bubble to ingest response. | 1 | python-backend-engineer | MAP-2, MAP-3, MAP-4 |
| MAP-6 | IntegrityDetector core | Implement `IntegrityDetector.check_run()`. Git diff extraction. Test file change extraction. `_git_available()` guard. Graceful degradation when Git unavailable. | Detector runs without crashing. When Git unavailable, returns [] and logs warning. When Git available but test file not modified, returns []. | 1 | backend-architect | Phase 1 (integrity repo) |
| MAP-7 | Signal detection rules | Implement all 5 signal detection functions: `assertion_removed`, `skip_introduced`, `xfail_added`, `broad_exception`, `edited_before_green`. Each operates on diff text + prior test result. | All 5 signal types detected on crafted test diffs. False positive rate < 10% on sample test files. Signals stored with correct severity. | 2 | backend-architect | MAP-6 |
| MAP-8 | Wire integrity background task + config | Fill in Phase 2's `_trigger_integrity_check()` stub. Add `CCDASH_INTEGRITY_SIGNALS_ENABLED` check. Add `CCDASH_PROJECT_ROOT` config var. | Integrity check runs after ingest when flag enabled. Skip when disabled. Project root defaults to cwd when not set. | 1 | python-backend-engineer | MAP-7 |

---

## Quality Gates

- [ ] `MappingProvider` protocol is `@runtime_checkable`
- [ ] `isinstance(provider, MappingProvider)` passes for all 3 provider implementations
- [ ] Conflict resolution: test mapped by two providers produces two DB rows, only one with `is_primary=True`
- [ ] `RepoHeuristicsProvider` maps test in `tests/auth/test_login.py` to domain "auth"
- [ ] `TestMetadataProvider` extracts `@pytest.mark.feature("my-feature")` correctly
- [ ] `SemanticLLMProvider` import endpoint returns 400 on malformed JSON
- [ ] Integrity detector returns `[]` when `git` not installed (no exception)
- [ ] `assertion_removed` signal detected on diff with `- assert response.status_code == 200`
- [ ] `skip_introduced` signal detected on diff with `+ @pytest.mark.skip`
- [ ] Signals stored in `test_integrity_signals` with correct `signal_type` and `severity`
- [ ] Background tasks run without blocking ingest response
- [ ] Unit tests: > 80% line coverage for `mapping_resolver.py` and `integrity_detector.py`

---

## Key Files Created / Modified

| File | Action | Notes |
|------|--------|-------|
| `backend/services/mapping_resolver.py` | Created | MappingProvider protocol, MappingResolver, 3 providers |
| `backend/services/integrity_detector.py` | Created | IntegrityDetector with 5 signal types |
| `backend/config.py` | Modified | CCDASH_INTEGRITY_SIGNALS_ENABLED, CCDASH_SEMANTIC_MAPPING_ENABLED, CCDASH_PROJECT_ROOT |
| `backend/routers/test_visualizer.py` | Modified | Add POST /api/tests/mappings/import endpoint |
| `backend/services/test_ingest.py` | Modified | Fill in _trigger_mapping_resolution and _trigger_integrity_check stubs |
| `backend/tests/test_mapping_resolver.py` | Created | Unit tests for all 3 providers + resolver |
| `backend/tests/test_integrity_detector.py` | Created | Unit tests for all 5 signal types |
