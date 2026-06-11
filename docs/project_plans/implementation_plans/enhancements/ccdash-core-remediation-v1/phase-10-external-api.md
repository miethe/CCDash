---
schema_version: 2
doc_type: phase_plan
title: "CCDash Core Remediation v1 — Phase 10: External API (IntentTree)"
status: draft
created: 2026-06-10
updated: 2026-06-10
phase: 10
phase_title: External API (IntentTree)
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
integration_owner: api-designer
entry_criteria:
  - Phase 0 (cross-project session correctness) green — zero-leak contract holds for cross-project reads.
  - Phase 1 (transport-neutral transcript service + redaction) shipped — redaction layer enforced on all egress.
  - Phase 2 (/api/v1 detail + transcript endpoints) shipped — v1 handlers + response models + contracts package exist and pin envelope.
  - `CCDASH_*` config surface (config.py) available for new CORS/bind/auth env vars.
exit_criteria:
  - IntentTree can list, search, and detail sessions from any project_id via documented `/api/v1` schema (cross-project param honored).
  - OpenAPI spec committed to repo and contract test pins the response envelope shape.
  - Capability advertisement endpoint live and lists `sessions:cross-project` and `sessions:detail`.
  - CORS, LAN bind, and auth (OQ-6 resolution) documented and config-gated; default posture is local-trust.
  - Example client checked in and exercised against a running instance (smoke).
  - task-completion-validator sign-off; api-documenter OpenAPI review sign-off.
---

# Phase 10: External API (IntentTree)

## Overview

Phase 10 promotes the `/api/v1` surface (built up through Phases 1–2) into a **documented external contract** for the IntentTree consumer and other LAN agents. This is a packaging-and-contract phase, not a retrieval-engine phase: the cross-project list/search/detail/transcript behavior already exists from Phases 0–2. Phase 10 adds (1) a checked-in OpenAPI spec, (2) a capability-advertisement endpoint so consumers can discover `sessions:cross-project` and `sessions:detail` support, (3) CORS / bind-host / auth configuration for cross-host LAN use under the operator's local-trust model (resolving OQ-6: bearer-token vs none-on-LAN), (4) a contract test pinning the envelope shape, and (5) a runnable example client.

Architecture, conventions, and the router→service→repository pattern are defined in `CLAUDE.md`; the transport-neutral query layer lives under `backend/application/services/agent_queries/`. This phase does NOT introduce new intelligence reads — it exposes and documents existing ones. PRD §FR-19, §6.2 (Security/egress, OQ-6), and the Phase 10 acceptance checklist (PRD §"External API / IntentTree") are the authoritative scope.

Per the decisions block: egress is local-trust on all surfaces **with redaction already enforced upstream (Phase 1)**; this phase must not bypass redaction. The auth decision (OQ-6) is resolved here as a config-gated optional bearer token defaulting to none-on-LAN (local-trust), so IntentTree works out-of-the-box on a trusted LAN while a token can be required for tighter deployments.

**Risk note (decisions block §Risk Hotspots):** `config.py` and `backend/runtime/` are shared-file collision risks with sync/runtime phases (5/7/8). Phase 10's edits there are limited to **new additive CORS/bind/auth env vars + middleware registration only**; coordinate via integration_owner so these do not land concurrently with sync-file edits on the same lines.

## Entry Criteria

- Phase 0, 1, and 2 complete and green (see frontmatter `entry_criteria`).
- `/api/v1` cross-project detail + transcript endpoints return redacted, paginated payloads with a stable envelope (`{items, cursor, limit, nextCursor}`).
- Contracts package from Phase 2 present and importable.

## Exit Criteria

See frontmatter `exit_criteria`. Quality gate: **task-completion-validator** (mandatory) plus **api-documenter** OpenAPI sign-off. No UI surfaces in this phase, so the runtime smoke gate applies to the live HTTP API + example-client smoke (T10-007) rather than a browser check.

## Files Affected (cite-only — do NOT open)

Sourced from the decisions block key-files for the `/api/v1` surface and config; do not read these to author the plan.

