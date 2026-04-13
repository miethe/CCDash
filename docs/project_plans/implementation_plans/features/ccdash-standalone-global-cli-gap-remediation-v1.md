---
schema_version: '1.0'
doc_type: implementation_plan
title: CCDash Standalone Global CLI - Gap Remediation Plan
description: Focused remediation plan for the post-implementation review gaps identified
  against the standalone global CLI PRD, design specs, and completed implementation
  plan.
status: completed
created: '2026-04-13'
updated: '2026-04-13'
feature_slug: ccdash-standalone-global-cli-gap-remediation
feature_version: v1
prd_ref: docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md
scope: Close high-priority review gaps in shared contracts, remote auth readiness,
  CLI surface parity, operator diagnostics, and release validation before upstream PR.
effort_estimate: 10-14 story points
effort_estimate_breakdown: 'Phase 1: 2.5-3.5 pts | Phase 2: 2-3 pts | Phase 3: 2.5-3.5
  pts | Phase 4: 3-4 pts'
priority: high
risk_level: medium
owner: Platform Engineering
contributors:
- Architecture Review Team
milestone: standalone-cli-pr-readiness
commit_refs:
- bd8b6c0
- 4257af6
- 4f34f8f
- 0192ba9
- 1a17a5b
pr_refs: []
files_affected: []
category: product-planning
tags:
- cli
- gap-remediation
- review-followup
- contracts
- auth
- release-readiness
related_documents:
- docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md
- docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md
- docs/project_plans/design-specs/cli-package-split-and-schemas.md
- docs/project_plans/design-specs/cli-target-model-and-auth.md
- docs/project_plans/design-specs/cli-versioned-api-surface.md
- docs/guides/standalone-cli-guide.md
- docs/guides/cli-migration-guide.md
---

# Implementation Plan: CCDash Standalone Global CLI Gap Remediation

## Executive Summary

The standalone global CLI implementation is materially complete, but the post-implementation review surfaced five notable gaps that should be closed before opening the upstream PR back to the parent branch:

1. The server-side v1 API contract is still duplicated instead of sourced from `ccdash_contracts`.
2. Remote-target bearer auth is implemented in the CLI but not actually enforced by the server runtime.
3. The operator surface is slightly off-spec: `ccdash --version` is missing.
4. Timeout diagnostics point to a nonexistent `--timeout` target option.
5. `ccdash target show` was planned but not shipped.

This remediation plan is intentionally narrow. It does not reopen the full standalone CLI scope. It closes review-blocking gaps, restores alignment with the PRD/design specs, and adds validation evidence suitable for the PR description.

**Scope**: shared contract convergence, remote auth closure, CLI surface parity, diagnostics cleanup, validation and docs alignment

**Total Effort**: 10-14 story points (expanded after Bob review 2026-04-13)

**Recommended Timeline**: 4 short phases across 2-4 days

**Critical Path**:

```text
Shared contract convergence
  ↓
Server auth enforcement for remote targets
  ↓
CLI parity and diagnostics cleanup
  ↓
Validation, docs alignment, PR evidence
```

---

## Review Inputs

This plan remediates the following findings:

| ID | Finding | Severity | Source |
|----|---------|----------|--------|
| GAP-1 | Shared client contract is duplicated instead of reused | P1 | Internal review |
| GAP-2 | Remote-target auth is only implemented on the CLI side | P1 | Internal review |
| GAP-3 | Required `ccdash --version` flow is missing | P2 | Internal review |
| GAP-4 | Timeout guidance points to a nonexistent CLI option | P2 | Internal review |
| GAP-5 | Planned `target show` command is missing | P2 | Internal review |
| GAP-6 | Broad `Exception` catch in `client.py` JSON parsing (line ~247) — should narrow to `json.JSONDecodeError` | P2 | Bob review (2026-04-13) |
| GAP-7 | Docstring f-string bug in `client.py` (line ~154) — `{_EXPECTED_API_VERSION}` won't interpolate in regular docstring | P3 | Bob review (2026-04-13) |
| GAP-8 | Missing return type annotations on several `client_v1.py` router endpoints | P3 | Bob review (2026-04-13) |
| GAP-9 | No README in `packages/ccdash_cli/` or `packages/ccdash_contracts/` | P2 | Bob review (2026-04-13) |
| GAP-10 | Comma-splitting logic duplicated across multiple command files — extract to shared utility | P3 | Bob review (2026-04-13) |
| GAP-11 | No command-level integration tests or formatter tests | P2 | Bob review (2026-04-13) |
| GAP-12 | No HTTPS warning for non-localhost HTTP targets | P3 | Bob review (2026-04-13) |

