---
title: CCDash Routing Feedback Consumer Contract v1
doc_type: design-spec
feature_slug: proof-to-routing-loop
status: draft
created: 2026-07-31
updated: 2026-07-31
audience: developers
category: cross-repo-integration
tags:
  - ccdash
  - routing-feedback
  - meaty-skills
  - consumer-contract
  - pull-transport
related_documents:
  - docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
  - docs/project_plans/design-specs/proof-to-routing-loop.md
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json
  - docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md
description: |
  Hand-off contract for MeatySkills/delegation-router consumers of CCDash's routing-feedback evidence.
  Specifies the PULL transport (REST/MCP/CLI), empirical metric inputs, mapping fidelity guardrails,
  and CCDash-side invariants. Consumers route based on `(task_class × model)` tuples and empirical
  metrics (`success_rate`, `cost_index`, `regression_rate`); CCDash never actuates routing decisions.
---

# CCDash Routing Feedback Consumer Contract v1

## Contract Overview

**Transport**: PULL (consumers query CCDash; CCDash never pushes or dispatches work)

**Canonical Source**: CCDash's REST/MCP/CLI surfaces expose the `routing_feedback_rollup` schema verbatim, vendored against the pinned `aos.routing.feedback` v1.0.0 contract and the exact `ccdash.skill_name_to_aos.routing.task_class` v1.1.0 mapping.

**Consumer Responsibility**: MeatySkills/delegation-router owns all routing adjustment math, bounded-cap enforcement, minimum-sample re-gating, decay blending, empirical scoring, and RoutingRecord provenance. CCDash produces evidence only.

**CCDash Responsibility**: deterministic, model-free aggregation of session outcomes over rolling windows, application of the exact pinned skill-name-to-task-class mapping, and provision of empirical proof metrics. Zero LLM calls. Zero autonomous dispatch or writeback.

---

## 1. Access Pattern (PULL)

### 1.1 REST Endpoint (Project-Wide List)

**The primary consumer PULL surface for listing all routing feedback rows in a project:**

```
GET /api/v1/routing/rollup?project_id={project_id}&bypass_cache={bool}
```

**Query Parameters:**
- `project_id` (required): the CCDash project identifier
- `bypass_cache` (optional, default false): skip query cache and fetch fresh data

**Response envelope** (ClientV1Envelope[RoutingRollupDTO]):

```typescript
{
  "status": "ok" | "partial" | "error",
  "data": {
    "project_id": string,
    "enabled": boolean,
    "generated_at": string | null,     // ISO 8601; null if disabled
    "contract_id": string,              // "aos.routing.feedback"
    "contract_version": string,         // "1.0.0"
    "taxonomy_id": string,              // "aos.routing.task_class"
    "taxonomy_version": string,         // "1.0.0"
    "taxonomy_digest": string,          // "sha256:..."
    "mapping_id": string,               // "ccdash.skill_name_to_aos.routing.task_class"
    "mapping_version": string,          // "1.1.0"
    "mapping_digest": string,           // "sha256:3935a9805c9197564af645311018e7fc61aabe10a6a82098920e32329066c855"
    "mapped_count": number,             // count of rows with task_class != "_unclassified"
    "unclassified_count": number,       // count of rows with task_class == "_unclassified"
    "distinct_unmapped_skill_names": [string],  // all skill_name values that mapped to _unclassified
    "keys": [
      // Each entry is a RoutingFeedbackKeyDTO (see §3 for full schema)
      {
        "producer": string,             // "ccdash"
        "source_skill_name": string,    // raw skill_name from session telemetry
        "task_class": string,           // derived via pinned mapping; "_unclassified" if not found
        "model": string,                // e.g., "claude-sonnet-5"
        "provider": string,             // derived via derive_model_identity()
        "sample_count": number,         // sessions in the window matching this key
        "success_rate": number | null,  // [0.0, 1.0]; fraction of non-failed outcomes. Nullable in v1 (RoutingFeedbackKeyDTO.success_rate: float | None = None) — null is a contract state, not a bug; see resilience-by-default convention
        "cost_index": number,           // relative cost vs baseline model for task_class
        "regression_rate": number | null, // [0.0, 1.0]; estimate of performance regression. Nullable in v1 (RoutingFeedbackKeyDTO.regression_rate: float | None = None) — same null-as-contract-state convention
        "confidence": number,           // [0.0, 1.0]; CCDash confidence in the metric aggregate
        "eligible_for_adjustment": boolean,  // true iff sample_count >= min_sample_threshold AND task_class not protected
        "window_start": string,         // ISO 8601; rolling window start
        "window_end": string,           // ISO 8601; rolling window end
        "freshness_ts": string          // ISO 8601; when this row was last computed
      }
    ]
  },
  "meta": {...}
}
```

