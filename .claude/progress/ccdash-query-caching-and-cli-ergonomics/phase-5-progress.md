---
schema_version: 2
doc_type: progress
type: progress
prd: "ccdash-query-caching-and-cli-ergonomics"
feature_slug: "ccdash-query-caching-and-cli-ergonomics"
phase: 5
title: "Testing, Observability, and Documentation Finalization"
status: pending
created: 2026-04-14
updated: 2026-04-14 (TEST-002.5, TEST-003.5, DOC-007 added; DOC-001/002/005/008 expanded)
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md
commit_refs: []
pr_refs: []
owners: ["python-backend-engineer"]
contributors: ["documentation-writer", "changelog-generator", "ai-artifacts-engineer"]
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 16
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "TEST-001"
    description: "CLI timeout comprehensive tests: precedence (flag>env>default), invalid values, RuntimeClient wiring, doctor output"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CLI-006"]
    estimated_effort: "1.5 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "TEST-002"
    description: "DTO alias fields comprehensive tests: deserialization includes name/status/telemetry_available, alias fields populated correctly from service, parity (alias==nested), backward compat (nested access still works), telemetry_available semantics correct"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["DTO-006"]
    estimated_effort: "1.5 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "TEST-002.5"
    description: "linked_sessions reconciliation integration test: assert feature_show.linked_sessions == feature_sessions endpoint result for same feature. Also test that the hint is displayed in CLI/MCP output. CI regression guard."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["REC-005"]
    estimated_effort: "1 pt"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "TEST-003"
    description: "Cache comprehensive unit+integration suite: hit/miss, TTL expiry, fingerprint invalidation, bypass, degradation, size limits. >80% coverage."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CACHE-011"]
    estimated_effort: "2 pts"
    priority: "high"
    assigned_model: "sonnet"
    model_effort: "medium"

  - id: "TEST-003.5"
    description: "Feature-list pagination and filtering integration suite: (1) default limit is 200; (2) truncated and total fields correct; (3) keyword filter works (--q / ?q=); (4) filter is case-insensitive substring match; (5) truncation hint displays correctly in CLI"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["PAGINATE-004", "FILTER-003"]
    estimated_effort: "1.5 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "TEST-004"
    description: "Background job comprehensive suite: interval, non-blocking, disablement (interval=0), error handling, cache warm after run"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["BG-005"]
    estimated_effort: "1.5 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "medium"

  - id: "TEST-005"
    description: "E2E CLI test: --timeout on slow query completes without timeout error. Document operator smoke-test procedure."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["CLI-005"]
    estimated_effort: "1 pt"
    priority: "low"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "TEST-006"
    description: "Full test suite pass: backend/tests/ CI green; mypy and ruff clean for all modified files; >80% coverage on new modules"
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TEST-001", "TEST-002", "TEST-002.5", "TEST-003", "TEST-003.5", "TEST-004", "TEST-005"]
    estimated_effort: "1 pt"
    priority: "high"
    assigned_model: "sonnet"
    model_effort: "low"

  - id: "DOC-001"
    description: "Update CHANGELOG.md: (1) CLI timeout via --timeout / CCDASH_TIMEOUT; (2) Query caching for 4 endpoints; (3) FeatureForensicsDTO alias fields name/status/telemetry_available; (4) Feature list default 200 with truncation hint and keyword filtering; (5) Feature-show linked_sessions reconciliation. Keep A Changelog format."
    status: "pending"
    assigned_to: ["changelog-generator"]
    dependencies: ["TEST-006"]
    estimated_effort: "0.5 pts"
    priority: "low"
    assigned_model: "haiku"
    model_effort: "low"

  - id: "DOC-002"
    description: "Update CLAUDE.md Commands & Configuration section: (1) CLI flag --timeout SECONDS; (2) Env vars CCDASH_TIMEOUT, CCDASH_QUERY_CACHE_TTL_SECONDS, CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS; (3) CLI flags --no-cache, --q <keyword>. Keep ≤15 lines; one-liners only."
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["TEST-006"]
    estimated_effort: "0.5 pts"
    priority: "low"
    assigned_model: "haiku"
    model_effort: "low"

  - id: "DOC-003"
    description: "Create docs/guides/query-cache-tuning-guide.md: 4 cached endpoints, TTL, background materialization, bypass, OTel monitoring, troubleshooting. <500 words."
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["TEST-006"]
    estimated_effort: "1 pt"
    priority: "medium"
    assigned_model: "haiku"
    model_effort: "low"

  - id: "DOC-004"
    description: "Create docs/guides/cli-timeout-debugging.md: causes, --timeout / CCDASH_TIMEOUT, ccdash doctor diagnosis, escalation path. <300 words."
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["TEST-006"]
    estimated_effort: "0.5 pts"
    priority: "low"
    assigned_model: "haiku"
    model_effort: "low"

  - id: "DOC-005"
    description: "Expand .claude/skills/ccdash/ skill spec: (1) Add Known Gotchas section to SKILL.md covering default limit (50→200), dual linked_sessions fields, keyword search brittleness, timeout behavior; (2) Add new recipe recipes/feature-retrospective.md (feature list → filter → feature show → feature sessions); (3) Add new recipe recipes/task-attribution.md (linked_tasks[].owner for agent-role attribution); (4) Update recipes/unreachable-server.md to distinguish transport failures from endpoint-specific timeouts; (5) Document --timeout, --no-cache, --q flags in CLI spec."
    status: "pending"
    assigned_to: ["ai-artifacts-engineer"]
    dependencies: ["TEST-006"]
    estimated_effort: "1.5 pts"
    priority: "medium"
    assigned_model: "sonnet"
    model_effort: "medium"

  - id: "DOC-006"
    description: "Update implementation plan frontmatter: status, commit_refs, pr_refs, files_affected, updated date"
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["DOC-001", "DOC-002", "DOC-003", "DOC-004", "DOC-005"]
    estimated_effort: "0.5 pts"
    priority: "low"
    assigned_model: "haiku"
    model_effort: "low"

  - id: "DOC-007"
    description: "Finalize deferred items and findings doc: check deferred_items_spec_refs — populate with placeholder design-spec path for 'Document body retrieval' deferred item (or mark resolved). Check findings_doc_ref — confirm null or update if findings doc was created during implementation. Update deferred items section in plan if needed."
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["DOC-006"]
    estimated_effort: "0.5 pts"
    priority: "low"
    assigned_model: "haiku"
    model_effort: "low"

  - id: "DOC-008"
    description: "Create .claude/worknotes/ccdash-query-caching-and-cli-ergonomics/feature-guide.md. Sections: (1) What Was Built (all five enhancements); (2) Architecture Overview (file/layer touches, phases); (3) How to Test (CLI + integration test instructions per enhancement); (4) Test Coverage Summary (phases 2/2.5/3/3.5/4, coverage); (5) Known Limitations. Keep <250 lines."
    status: "pending"
    assigned_to: ["documentation-writer"]
    dependencies: ["DOC-007"]
    estimated_effort: "1.5 pts"
    priority: "medium"
    assigned_model: "haiku"
    model_effort: "low"

