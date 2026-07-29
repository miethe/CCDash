---
title: "Phase 6: Validation, Guards & Docs"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-07-29
updated: 2026-07-29
feature_slug: "proof-to-routing-loop"
feature_version: "v1"
phase: 6
phase_title: "Validation, Guards & Docs"
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
entry_criteria: ["Phase 4 and Phase 5 both complete"]
exit_criteria: ["task-completion-validator pass", "karen feature-end pass"]
related_documents:
  - docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md
  - docs/guides/aar-review-loop.md
  - backend/tests/test_aar_review_no_llm_imports.py
spike_ref: null
adr_refs: []
charter_ref: null
changelog_ref: null
test_plan_ref: null
integration_owner: python-backend-engineer
ui_touched: false
target_surfaces:
  - backend/application/services/agent_queries/routing_task_map_v1.json
  - backend/application/services/agent_queries/routing_feedback_contract.py
  - backend/routers/client_v1.py
  - backend/config.py
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - backend/db/migration_governance.py
  - backend/db/repositories/routing_rollup.py
  - backend/application/services/agent_queries/routing_rollup.py
  - backend/application/services/agent_queries/models.py
  - backend/adapters/jobs/routing_rollup_sweep_job.py
  - backend/adapters/jobs/runtime.py
  - backend/runtime/container.py
  - backend/routers/_client_v1_routing_rollup.py
  - backend/mcp/tools/routing.py
  - backend/mcp/tools/__init__.py
  - backend/cli/commands/routing.py
  - backend/cli/main.py
seam_tasks: [T6-002, T6-003]
owner: null
contributors: []
priority: medium
risk_level: medium
category: "product-planning"
tags: [phase-plan, implementation, infrastructure, routing-feedback, no-llm, cross-repo]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/tests/test_routing_rollup_no_llm_imports.py
  - backend/tests/test_routing_feedback_contract_parity.py
  - backend/tests/test_routing_rollup_envelope_completeness.py
  - backend/tests/test_routing_rollup_determinism.py
  - backend/tests/test_routing_rollup_sparse_protected.py
  - backend/tests/test_routing_rollup_disabled_state.py
  - docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md
  - docs/guides/routing-feedback-loop.md
  - docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
  - docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md
  - docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md
  - CHANGELOG.md
---

# Phase 6: Validation, Guards & Docs

**Parent Plan**: [Proof → Routing Feedback Loop — CCDash Producer Surface (BP-6)](../proof-to-routing-loop-v1.md)
**Duration**: ~2-3 days
**Effort**: 2 story points
**Dependencies**: Phase 4 (Worker Sweep Job) and Phase 5 (Transport Surfaces) both complete
**Team Members**: python-backend-engineer (tests/guards), documentation-writer (docs), task-completion-validator (gate), karen (gate)

---

## Phase Overview

This is the feature's terminal validation and documentation phase. It does not add new production
behavior — every module the feature needs (contract constants, `routing_rollup` table, compute
service, worker sweep, REST/MCP/CLI transports) is already shipped by Phases 1-5. Phase 6's job is to
prove, with CI-enforced tests, that the whole assembled feature actually satisfies PRD §11's AC-1
through AC-8, then close out the three deferred cross-repo items and the operator-facing
documentation before the feature is sealed.

This phase is a structural clone of the shipped Automated AAR Review Loop's own validation phase: the
no-LLM AST-walk guard, the consumer-contract doc, and the operator guide all mirror
`backend/tests/test_aar_review_no_llm_imports.py`, `docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md`,
and `docs/guides/aar-review-loop.md` respectively.

### Goals

- Extend the no-LLM guard to cover the worker (T6-001), not just the compute service.
- Lock the two cross-repo seam guarantees — mapping-digest parity and envelope completeness — as
  CI-enforced tests, not manual review (T6-002, T6-003; R-P3 seam tasks).
- Re-confirm determinism end-to-end through the persisted worker path (T6-004).
- Prove sparse-key visibility and protected-class coverage-only handling against the value-findings
  density fixture (T6-005).
- Prove disabled-state byte-identity, flag-flip reversibility, version-field presence, and unconditional
  capability advertisement across all three transports (T6-006).
- Gate the whole feature through `task-completion-validator` (T6-007) and `karen` (T6-008).
- Ship the CHANGELOG entry, the consumer-contract doc, the operator guide, and all three DOC-006
  deferred-items design specs (DOC-001, DOC-002, DOC-003, DOC-006).

### Architecture Focus

This phase implements the **Testing/Validation** and **Documentation** layers following the shipped
AAR-review clone pattern:

- **Layer**: Testing (CI guards, contract-lock tests, fixture tests) + Documentation
- **Patterns**: AST-walk import-graph guard (clone of `test_aar_review_no_llm_imports.py`); byte-exact
  digest-parity assertion; deterministic fixture-DB re-run comparison; consumer-contract doc mirroring
  `ccdash-aar-review-consumer-contract-v1.md`'s section structure
- **Standards**: No LLM anywhere in the compute/worker closure (AOS Constraint 4); zero re-derivation
  of AC prose (cite PRD §11 by ID); `deferred_items_spec_refs` populated with all three DOC-006 paths
  before the phase seals

---

## Task Breakdown