**Note on structure**: No `success`, `error`, or `request_id` fields. The `keys` array contains all available rollup keys for the project. No pagination (`limit`, `offset`) is supported in v1.

### 1.2 MCP Tool (Project-Scoped Query)

Exposed as `ccdash_routing_rollup` (transport-neutral, project-scoped query):

```typescript
parameters:
  - project_id: string | None (optional) — the CCDash project identifier
```

**Returns**: A complete `RoutingRollupDTO` for the specified project. There is no `task_class` filter parameter on this tool in v1 — it always returns the full set of rollup keys for the project.

**Note**: This is a project-scoped query tool, not a single-key lookup. Use the REST endpoint (§1.1) for comprehensive browsing and filtering.

### 1.3 CLI Surface (Project-Scoped Query)

```bash
ccdash routing rollup [--project <project_id>] [--task-class <class>] [--output json|md|text]
```

**Flags:**
- `--project` (optional): the CCDash project identifier; if not provided, uses the current active project
- `--task-class` (optional): filter to this task_class only
- `--output` or `--json` or `--md` (optional): output format (default: text)

**Returns**: Routing feedback metrics for the project, optionally filtered by task_class.

**Note**: This is a project-scoped command, not a single-key lookup. The CLI does not support `--model` or `--skill-name` individual filters; use the REST endpoint (§1.1) and filter client-side if needed.

### 1.4 PROPOSED (Not Yet Implemented): Paginated Filtered List

**Future enhancement** (does not ship in P1; marked explicitly to prevent integration against an unshipped surface):

```
GET /api/v1/routing/rollup/list?project_id=<id>&task_class=<class>&limit=50&offset=0
```

This surface would support `limit`, `offset`, and `task_class` query parameters for paginated, filtered browsing. It is NOT available today. Consumers wanting to filter today must fetch all keys via §1.1 and filter client-side.

### 1.5 Capability Advertisement

All CCDash servers advertise capability discovery on startup:

```
GET /api/v1/capabilities
```

**Response**:

```typescript
{
  "capabilities": [
    "routing:feedback",
    "aar-review",
    "sessions:detail",
    "sessions:cross-project",
    ...
  ]
}
```

**Consumer contract**: Consumers MUST NOT hard-fail if the `routing:feedback` capability string is absent. Absent capability means the server predates this feature; present means the contract documented below is honored. Poll `/api/v1/capabilities` before using routing-feedback endpoints; treat unknown capability strings as "may not be supported yet."

---

## 2. Empirical Metric Inputs & Routing Decisions

**CCDash provides these inputs to support empirical routing decisions:**

1. **`sample_count`** (integer, ≥ 0)
   - Number of sessions in the rolling window matching this `(source_skill_name × model)` key.
   - Signals data richness for the tuple.

2. **`success_rate`** (float | null, [0.0, 1.0])
   - Fraction of sessions in the sample that completed without a terminal failure.
   - Higher is better; 1.0 means 100% success.
   - **Nullable in v1**: `RoutingFeedbackKeyDTO.success_rate` is `float | None = None` (`backend/application/services/agent_queries/models.py`). Null means the value was not yet computable for this key (e.g., no eligible outcome data) — a contract state, not a bug. Consumers must not fail parsing on null.

3. **`cost_index`** (float, ≥ 0.0)
   - Relative token/cost expenditure vs the baseline model for the task_class.
   - 1.0 is the baseline; 2.0 means 2x cost; 0.5 means half cost.

4. **`regression_rate`** (float | null, [0.0, 1.0])
   - Estimated probability that this model is performing worse than it did historically.
   - Higher means higher risk of regression.
   - **Nullable in v1**: `RoutingFeedbackKeyDTO.regression_rate` is `float | None = None`, same null-as-contract-state convention as `success_rate` above.