parallelization:
  batch_1: ["TEST-001", "TEST-002", "TEST-002.5", "TEST-003", "TEST-003.5", "TEST-004", "TEST-005"]
  batch_2: ["TEST-006"]
  batch_3: ["DOC-001", "DOC-002", "DOC-003", "DOC-004", "DOC-005"]
  batch_4: ["DOC-006"]
  batch_5: ["DOC-007"]
  batch_6: ["DOC-008"]
  critical_path: ["TEST-003", "TEST-006", "DOC-001", "DOC-006", "DOC-007", "DOC-008"]
  estimated_total_time: "1.5-2 days"

blockers: []

success_criteria:
  - { id: "SC-5.1", description: "All unit/integration tests pass (>80% coverage on new modules)", status: "pending" }
  - { id: "SC-5.2", description: "mypy and ruff clean for all modified files", status: "pending" }
  - { id: "SC-5.3", description: "CHANGELOG entry added", status: "pending" }
  - { id: "SC-5.4", description: "CLAUDE.md updated with new env vars and flags", status: "pending" }
  - { id: "SC-5.5", description: "Operator guides created (query-cache-tuning, cli-timeout-debugging)", status: "pending" }
  - { id: "SC-5.6", description: "CLI skill SKILL.md updated with Known Gotchas section, new recipes (feature-retrospective, task-attribution), updated unreachable-server recipe, and new CLI flags documented", status: "pending" }
  - { id: "SC-5.7", description: "Implementation plan frontmatter populated (commit_refs, pr_refs, files_affected, status)", status: "pending" }
  - { id: "SC-5.8", description: "Deferred items finalized in plan (doc-retrieval placeholder or resolved); findings doc confirmed null or finalized", status: "pending" }
  - { id: "SC-5.9", description: "Feature guide created covering all five enhancements", status: "pending" }