- `backend/routers/client_v1.py` — v1 router; add capability-advertisement endpoint; wire CORS/auth dependency.
- `backend/routers/_client_v1_sessions.py` — v1 session handlers (list/search/detail/transcript); confirm cross-project param surfaced in external contract.
- `packages/ccdash_contracts/` — shared contract models; add capability model; response models are the OpenAPI source of truth.
- `backend/config.py` — additive `CCDASH_*` env vars for CORS origins, bind host, and optional bearer token.
- `backend/runtime/` (app bootstrap / container composition) — register CORS middleware + auth dependency under runtime profiles.
- `backend/models.py` — capability-advertisement response model (if not housed in contracts package).
- `docs/openapi/ccdash-v1.json` (or repo-canonical OpenAPI path) — checked-in spec artifact.
- `backend/tests/` — contract test pinning envelope + capability shape.
- `examples/intenttree-client/` (new) — example client script + README.
- `docs/guides/` — external-API / LAN-deployment guide (CORS, bind, auth, capability discovery).

## Task Table

**Column conventions** per the root template: `Estimate` = task size; `Model` = executor; `Effort` = reasoning budget (`adaptive`/`extended` for Claude). Agent + model routing taken from the decisions block (Phase 10 primary: api-designer / python-backend-engineer; secondary: api-documenter for OpenAPI). Executors `sonnet/adaptive`; docs `haiku/adaptive`.

| Task ID | Name | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|----------------------|-------|--------|
| T10-001 | Capability advertisement endpoint | Add a `/api/v1` capability-discovery endpoint that advertises supported capabilities (`sessions:cross-project`, `sessions:detail`) plus API version. Model in `packages/ccdash_contracts/`. Wire into `backend/routers/client_v1.py`. | See AC R10.1 | 1 pt | python-backend-engineer | sonnet | adaptive |
| T10-002 | Cross-project external contract surface | Confirm list/search/detail/transcript v1 handlers accept and honor the cross-project `project_id` param as the **external** contract (not active-project-bound), reusing Phase 2 wiring. Add explicit handler-level validation that `project_id` is required for cross-project reads. | See AC R10.2 | 1 pt | python-backend-engineer | sonnet | adaptive |
| T10-003 | CORS + LAN bind config | Add additive `CCDASH_*` env vars in `backend/config.py` for allowed CORS origins and bind host; register CORS middleware in `backend/runtime/` app bootstrap (gated, default permissive-on-LAN per local-trust). No edits outside the new config/middleware lines (shared-file discipline). | See AC R10.3 | 1 pt | python-backend-engineer | sonnet | adaptive |
| T10-004 | Auth model (OQ-6 resolution) | Resolve OQ-6: optional bearer-token auth dependency on `/api/v1`, **default none-on-LAN (local-trust)**. When `CCDASH_API_TOKEN` is set, require it on v1 routes; when unset, allow unauthenticated LAN access. Capability endpoint reachability matches the chosen posture. | See AC R10.4 | 1 pt | python-backend-engineer | sonnet | adaptive |
| T10-005 | Checked-in OpenAPI spec | Generate and commit the `/api/v1` OpenAPI spec artifact (response models from contracts package are the source of truth). Add a regen note/script so the spec is reproducible. | See AC R10.5 | 1 pt | api-documenter | haiku | adaptive |
| T10-006 | Contract + envelope pin test | Add a contract test pinning the list/detail response envelope (`{items, cursor, limit, nextCursor}`) and the capability-advertisement shape; fails on drift. Use named test files (per memory: never unscoped pytest). | See AC R10.6 | 1 pt | python-backend-engineer | sonnet | adaptive |
| T10-007 | Example IntentTree client + LAN smoke | Add `examples/intenttree-client/` (script + README) that discovers capabilities, lists/searches, and pulls one session detail from a **non-active** project over HTTP. Run against a live instance as the phase smoke (HTTP API only; no UI). | See AC R10.7 | 1 pt | python-backend-engineer | sonnet | adaptive |
| T10-008 | External-API / LAN-deployment doc | Author a `docs/guides/` guide covering capability discovery, CORS origins, bind host, auth (OQ-6 outcome), and the example client. Reference `CLAUDE.md` conventions by path; do not restate architecture. | See AC R10.8 | 0.5 pts | documentation-writer | haiku | adaptive |
| T10-009 | Quality gate — validator | task-completion-validator pass: verify all ACs met, OpenAPI committed, contract test green, example-client smoke executed, auth/CORS config documented. api-documenter signs off on OpenAPI. | Phase exit_criteria satisfied; validator + api-documenter sign-off recorded in progress file | 0.5 pts | task-completion-validator | sonnet | adaptive |

