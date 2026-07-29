---
title: "Phase 1: Contract & Envelope Foundations"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-29
updated: 2026-07-29
feature_slug: "proof-to-routing-loop"
feature_version: "v1"
phase: 1
phase_title: "Contract & Envelope Foundations"
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
entry_criteria: ["PRD approved", "Decisions block D1-D8 locked"]
exit_criteria: ["Digest-parity test green", "CCDASH_ROUTING_FEEDBACK_ENABLED reads false by default"]
related_documents:
  - .claude/worknotes/proof-to-routing-loop/decisions-block.md
  - docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
  - docs/guides/aar-review-loop.md
spike_ref: null
adr_refs: []
charter_ref: docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-charter.md
changelog_ref: null
test_plan_ref: null
integration_owner: null
ui_touched: false
target_surfaces:
  - backend/application/services/agent_queries/routing_task_map_v1.json
  - backend/application/services/agent_queries/routing_feedback_contract.py
  - backend/routers/client_v1.py
  - backend/config.py
  - backend/tests/test_routing_feedback_contract_parity.py
seam_tasks: []
owner: null
contributors: []
priority: medium
risk_level: low
category: "product-planning"
tags: [phase-plan, implementation, infrastructure, routing-feedback, no-llm]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/application/services/agent_queries/routing_task_map_v1.json
  - backend/application/services/agent_queries/routing_feedback_contract.py
  - backend/routers/client_v1.py
  - backend/config.py
  - backend/tests/test_routing_feedback_contract_parity.py
---

# Phase 1: Contract & Envelope Foundations

**Parent Plan**: [Proof → Routing Feedback Loop — CCDash Producer Surface (BP-6)](../proof-to-routing-loop-v1.md)
**Duration**: ~1 day
**Effort**: 2 story points
**Dependencies**: None (first phase; critical-path entry point for the feature)
**Team Members**: backend-architect, python-backend-engineer

---

## Phase Overview

This phase lands the feature's frozen contract surface with **zero behavior change**. It vendors the
pinned cross-repo `routing-feedback-task-map.v1.json` mapping byte-for-byte, exposes its identity as
frozen Python constants (contract/taxonomy/mapping ids, versions, and SHA-256 digests), advertises the
`routing:feedback` capability string ahead of any route existing, and adds the default-off feature flag
plus its companion tunables. Every downstream phase (Data Layer, Rollup Compute Service, Worker Sweep
Job, Transport Surfaces, Validation/Guards/Docs) imports from this phase's constants module rather than
re-deriving any contract identity value — this is the seam-precision phase and is deliberately kept on
primary Claude (sonnet), not offloaded, per the decisions block's model-routing rationale.

This phase is a structural clone of the envelope-and-flag scaffolding step in the shipped Automated AAR
Review Loop: the capability string mirrors `"aar-review"` in `_V1_CAPABILITIES`
(`backend/routers/client_v1.py` ~line 153), and the config flag mirrors
`CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` and its sibling tunables (`backend/config.py` ~line 128),
using the existing `_env_bool`/`_env_int` helpers already defined at the top of that module.

### Goals

- Vendor the normative `routing-feedback-task-map.v1.json` mapping into CCDash at the pinned canonical
  path (OQ-5 resolution) with zero transformation.
- Freeze all eight contract/taxonomy/mapping identity constants — contract id/version, taxonomy
  id/version/digest, mapping id/version/digest — plus the capability string and the mapping's file path,
  in one importable module.
- Advertise the `routing:feedback` capability string in `_V1_CAPABILITIES` ahead of any route landing
  (Phase 5), so capability discovery is truthful the moment the flag is later flipped on.
- Add the default-off master flag `CCDASH_ROUTING_FEEDBACK_ENABLED` and its three companion tunables to
  `backend/config.py`, following the exact `CCDASH_AAR_REVIEW_*` helper pattern.
- Prove digest parity and the flag's off-by-default posture with a CI-enforced test, so any future
  accidental edit to the vendored mapping or the flag default fails the build immediately.

### Architecture Focus