files_modified:
  - "CHANGELOG.md"
  - "CLAUDE.md"
  - "docs/guides/query-cache-tuning-guide.md"
  - "docs/guides/cli-timeout-debugging.md"
  - ".claude/skills/ccdash/SKILL.md"
  - ".claude/skills/ccdash/recipes/feature-retrospective.md"
  - ".claude/skills/ccdash/recipes/task-attribution.md"
  - ".claude/skills/ccdash/recipes/unreachable-server.md"
  - ".claude/worknotes/ccdash-query-caching-and-cli-ergonomics/feature-guide.md"
  - "docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md"
  - "backend/tests/"
---

# CCDash Query Caching and CLI Ergonomics - Phase 5: Testing, Observability, and Documentation Finalization

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-query-caching-and-cli-ergonomics/phase-5-progress.md \
  -t TEST-001 -s completed
```

---

## Quick Reference

Batch 1 tests can all run in parallel. DOC tasks (batch 3) can run in parallel after TEST-006 passes.

**Cross-phase dependencies**: TEST-001 needs CLI-006 done; TEST-002 needs DTO-006 done; TEST-002.5 needs REC-005 done; TEST-003 needs CACHE-011 done; TEST-003.5 needs PAGINATE-004 and FILTER-003 done; TEST-004 needs BG-005 done; TEST-005 needs CLI-005 done.

| Task | Model | Effort | Invocation |
|------|-------|--------|-----------|
| TEST-001 | sonnet | low | `Task("TEST-001: Write pytest tests for CLI timeout: (1) flag>env>default precedence; (2) invalid values rejected; (3) RuntimeClient receives correct timeout; (4) doctor output shows active timeout + source. Prereq: CLI-006 complete.", model="sonnet")` |
| TEST-002 | sonnet | low | `Task("TEST-002: Write pytest tests for DTO alias fields: (1) deserialization includes name, status, telemetry_available; (2) service populates correctly; (3) parity (alias==nested); (4) nested access still works; (5) telemetry_available semantics correct (len>0 == true). Prereq: DTO-006 complete.", model="sonnet")` |
| TEST-002.5 | sonnet | low | `Task("TEST-002.5: Write pytest integration test asserting feature_show.linked_sessions == feature_sessions endpoint result for same feature. Also verify hint is displayed in CLI/MCP output. CI regression guard. Prereq: REC-005 complete.", model="sonnet")` |
| TEST-003 | sonnet | medium | `Task("TEST-003: Write pytest unit+integration suite for cache module: hit/miss on repeated calls, TTL expiry, fingerprint invalidation on data write, bypass_cache/--no-cache forces miss, graceful degradation on fingerprint failure, cache size limits. >80% coverage on cache.py. Prereq: CACHE-011 complete.", model="sonnet")` |
| TEST-003.5 | sonnet | low | `Task("TEST-003.5: Write pytest integration tests for feature-list pagination and keyword filtering: (1) default limit is 200; (2) truncated and total fields correct; (3) keyword filter --q / ?q= works; (4) case-insensitive substring match; (5) truncation hint displayed. Prereq: PAGINATE-004 and FILTER-003 complete.", model="sonnet")` |
| TEST-004 | sonnet | medium | `Task("TEST-004: Write pytest tests for background job: (1) job runs at configured interval; (2) HTTP requests not blocked; (3) interval=0 disables job; (4) job errors handled gracefully; (5) cache warm after job run. Prereq: BG-005 complete.", model="sonnet")` |
| TEST-005 | sonnet | low | `Task("TEST-005: Write e2e or documented smoke test: CLI invokes slow endpoint with --timeout 120; query completes without timeout error. Document operator procedure. Prereq: CLI-005 complete.", model="sonnet")` |
| TEST-006 | sonnet | low | `Task("TEST-006: Run full backend/tests/ suite. Fix any failures. Run mypy and ruff on all modified files; fix all issues. Confirm >80% coverage on new modules. Prereq: TEST-001 through TEST-005.", model="sonnet")` |
| DOC-001 | haiku | low | `Task("DOC-001: Add CHANGELOG.md entry under Enhancements: (1) CLI timeout via --timeout / CCDASH_TIMEOUT; (2) Query caching for 4 endpoints; (3) FeatureForensicsDTO alias fields name/status. Keep A Changelog format. Prereq: TEST-006.", model="haiku")` |
| DOC-002 | haiku | low | `Task("DOC-002: Update CLAUDE.md Configuration section with CCDASH_TIMEOUT, CCDASH_QUERY_CACHE_TTL_SECONDS, CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS env vars and --timeout global flag. ≤10 lines total added. Prereq: TEST-006.", model="haiku")` |
| DOC-003 | haiku | low | `Task("DOC-003: Create docs/guides/query-cache-tuning-guide.md. Cover: 4 cached endpoints, TTL defaults and override, background materialization cadence, disable cache (--no-cache/bypass_cache=true), OTel hit/miss monitoring, troubleshooting slow queries. <500 words. Prereq: TEST-006.", model="haiku")` |
| DOC-004 | haiku | low | `Task("DOC-004: Create docs/guides/cli-timeout-debugging.md. Cover: timeout causes, --timeout flag and CCDASH_TIMEOUT usage, ccdash doctor diagnosis, escalation. <300 words, actionable. Prereq: TEST-006.", model="haiku")` |
| DOC-005 | sonnet | medium | `Task("DOC-005: Expand .claude/skills/ccdash/ skill spec. (1) Add Known Gotchas section to SKILL.md: default limit 50→200, dual linked_sessions fields, keyword search brittleness, timeout behavior. (2) Create recipes/feature-retrospective.md: feature list → filter → feature show → feature sessions pattern. (3) Create recipes/task-attribution.md: using linked_tasks[].owner for agent-role attribution. (4) Update recipes/unreachable-server.md to distinguish transport failures from endpoint-specific timeouts. (5) Document --timeout, --no-cache, --q flags in CLI spec. Prereq: TEST-006.", model="sonnet")` |
| DOC-006 | haiku | low | `Task("DOC-006: Update docs/project_plans/implementation_plans/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md frontmatter: status→completed (if merged), populate commit_refs, pr_refs, files_affected, updated date. Prereq: DOC-001 through DOC-005.", model="haiku")` |
| DOC-007 | haiku | low | `Task("DOC-007: Finalize deferred items in plan frontmatter. Check deferred_items_spec_refs: populate with placeholder design-spec path for 'Document body retrieval' deferred item (or mark resolved). Check findings_doc_ref: confirm null or update if findings doc was created. Update deferred items section in plan if needed. Prereq: DOC-006.", model="haiku")` |
| DOC-008 | haiku | low | `Task("DOC-008: Create .claude/worknotes/ccdash-query-caching-and-cli-ergonomics/feature-guide.md with frontmatter (doc_type: feature_guide). Sections: (1) What Was Built (all five enhancements); (2) Architecture Overview; (3) How to Test (per enhancement); (4) Test Coverage Summary (phases 2/2.5/3/3.5/4); (5) Known Limitations. Keep <250 lines. Prereq: DOC-007.", model="haiku")` |

---

## Objective

Comprehensive test coverage, OTel instrumentation verification, and documentation finalization for all three enhancements. Gate the feature for PR creation.

---

## Implementation Notes

### Architectural Decisions

- Tests in batch 1 (TEST-001 through TEST-005) are independent of each other and can run in parallel across agents.
- DOC tasks gate on TEST-006 (CI green) before writing docs — ensures docs describe the real implemented behavior.
- DOC-007 from the plan (findings doc finalization) is confirmed N/A: the plan notes no deferred items and no findings doc was created. No task needed.

### Cross-Phase Dependencies

All tasks in batch 1 depend on a specific completed task from prior phases:
- TEST-001 → CLI-006 (Phase 1)
- TEST-002 → DTO-006 (Phase 2)
- TEST-002.5 → REC-005 (Phase 2.5)
- TEST-003 → CACHE-011 (Phase 3)
- TEST-003.5 → PAGINATE-004, FILTER-003 (Phase 3.5)
- TEST-004 → BG-005 (Phase 4)
- TEST-005 → CLI-005 (Phase 1)

### Known Gotchas

- DOC-005: The CCDash CLI skill spec path is likely `.claude/skills/ccdash/` but verify exact file before editing.
- TEST-003: Use a short TTL (e.g., 2 s) for TTL-expiry tests; do not use `time.sleep()` in async test code — use `asyncio.sleep()` or freeze time with `freezegun`.

### PR Creation (after DOC-008)

After feature guide is committed, open the PR per the plan's wrap-up section:
```bash
gh pr create \
  --title "feat(cli, cache): configurable timeout, query caching, DTO aliases" \
  --body "..."
```

---

## Completion Notes

_(Fill in when phase is complete)_