### Epic: Validation, Guards & Docs

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---|---|---|---|---|---|---|---|---|
| T6-001 | Extend no-LLM guard to worker | Extend `backend/tests/test_routing_rollup_no_llm_imports.py` (created Phase 3, T3-005) to also AST-walk `backend/adapters/jobs/routing_rollup_sweep_job.py`'s transitive import graph, cloning `test_aar_review_no_llm_imports.py`'s guard shape for the worker module. | Guard covers compute service AND worker; zero banned symbols in either closure (AC-3) | 0.2 pts | python-backend-engineer | sonnet | adaptive | Phase 4 complete |
| T6-002 | Digest-parity CI test (seam task) | Extend/confirm `backend/tests/test_routing_feedback_contract_parity.py` (Phase 1, T1-005): CI test asserting the vendored `routing_task_map_v1.json` bytes SHA-256 == `MAPPING_DIGEST` (`sha256:45a49bb1a6194c6a576160edab7c3212a9cc20e17e6a0b79d531c1c4928f63f5`), byte-for-byte, every CI run. This is the R-P3 cross-repo seam task defending Risk 1 (silent non-join / vocabulary drift). | Digest mismatch fails the build immediately (AC-2) | 0.3 pts | python-backend-engineer | sonnet | adaptive | T6-001 |
| T6-003 | Envelope-completeness test (seam task) | New `backend/tests/test_routing_rollup_envelope_completeness.py`: assert every enabled response, on every transport, carries all 11 pinned envelope fields (`producer`, `contract_id`, `contract_version`, `taxonomy_id`, `taxonomy_version`, `taxonomy_digest`, `mapping_id`, `mapping_version`, `mapping_digest`, `source_skill_name`, `task_class` — per PRD §6.3 JSON example) per key, plus `mapped_count`/`unclassified_count`/`distinct_unmapped_skill_names` at the top level. Second R-P3 seam task, paired with T6-002. | A response missing any pinned field fails the build (AC-1) | 0.3 pts | python-backend-engineer | sonnet | adaptive | T6-002 |
| T6-004 | Determinism re-confirmation | Re-run/extend `backend/tests/test_routing_rollup_determinism.py` (Phase 3, T3-005) across the full Phase 4 worker path end-to-end (not just the Phase 3 service in isolation): two full sweep-job runs over an unchanged fixture window produce field-identical `routing_rollup` rows. | End-to-end determinism through persistence (AC-3) | 0.2 pts | python-backend-engineer | sonnet | adaptive | T6-003 |
| T6-005 | Sparse-key + protected-class fixture tests | New `backend/tests/test_routing_rollup_sparse_protected.py`: (a) sparse-key visibility — sub-threshold keys still carry `sample_count` + `eligible_for_adjustment=false`, never suppressed (AC-5), against the value-findings density fixture (40 keys, 52% N≥5); (b) protected-class/`_unclassified` coverage-only handling — rows always hardcode `eligible_for_adjustment=false` (AC-6). | Both fixture tests green | 0.2 pts | python-backend-engineer | sonnet | adaptive | T6-004 |
| T6-006 | Disabled-state + reversibility + version-field tests | New `backend/tests/test_routing_rollup_disabled_state.py`: (a) disabled-state contract test — REST/MCP/CLI byte-identical disabled envelopes, extends Phase 5's T5-004 to full contract-lock scope, and additionally asserts `GET /api/v1/capabilities` unconditionally includes `"routing:feedback"` with the flag both off and on (AC-4); (b) flag-flip reversibility re-confirmation across all three transports, extends Phase 4's T4-003 (AC-7); (c) version-field-presence test — every response (enabled or disabled) carries `contract_version`/`taxonomy_version`/`mapping_version` (AC-8). | All three sub-tests green across REST/MCP/CLI, including the capability-string assertion under both flag states | 0.2 pts | python-backend-engineer | sonnet | adaptive | T6-005 |
| T6-007 | task-completion-validator gate | Phase-end review: verify T1-001 through T6-006 all have passing evidence, AC-1..AC-8 each have a green `verified_by` test, no Mode-D risk introduced. Mandatory per Tier 2 workflow. This is a review gate — NO Model/Effort columns. | Gate passes before phase sealed | — | task-completion-validator | — | — | T6-006 |
| T6-008 | karen feature-end review | Mandatory Tier-2 feature-end review (decisions block §4: karen at Phase 3 milestone AND feature end — Phase 3's own file should already reference the milestone review). Verifies claimed completion against actual behavior across all 6 phases. Review gate — NO Model/Effort columns. | Gate passes before feature marked complete | — | karen | — | — | T6-007 |
| DOC-001 | CHANGELOG entry | Add an `[Unreleased]` entry per `.claude/specs/changelog-spec.md`: new capability `routing:feedback`, new REST/MCP/CLI surfaces, default-off. | Entry exists under `[Unreleased]`; `changelog_ref` set | 0.1 pts | changelog-generator | haiku | adaptive | Phase 5 complete |
| DOC-002 | Consumer-contract doc | New `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md` mirroring `ccdash-aar-review-consumer-contract-v1.md`'s structure: documents which guardrails are CCDash's (verifiable — digest parity, no-LLM, determinism) vs. the router's (asserted only — `validateFeedbackJoin`, merge math). | Doc mirrors the AAR precedent's section structure | 0.15 pts | documentation-writer | haiku | adaptive | Phase 5 complete |
| DOC-003 | Operator guide | New `docs/guides/routing-feedback-loop.md` mirroring `docs/guides/aar-review-loop.md`: flag name, tunables, how to verify the rollup is populating, how to read the disabled envelope. | Doc mirrors the AAR precedent's structure | 0.15 pts | documentation-writer | haiku | adaptive | Phase 5 complete |
| DOC-006 | Deferred-items design specs | Author all three design specs from the parent plan's Deferred Items Triage Table (DI-1/DI-2/DI-3): `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md`, `.../routing-feedback-model-provider-namespacing.md`, `.../routing-feedback-window-decay-defaults.md` — each `maturity: idea`, `prd_ref` set to the parent PRD, NEVER describing router-repo implementation as an executable task (name the seam only). Append all three paths to the parent plan's `deferred_items_spec_refs` frontmatter field. | All three specs exist; parent plan frontmatter updated | 0.2 pts | documentation-writer | sonnet | adaptive | Phase 5 complete |

**Phase total: 2 pts**

**Model Selection Guidance**: Refer to `.claude/config/multi-model.toml` for valid model values and effort policies:
- **Sonnet** (default implementation): the six test-authoring tasks (T6-001..T6-006) — each requires
  understanding a real transitive import graph, an existing fixture DB, or a three-transport contract
  shape, not mechanical extraction.
- **Haiku** (default docs/extraction): CHANGELOG entry (DOC-001), consumer-contract doc (DOC-002), and
  operator guide (DOC-003) — all are structural clones of an existing shipped precedent doc.
- **Sonnet for DOC-006**: three cross-repo handoff specs require synthesizing the parent plan's
  Deferred Items Triage Table correctly and must never mis-describe router-repo scope as CCDash work —
  this judgment call is worth the sonnet upgrade over haiku.
- **Review gates** (T6-007, T6-008): reviewer agents, not implementers — no Model/Effort columns per
  the reviewer-gate convention.

**Effort Policy** (see `.claude/config/multi-model.toml`):
- **adaptive**: default reasoning for every implementer task in this phase; no task here needs
  `extended` — Phase 3 (the algorithmic core) already absorbed the feature's one high-reasoning slot.

---

## Detailed Task Specifications

### Task T6-001: Extend no-LLM guard to worker

**Estimate**: 0.2 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: Phase 4 complete
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
`backend/tests/test_routing_rollup_no_llm_imports.py` was created in Phase 3 (T3-005) and walks the
compute service's (`routing_rollup.py`) transitive import graph only. This task adds a second,
independent BFS entry point rooted at `backend/adapters/jobs/routing_rollup_sweep_job.py`, cloning the
exact shape `test_aar_review_no_llm_imports.py` uses for its own `_P6_ENTRY_MODULES` expansion (two
independent walks, one per entry point, both must be clean).

**Acceptance Criteria**:
- [ ] AC-3 (Determinism + no-LLM, no-LLM half — see PRD §11 AC-3 for full propagation_contract text):
      the worker's transitive import graph contains zero banned model-client or Task/Agent-dispatch
      symbols, verified by an independent BFS walk (not shared traversal state with the Phase 3 walk)
- [ ] The pre-existing Phase 3 service-only guard test remains green (no regression to the original
      entry point)
- [ ] The new worker-entry-point test asserts it visited more than just the entry module itself (a
      trivial "visited only itself" pass is a false negative, per the AAR precedent's own sanity
      assertion pattern)

**Implementation Notes**:
- Clone `NoLLMOrAgentDispatchImportGraphTests.test_p6_entry_modules_have_no_llm_client_import_or_agent_dispatch_symbol`
  from `backend/tests/test_aar_review_no_llm_imports.py` — same `_walk_dependency_graph` helper shape,
  same banned-import/banned-symbol pattern lists, new `_ENTRY_MODULES` tuple containing
  `backend.adapters.jobs.routing_rollup_sweep_job`.
- Do not merge the two BFS walks into one traversal — independent walks catch a banned import that
  exists in one closure but not the other, exactly as the AAR precedent's docstring explains.

**Files Involved**:
- `backend/tests/test_routing_rollup_no_llm_imports.py` - add a second entry-point walk for the worker module

---

### Task T6-002: Digest-parity CI test (seam task)

**Estimate**: 0.3 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T6-001
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
This is the first of the phase's two R-P3 seam tasks (`integration_owner: python-backend-engineer`).
The vendored `routing_task_map_v1.json` file (Phase 1, T1-001) must byte-for-byte digest-match the
pinned `mapping_digest` constant. `backend/tests/test_routing_feedback_contract_parity.py` was created
in Phase 1 (T1-005) to assert this; this task confirms the test still covers the shipped path after
Phases 2-5 landed and hardens it if any drift crept in (e.g. a re-serialization of the JSON file that
changed byte layout without bumping the digest).

**Acceptance Criteria**:
- [ ] AC-2 (Mapping fidelity — see PRD §11 AC-2): the vendored mapping file's SHA-256 digest equals
      `sha256:45a49bb1a6194c6a576160edab7c3212a9cc20e17e6a0b79d531c1c4928f63f5` byte-for-byte
- [ ] A deliberately corrupted/edited copy of the vendored file (test-local fixture, never the real
      file) fails the test — proves the assertion is load-bearing, not vacuous
- [ ] Test runs as a normal `pytest` collection item (no manual/CI-only script step) so it executes on
      every build, per FR-1's CI-verification requirement

**Implementation Notes**:
- This is a **seam task**: it is the CCDash-side half of the cross-repo join-integrity contract. The
  router's `validateFeedbackJoin()` is the other half and is asserted-only from CCDash's side (per the
  consumer-contract doc, DOC-002) — CCDash cannot execute the router's code, only guarantee its own
  vendored copy never silently drifts from the contract's normative digest.
- Reuse the exact digest string from PRD §11 AC-2 and §6.3 (`mapping_digest`) — do not recompute or
  re-derive it from a fresh SHA-256 run over an assumed-correct file; the test must fail if the
  vendored file itself is wrong, so the expected digest must come from the pinned contract constant.

**Files Involved**:
- `backend/tests/test_routing_feedback_contract_parity.py` - confirm/harden the digest-parity assertion

---

### Task T6-003: Envelope-completeness test (seam task)

**Estimate**: 0.3 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T6-002
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
The second of the phase's two R-P3 seam tasks. Where T6-002 defends the mapping's byte-identity, this
task defends the **envelope's structural completeness** — the actual join contract the router's
`validateFeedbackJoin()` depends on receiving. A new test asserts every enabled response, on every
transport (REST/MCP/CLI), carries all 11 pinned envelope fields per key plus the three top-level
coverage counters.

**Acceptance Criteria**:
- [ ] AC-1 (Envelope completeness — see PRD §11 AC-1): every enabled response, on every transport,
      carries all 11 pinned fields per key (`producer`, `contract_id`, `contract_version`,
      `taxonomy_id`, `taxonomy_version`, `taxonomy_digest`, `mapping_id`, `mapping_version`,
      `mapping_digest`, `source_skill_name`, `task_class`) plus `mapped_count`, `unclassified_count`,
      and `distinct_unmapped_skill_names` at the top level, with `producer`'s value asserted equal to
      the frozen `PRODUCER = "ccdash"` constant exactly — not merely asserted present
- [ ] The test parametrizes over all three transports (REST, MCP, CLI) rather than asserting only one
      and assuming DTO-shape identity guarantees the others
- [ ] A response with any one field deliberately stripped (test-local monkeypatch/fixture) fails the
      build — proves the assertion catches an incomplete envelope, not just a well-formed one

**Implementation Notes**:
- Pull the exact 11-field list and top-level counter names from PRD §6.3's JSON example — do not
  re-derive or improvise field names.
- This test is the structural counterpart to T6-002: T6-002 proves the mapping bytes are correct;
  T6-003 proves the *response shape* actually surfaces the fields a compliant consumer's
  `validateFeedbackJoin()` needs to re-verify each row independently.

**Files Involved**:
- `backend/tests/test_routing_rollup_envelope_completeness.py` - new file, three-transport parametrized envelope assertion

---

### Task T6-004: Determinism re-confirmation

**Estimate**: 0.2 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T6-003
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
`backend/tests/test_routing_rollup_determinism.py` (Phase 3, T3-005) proved determinism at the
`RoutingRollupQueryService` layer in isolation. This task re-runs the same determinism property
end-to-end through the full Phase 4 worker path: two full `RoutingRollupSweepJob` runs over an
unchanged fixture session window must persist field-identical `routing_rollup` rows, not merely
compute field-identical in-memory results.

**Acceptance Criteria**:
- [ ] AC-3 (Determinism + no-LLM, determinism half — see PRD §11 AC-3): two sweep-job runs over an
      unchanged session window produce field-identical persisted `routing_rollup` rows
- [ ] The test exercises the worker's upsert path (not a direct service call), so an upsert bug that
      corrupts row identity between runs would be caught here even if the Phase 3 service-level test
      stays green
- [ ] The existing Phase 3 service-level determinism test remains unmodified and green

**Implementation Notes**:
- Use the same fixture-DB approach as Phase 3's test but drive it through `RoutingRollupSweepJob.run()`
  (or its equivalent entry point) twice, comparing the resulting table rows column-for-column.
- Do not assume: fully deterministic sweep timestamps (`freshness_ts`/`generated_at`) may legitimately
  differ between the two runs — scope the field-identity assertion to the aggregation/mapping fields,
  not wall-clock-derived ones. If the row schema conflates the two, flag as a finding rather than
  weakening the test's intent.

**Files Involved**:
- `backend/tests/test_routing_rollup_determinism.py` - extend to an end-to-end worker-path variant

---

### Task T6-005: Sparse-key + protected-class fixture tests

**Estimate**: 0.2 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T6-004
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
Two independent fixture tests in one new file, each closing a distinct PRD AC:

(a) **Sparse-key visibility** — against the value-findings density fixture (40 distinct
`(skill_name, model)` keys, 52% clearing N≥5), assert every emitted key — including the sub-threshold
48% — carries `sample_count` and `eligible_for_adjustment`, and that sub-threshold keys are never
dropped from the response.

(b) **Protected-class / `_unclassified` coverage-only handling** — assert rows for `_unclassified`,
`orchestration`, and `mode_d` always hardcode `eligible_for_adjustment: false`, non-overridable by any
config knob.

**Acceptance Criteria**:
- [ ] AC-5 (Sparse-key / eligibility visibility — see PRD §11 AC-5): every emitted key carries
      `sample_count` + `eligible_for_adjustment` regardless of threshold; sub-threshold keys are never
      suppressed from the response
- [ ] AC-6 (`_unclassified` / protected-class coverage-only handling — see PRD §11 AC-6): rows for
      `_unclassified`, `orchestration`, and `mode_d` always carry a hardcoded, non-overridable
      `eligible_for_adjustment: false`
- [ ] The sparse-key fixture reproduces the value-findings spike's density profile (40 keys, 52%
      N≥5) rather than a synthetic all-dense or all-sparse fixture, so the test exercises the real
      shape this feature was sized against