5. **`confidence`** (float, [0.0, 1.0])
   - CCDash's confidence in the metric aggregate over the sample window.
   - Confidence is lower for sparse samples; higher for dense, consistent data.

6. **`eligible_for_adjustment`** (boolean)
   - TRUE iff `sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` AND `task_class` is not in the protected set (`_unclassified`, `orchestration`, `mode_d`).
   - FALSE means the row is evidence-only, never an addressable routing key.

7. **`window_start` / `window_end` / `freshness_ts`** (ISO 8601 timestamps)
   - Temporal context: which rolling window this row represents and when it was computed.

**Everything else in the key is context; routing decisions are built from the 6 metrics above and `eligible_for_adjustment`.**

---

## 3. `routing_feedback_rollup` Schema (VERBATIM from PRD §6, D5)

```yaml
# emitted by CCDash; consumed by delegation-router (cross-repo, out of scope here). Producer-side contract lock.
schema_version: 1
event_type: routing_feedback_rollup
producer: ccdash

# Pinned contract envelope (aos.routing.feedback v1.0.0 — 11 fields, all required)
contract_id: str                                    # "aos.routing.feedback"
contract_version: str                              # "1.0.0"
taxonomy_id: str                                   # "aos.routing.task_class"
taxonomy_version: str                              # "1.0.0"
taxonomy_digest: str                               # SHA-256 of normative taxonomy
mapping_id: str                                    # "ccdash.skill_name_to_aos.routing.task_class"
mapping_version: str                               # "1.1.0"
mapping_digest: str                                # SHA-256 of ccdash.skill_name_to_aos.routing.task_class v1.1.0 (fixed: 3935a980...)
source_skill_name: str                             # raw skill_name from sessions table
task_class: str                                    # derived via pinned mapping; "_unclassified" if no match

# CCDash-designed metric payload (D5 — additive-versioned, open to extension in v1.1+)
model: str                                         # e.g., "claude-sonnet-5"
provider: str                                      # derived via derive_model_identity()
sample_count: int                                  # sessions in window matching (source_skill_name, model)
success_rate: float | None                         # [0.0, 1.0]; nullable in v1 — null is a contract state, not a bug
cost_index: float                                  # >= 0.0, relative to baseline for task_class
regression_rate: float | None                      # [0.0, 1.0]; nullable in v1 — null is a contract state, not a bug
confidence: float                                  # [0.0, 1.0]
eligible_for_adjustment: bool                      # true iff sample_count >= min_sample AND task_class not protected
window_start: datetime                             # ISO 8601; rolling window start
window_end: datetime                               # ISO 8601; rolling window end
freshness_ts: datetime                             # ISO 8601; when this row was computed by worker

# Project-scoped context (CCDash-added)
project_id: str                                    # which registered project this key is scoped to
```

---

## 4. Mapping Fidelity & Vocabulary Guardrails

### 4.1 The Pinned Mapping — Non-Negotiable Precision

**CRITICAL GUARANTEE:**

> CCDash **never** emits raw `skill_name` as `task_class`. Every `task_class` value is derived deterministically and verbatim from the pinned `ccdash.skill_name_to_aos.routing.task_class` v1.1.0 mapping (digest: `sha256:3935a9805c9197564af645311018e7fc61aabe10a6a82098920e32329066c855`).

**Verification**: CCDash vendors this mapping file locally and CI-verifies the SHA-256 digest against the contract's pinned value on every build. The vendored file is immutable at runtime; it does not call out to agentic_meta_dev or any external taxonomy source.

### 4.2 Protected Classes & `_unclassified` Handling

**Protected-class task names** (`orchestration`, `mode_d`, and any future MUST-STAY entries in the taxonomy) are never presented as addressable routing keys:

- Rows with `task_class` in the protected set carry `eligible_for_adjustment: false` (hardcoded, non-overridable).
- Rows with `source_skill_name` not found in the pinned mapping are assigned `task_class: "_unclassified"` and marked `eligible_for_adjustment: false`.
- Both types are emitted as coverage evidence only, never as routing keys.

**Consumer guarantee**: No protected-class row will ever carry `eligible_for_adjustment: true`, and the router's own `validateFeedbackJoin()` re-check provides a second defense layer.

### 4.3 Row Grain & Router-Side Merge Responsibility

**Emission/storage grain**: `(project_id, source_skill_name, model)` per rolling window.