This phase implements the **Contract/Envelope Foundation** layer — a pre-Database, pre-Service layer
that exists purely to freeze identity and configuration before any persistence or compute logic is
written:
- **Layer**: Pre-Database (contract constants + config flags); no DB, no router logic yet.
- **Patterns**: Vendored-artifact-with-digest-pin (same pattern as any cross-repo contract snapshot in
  this codebase); frozen-constants module (no runtime mutation, no environment override of identity
  fields — only the *flag* fields are environment-configurable); capability-advertisement-before-route
  (the `sessions:detail`/`aar-review` precedent already establishes that a capability string can be
  advertised independently of the route landing in the same phase).
- **Standards**: `_env_bool`/`_env_int` helpers (`backend/config.py` lines 13–27) are the only sanctioned
  way to read `CCDASH_*` env vars — no ad-hoc `os.getenv` calls in this or any later phase.

---

## Task Breakdown

### Epic: Contract & Envelope Foundations

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|-------------------|----------|---------------------|-------|--------|--------------|
| T1-001 | Vendor mapping JSON | Copy `routing-feedback-task-map.v1.json` verbatim (byte-for-byte, no transformation) from `agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json` into `backend/application/services/agent_queries/routing_task_map_v1.json` — this exact path is the canonical OQ-5 resolution, do not choose another. | File exists at the pinned path; bytes match source | 0.5 pts | backend-architect | sonnet | adaptive | None |
| T1-002 | Envelope constants module | New `backend/application/services/agent_queries/routing_feedback_contract.py` exposing frozen constants: `CONTRACT_ID="aos.routing.feedback"`, `CONTRACT_VERSION="1.0.0"`, `TAXONOMY_ID="aos.routing.task_class"`, `TAXONOMY_VERSION="1.0.0"`, `TAXONOMY_DIGEST="sha256:d96a0819b0a3a42d14eccc1421d3146b8364253d975d9d54f4f264d4b6adeaca"`, `MAPPING_ID="ccdash.skill_name_to_aos.routing.task_class"`, `MAPPING_VERSION="1.0.0"`, `MAPPING_DIGEST="sha256:45a49bb1a6194c6a576160edab7c3212a9cc20e17e6a0b79d531c1c4928f63f5"`, `PRODUCER="ccdash"`, `CAPABILITY_STRING="routing:feedback"`, `MAPPING_JSON_PATH` pointing at T1-001's file. | All 9 values present verbatim; sources AC-8 version fields | 0.5 pts | backend-architect | sonnet | adaptive | T1-001 |
| T1-003 | Capability string | Add `"routing:feedback"` to `_V1_CAPABILITIES` in `backend/routers/client_v1.py`, mirroring the existing `"aar-review"` entry with an inline comment noting the route lands in Phase 5. No route wired yet. | Capability advertised even while flag is off | 0.25 pts | python-backend-engineer | sonnet | adaptive | T1-002 |
| T1-004 | Config flag + tunables | In `backend/config.py` add `CCDASH_ROUTING_FEEDBACK_ENABLED` (bool, default `False`), `CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` (int, default `5`), `CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS` (int, default `30`), `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS` (bool, default `True`) near the existing `CCDASH_AAR_REVIEW_*` flags, same helper pattern. | All 4 env vars present with exact names/defaults | 0.25 pts | python-backend-engineer | sonnet | adaptive | None |
| T1-005 | Digest-parity + flag-default test | New `backend/tests/test_routing_feedback_contract_parity.py`: (a) SHA-256 of vendored JSON bytes == `MAPPING_DIGEST`; (b) `CCDASH_ROUTING_FEEDBACK_ENABLED` defaults False when unset. Phase 6 (T6-002) later extends this test. | Test passes; fails loudly on digest drift | 0.5 pts | backend-architect | sonnet | adaptive | T1-001, T1-002, T1-004 |

**Phase Total**: 2.0 pts

**Model Selection Guidance**: Refer to `.claude/config/multi-model.toml` for valid model values and
effort policies. All five tasks in this phase are Claude-primary (sonnet) — this phase is
precision-critical (digest pins, capability advertisement, config surface) and is explicitly **not**
ICA-offloaded per the decisions block's model-routing notes (§6): "Cross-repo/seam phases (P1, P3,
P6-parity) are not offloaded — precision + digest-fidelity outweigh cost-shift."