**Implementation Notes**:
- Reuse or port the value-findings density fixture referenced in the parent plan's risk table
  ("Coarsened, density-validated tuple (52% N≥5 per value-findings)") rather than inventing a new
  fixture shape.
- Even attempting to flip `eligible_for_adjustment` via `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`
  or any other config knob must not change the hardcoded `false` — the test should assert this
  explicitly (config-knob-immunity), not just the default-config case.

**Files Involved**:
- `backend/tests/test_routing_rollup_sparse_protected.py` - new file, two fixture-driven sub-tests

---

### Task T6-006: Disabled-state + reversibility + version-field tests

**Estimate**: 0.2 points
**Assigned Subagent(s)**: python-backend-engineer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: T6-005
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
Three sub-tests in one new file, each closing a distinct PRD AC, all scoped to full REST/MCP/CLI
contract-lock coverage rather than a single transport:

(a) **Disabled-state contract test** — with `CCDASH_ROUTING_FEEDBACK_ENABLED=false`, REST/MCP/CLI
return byte-identical disabled envelopes; extends Phase 5's T5-004 from a spot-check to a full
contract-lock assertion, and — run once with the flag `false` and once with it `true` — additionally
asserts `GET /api/v1/capabilities` unconditionally includes `"routing:feedback"` in both runs (AC-4).

