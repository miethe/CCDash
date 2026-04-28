---
type: progress
schema_version: 2
doc_type: progress
prd: containerized-deployment-v1-followups
feature_slug: containerized-deployment-v1-followups
plan_ref: docs/project_plans/implementation_plans/infrastructure/containerized-deployment-v1.md
title: "Containerized Deployment v1 \u2014 Phase 7 Follow-ups"
status: completed
created: '2026-04-27'
updated: '2026-04-27'
owners:
- opus-orchestrator
tasks:
- id: FU-001
  description: "Frontend image size: reduce \u226450 MB (currently 61.1 MB). Audit\
    \ layers; switch to nginx:1.27-alpine-slim or unprivileged variant; verify functional\
    \ parity"
  status: completed
  assigned_to:
  - devops-architect
- id: FU-002
  description: 'AC-3 external-Postgres: add compose override removing optional postgres
    depends_on so podman-compose 1.5.0 (no required:false support) can run --profile
    enterprise alone'
  status: completed
  assigned_to:
  - devops-architect
  evidence:
  - note: compose.external-postgres.yaml using !reset on depends_on; verified via
      podman-compose ... config rendering api/worker without depends_on
- id: FU-003
  description: "Quickstart drift: replace `http://backend:8000` \u2192 `http://api:8000`;\
    \ add CCDASH_WORKER_PROJECT_ID to env-var table for enterprise profile"
  status: completed
  assigned_to:
  - documentation-writer
- id: FU-004
  description: "Investigate 4\u20136 pre-existing test_runtime_bootstrap failures\
    \ (pytest hangs on collection in current env); identify root cause; fix or document\
    \ as known-skip with reason"
  status: completed
  assigned_to:
  - ultrathink-debugger
  evidence:
  - note: 5 @unittest.skip decorators added with FU-004 traceability. Identified production
      drift in bootstrap._build_health_payload (drops authGuardrail, probeDetailWarningCodes)
      and _build_detail_probe_payload (drops detail.warningCodes/warnings/auth); 1
      test bug (wrong reload module); 1 macOS UE-zombie hang triggered by test_worker_process_starts_without_http_server.
      Production fixes deferred to separate ticket per task guardrail.
- id: FU-005
  description: 'Backfill commit_refs in phase-{4,5,7}-progress files with real SHAs
    (c233b8d, 48bbaca); replace "commit: pending" entries; do NOT amend git history'
  status: completed
  assigned_to:
  - opus-orchestrator
context_summary: "Phase 7 of containerized-deployment-v1 shipped with 5 advisory follow-ups.\n\
  Items 1\u20133 are localized fixes. Item 4 is investigation. Item 5 is local file\n\
  edits only; no `git rebase`/`git commit --amend` because target commits\nc233b8d/48bbaca\
  \ are already in shared history.\n"
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
progress: 100
---

# Containerized Deployment v1 — Phase 7 Follow-ups

Quick-feature remediation of advisory items recorded after phase-7 completion.

## Items

1. **Frontend image size** — currently 61.1 MB vs 50 MB gate. Audit Dockerfile layers; switch base or trim assets.
2. **AC-3 enterprise external-Postgres** — `podman-compose 1.5.0` does not honor `required: false` on `depends_on`. Add a compose override removing the optional postgres dependency for the external-Postgres scenario.
3. **Quickstart drift** — `docs/guides/containerized-deployment-quickstart.md` line 172 references `http://backend:8000`; default upstream is `http://api:8000`. Also add `CCDASH_WORKER_PROJECT_ID` to the env-var table (currently mentioned only in troubleshooting at line 199).
4. **Pre-existing test failures** — `backend/tests/test_runtime_bootstrap.py` collection hangs in current env; investigate, identify failures, fix or document with explicit skip reason.
5. **Commit SHA backfill** — replace `commit: pending` evidence + populate `commit_refs:` frontmatter in `.claude/progress/containerized-deployment-v1/phase-{4,5,7}-progress.md` with actual SHAs (c233b8d Phase 4-Postgres-profile, 48bbaca Phase 4-5-7 ship). No history rewrite.

## Out of scope

- Distroless migration (would require new nginx pipeline; revisit if alpine-slim insufficient).
- Upgrading podman-compose (operator-side dependency).

## FU-004 production-drift handoff (NOT in this PR)

Investigation of `test_runtime_bootstrap.py` surfaced four real defects that pre-date this work. They are tracked here for a follow-up ticket; the test suite skips them with explicit FU-004 markers so signal isn't lost.

- `backend/runtime/bootstrap.py::_build_health_payload` drops `authGuardrail` and `probeDetailWarningCodes` even though `RuntimeContainer.runtime_status()` (`backend/runtime/container.py:364–366`) still produces them. Two skipped tests cover this regression.
- `backend/runtime/bootstrap.py::_build_detail_probe_payload` rebuilds the `detail` block by hand and omits `warningCodes`, `warnings`, and the `auth` subtree present in the underlying probe contract.
- `test_health_endpoint_exposes_runtime_perf_defaults` is a test-side bug: it reloads `backend.runtime.bootstrap` and calls `bootstrap_mod.build_local_app()`, but `build_local_app` lives in `backend.runtime.bootstrap_local`.
- `test_worker_process_starts_without_http_server` invokes `serve_worker(...)` inside `IsolatedAsyncioTestCase`; on macOS this leaks a worker process that wedges the Python interpreter in uninterruptible-exit state, cascading to every subsequent invocation. Recommended remediation: relocate to a subprocess-isolated module so the leak dies with the subprocess. Whole `RuntimeBootstrapLifecycleTests` class is skipped meanwhile.

Final expected outcome (post-reboot verification recommended): 37 sync tests run, 4 skipped for production-drift, 11 lifecycle tests skipped, 0 failures.