---

## Implementation Strategy

### Remediation principles

1. **Do not re-solve the whole feature**: only touch the surfaces needed to close the review findings.
2. **Make the contract actually shared**: the server and standalone CLI should deserialize the same DTOs and envelopes from one package.
3. **Close the auth loop end-to-end**: if the CLI can send bearer tokens, the runtime must have a real validation/enforcement path for remote targets.
4. **Prefer spec alignment over new invention**: restore planned commands and flags rather than expanding scope.
5. **Produce PR-ready evidence**: finish with passing validation steps, updated docs, and a short gap-closure summary.

### Architectural defaults for this remediation

1. `packages/ccdash_contracts/` becomes the source of truth for wire DTOs and envelopes.
2. `backend/routers/client_v1_models.py` is reduced to router-only adapters or removed entirely where duplication is unnecessary.
3. Remote auth is enforced on `/api/v1` using a runtime-aware bearer-token path that preserves local no-auth defaults.
4. Operator parity favors the PRD command names, with backwards-compatible aliases where low-cost.

---

## Phase Breakdown

| Phase | Goal | Effort | Key deliverables | Assigned subagent(s) |
|------|------|--------|------------------|----------------------|
| 1 | Converge shared contract ownership | 2-3 pts | single-source DTO/envelope usage across server and CLI | `backend-architect`, `python-backend-engineer` |
| 2 | Close remote auth gap end-to-end | 2-3 pts | bearer auth enforcement path for remote targets, local-safe defaults | `backend-architect`, `python-backend-engineer` |
| 3 | Restore CLI surface parity | 1-2 pts | `--version`, `target show`, corrected timeout guidance | `python-backend-engineer` |
| 4 | Validation and docs alignment | 2 pts | tests, smoke evidence, updated operator docs, PR-ready summary | `python-backend-engineer`, `documentation-writer` |

---

## Phase 1: Shared Contract Convergence

**Goal:** Ensure the standalone CLI contract is genuinely shared instead of duplicated between server and package-local model definitions.

| Task ID | Task | Description | Acceptance criteria | Estimate | Assigned subagent(s) |
|--------|------|-------------|---------------------|----------|----------------------|
| GAP-101 | Audit contract drift | Compare `backend/routers/client_v1_models.py` against `packages/ccdash_contracts/` and current server payloads. Document field-level mismatches before refactor. | Drift inventory exists and covers envelopes plus embedded DTOs. | 0.5 pt | `backend-architect` |
| GAP-102 | Move server v1 router to shared contracts | Update server-side `/api/v1` handlers to import DTO/envelope types from `ccdash_contracts` rather than local duplicates or backend-only models where those types are operator-facing. | Server compiles and returns v1 payloads using shared contract types. | 1 pt | `python-backend-engineer` |
| GAP-103 | Remove or reduce duplicate models | Delete duplicated fields/models where safe, or leave thin compatibility aliases with comments explaining ownership. | No active server path depends on divergent duplicate wire-model definitions. | 0.5 pt | `python-backend-engineer` |
| GAP-104 | Add contract parity tests | Extend contract tests to assert the server and package DTOs stay aligned for envelope and key payload shapes. | Automated tests fail on contract drift between server and `ccdash_contracts`. | 0.5-1 pt | `python-backend-engineer` |
| GAP-105 | Add return type annotations to `client_v1.py` endpoints | Several router endpoints are missing return type annotations (e.g., `-> ClientV1Envelope[ProjectStatusDTO]`), which degrades OpenAPI schema quality. | All `/api/v1` endpoints have explicit return type annotations. | 0.5 pt | `python-backend-engineer` |

### Phase 1 Quality Gate

- [ ] `ccdash_contracts` is the declared source of truth for `/api/v1` wire models.
- [ ] Server-side v1 responses no longer rely on backend-only DTO ownership for shared payloads.
- [ ] Contract tests cover at least instance, features, sessions, and error envelopes.

---

## Phase 2: Remote Auth Closure