**Effort Policy** (see `.claude/config/multi-model.toml`):
- **adaptive**: Default reasoning for all five tasks in this phase — none require `extended` effort;
  the work is mechanical vendoring + constant definition + config wiring, not algorithmic design.

---

## Detailed Task Specifications

### Task T1-001: Vendor mapping JSON

**Estimate**: 0.5 points
**Assigned Subagent(s)**: backend-architect
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: None
**started**: null
**completed**: null
**verified_by**: [T1-005]
**evidence**: []

**Description**:
Copy the normative `routing-feedback-task-map.v1.json` file from
`agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json` into this repo at
`backend/application/services/agent_queries/routing_task_map_v1.json`. This is a **verbatim, byte-for-byte
copy** — no reformatting, no re-indentation, no key reordering, no trailing-newline normalization beyond
what the source file already has. The copied file is the OQ-5 resolution locked in the decisions block
and PRD frontmatter (`status: "resolved — backend/application/services/agent_queries/routing_task_map_v1.json"`)
— do not choose a different path, do not place it under `backend/config/` or any other directory.

**Acceptance Criteria**:
- [ ] `backend/application/services/agent_queries/routing_task_map_v1.json` exists at exactly this path
- [ ] File bytes are byte-for-byte identical to the source
      `agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json` (verify via
      `diff` or `sha256sum` comparison, not visual inspection)
- [ ] No transformation applied — same JSON key order, same whitespace, same trailing newline (or
      absence thereof) as the source file
- [ ] File is committed and readable at import time by `routing_feedback_contract.py` (T1-002)

**Implementation Notes**:
- Use a direct file copy (`cp` or equivalent), not a hand-retyped JSON literal — any manual retyping
  risks a silent single-character drift that the T1-005 digest test is specifically designed to catch,
  but it is cheaper to get this right at copy time than to debug a digest mismatch later.