**Router-facing join dimension**: `(task_class × model)`.

**Key insight**: The router is responsible for merging rows across multiple `source_skill_name` values that share a `task_class` — CCDash emits every row at the source-skill-name grain. This design allows:
- The router to independently re-validate each row's mapping (defense-in-depth via `validateFeedbackJoin()`).
- CCDash to emit self-describing, traceable evidence (raw skill name is always present).
- Ambiguity resolution at the router (if two skills legitimately map to the same task_class, the router sees both rows and decides how to merge).

---

## 5. CCDash-Side Invariants (Consumer Guarantees)

The consumer can rely unconditionally on these invariants:

### 5.1 Deterministic Aggregation, No LLM

- **Guarantee**: Every row is computed via deterministic SQL aggregation and threshold/mapping lookup over already-ingested DB rows.
- **Verification**: No model-client import exists anywhere in `backend/application/services/agent_queries/routing_rollup.py` or its dependency graph. CI-enforced AST-walk guard prevents LLM-related imports.
- **Consequence**: Rows are reproducible, auditable, and cost-neutral to CCDash's recall path.

### 5.2 Producer-Only, No Dispatch

- **Guarantee**: CCDash emits rollup keys and exposes query surfaces only. It never calls delegation-router, MeatySkills, or AOS APIs; never schedules routing adjustments; never mutates SkillMeat/agents/skills.
- **Verification**: Codebase review confirms no router-client, meaty-skills-client, or swarm imports in CCDash's routing-feedback code.
- **Consequence**: CCDash is a source of truth (producer), not an orchestrator or adjuster.

### 5.3 Mapping Digest Enforcement

- **Guarantee**: The vendored `routing-feedback-task-map.v1.json` is SHA-256-verified against the pinned digest (`3935a9805c9197564af645311018e7fc61aabe10a6a82098920e32329066c855`) on every CI run.
- **Verification**: A failed digest parity check fails the build immediately; no rollup logic runs against a stale or locally-edited mapping.
- **Consequence**: Silent vocabulary drift (skill-name non-join or mis-join) is impossible; CCDash's mapping is byte-for-byte identical to the normative copy in agentic_meta_dev.

### 5.4 Redaction-Passed Input

- **Guarantee**: Every metric reads only from CCDash's redaction-passed `session_detail` data, not raw JSONL.
- **Verification**: Metrics depend on `sessions` table columns and repository queries only; no unparsed JSONL or transcript content touches the aggregation.
- **Consequence**: Sensitive data (credentials, API keys, personal information) present in raw sessions is already scrubbed before metrics run.

### 5.5 Explicit Enabled/Disabled State

- **Guarantee**: When `CCDASH_ROUTING_FEEDBACK_ENABLED=false`, all three transports return the byte-identical disabled envelope (HTTP 200, `"enabled": false`, empty `keys[]`, zero counts). When enabled, `"enabled": true` + full data.
- **Verification**: Unit test across REST/MCP/CLI transports asserts field-identical disabled envelopes.
- **Consequence**: Absence of data is a distinguishable state, never an ambiguous 404/500/null-body edge case.

### 5.6 Version Fields Always Present

- **Guarantee**: Every response — enabled or disabled — carries `contract_version`, `taxonomy_version`, and `mapping_version` fields.
- **Verification**: DTO schema enforces presence regardless of enabled flag.
- **Consequence**: A consumer pinned to a different version can detect the mismatch and refuse to actuate per the contract's compatibility rules.

### 5.7 Project Scoping via DB Registry

- **Guarantee**: All data returned by routing-feedback queries is scoped to the authenticated project (ADR-006, DB-authoritative registry).
- **Verification**: AuthContext in every REST/MCP/CLI request; routers enforce project_id scoping at the SQL layer.
- **Consequence**: No cross-project data leakage; multi-tenant safety.

---

## 6. Ownership & Boundaries

### 6.1 CCDash Owns

- Computing empirical metrics (success_rate, cost_index, regression_rate, confidence, sample_count) from session telemetry over rolling windows
- Applying the exact pinned skill-name-to-task-class mapping to derive `task_class`
- Identifying and marking protected-class and `_unclassified` rows as coverage-only
- Emitting the full 11-field join envelope with CCDash-designed metric payload
- Persisting rollup rows and coverage counters
- Exposing rollup via REST/MCP/CLI transports with version/digest identity fields