**Total estimate: ~8 pts** (PRD anchor ~5 pts + ~18% hidden plumbing for OpenAPI/contracts/example-client/config, per decisions-block estimation anchors).

## Structured Acceptance Criteria

Per AC-schema (`.claude/skills/planning/references/ac-schema.md`) and Plan Generator Rule **R-P1**: ACs using scope words ("any project", "all surfaces") are expanded with explicit targets. There are **no `*.tsx` surfaces** in this phase, so `target_surfaces` lists name the API/contract/config surfaces consumed by the external contract; `resilience` is given for the optional backend fields introduced (capability list, auth token). R-P4 (UI runtime-smoke task) does not apply; the HTTP/example-client smoke (T10-007) covers the runtime gate.

#### AC R10.1: Capability advertisement lists cross-project + detail support
- target_surfaces:
    - backend/routers/client_v1.py
    - packages/ccdash_contracts/
- propagation_contract: >
    The capability endpoint returns a typed model (defined in ccdash_contracts) listing
    `sessions:cross-project` and `sessions:detail` plus the API version string; client_v1.py
    serves it without reaching into active-project state.
- resilience: >
    Capabilities are a server-declared list; a consumer encountering an unknown capability MUST
    ignore it, not fail. Consumers feature-detect: absence of a capability means "unsupported",
    never assume presence.
- visual_evidence_required: false
- verified_by:
    - T10-006
    - T10-009

#### AC R10.2: Any-project list/search/detail/transcript via documented param
- target_surfaces:
    - backend/routers/_client_v1_sessions.py
    - backend/routers/client_v1.py
    - packages/ccdash_contracts/
- propagation_contract: >
    External consumers pass `project_id` as the documented query param; v1 handlers route to the
    Phase 1 transport-neutral service scoped to that project_id (NOT active-project-bound).
    Reuses Phase 2 wiring; no new retrieval path is introduced.
- resilience: >
    Missing/empty `project_id` on a cross-project read returns a 4xx with the ErrorResponse
    envelope, never silently falls back to the active project. The Phase 0 zero-leak contract is
    relied upon, not re-implemented.
- visual_evidence_required: false
- verified_by:
    - T10-006
    - T10-007
    - T10-009

#### AC R10.3: CORS + LAN bind configurable, local-trust default
- target_surfaces:
    - backend/config.py
    - backend/runtime/
- propagation_contract: >
    New additive `CCDASH_*` env vars (allowed CORS origins, bind host) read in config.py and
    consumed by CORS middleware + server bind in runtime app bootstrap. Edits confined to the new
    config/middleware lines (shared-file discipline with Phases 5/7/8).
- resilience: >
    Unset CORS-origins var → permissive-on-LAN default consistent with local-trust (documented).
    Unset bind-host var → retain current default bind. No new var being set must ever break an
    existing deployment.
- visual_evidence_required: false
- verified_by:
    - T10-008
    - T10-009

#### AC R10.4: Optional bearer auth, none-on-LAN default (OQ-6)
- target_surfaces:
    - backend/routers/client_v1.py
    - backend/config.py
    - backend/runtime/
- propagation_contract: >
    `CCDASH_API_TOKEN` (new, optional) read in config.py; an auth dependency on /api/v1 routes
    enforces it when set and is a no-op when unset (local-trust none-on-LAN).
- resilience: >
    Token unset → unauthenticated LAN access allowed (local-trust default). Token set but request
    missing/incorrect → 401 with ErrorResponse envelope. Both states are documented and
    contract-stable; absence of the token var is a supported configuration, not an error.
- visual_evidence_required: false
- verified_by:
    - T10-008
    - T10-009