- If the source file at `agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json`
  is unreachable (e.g., the `agentic_meta_dev` working directory is not checked out locally in this
  agent's environment), escalate rather than reconstructing the mapping from memory or from the PRD's
  §6.3 example snippet — the PRD example is illustrative only and is not the full mapping.
- This file has **no code dependents in this task** — T1-002 only references its *path*, not its
  contents, at this phase. Content-level mapping *application* logic (looking up `skill_name →
  task_class`) is Phase 3's concern (`RoutingRollupQueryService`), not this phase's.

**Files Involved**:
- `backend/application/services/agent_queries/routing_task_map_v1.json` - New file; verbatim vendored copy of the pinned cross-repo mapping artifact.

---

### Task T1-002: Envelope constants module

**Estimate**: 0.5 points
**Assigned Subagent(s)**: backend-architect
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T1-001
**started**: null
**completed**: null
**verified_by**: [T1-005]
**evidence**: []

**Description**:
Create `backend/application/services/agent_queries/routing_feedback_contract.py` — a new module
exposing nine frozen module-level constants plus one path constant, all defined as simple Python
literals (no dynamic computation, no environment-variable overrides — these are contract-identity
constants, not runtime configuration). This module is the **single source of truth** every downstream
phase imports from; no other module in this feature may re-declare or hardcode any of these values.

Required constants (verbatim values, per the task prompt):

```python
CONTRACT_ID = "aos.routing.feedback"
CONTRACT_VERSION = "1.0.0"
TAXONOMY_ID = "aos.routing.task_class"
TAXONOMY_VERSION = "1.0.0"
TAXONOMY_DIGEST = "sha256:d96a0819b0a3a42d14eccc1421d3146b8364253d975d9d54f4f264d4b6adeaca"
MAPPING_ID = "ccdash.skill_name_to_aos.routing.task_class"
MAPPING_VERSION = "1.0.0"
MAPPING_DIGEST = "sha256:45a49bb1a6194c6a576160edab7c3212a9cc20e17e6a0b79d531c1c4928f63f5"
PRODUCER = "ccdash"
CAPABILITY_STRING = "routing:feedback"
MAPPING_JSON_PATH = <path object pointing at T1-001's vendored file>
```

**Acceptance Criteria**:
- [ ] All 9 identity/version/digest values present, spelled exactly as specified above (no whitespace
      drift, no case changes)
- [ ] `CAPABILITY_STRING` constant present and equal to `"routing:feedback"`
- [ ] `MAPPING_JSON_PATH` resolves to the exact file written in T1-001 (prefer a `pathlib.Path` relative
      to `__file__` so the constant is correct regardless of process working directory)
- [ ] Module has no side effects at import time beyond defining these constants (no file I/O, no digest
      computation at import — the digest *verification* happens in T1-005's test, not here)
- [ ] Module docstring or inline comment cites this task ID and the pinned contract source
      (`agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md`) for future maintainers

**Implementation Notes**:
- These constants source PRD AC-8 ("Version-mismatch resilience") — every downstream response (enabled
  or disabled) must carry `contract_version`/`taxonomy_version`/`mapping_version` sourced from *this*
  module, never re-typed inline in a router/service/DTO file.
- Keep this module free of any import from `backend.config` — the *identity* constants here are
  contract-frozen and must never be environment-overridable; the *behavior* flag
  (`CCDASH_ROUTING_FEEDBACK_ENABLED`, T1-004) is deliberately kept in a separate module (`backend/config.py`)
  precisely so identity and runtime toggles are never conflated.
- No LLM/model-client import anywhere in this module or its transitive closure — this constants-only
  module is trivially compliant, but keep it that way as later phases build on top of it (AOS
  Constraint 4, verified at scale by Phase 6's AST-walk guard).

**Files Involved**:
- `backend/application/services/agent_queries/routing_feedback_contract.py` - New file; frozen contract/taxonomy/mapping identity constants + capability string + vendored-mapping path pointer.

---

### Task T1-003: Capability string

**Estimate**: 0.25 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T1-002
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
In `backend/routers/client_v1.py`, add `"routing:feedback"` to the `_V1_CAPABILITIES` list (defined
~line 147, alongside the existing `"sessions:cross-project"`, `"sessions:detail"`, `"research-runs:*"`,
and `"aar-review"` entries). Mirror the existing `"aar-review"` entry's inline-comment style exactly —
that entry reads:

```python
"aar-review",              # Persisted AAR-document-to-session triage rollup (T4-002) —
                           # GET /api/v1/project/aar-review reads the aar_reviews table.
```

The new entry's comment must instead note that the actual route (`GET /api/v1/routing/rollup`) lands in
Phase 5 of this feature, not in this phase — this phase advertises the capability string ahead of the
route existing, exactly as `"research-runs:*"` was itself once a "wildcard placeholder for the eventual
query surface." No route, no service call, no DTO wiring in this task — capability advertisement only.

**Acceptance Criteria**:
- [ ] `"routing:feedback"` appears as a new entry in `_V1_CAPABILITIES` (`backend/routers/client_v1.py`)
- [ ] Inline comment mirrors the `"aar-review"` entry's format and explicitly notes "route lands in
      Phase 5" (or equivalent language making clear no route exists yet in this phase)
- [ ] `GET /api/v1/capabilities` response includes `"routing:feedback"` in its `capabilities` array
      unconditionally — i.e., the capability is advertised **regardless** of
      `CCDASH_ROUTING_FEEDBACK_ENABLED`'s value (capability presence signals feature *existence*, not
      enabled state, per the existing `sessions:detail`/`aar-review` convention and PRD FR-10)
- [ ] No new route, service call, or import added to `client_v1.py` beyond the one list entry + comment
- [ ] Existing capability-discovery test(s) (if any assert on the exact `_V1_CAPABILITIES` list contents)
      updated to include the new string, or confirmed to already tolerate list growth

**Implementation Notes**:
- This is a one-line-plus-comment change; resist scope creep into wiring a stub route — that belongs to
  Phase 5 (T5-*) once the DTO shape is frozen by Phase 3.
- Import `CAPABILITY_STRING` from `routing_feedback_contract` (T1-002) rather than hardcoding the
  literal string `"routing:feedback"` a second time in `client_v1.py` — this keeps the capability string
  single-sourced, consistent with T1-002's "single source of truth" design intent.
- Per the capability-discovery docstring already in `client_v1.py` (~line 164-171): "Callers SHOULD
  check `capabilities` before using a capability-dependent endpoint... Unknown strings must be treated as
  future additions and MUST NOT cause the client to error." This behavior is preserved automatically by
  simply appending to the list — no consumer-side code in this repo needs to change.

**Files Involved**:
- `backend/routers/client_v1.py` - Add `"routing:feedback"` to `_V1_CAPABILITIES` (~line 147-155), importing `CAPABILITY_STRING` from the new contract module.

---

### Task T1-004: Config flag + tunables

**Estimate**: 0.25 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: None
**started**: null
**completed**: null
**verified_by**: [T1-005]
**evidence**: []

**Description**:
In `backend/config.py`, add four new environment-driven configuration values near the existing
`CCDASH_AAR_REVIEW_*` flags (~line 101-133), using the module's existing `_env_bool`/`_env_int` helper
functions (defined at lines 13-27) — never a raw `os.getenv` call:

```python
CCDASH_ROUTING_FEEDBACK_ENABLED = _env_bool("CCDASH_ROUTING_FEEDBACK_ENABLED", False)
CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE = _env_int("CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE", 5)
CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS = _env_int("CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS", 30)
CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS = _env_bool("CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS", True)
```

Note the deliberate contrast with the AAR-review precedent: `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED`
defaults `True` (default-on, opt-out), while `CCDASH_ROUTING_FEEDBACK_ENABLED` defaults `False`
(default-off, opt-in) — this is decisions-block D6, locked, and honours the cross-repo contract's
"not-implemented / disabled" baseline. Do not copy the AAR-review flag's default polarity.

**Acceptance Criteria**:
- [ ] `CCDASH_ROUTING_FEEDBACK_ENABLED` present, `_env_bool`-backed, default `False`
- [ ] `CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` present, `_env_int`-backed, default `5`
- [ ] `CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS` present, `_env_int`-backed, default `30`
- [ ] `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS` present, `_env_bool`-backed, default `True`
- [ ] All four names spelled exactly as above (no abbreviation, no pluralization drift)
- [ ] Placed adjacent to the `CCDASH_AAR_REVIEW_*` block (~line 101-133) with a short comment block
      (mirroring that block's comment style) explaining the feature and pointing at this phase file /
      the PRD
- [ ] No other module in the codebase reads these env vars directly — all consumers (Phase 3's compute
      service, Phase 4's worker, Phase 5's transports) import from `backend.config`

**Implementation Notes**:
- These four names are locked by the PRD (§6.3 "Candidate config knobs" / §8 "Feature Flags") and the
  decisions block — do not rename, even though the PRD frontmatter records
  `CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS`'s numeric default as "non-binding" (OQ-6) — the **name** and the
  literal integer `30` as *default* are locked for this phase; only a future phase could change the
  default value via a design-spec-driven follow-up, not this task.
- `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS` gates Phase 3's `_unclassified`/protected-class
  coverage-only row visibility (OQ-4) — this task only defines the flag; Phase 3 is where it is actually
  read and branched on.
- No wiring into `backend/runtime/container.py`, `backend/adapters/jobs/*`, or any router in this task —
  that is Phase 4 (worker registration) and Phase 5 (transport gating) respectively. This task defines
  the four config values and nothing else.

**Files Involved**:
- `backend/config.py` - Add 4 new `CCDASH_ROUTING_FEEDBACK_*` constants near the existing `CCDASH_AAR_REVIEW_*` block (~line 101-133), using `_env_bool`/`_env_int`.

---

### Task T1-005: Digest-parity + flag-default test

**Estimate**: 0.5 points
**Assigned Subagent(s)**: backend-architect
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T1-001, T1-002, T1-004
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
Create `backend/tests/test_routing_feedback_contract_parity.py` with (at minimum) two test cases:

1. **Digest parity**: Compute SHA-256 of the vendored `routing_task_map_v1.json` file's raw bytes
   (`backend/application/services/agent_queries/routing_task_map_v1.json`, per T1-001) and assert it
   equals `routing_feedback_contract.MAPPING_DIGEST` (stripping/normalizing the `sha256:` prefix as
   needed to compare like-for-like against `hashlib.sha256(...).hexdigest()`'s output).
2. **Flag-default test**: Assert `backend.config.CCDASH_ROUTING_FEEDBACK_ENABLED is False` when the
   `CCDASH_ROUTING_FEEDBACK_ENABLED` environment variable is unset — this is the AC-4/D6
   "reads false by default" exit criterion for this entire phase, verified mechanically rather than by
   inspection.

This test is explicitly named in the plan as a test that **Phase 6 (T6-002) later extends** — do not
over-build it into a full guard suite here; Phase 6 owns the no-LLM AST-walk guard, the full DTO
contract-lock test, and the determinism test. This phase's test is narrowly scoped to the two assertions
above.

**Acceptance Criteria**:
- [ ] `backend/tests/test_routing_feedback_contract_parity.py` exists and is collected by the project's
      test runner (`backend/.venv/bin/python -m pytest backend/tests/test_routing_feedback_contract_parity.py -v`)
- [ ] Digest-parity assertion fails loudly (clear failure message naming the expected vs. actual digest)
      if the vendored JSON bytes are edited even by one character — verify this by locally mutating a
      single byte in a scratch copy and confirming the test fails, then reverting
- [ ] Flag-default assertion passes with `CCDASH_ROUTING_FEEDBACK_ENABLED` unset in the test environment
- [ ] Test does not depend on network access, a running server, or a live database connection — pure
      file-read + import-time assertion
- [ ] Test module imports `MAPPING_DIGEST` and `MAPPING_JSON_PATH` from `routing_feedback_contract`
      (T1-002) and `CCDASH_ROUTING_FEEDBACK_ENABLED` from `backend.config` (T1-004) — no hardcoded
      duplicate literals inside the test itself beyond the comparison logic

**Implementation Notes**:
- Follow the sibling precedent's test style: `backend/tests/test_aar_review_no_llm_imports.py` and any
  existing digest/parity-style test in the codebase for structure (imports, fixture setup, assertion
  style) — but this test does not need the AST-walk machinery; it is a straightforward
  hash-and-compare-plus-env-default check.
- Use `hashlib.sha256(path.read_bytes()).hexdigest()` and compare against `MAPPING_DIGEST` with the
  `sha256:` prefix stripped (or prepend it to the computed digest before comparing) — pick one
  normalization convention and keep it consistent, since Phase 3/6 will reuse the same comparison
  pattern for the taxonomy digest.
- This test is the mechanical enforcement of the phase's `exit_criteria` in this file's frontmatter:
  `["Digest-parity test green", "CCDASH_ROUTING_FEEDBACK_ENABLED reads false by default"]`. Do not mark
  this phase's Quality Gates section satisfied until this test is green in CI, not just locally.

**Files Involved**:
- `backend/tests/test_routing_feedback_contract_parity.py` - New file; digest-parity assertion (T1-001 bytes vs. T1-002's `MAPPING_DIGEST`) + flag-default assertion (T1-004's `CCDASH_ROUTING_FEEDBACK_ENABLED`).

---

## Quality Gates

This phase is complete when:

- [ ] **Functional**: `routing_task_map_v1.json` is vendored verbatim at the pinned path; the
      `routing_feedback_contract` module exposes all 8 identity constants + capability string + mapping
      path; `"routing:feedback"` is advertised via `/api/v1/capabilities` unconditionally; all 4
      `CCDASH_ROUTING_FEEDBACK_*` config values exist with the specified defaults.
- [ ] **Testing**: `backend/tests/test_routing_feedback_contract_parity.py` passes locally and in CI;
      both the digest-parity and flag-default assertions are exercised.
- [ ] **Performance**: N/A — this phase introduces no runtime code path exercised at request time (no
      route logic, no compute, no worker registration).
- [ ] **Security**: N/A — no new PII/secret exposure; the vendored mapping is a public cross-repo
      contract artifact, not sensitive data.
- [ ] **Documentation**: This phase file itself is the documentation of record for this scope; no
      user-facing doc changes are due until Phase 6 (consumer-contract doc, operator guide).
- [ ] **Code Quality**: No new lint/type errors introduced; `routing_feedback_contract.py` has no
      side-effecting import-time behavior.
- [ ] **Architecture**: No behavior change — this phase is strictly additive scaffolding; existing
      `/api/v1/capabilities`, `_V1_CAPABILITIES` consumers, and `backend/config.py` consumers are
      unaffected apart from list/module growth.
- [ ] **Seam verification** (if `integration_owner` set): N/A — `integration_owner` is `null` for this
      phase; cross-owner seam verification belongs to Phase 6 per the decisions block (§3 Risk 1
      mitigation names the P6 parity/seam task as the integration owner, not this phase).
- [ ] **Runtime smoke** (if `ui_touched: true`): N/A — `ui_touched: false`; this feature has no frontend
      surface anywhere. No runtime-smoke task exists in this phase or any phase of this plan.

---

## Integration Points

### External Systems

- **agentic_meta_dev contract repo** (informational, no runtime call): CCDash vendors a frozen snapshot
  of `routing-feedback-task-map.v1.json` at build/commit time (T1-001). CCDash never fetches this file
  live at runtime — there is no network dependency introduced by this phase or any later phase.

### Internal Systems

- **`backend/routers/client_v1.py` capability discovery**: This phase's sole internal-system touch point
  beyond `backend/config.py` — `_V1_CAPABILITIES` grows by one entry (T1-003), consumed unconditionally
  by every existing `/api/v1/capabilities` caller (no breaking change to the response shape, only list
  growth, per the existing "unknown strings must not cause the client to error" contract).
- **Phase 2 (Data Layer)**: Consumes nothing from this phase directly (table DDL has no dependency on
  contract constants), but Phase 2's repository module will sit alongside this phase's contract module in
  the same package tree.
- **Phase 3 (Rollup Compute Service)**: The first real *consumer* of this phase's output — imports
  `routing_feedback_contract`'s constants (mapping path, digests, versions) to build the envelope, and
  reads `backend.config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` /
  `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS` for eligibility/coverage logic.
- **Phase 4 (Worker Sweep Job)** and **Phase 5 (Transport Surfaces)**: Both read
  `CCDASH_ROUTING_FEEDBACK_ENABLED` (T1-004) as their respective on/off gate.
- **Phase 6 (Validation, Guards & Docs)**: T6-002 extends this phase's T1-005 test into the full
  digest-parity + envelope-completeness + version-field-presence test battery (AC-2, AC-8).

---

## Key Files Modified

| File Path | Lines | Purpose | Subagent |
|-----------|-------|---------|----------|
| `backend/application/services/agent_queries/routing_task_map_v1.json` | new file | Verbatim vendored cross-repo mapping artifact (OQ-5 canonical path) | backend-architect |
| `backend/application/services/agent_queries/routing_feedback_contract.py` | new file | Frozen contract/taxonomy/mapping identity constants + capability string + mapping path | backend-architect |
| `backend/routers/client_v1.py` | ~147-155 | Add `"routing:feedback"` to `_V1_CAPABILITIES`, mirroring the `"aar-review"` entry | python-backend-engineer |
| `backend/config.py` | ~101-133 | Add 4 `CCDASH_ROUTING_FEEDBACK_*` env-driven config values near `CCDASH_AAR_REVIEW_*` | python-backend-engineer |
| `backend/tests/test_routing_feedback_contract_parity.py` | new file | Digest-parity + flag-default CI test | backend-architect |

---

## Testing Strategy

### Unit Tests

- Digest-parity test (T1-005a): vendored JSON bytes SHA-256 == `MAPPING_DIGEST` constant.
- Flag-default test (T1-005b): `CCDASH_ROUTING_FEEDBACK_ENABLED` is `False` when the env var is unset.
- Coverage target for this phase: both assertions in `test_routing_feedback_contract_parity.py` green;
  no other new test surface is expected at this phase (no route, no service, no worker exist yet).

### Integration Tests

- None required at this phase — there is no cross-module runtime behavior to integration-test yet (no
  DB table, no route, no worker). Integration-level testing of the full envelope begins in Phase 3
  (compute service against a fixture DB) and Phase 5 (DTO contract-lock across REST/MCP/CLI).

### E2E Tests (if applicable)

- Not applicable — this feature has no frontend surface and no end-user journey; the "E2E" analog for
  this feature is the cross-repo digest-parity check, which is exactly what T1-005 (and its Phase 6
  extension, T6-002) provides.

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Vendored mapping bytes drift from the normative contract copy (hand-edit, encoding change, line-ending normalization by an editor/IDE) | High | T1-005's digest-parity test fails the build immediately on any byte-level drift; T1-001's implementation notes explicitly warn against hand-retyping the JSON. |
| Contract identity constants (T1-002) get re-typed inline elsewhere in the codebase instead of imported, causing silent drift between two copies | Medium | T1-002's design intent (single source of truth) is called out explicitly in T1-003's and T1-004's implementation notes; later phases (3, 4, 5, 6) are expected to import from `routing_feedback_contract`, never re-declare. |
| `CCDASH_ROUTING_FEEDBACK_ENABLED` default polarity accidentally copied from the AAR-review precedent (`True`) instead of the locked D6 default (`False`) | Medium | T1-004's description explicitly flags the contrast with the AAR-review flag and calls out "do not copy the AAR-review flag's default polarity"; T1-005b's flag-default test is the mechanical backstop. |
| Capability string advertised (T1-003) before any consumer double-checks the disabled-state behavior contract (AC-4, Phase 5) | Low | Advertising `"routing:feedback"` ahead of the route is an established, safe pattern in this codebase (`"research-runs:*"` precedent) — capability presence signals feature *existence*, never enabled state; no route exists yet to misbehave. |

---

## Success Metrics

- **Completion**: All 5 tasks (T1-001 through T1-005) checked off.
- **Quality**: All Quality Gates in this file passed; both assertions in
  `test_routing_feedback_contract_parity.py` green in CI.
- **Performance**: N/A for this phase (no runtime request-path code introduced).
- **Testing**: `backend/tests/test_routing_feedback_contract_parity.py` collected and passing; no
  regression in any existing test suite (this phase touches only additive list/module/config growth).

---

## Notes

### Implementation Approach

This phase is deliberately the lowest-risk, most mechanical phase in the plan by design — it exists to
freeze identity before any logic is written against it. The five tasks are intentionally small
(0.25–0.5 pts each) and mostly independent of one another (only T1-002 depends on T1-001, and T1-005
depends on all three preceding constant/flag tasks). There is no reason to batch these across multiple
agents in parallel; a single agent context can carry T1-001 through T1-005 sequentially without context
pressure, though the task table above assigns backend-architect to the precision-critical constant/test
tasks (T1-001, T1-002, T1-005) and python-backend-engineer to the two mechanical wiring tasks (T1-003,
T1-004) per the decisions block's agent-routing table (§2).

### Gotchas

- **Byte-for-byte means byte-for-byte**: Any editor auto-formatting (trailing newline insertion, line
  ending conversion CRLF↔LF, JSON re-indentation) on the vendored file in T1-001 will silently break
  T1-005's digest-parity test. Copy the file with a tool that does not "helpfully" reformat JSON.
- **Two different digest prefix conventions**: The `MAPPING_DIGEST`/`TAXONOMY_DIGEST` constants carry a
  literal `sha256:` prefix (per the contract's own convention), while Python's `hashlib.sha256(...).hexdigest()`
  does not emit that prefix — T1-005's test must normalize one side or the other consistently, and this
  same normalization convention will be reused by Phase 3/6, so get it right once here.
- **Do not conflate identity constants with runtime flags**: `routing_feedback_contract.py` (T1-002) and
  `backend/config.py`'s new entries (T1-004) are deliberately two separate modules with two separate
  mutability models (frozen contract identity vs. environment-configurable behavior toggle) — resist the
  temptation to merge them into one file for convenience.

### Learnings

*Capture learnings here as this phase progresses during execution.*

### Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-29

[Return to Parent Plan](../proof-to-routing-loop-v1.md)