(b) **Flag-flip reversibility** — flipping the flag off and restarting stops all new writes and the
very next call on every transport returns the disabled envelope, with no stale enabled rows served;
extends Phase 4's T4-003.

(c) **Version-field-presence test** — every response, enabled or disabled, carries `contract_version`,
`taxonomy_version`, and `mapping_version`.

**Acceptance Criteria**:
- [ ] AC-4 (Default-off disabled behavior — see PRD §11 AC-4): all three transports return the
      byte-identical disabled envelope (`enabled: false`, empty `keys[]`, zero counts), HTTP 200
- [ ] Capabilities advertisement (extends AC-4): `GET /api/v1/capabilities` includes `"routing:feedback"`
      regardless of `CCDASH_ROUTING_FEEDBACK_ENABLED`'s value — the string advertises this server
      version's understanding of the `aos.routing.feedback` contract and is NEVER conditioned on the
      flag; disabled-ness is expressed only via the PULL surface's deterministic disabled envelope
      (empty `keys[]`, `enabled: false`), never by hiding the capability string
- [ ] AC-7 (Reversibility — see PRD §11 AC-7): flag-flip-to-false stops all new `routing_rollup` writes
      and the next call on every transport returns the disabled envelope; no partial state, no stale
      enabled rows served
- [ ] AC-8 (Version-mismatch resilience — see PRD §11 AC-8): every response — enabled or disabled —
      carries `contract_version`, `taxonomy_version`, and `mapping_version`