### 6.2 Delegation-Router / MeatySkills Owns

- Re-validating each row's `source_skill_name → task_class` mapping independently (`validateFeedbackJoin()`)
- Merging rows across multiple source skill names sharing a task_class (if desired)
- Applying bounded-cap enforcement, effective-score floors, minimum-sample re-gating, decay blending
- Deriving adjusted RoutingRecord values and RoutingRecord provenance
- Making actual routing adjustments (CCDash's feedback is input only, never actuated by CCDash)
- All HITL gates and approvals

**Seam**: The `routing_feedback_rollup` event and its payload of metrics and mapping identity.

---

## 7. Metric Semantics & Operator Visibility

### 7.1 Metric Definitions (Per Project Per Window)

**`success_rate`** (derived from session outcome telemetry):
- Fraction of sessions in the sample that did not end with a terminal failure (error, timeout, OOM, etc.).
- Sessions ending in partial success, warnings, or retries are counted as successes.
- 1.0 = all succeeded; 0.0 = all failed.
- Empty sample → 0.5 (neutral default).

**`cost_index`** (relative to task_class baseline):
- Ratio of observed cost (tokens + compute) to the baseline model for the task_class.
- Computed by: `observed_cost / baseline_cost_for_task_class`.
- 1.0 = on-par; 2.0 = 2x cost; 0.5 = half cost.
- Baseline is established externally (operator-configured); CCDash computes the ratio only.

**`regression_rate`** (statistical estimate):
- Estimated probability that this model's success_rate or cost_index has degraded vs historical baseline.
- Computed by comparing current window to prior window(s) via statistical test (e.g., z-test on success_rate).
- 0.0 = no evidence of regression; 1.0 = strong evidence of regression.

**`confidence`** (sample quality indicator):
- Meta-measure of data richness and consistency.
- Computed from: `sample_count`, coefficient of variation across sub-windows, density of non-null sessions.
- Higher sample_count → higher confidence; lower variance → higher confidence.
- 0.0 = very sparse/noisy; 1.0 = very dense/consistent.

### 7.2 Coverage & Visibility Counters

**`mapped_count`**: Number of rows with `task_class != "_unclassified"`. Indicates what fraction of the session corpus was successfully classified.

**`unclassified_count`**: Number of rows with `task_class == "_unclassified"`. Indicates detection/mapping gaps.

**`distinct_unmapped_skill_names`**: Full list of unique `source_skill_name` values that did not match the pinned mapping. Enables operators to identify which skills are orphaned and may need taxonomy extension.

### 7.3 Eligibility & Routing Readiness

**`eligible_for_adjustment`** per row:
- TRUE: `sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` AND `task_class` not in protected set.
- FALSE: Either condition fails. Row is emitted as evidence/coverage only.

**Consumer interpretation**: Only rows with `eligible_for_adjustment: true` should be considered for routing adjustments. Rows with FALSE should be studied as evidence but not actuated upon — either the sample is too sparse or the task class is protected from routing changes.

---

## 8. Resilience & Degradation

### 8.1 Capability Negotiation

Consumers calling `/api/v1/capabilities` before accessing routing-feedback endpoints must handle:

- **Server predates routing-feedback**: `"routing:feedback"` capability absent → routing-feedback endpoints may not exist.
  - Consumer action: skip routing-feedback queries; rely on existing manual scorecard or other routing sources.

- **Server supports routing-feedback**: `"routing:feedback"` capability present AND feature enabled → contract documented here is guaranteed.
  - Consumer action: proceed with routing-feedback queries per the metrics above.

- **Server supports feature but it is disabled**: Capability present BUT `enabled: false` in response → feature exists but is administratively off.
  - Consumer action: poll occasionally; re-enable may happen without server restart. Treat disabled state as "no new data" (empty keys[], zero counts).

### 8.2 Missing/Null Fields

Event examples:

- `metrics.*` are null or absent → computation was skipped (e.g., sample_count < 1).
  - Consumer action: treat as no data for this key; do not fail parsing.

- `distinct_unmapped_skill_names` is empty → all skill names in the window mapped successfully.
  - Consumer action: perfect classification; no operator action needed.

- `window_start` / `window_end` are identical → the window is degenerate or misconfigured.
  - Consumer action: log as a warning; fetch fresh data from the next successful rollup.

### 8.3 Transient Query Failures

Endpoints may return:

```json
{
  "status": "error",
  "error": "project not found",
  "data": null
}
```

Consumer action: log the error; retry with exponential backoff. Escalate to operator if persistent.

### 8.4 Sparse-Key Handling

A key with `sample_count = 1` and `eligible_for_adjustment = true`:

- CCDash considers it eligible (threshold was met).
- Router may apply its own stricter threshold before actuating (out of scope here).
- Row is valid evidence either way; the router is free to ignore sparse keys.

---

## 9. Observability & Auditing

### 9.1 Structured Logs on Rollup Emission (Worker Path)

Every `routing_rollup` computation logs (structured JSON):

```json
{
  "timestamp": "ISO8601",
  "event_type": "routing_rollup_computed",
  "project_id": "...",
  "window_start": "ISO8601",
  "window_end": "ISO8601",
  "total_keys_emitted": 42,
  "mapped_count": 40,
  "unclassified_count": 2,
  "rows_at_sample_threshold": 38,
  "rows_below_threshold": 4,
  "distinct_unmapped_skill_names_count": 2,
  "trace_id": "...",
  "span_id": "..."
}
```

**Content guarantee**: Never includes session content, metrics details, or skill names. Only counts and metadata.

### 9.2 Consumer Observability

Consumers SHOULD log every decision point:

```json
{
  "timestamp": "ISO8601",
  "event": "routing_feedback_consumed",
  "project_id": "...",
  "keys_fetched": 42,
  "eligible_keys": 38,
  "adjustment_keys_selected": 5,
  "trace_context": "inherited from CCDash rollup"
}
```

This enables end-to-end tracing from rollup emission through consumer evaluation to routing outcome.

---

## 10. P1-P4 Stability (Feature Rollout)

| Phase | Data Available | Guarantees |
|-------|---|---|
| **P1** | Yes (REST/MCP/CLI read-only) | Metrics + mapping identity stable; enabled/disabled state deterministic. |
| **P2** | Yes (FE operator visibility surface) | Same metrics + identity; rollup table persisted; no cross-repo consumer yet. |
| **P3** | Yes (cross-repo consumer spec locked) | Same metrics + identity; router validation implemented on consumer side; no live consumption yet. |
| **P4** | Yes (live consumption enabled on router) | Same metrics + identity; router-side merge math operationalized; consumer is live. |

**Consumer contract stability**: The 6 core metrics (`sample_count`, `success_rate`, `cost_index`, `regression_rate`, `confidence`, `eligible_for_adjustment`) and the mapping digest are **fixed** across all phases. New fields in the payload are added in later versions (v1.1+) as non-breaking extensions (null/absent in prior versions).

---

## 11. Examples

### 11.1 Example: High-Sample, High-Confidence Key

```json
{
  "producer": "ccdash",
  "source_skill_name": "dev-execution",
  "task_class": "implementation",
  "model": "claude-sonnet-5",
  "provider": "anthropic",
  "sample_count": 68,
  "success_rate": 0.91,
  "cost_index": 1.0,
  "regression_rate": 0.03,
  "confidence": 0.88,
  "eligible_for_adjustment": true,
  "window_start": "2026-06-29T00:00:00Z",
  "window_end": "2026-07-29T00:00:00Z",
  "freshness_ts": "2026-07-29T02:00:00Z",
  "contract_version": "1.0.0",
  "taxonomy_version": "1.0.0",
  "mapping_version": "1.1.0"
}
```

**Consumer interpretation**:
- High sample (68), high confidence (0.88).
- Success rate 91% is solid; cost is at baseline.
- Regression rate 3% is low (minimal drift).
- **Decision**: This key is a strong candidate for routing adjustments. Good empirical foundation for routing decisions.

### 11.2 Example: Sparse Key Below Threshold

```json
{
  "producer": "ccdash",
  "source_skill_name": "rare-skill",
  "task_class": "analysis",
  "model": "gpt-5.6-terra",
  "provider": "openai",
  "sample_count": 1,
  "success_rate": 1.0,
  "cost_index": 3.2,
  "regression_rate": 0.5,
  "confidence": 0.2,
  "eligible_for_adjustment": false,
  "window_start": "2026-06-29T00:00:00Z",
  "window_end": "2026-07-29T00:00:00Z",
  "freshness_ts": "2026-07-29T02:00:00Z",
  "contract_version": "1.0.0",
  "taxonomy_version": "1.0.0",
  "mapping_version": "1.1.0"
}
```

**Consumer interpretation**:
- Sparse sample (1), very low confidence (0.2).
- Success rate is 100%, but based on one data point — meaningless.
- Cost is very high (3.2x), but on one sample — could be an outlier.
- Regression rate 50% is inconclusive with n=1.
- `eligible_for_adjustment: false` because `sample_count < threshold`.
- **Decision**: Do not route based on this row. Study it, but wait for more data or use other evidence.

### 11.3 Example: Protected-Class Row (Coverage-Only)

```json
{
  "producer": "ccdash",
  "source_skill_name": "orchestration-controller",
  "task_class": "orchestration",
  "model": "claude-sonnet-5",
  "provider": "anthropic",
  "sample_count": 200,
  "success_rate": 0.99,
  "cost_index": 0.8,
  "regression_rate": 0.0,
  "confidence": 0.95,
  "eligible_for_adjustment": false,
  "window_start": "2026-06-29T00:00:00Z",
  "window_end": "2026-07-29T00:00:00Z",
  "freshness_ts": "2026-07-29T02:00:00Z",
  "contract_version": "1.0.0",
  "taxonomy_version": "1.0.0",
  "mapping_version": "1.1.0"
}
```

**Consumer interpretation**:
- Large sample (200), very high confidence (0.95).
- Excellent success rate (99%), low cost (0.8x).
- `task_class: "orchestration"` is in the protected set.
- `eligible_for_adjustment: false` is **hardcoded for this task_class**, never overridable.
- **Decision**: This row is evidence of stable system behavior, never an adjustment key. Do not route based on it (even if metrics are excellent).

### 11.4 Example: Unclassified Row (Coverage-Only)

```json
{
  "producer": "ccdash",
  "source_skill_name": "new-experimental-skill",
  "task_class": "_unclassified",
  "model": "claude-opus-5",
  "provider": "anthropic",
  "sample_count": 15,
  "success_rate": 0.87,
  "cost_index": 1.5,
  "regression_rate": 0.1,
  "confidence": 0.6,
  "eligible_for_adjustment": false,
  "window_start": "2026-06-29T00:00:00Z",
  "window_end": "2026-07-29T00:00:00Z",
  "freshness_ts": "2026-07-29T02:00:00Z",
  "contract_version": "1.0.0",
  "taxonomy_version": "1.0.0",
  "mapping_version": "1.1.0"
}
```

**Consumer interpretation**:
- Good sample (15), fair confidence (0.6).
- Decent metrics, but `task_class: "_unclassified"` (not in pinned mapping).
- `eligible_for_adjustment: false` because the skill is not yet in the taxonomy.
- **Decision**: Operator action: add `"new-experimental-skill" → "analysis"` (or appropriate class) to the pinned mapping in agentic_meta_dev. Once updated + digested, this row will re-classify and become eligible. Until then, it's evidence of an unmapped skill.

---

## 12. References & Related Docs

- **PRD (north-star)**: `docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md` (sections 6, 7, 8, functional/non-functional requirements)
- **Design Spec**: `docs/project_plans/design-specs/proof-to-routing-loop.md` (structural details, P1-P4 rollout)
- **Cross-repo contract**: `/Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md` (`aos.routing.feedback` v1.0.0 — the normative specification)
- **Mapping artifact**: `/Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json` (`ccdash.skill_name_to_aos.routing.task_class` v1.1.0)
- **Precedent (producer/consumer pattern)**: `docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md` (parallel contract for AAR review)
- **Operator guide**: `docs/guides/routing-feedback-loop.md` (how-to for enabling, tuning, monitoring the feature)

---

## 13. Change Log

- **2026-07-31**: Initial draft. Contract locked at P1 scope (PULL transport, 6-metric inputs, mapping fidelity guardrails, invariants). Router-side empirical merge is named as out-of-scope cross-repo deferral.
- **Mapping history**: v1.0.0 (17 rules, initial) → v1.1.0 (36 rules; added 19 observed-but-unmapped skill names so the coverage report distinguishes "known and deliberately unroutable" from "never seen"). Contract version and taxonomy are unchanged.