**Goal:** Align runtime behavior with the PRD so remote targets can be authenticated in practice, not just configured in the CLI.

| Task ID | Task | Description | Acceptance criteria | Estimate | Assigned subagent(s) |
|--------|------|-------------|---------------------|----------|----------------------|
| GAP-201 | Decide v1 auth enforcement mode | Lock the minimal server-side bearer-token behavior for `/api/v1`, including local-default no-auth semantics and remote-target enforcement expectations. | Decision is documented in code comments and reflected in tests/docs. | 0.5 pt | `backend-architect` |
| GAP-202 | Implement bearer-token validation path | Add runtime auth handling so `/api/v1` can reject missing/invalid bearer tokens when auth is enabled, while preserving current local-no-auth behavior where intended. | Auth-enabled runtime returns 401/403 appropriately; local-default remains compatible. | 1-1.5 pts | `python-backend-engineer` |
| GAP-203 | Separate auth vs connectivity failures cleanly | Ensure the standalone CLI receives distinct exit-code-producing responses for 401, 403, and unreachable server cases. | CLI error handling matches PRD auth/connectivity distinctions end to end. | 0.5 pt | `python-backend-engineer` |
| GAP-204 | Add auth coverage | Add tests for unauthenticated, authenticated, and local-no-auth execution paths against `/api/v1`. | Test coverage proves remote auth is not CLI-only anymore. | 0.5-1 pt | `python-backend-engineer` |

### Phase 2 Quality Gate

- [ ] `/api/v1` can enforce bearer auth in an auth-enabled runtime.
- [ ] Local development still works without forcing tokens where the runtime is intentionally local/no-auth.
- [ ] Auth failures and connectivity failures are observably distinct to operators and scripts.

---

## Phase 3: CLI Surface Parity

**Goal:** Close the operator-facing mismatches between the shipped CLI and the planned command surface.

| Task ID | Task | Description | Acceptance criteria | Estimate | Assigned subagent(s) |
|--------|------|-------------|---------------------|----------|----------------------|
| GAP-301 | Add `ccdash --version` | Support the top-level version flag promised by the PRD, while preserving the existing `version` subcommand if desired for compatibility. | `ccdash --version` exits 0 and prints CLI version. | 0.5 pt | `python-backend-engineer` |
| GAP-302 | Add `target show` | Implement a target-inspection command that reports resolved active-target details without requiring `doctor`. | `ccdash target show` exists and clearly reports active target state. | 0.5-1 pt | `python-backend-engineer` |
| GAP-303 | Fix timeout guidance | Remove or replace the nonexistent `--timeout` remediation path in HTTP timeout messages, or implement actual timeout configuration if justified. | No user-facing error suggests an unsupported command/flag. | 0.5 pt | `python-backend-engineer` |
| GAP-304 | Reconcile command naming in docs/help | Align docs/help for `feature report` vs `report feature`, with a clear decision on canonical form and compatibility aliases if needed. | Operator docs and CLI help match the intended command surface. | 0.5 pt | `python-backend-engineer`, `documentation-writer` |
| GAP-305 | Narrow broad exception catch in `client.py` | JSON parsing at `client.py:~247` catches bare `Exception` — narrow to `json.JSONDecodeError` / `ValueError`. | No bare `Exception` catch for JSON parsing in the HTTP client. | 0.25 pt | `python-backend-engineer` |
| GAP-306 | Fix docstring f-string bug in `client.py` | `VersionMismatchError` docstring at line ~154 uses `{_EXPECTED_API_VERSION}` which won't interpolate in a regular docstring. Replace with literal `"v1"`. | Docstring accurately reflects the expected API version. | 0.25 pt | `python-backend-engineer` |
| GAP-307 | Extract comma-splitting utility | Comma-splitting logic for multi-value CLI options is duplicated across `feature.py`, `session.py`, and other command files. Extract to a shared helper. | Single shared utility for expanding comma-separated CLI values. | 0.5 pt | `python-backend-engineer` |
| GAP-308 | Add HTTPS warning for non-localhost HTTP targets | CLI silently accepts `http://` URLs for remote targets with no security warning. Add a warning when a non-localhost target uses plain HTTP. | CLI emits a warning when targeting non-localhost HTTP endpoints. | 0.25 pt | `python-backend-engineer` |

### Phase 3 Quality Gate