#### AC R10.5: OpenAPI spec checked in and reproducible
- target_surfaces:
    - docs/openapi/ccdash-v1.json
    - packages/ccdash_contracts/
- propagation_contract: >
    Request/response models in ccdash_contracts are the single source of truth; the committed
    OpenAPI artifact is generated from them via a documented regen step, so the spec cannot drift
    from the contracts package undetected.
- resilience: >
    If regenerated and differing from the committed artifact, the contract test (R10.6) surfaces
    the drift rather than letting a stale spec ship silently.
- visual_evidence_required: false
- verified_by:
    - T10-005
    - T10-006
    - T10-009

#### AC R10.6: Contract test pins envelope + capability shape
- target_surfaces:
    - backend/tests/
    - packages/ccdash_contracts/
- propagation_contract: >
    A named contract test asserts the list/detail envelope (`{items, cursor, limit, nextCursor}`)
    and the capability-advertisement response shape; it fails on any field add/remove/rename.
- resilience: >
    Test runs via a named test file (never unscoped `pytest backend/tests` — per project memory on
    collection hangs). Drift in either the envelope or the OpenAPI spec fails CI.
- visual_evidence_required: false
- verified_by:
    - T10-006
    - T10-009

#### AC R10.7: Example client round-trips a non-active project (smoke)
- target_surfaces:
    - examples/intenttree-client/
    - backend/routers/_client_v1_sessions.py
- propagation_contract: >
    The example client discovers capabilities, then lists/searches and pulls one session detail
    for a project that is NOT the active project, over HTTP against a running instance.
- resilience: >
    With redaction active (Phase 1), the client still receives a well-formed, redacted payload and
    must not assume unredacted content. If the target project has no sessions, the client handles
    an empty `items` list gracefully (no crash).
- visual_evidence_required: false
- verified_by:
    - T10-007
    - T10-009

#### AC R10.8: External-API / LAN-deployment guide
- target_surfaces:
    - docs/guides/
- propagation_contract: >
    Guide documents capability discovery, CORS origins, bind host, the OQ-6 auth outcome, and the
    example client. References CLAUDE.md / feature-surface-architecture.md by path; does not restate.
- resilience: >
    Guide states the local-trust default behavior explicitly so operators understand the
    unauthenticated-on-LAN posture and how to harden it (set CCDASH_API_TOKEN).
- visual_evidence_required: false
- verified_by:
    - T10-009

## Quality Gate

Phase 10 cannot be marked `completed` until:
- All ACs (R10.1–R10.8) verified.
- OpenAPI spec committed and api-documenter sign-off recorded.
- Contract test (T10-006) green via a named test file.
- Example-client HTTP smoke (T10-007) executed against a live instance (satisfies the runtime gate for this no-UI phase).
- CORS/bind/auth configuration documented (T10-008).
- **task-completion-validator** sign-off recorded in `.claude/progress/ccdash-core-remediation/phase-10-progress.md`.

## Dependencies & Sequencing

- **Upstream:** Phase 0 → 1 → 2 (critical path) must be green. Phase 10 sits on the `2 → 10` branch of the dependency map (decisions block §Dependency Map) and runs in Wave 4 alongside Phases 3 and 9.
- **Downstream:** Phase 12 (docs finalization + karen) folds this phase's surfaces into `feature-surface-architecture.md` and CHANGELOG.
- **Shared-file caution:** `config.py` and `backend/runtime/` are also touched by sync/runtime Phases 5/7/8. Single-thread these edits; integration_owner (api-designer) coordinates landing order so additive v1 config does not collide with sync-file edits.

## References (by path — do not restate)

- PRD: `docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md` (§FR-19, §6.2 Security/egress, §OQ-6, §"External API / IntentTree").
- Decisions block: `.claude/worknotes/ccdash-core-remediation/decisions-block.md` (Phase 10 row, Agent/Model Routing, Risk Hotspots, Dependency Map, OQ-6).
- Architecture/conventions: root `CLAUDE.md` (router→service→repository pattern, transport-neutral agent queries, config/`.env` conventions, runtime smoke gate, resilience-by-default).
- AC schema: `.claude/skills/planning/references/ac-schema.md`.