- [ ] All three sub-tests are parametrized across REST/MCP/CLI rather than asserting one transport and
      assuming DTO-shape identity implies the others match

**Implementation Notes**:
- "Byte-identical" for (a) means comparing serialized response bodies across transports, not just
  Python-object equality of a shared DTO before transport-specific serialization — a REST/MCP/CLI
  divergence introduced at the serialization boundary must be caught here.
- For (b), assert the *absence* of any residual write after disablement (no partial `routing_rollup`
  row from a sweep that started before the flag flipped and finished after) — not just that the read
  surface reports disabled.

**Files Involved**:
- `backend/tests/test_routing_rollup_disabled_state.py` - new file, three sub-tests across REST/MCP/CLI

---

### Task T6-007: task-completion-validator gate

**Estimate**: —
**Assigned Subagent(s)**: task-completion-validator
**Model**: — (review gate)
**Effort**: — (review gate)
**Dependencies**: T6-006
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
Phase-end review gate, mandatory per the Tier 2 workflow (see `.claude/skills/dev-execution/validation/completion-criteria.md`).
Verifies T1-001 through T6-006 all have passing evidence, that AC-1 through AC-8 each have a green
`verified_by` test per the Acceptance Criteria Closure table below, and that no Mode-D risk was
introduced anywhere in Phases 1-6 (this feature is additive-only DDL throughout — a Mode-D finding here
would itself be a phase-blocking discovery).

**Acceptance Criteria**:
- [ ] Every task T1-001 through T6-006 across all six phases has recorded evidence (commit ref, test
      ref, or equivalent)
- [ ] AC-1 through AC-8 each resolve to at least one green test per the Acceptance Criteria Closure
      table (see below) — no AC is left with an empty `verified_by`
- [ ] No task in this feature introduced a Mode-D (destructive/irreversible) migration; the
      `routing_rollup` table and all endpoints remain additive-only

**Implementation Notes**:
- This is a review gate, not an implementation task — no Model/Effort columns per the reviewer-gate
  convention (`.claude/skills/planning/references/subagent-assignments.md`).
- Gate output format: see `.claude/skills/dev-execution/validation/completion-criteria.md`.

**Files Involved**:
- (review-only; no files modified by this task)

---

### Task T6-008: karen feature-end review

**Estimate**: —
**Assigned Subagent(s)**: karen
**Model**: — (review gate)
**Effort**: — (review gate)
**Dependencies**: T6-007
**started**: null
**completed**: null
**verified_by**: []
**evidence**: []

**Description**:
Mandatory Tier-2 feature-end review per the decisions block's reviewer-gate schedule (karen at the
Phase 3 milestone and again at feature end). Verifies claimed completion against actual behavior across
all six phases — not just that tests pass, but that the shipped feature actually matches the PRD's
intent (deterministic, opt-in, no-LLM, reversible, never actuates routing).

**Acceptance Criteria**:
- [ ] Feature behavior, inspected directly (not merely test-suite-reported), matches PRD §10 Target
      State for both the enabled and disabled configurations
- [ ] No claimed-complete task from any of the six phases is found to be partially or falsely complete
      upon direct inspection
- [ ] Feature-end review sign-off recorded before the plan's `status` frontmatter field advances to
      `completed`