- [ ] The shipped CLI surface covers the review-identified missing operator commands/flags.
- [ ] Diagnostics never point to unsupported commands.
- [ ] Command naming is internally consistent across help text and guides.
- [ ] No bare `Exception` catches for typed error paths in the HTTP client.
- [ ] Duplicated CLI option parsing logic is extracted to shared utilities.
- [ ] Non-localhost HTTP targets emit a security warning.

---

## Phase 4: Validation, Docs, and PR Evidence

**Goal:** Produce the validation and documentation evidence missing from the initial completion claim so the upstream PR is reviewable on its own merits.

| Task ID | Task | Description | Acceptance criteria | Estimate | Assigned subagent(s) |
|--------|------|-------------|---------------------|----------|----------------------|
| GAP-401 | Run standalone package tests | Execute standalone CLI and `/api/v1` contract coverage in a working Python test environment. | Test commands and results are captured for the PR summary. | 0.5 pt | `python-backend-engineer` |
| GAP-402 | Add install/smoke evidence | Run at least one clean-install or isolated-package smoke flow covering `ccdash --version`, `ccdash doctor`, and one live command. | A reproducible smoke path exists and is documented. | 0.5-1 pt | `python-backend-engineer` |
| GAP-403 | Update guides | Align [standalone-cli-guide.md](../../../guides/standalone-cli-guide.md) and [cli-migration-guide.md](../../../guides/cli-migration-guide.md) with the final command/auth behavior. | Docs no longer describe commands or auth behavior that differ from shipping code. | 0.5 pt | `documentation-writer` |
| GAP-404 | Write PR gap-closure summary | Prepare a concise “closed review gaps” section suitable for the PR description. | Reviewers can see exactly which gaps were addressed and how they were validated. | 0.5 pt | `documentation-writer` |
| GAP-405 | Add README to `packages/ccdash_cli/` | Create README with installation instructions, quick start guide, configuration reference, and environment variable reference. | README exists with install, quick start, config reference, and troubleshooting sections. | 0.5 pt | `documentation-writer` |
| GAP-406 | Add README to `packages/ccdash_contracts/` | Create README explaining the contract package purpose, versioning strategy, and usage from both CLI and server. | README exists explaining package purpose and consumption patterns. | 0.25 pt | `documentation-writer` |
| GAP-407 | Add command integration tests and formatter tests | No tests invoke CLI commands end-to-end or verify formatter output. Add integration tests that exercise CLI invocation and output rendering. | Integration tests cover at least 3 command groups; formatter tests cover JSON/markdown/table output. | 1 pt | `python-backend-engineer` |

### Phase 4 Quality Gate

- [ ] Validation was run in a functioning Python environment.
- [ ] Standalone install/smoke evidence exists, not just unit-test coverage.
- [ ] User guides and migration docs describe the final shipped surface accurately.
- [ ] Both `packages/ccdash_cli/` and `packages/ccdash_contracts/` have README files.
- [ ] Command integration tests and formatter tests exist with meaningful coverage.
- [ ] The PR can explicitly claim which review findings are closed.

---

## Dependencies and Sequencing

### Strict dependencies

1. **Phase 2 depends on Phase 1** because auth enforcement should target the finalized shared `/api/v1` contract surface.
2. **Phase 3 can run partly in parallel with Phase 2** once command-surface decisions are fixed.
3. **Phase 4 depends on prior phases** because validation and docs must reflect the final behavior.

### Parallelization opportunities

1. CLI parity work (`--version`, `target show`, timeout guidance) can proceed while server auth tests are being implemented.
2. Documentation updates can begin once command naming and auth behavior are finalized.

---

## Out of Scope

The following are explicitly not part of this remediation plan:

1. New data domains beyond the existing standalone CLI scope.
2. Federation or cross-instance aggregation.
3. Full auth platform redesign beyond the minimal v1 remote-target closure.
4. Broad formatter or UX redesign unrelated to the review findings.

---

## Definition of Done

This gap plan is complete when:

1. The five review findings are either closed in code or explicitly downgraded/deferred with documented rationale.
2. `/api/v1` wire DTO ownership is shared and test-enforced.
3. Remote-target bearer auth is validated end to end where auth is enabled.
4. The CLI ships the planned operator parity fixes (`--version`, `target show`, corrected diagnostics).
5. Validation evidence and docs are ready to cite directly in the upstream PR.