**Implementation Notes**:
- This is the feature's final quality gate; the plan cannot be marked `completed`
  (`manage-plan-status.py --status completed`) until this gate passes.
- Gate output format: see `.claude/skills/dev-execution/validation/completion-criteria.md`.

**Files Involved**:
- (review-only; no files modified by this task)

---

### Task DOC-001: CHANGELOG entry

**Estimate**: 0.1 points
**Assigned Subagent(s)**: changelog-generator
**Model**: haiku
**Effort**: adaptive
**Dependencies**: Phase 5 complete
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
Add an `[Unreleased]` CHANGELOG entry per `.claude/specs/changelog-spec.md`'s categorization rules,
covering: the new `routing:feedback` capability string, the new REST/MCP/CLI surfaces (`GET
/api/v1/routing/rollup`, MCP tool, `ccdash routing rollup` CLI command), and the default-off rollout
posture (`CCDASH_ROUTING_FEEDBACK_ENABLED=false`).

**Acceptance Criteria**:
- [ ] Entry exists under CHANGELOG.md's `[Unreleased]` section, correctly categorized per
      `.claude/specs/changelog-spec.md`
- [ ] Entry mentions the default-off posture (not framed as an always-active user-facing change)
- [ ] Parent plan frontmatter `changelog_ref` set to `CHANGELOG.md` once the entry lands

**Implementation Notes**:
- Follow the `changelog-generator` skill's categorization conventions exactly as used for the shipped
  AAR-review loop's own CHANGELOG entry — no new categorization pattern.

**Files Involved**:
- `CHANGELOG.md` - new `[Unreleased]` entry

---

### Task DOC-002: Consumer-contract doc

**Estimate**: 0.15 points
**Assigned Subagent(s)**: documentation-writer
**Model**: haiku
**Effort**: adaptive
**Dependencies**: Phase 5 complete
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
New `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md`, mirroring
`docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md`'s exact section structure
(Contract Overview, Access Pattern, Routing/Join Decision Inputs, Event/Envelope Schema, Semantics &
Guarantees, CCDash-Side Invariants, Ownership & Boundaries, Resilience & Degradation, Observability,
Phase Stability, Examples, References, Change Log). Documents which guardrails are CCDash's
(verifiable — digest parity T6-002, envelope completeness T6-003, no-LLM T6-001, determinism T6-004)
versus the router's (asserted only — `validateFeedbackJoin()`, the merge math named in DI-1).

**Acceptance Criteria**:
- [ ] Doc mirrors the AAR precedent's section structure exactly (same section list, same ordering)
- [ ] A clearly-labeled subsection distinguishes CCDash-verifiable guarantees (with pointers to the
      specific T6-00x test that proves each) from router-side-asserted-only guarantees
- [ ] Doc cites the pinned envelope example from PRD §6.3 verbatim rather than re-deriving field names

**Implementation Notes**:
- This doc is read by an external cross-repo consumer (the delegation-router owner) — do not describe
  router-repo implementation details CCDash cannot verify; name the seam and cite `DI-1`
  (`docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md`, from DOC-006) for the
  router-side detail.

**Files Involved**:
- `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md` - new file

---

### Task DOC-003: Operator guide

**Estimate**: 0.15 points
**Assigned Subagent(s)**: documentation-writer
**Model**: haiku
**Effort**: adaptive
**Dependencies**: Phase 5 complete
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
New `docs/guides/routing-feedback-loop.md`, mirroring `docs/guides/aar-review-loop.md`'s structure
(Overview, Capability Discovery, Read Endpoint, Worker Flags/Tunables, Hard Invariants,
Troubleshooting, Quick-Start Checklist, Reference). Covers: the `CCDASH_ROUTING_FEEDBACK_ENABLED` flag
name and its companion tunables (`CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`,
`CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS`, `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`), how an
operator verifies the rollup is populating (via the REST endpoint / CLI command), and how to read the
disabled envelope so an operator does not mistake it for an error.

**Acceptance Criteria**:
- [ ] Doc mirrors the AAR precedent's structure (same section list)
- [ ] All four config flags are documented with default values and one-line meaning
- [ ] A worked example of the disabled envelope (`enabled: false`, empty `keys[]`, zero counts) is
      included so an operator can distinguish "off, working as intended" from an error state

**Implementation Notes**:
- Keep the guide usage-focused, not verbose, per `./references/doc-finalization-guidance.md` — this is
  a sibling doc to `aar-review-loop.md`, not a new documentation pattern.

**Files Involved**:
- `docs/guides/routing-feedback-loop.md` - new file

---

### Task DOC-006: Deferred-items design specs

**Estimate**: 0.2 points
**Assigned Subagent(s)**: documentation-writer
**Model**: sonnet
**Effort**: adaptive
**Dependencies**: Phase 5 complete
**started**: null
**completed**: null
**verified_by**: [T6-007]
**evidence**: []

**Description**:
Author all three design specs named in the parent plan's Deferred Items Triage Table
(`docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md` § Deferred Items
& In-Flight Findings Policy):

- `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` (DI-1 — router-side
  empirical merge + live consumption; owned by MeatySkills/`ibm-main`)
- `docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md` (DI-2 —
  model/provider cross-repo namespacing negotiation)
- `docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md` (DI-3 — window/decay
  numeric defaults beyond CCDash's own config knobs)

Each spec is `maturity: idea`, `prd_ref` set to
`docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`, and NEVER describes router-repo
implementation as an executable CCDash task — the spec names the seam only (what CCDash emits, what the
other side must independently decide), per the parent plan's DI-1 rule.

**Acceptance Criteria**:
- [ ] All three specs exist with the exact filenames above, `maturity: idea`, `prd_ref` populated
- [ ] None of the three specs describes router-repo (MeatySkills/`ibm-main`) implementation steps as if
      they were CCDash-executable tasks — each stops at naming the seam and the trigger condition for
      promotion (per the parent plan's triage table "Trigger for Promotion" column)
- [ ] Parent plan frontmatter `deferred_items_spec_refs` is appended with all three paths

**Implementation Notes**:
- Read the parent plan's Deferred Items Triage Table directly for the exact "Reason Deferred" and
  "Trigger for Promotion" wording per item (DI-1/DI-2/DI-3) — do not re-derive or paraphrase from this
  phase file, which does not restate the table.
- This is the single combined DOC-006 task producing three output docs, per the Documentation
  Finalization convention noted in the parent plan.

**Files Involved**:
- `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` - new file (DI-1)
- `docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md` - new file (DI-2)
- `docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md` - new file (DI-3)
- `docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md` - append `deferred_items_spec_refs`

---

## Quality Gates

This phase is complete when:

- [ ] **Functional**: All six T6-00x tests are authored, green, and collected by the normal pytest run
      (no manual/CI-only script step required)
- [ ] **Testing**: No-LLM guard covers both the compute service and the worker (T6-001); digest-parity
      and envelope-completeness seam tests are green (T6-002, T6-003); end-to-end determinism through
      the worker path is confirmed (T6-004); sparse-key and protected-class fixture tests are green
      (T6-005); disabled-state, reversibility, and version-field tests are green across REST/MCP/CLI
      (T6-006)
- [ ] **Performance**: N/A — this phase adds no new runtime code path; it only tests already-shipped
      behavior
- [ ] **Security**: N/A — no new PII/secret exposure surface introduced by this phase's tests or docs
- [ ] **Documentation**: CHANGELOG `[Unreleased]` entry (DOC-001), consumer-contract doc (DOC-002),
      operator guide (DOC-003), and all three DOC-006 deferred-items specs are authored
- [ ] **Code Quality**: All new test files pass linting; no skipped/xfail markers left on any T6-00x
      test without an explicit, documented reason
- [ ] **Architecture**: Follows the shipped AAR-review validation-phase clone pattern; no new
      documentation or test pattern introduced without citing a precedent
- [ ] **Seam verification** (`integration_owner: python-backend-engineer` set): `seam_tasks` (T6-002,
      T6-003) are completed and their `verified_by` references are populated (R-P3)
- [ ] **Deferred items closed**: `deferred_items_spec_refs` in the parent plan frontmatter is populated
      with all three DOC-006 paths (DI-1/DI-2/DI-3)
- [ ] **Acceptance Criteria Closure**: AC-1 through AC-8 each resolve to a green test per the table
      below — no AC left unverified
- [ ] **Runtime smoke**: N/A — `ui_touched: false`, no frontend surface in this feature; not applicable
      per R-P4
- [ ] **task-completion-validator** (T6-007) passes
- [ ] **karen feature-end review** (T6-008) passes

---

## Integration Points

### External Systems

- **MeatySkills delegation-router** (`ibm-main` branch, out of scope for implementation): This phase's
  two seam tasks (T6-002, T6-003) are the CCDash-side half of the cross-repo join-integrity contract.
  CCDash cannot execute or test the router's `validateFeedbackJoin()`; it can only guarantee its own
  vendored mapping bytes and response envelope never silently drift from what that function expects.
  DOC-002 documents this boundary explicitly.

### Internal Systems

- **Phase 1 (Contract & Envelope Foundations)**: T6-002 and T6-006(c) re-verify the pinned constants
  Phase 1 established (`MAPPING_DIGEST`, `contract_version`/`taxonomy_version`/`mapping_version`).
- **Phase 2 (Data Layer)**: T6-004's end-to-end determinism test exercises the `routing_rollup` table's
  upsert path Phase 2 built.
- **Phase 3 (Rollup Compute Service)**: T6-001, T6-004, and T6-005 all extend or re-confirm tests first
  authored in Phase 3 (T3-005).
- **Phase 4 (Worker Sweep Job)**: T6-001's second BFS entry point and T6-006(b)'s reversibility
  re-confirmation both target `RoutingRollupSweepJob` directly.
- **Phase 5 (Transport Surfaces)**: T6-003 and T6-006(a) both parametrize across the REST/MCP/CLI trio
  Phase 5 shipped.

---

## Key Files Modified

| File Path | Lines | Purpose | Subagent |
|-----------|-------|---------|----------|
| `backend/tests/test_routing_rollup_no_llm_imports.py` | extend | Add worker entry-point BFS walk | python-backend-engineer |
| `backend/tests/test_routing_feedback_contract_parity.py` | extend | Confirm/harden digest-parity assertion | python-backend-engineer |
| `backend/tests/test_routing_rollup_envelope_completeness.py` | new | 11-field + 3-counter envelope assertion, all transports | python-backend-engineer |
| `backend/tests/test_routing_rollup_determinism.py` | extend | End-to-end worker-path determinism | python-backend-engineer |
| `backend/tests/test_routing_rollup_sparse_protected.py` | new | Sparse-key visibility + protected-class coverage-only | python-backend-engineer |
| `backend/tests/test_routing_rollup_disabled_state.py` | new | Disabled-state + reversibility + version-field, all transports | python-backend-engineer |
| `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md` | new | Cross-repo consumer contract doc | documentation-writer |
| `docs/guides/routing-feedback-loop.md` | new | Operator guide | documentation-writer |
| `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` | new | DI-1 handoff spec | documentation-writer |
| `docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md` | new | DI-2 handoff spec | documentation-writer |
| `docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md` | new | DI-3 handoff spec | documentation-writer |
| `CHANGELOG.md` | append | `[Unreleased]` entry | changelog-generator |

---

## Testing Strategy

### Unit Tests

- No-LLM AST-walk guard, second entry point for the worker module (T6-001)
- Digest-parity byte comparison against a deliberately-corrupted fixture copy (T6-002)
- Sparse-key and protected-class fixture assertions against the value-findings density fixture (T6-005)

### Integration Tests

- Envelope-completeness assertion parametrized across REST/MCP/CLI (T6-003)
- End-to-end determinism through the persisted worker upsert path, two full sweep runs (T6-004)
- Disabled-state byte-identity, flag-flip reversibility, version-field presence, and unconditional
  capability advertisement, all parametrized across REST/MCP/CLI (T6-006)

### E2E Tests (if applicable)

- N/A — no frontend surface; the REST/MCP/CLI parametrized tests in T6-003 and T6-006 are the closest
  analog to an E2E check for this feature (full transport-to-transport contract verification).

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Silent non-join / cross-repo vocabulary drift (seam risk, R-P3) | High | T6-002 (digest-parity, byte-exact) and T6-003 (envelope-completeness, structural) are CI-enforced, not manually reviewed; both fail the build on any drift, before the router's own `validateFeedbackJoin()` backstop is ever reached. |
| Constraint-4 violation (LLM on the compute/read path) | Medium | T6-001's second independent BFS entry point closes the one remaining gap (the worker was previously covered only by convention, not by the Phase 3 guard's traversal). |
| A phase-6 test regresses a Phase 1-5 test while extending it | Medium | Every T6-00x task that extends an existing test file (T6-001, T6-002, T6-004) explicitly requires the pre-existing assertion to remain green, not just the new one added. |
| A deferred-items spec accidentally scopes router-repo work as a CCDash task | Medium | DOC-006's acceptance criteria explicitly require the spec to stop at naming the seam; task-completion-validator (T6-007) checks this during the gate. |

---

## Success Metrics

Per the parent plan's frontmatter `success_metrics` (this phase is where each is finally proven, not
merely designed):

- **Mapping digest parity: 100%** — closed by T6-002
- **No-LLM compliance: 100%** — closed by T6-001 (worker) + the pre-existing Phase 3 guard (service)
- **Determinism: 100%** — closed by T6-004 (end-to-end, worker path)
- **Disabled-state consistency: 100%** — closed by T6-006(a)
- **Coverage visibility** (`mapped_count`/`unclassified_count`/`distinct_unmapped_skill_names` on every
  response) — closed by T6-003

---

## Acceptance Criteria Closure

Copied verbatim from the parent plan's Acceptance Criteria Index (`docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md`
§ "Acceptance Criteria Index"); full AC text (target_surfaces, propagation_contract, resilience) lives
in PRD §11 — not re-derived here.

| AC | Title | verified_by |
|----|-------|-------------|
| AC-1 | Envelope completeness | T6-003 |
| AC-2 | Mapping fidelity | T1-005, T6-002 |
| AC-3 | Determinism + no-LLM | T3-005, T6-001, T6-004 |
| AC-4 | Default-off disabled behavior | T5-004, T6-006 |
| AC-5 | Sparse-key / eligibility visibility | T3-004, T6-005 |
| AC-6 | `_unclassified` / protected-class coverage-only handling | T3-002, T6-005 |
| AC-7 | Reversibility | T4-003, T6-006 |
| AC-8 | Version-mismatch resilience | T1-002, T1-005, T6-006 |

---

## Notes

### Implementation Approach

This phase adds zero production code — every task is a test, a CI guard, or a document. The correct
posture for every T6-00x task is "extend or confirm coverage of already-shipped behavior," not
"implement new behavior to make a test pass." If any T6-00x test fails against the Phase 1-5 shipped
code, that is a **regression finding** against an earlier phase, not a Phase 6 implementation task —
route it back to the owning phase's own progress file rather than patching around it here.

### Gotchas

- **Digest strings are load-bearing literals.** `MAPPING_DIGEST`
  (`sha256:45a49bb1a6194c6a576160edab7c3212a9cc20e17e6a0b79d531c1c4928f63f5`) and `taxonomy_digest`
  (`sha256:d96a0819b0a3a42d14eccc1421d3146b8364253d975d9d54f4f264d4b6adeaca`) must be copied
  character-for-character from PRD §6.3 / §11 AC-2 — a single transcription typo makes T6-002 fail
  against a *correct* vendored file, which looks identical to a real drift finding until traced back.
- **"Byte-identical" across transports is stricter than "equal after JSON round-trip."** T6-003 and
  T6-006(a) should compare serialized bytes/structures per-transport, not just assert three Python
  dicts are `==` — a REST/MCP/CLI serialization-layer divergence (e.g. key ordering, null vs. absent)
  would otherwise slip through.
- **The two seam tasks (T6-002, T6-003) are intentionally sequenced, not parallelized** with each
  other in this task table, even though they touch different files — this keeps the R-P3 seam
  narrative linear and easy for `task-completion-validator` to audit as one continuous defense of
  Risk 1, rather than two independently-landing changes.

### Learnings

_Capture learnings as this phase progresses._

### Findings Captured This Phase

- [ ] No new findings this phase (default)

---

**Phase Version**: 1.0
**Last Updated**: 2026-07-29

[Return to Parent Plan](../proof-to-routing-loop-v1.md)
