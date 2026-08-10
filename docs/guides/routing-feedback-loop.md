---
title: "Routing Feedback Loop Operator Guide"
description: "Configure and operate the CCDash routing feedback producer surface: PULL endpoint, capability discovery, empirical rollup emission, and model namespacing caveats"
category: guides
tags: [api, routing-feedback, operator, cross-repo, aos-contract, empirical-routing]
updated: 2026-07-31
---

# Routing Feedback Loop Operator Guide

This guide covers operating the CCDash Routing Feedback Loop producer surface for external
routing consumers (delegation-router in MeatySkills, LAN agents). The loop is deterministic,
model-free, emit-only, and reversible; this document focuses on configuration, capability
discovery, and the cross-repo contract boundaries.

> **Architecture reference**: `CLAUDE.md` § Key Conventions for the core invariants.
> For the cross-repo consumer contract and router-side empirical merge, see
> `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md` and
> `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md`.

---

## Overview: Deterministic Empirical Rollup (Producer Only)

The Routing Feedback Loop consists of two distinct phases—both **producer-side** (this repo):

1. **Deterministic Rollup Computation** (always on when enabled, read-only): Aggregates
   session outcomes at `(source_skill_name × model)` grain, applies the pinned
   `aos.routing.feedback` v1.0.0 contract's exact `skill_name → task_class` mapping, and
   computes empirical metrics (sample count, success rate, cost index, regression rate,
   confidence, window/freshness). No LLM involved. Rollup rows are available immediately
   via the v1 endpoint and persisted in the `routing_rollup` table.

2. **Autonomous Worker** (enabled by default; worker-profile-gated): A background sweep job
   that periodically aggregates sessions across **every registered project** and persists
   rollup rows to the `routing_rollup` table. It runs only under the `worker` runtime
   profile (the dedicated `ccdash_worker` container in the compose stack), never under
   `api`/`local`/`test`. No model calls. No push/dispatch to the router—PULL only.
   Set `CCDASH_ROUTING_FEEDBACK_ENABLED=false` to disable entirely.

**Producer-only scope**: CCDash emits evidence only. The backward-pass loop does not close
end-to-end until the router-side empirical merge (bounded-adjustment cap, effective-score floor,
decay blend, `RoutingRecord` provenance) lands in MeatySkills/`ibm-main` — currently
`live_consumption_disabled`. Nothing in this document claims routing improves automatically;
it claims only that CCDash's evidence becomes consumable.

**Mapping history**: v1.0.0 (17 rules, initial) → v1.1.0 (36 rules; added 19 observed-but-unmapped
skill names so the coverage report distinguishes "known and deliberately unroutable" from
"never seen").

---

## Capability Discovery

All CCDash servers declare the `routing:feedback` capability via the standard discovery endpoint:

```bash
GET /api/v1/capabilities
```

**Response:**

```json
{
  "status": "ok",
  "data": {
    "api_version": "1",
    "capabilities": ["routing:feedback", "aar-review", "sessions:detail", ...],
    "instance_id": "ccdash-local",
    "server_time": "2026-07-31T02:00:00Z"
  },
  "meta": { ... }
}
```

| Capability | Meaning |
|---|---|
| `routing:feedback` | The v1 `GET /api/v1/routing/rollup` endpoint is available; consumers can query empirical `(skill_name × model)` routing feedback for evidence-based routing decisions. |

**Consumer rule**: Treat an unknown capability string as a future addition — do NOT error
on strings you do not recognize. Absent `routing:feedback` means the server predates this feature
or has it disabled. **Importantly**: `routing:feedback` in the capability list means the endpoint
exists and is contract-compliant; it does not mean `CCDASH_ROUTING_FEEDBACK_ENABLED=true`.
A disabled feature still advertises its capability.

---

## Read Endpoint: Empirical Routing Feedback Rollup

### GET /api/v1/routing/rollup

The primary PULL surface for fetching all computed routing-feedback rollup keys:

```bash
GET /api/v1/routing/rollup?project_id={project_id}&bypass_cache={bool}
```

**Query Parameters:**

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `project_id` | string | yes | — | The CCDash project identifier. |
| `bypass_cache` | bool | no | false | Skip query cache and fetch fresh data. |

**Response Envelope** (ClientV1Envelope[RoutingRollupResponseDTO]):

```json
{
  "status": "ok",
  "data": {
    "enabled": true,
    "generated_at": "2026-07-31T02:00:00Z",
    "contract_id": "aos.routing.feedback",
    "contract_version": "1.0.0",
    "taxonomy_id": "aos.routing.task_class",
    "taxonomy_version": "1.0.0",
    "taxonomy_digest": "sha256:d96a0819b0a3a42d14eccc1421d3146b8364253d975d9d54f4f264d4b6adeaca",
    "mapping_id": "ccdash.skill_name_to_aos.routing.task_class",
    "mapping_version": "1.1.0",
    "mapping_digest": "sha256:3935a9805c9197564af645311018e7fc61aabe10a6a82098920e32329066c855",
    "mapped_count": 767,
    "unclassified_count": 13632,
    "distinct_unmapped_skill_names": ["skill-x", "skill-y"],
    "skill_attributed_key_count": 82,
    "skill_unattributed_key_count": 106,
    "keys": [
      {
        "producer": "ccdash",
        "contract_id": "aos.routing.feedback",
        "contract_version": "1.0.0",
        "taxonomy_id": "aos.routing.task_class",
        "taxonomy_version": "1.0.0",
        "taxonomy_digest": "sha256:d96a0819b0a3a42d14eccc1421d3146b8364253d975d9d54f4f264d4b6adeaca",
        "mapping_id": "ccdash.skill_name_to_aos.routing.task_class",
        "mapping_version": "1.1.0",
        "mapping_digest": "sha256:3935a9805c9197564af645311018e7fc61aabe10a6a82098920e32329066c855",
        "source_skill_name": "dev-execution",
        "task_class": "implementation",
        "model": "claude-sonnet-5",
        "provider": "anthropic",
        "sample_count": 68,
        "success_rate": 0.91,
        "success_rate_coverage_fraction": null,
        "cost_index": 1.12,
        "cost_coverage_fraction": 0.94,
        "regression_rate": 0.03,
        "confidence": 0.8,
        "eligible_for_adjustment": true,
        "window_start": "2026-06-29T00:00:00Z",
        "window_end": "2026-07-31T00:00:00Z",
        "freshness_ts": "2026-07-31T02:00:00Z"
      }
    ]
  },
  "meta": { ... }
}
```

> **`success_rate_coverage_fraction` note (DI-4e):** unlike `cost_coverage_fraction`, this field is
> compute-layer/response-DTO only — no persisted column was added. It always reads back `null` on
> `/api/v1/routing/rollup` (and every other transport, since all three read the persisted table),
> shown as `null` above deliberately rather than a numeric placeholder.

**Field Definitions — Pinned Join Envelope** (aos.routing.feedback v1.0.0):

| Field | Type | Meaning |
|---|---|---|
| `producer` | string | Always `"ccdash"`. Identifies this as a CCDash-originated rollup. |
| `contract_id` | string | Always `"aos.routing.feedback"`. Identifies the normative cross-repo contract. |
| `contract_version` | string | The version of the contract this rollup claims compliance with (currently `"1.0.0"`). |
| `taxonomy_id` | string | Always `"aos.routing.task_class"`. Identifies the task-class taxonomy. |
| `taxonomy_version` | string | The version of the task-class taxonomy (`"1.0.0"`). |
| `taxonomy_digest` | string | SHA-256 hash of the canonical taxonomy file. Consumer may re-verify if desired. |
| `mapping_id` | string | Always `"ccdash.skill_name_to_aos.routing.task_class"`. Identifies this feature's skill→task_class mapping. |
| `mapping_version` | string | The version of the mapping (`"1.1.0"`). |
| `mapping_digest` | string | SHA-256 hash of the vendored mapping file. **Seam safety**: must match the contract's pinned digest on every response. |
| `source_skill_name` | string | The raw `skill_name` as captured from the session. **Critical for router's `validateFeedbackJoin()`**: the router re-validates this field's mapping independently; never rely on the derived `task_class` alone. |
| `task_class` | string | The normalized task-class label derived by applying the pinned mapping to `source_skill_name`. Possible values: `implementation`, `planning`, `testing`, `documentation`, `refactoring`, `debugging`, `orchestration` (protected), `mode_d` (protected), `_unclassified` (coverage). |

**Field Definitions — Empirical Metrics (CCDash-designed, D5)**:

| Field | Type | Meaning |
|---|---|---|
| `model` | string | The model identifier as captured from the session (e.g., `"claude-sonnet-5"`, `"gpt-5.6-terra"`). Verbatim; no cross-repo canonicalization yet. |
| `provider` | string | Derived from `model` via `derive_model_identity()` (`"anthropic"`, `"openai"`, etc.). Never an independent routing dimension. |
| `sample_count` | int | Number of sessions aggregated in this `(source_skill_name, model)` key within the rolling window. |
| `success_rate` (DI-4e) | float \| null | The key's tool-error-rate complement — `1 - (sum(tool_errors) / sum(tool_calls))`, call-volume-weighted across every tool-usage-attributed session in the key (never a mean of per-session rates). `null` (never a fabricated constant) for a key with zero tool-usage-attributed sessions. Compute logic implemented 2026-08-10, superseding the permanent-`null` v1 placeholder. **The D-b4 live gate HALTed at ship time for the Codex/GPT family, and this is now enforced mechanically, not just documented**: `config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS` (default `("openai",)`) unconditionally forces `success_rate: null` for any matching `provider`, at both compute time and the persisted-read path — so a Codex/GPT-family key is *always* `null` here today, never merely "untrustworthy." This stays `null` until a Codex `session_tool_usage` backfill/resync follow-up runs and a re-check of the D-b4 query passes, at which point an operator clears the flag; see `routing-feedback-router-merge-handoff.md` §0a. |
| `success_rate_coverage_fraction` (DI-4e) | float \| null | `tool_usage_covered_count / sample_count` for this key — mirrors `cost_coverage_fraction`'s shape. **Compute-layer/response-DTO only** (no persisted column) — always `null` on the persisted `/api/v1/routing/rollup` read path; recoverable only from a live `RoutingRollupQueryService.compute_metrics()` call. |
| `cost_index` (DI-4a) | float \| null | This key's mean cost-per-covered-session divided by its own `task_class`'s mean cost-per-covered-session — **never a global baseline**: an orchestration key's cost is not comparable to a mechanical key's. A key at its class's baseline reads `~1.0`; twice as expensive reads `~2.0`. `null` when the key has zero cost-attributed sessions, or when its entire `task_class` has none to normalize against — never a fabricated `1.0`. |
| `cost_coverage_fraction` (DI-4a) | float \| null | `cost_covered_count / sample_count` for this key — the fraction of sessions that actually carried cost attribution, letting a router discount a `cost_index` computed from a small covered subset. Computed directly via `RoutingRollupQueryService.compute_metrics`, it is always a real float (`0.0` at zero coverage, never `null`). As of schema v47 it IS persisted (`routing_rollup.cost_coverage_fraction`), so the persisted `/api/v1/routing/rollup` read path returns its true value; `null` on that path means no column value yet (a row written before v47, or never re-swept since), kept distinguishable from a genuinely computed `0.0`. |
| `regression_rate` | float \| null | Fraction of sessions in this key that regressed (introduced errors or quality loss) relative to the previous task (0.0–1.0). `null`, permanently — CLOSED per DI-4b: no `test_results`/`test_runs` signal exists anywhere in this schema. Unlike `success_rate`, this is a decided non-goal, not a deferred gap. |
| `confidence` | float | Producer confidence in the metrics (0.0–1.0), derived from sample density and stability. Higher = more reliable. |
| `eligible_for_adjustment` | bool | `true` if `sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`; `false` for `_unclassified`, `orchestration`, `mode_d`. Router may apply its own secondary threshold; this field is advisory. |
| `window_start` | string | ISO 8601 start of the rolling aggregation window. |
| `window_end` | string | ISO 8601 end of the rolling aggregation window. |
| `freshness_ts` | string | ISO 8601 timestamp of when this rollup row was last computed. |

**Top-Level Envelope Fields:**

| Field | Type | Meaning |
|---|---|---|
| `enabled` | bool | `true` if `CCDASH_ROUTING_FEEDBACK_ENABLED=true`; `false` otherwise. |
| `generated_at` | string | ISO 8601 timestamp when the response was generated. `null` if disabled. |
| `mapped_count` | int | Total number of rollup keys where `source_skill_name` mapped successfully to a `task_class`. |
| `unclassified_count` | int | Total number of rollup keys where `source_skill_name` could not be mapped (emitted as `task_class: "_unclassified"`, coverage-only, never addressable). |
| `distinct_unmapped_skill_names` | array | Full list of distinct `source_skill_name` values that failed mapping. Operator visibility for integration debugging. |
| `skill_attributed_key_count` (DI-4e, AC3) | int | Count of `min_sample_size`-clearing keys (evaluated at the raw grain, before mapping) with a non-empty `source_skill_name` — a genuinely skill-aware key. |
| `skill_unattributed_key_count` (DI-4e, AC3) | int | Count of `min_sample_size`-clearing keys with an empty `source_skill_name` — a `(project × model)` key wearing a three-part key's clothes. Per the routing-key-skill-attribution feasibility brief, this cohort is expected to be the **majority** (~55-60%) of the eligible population; count/fraction only, a consumer computes its own discounting — CCDash does not build a per-consumer weighting algorithm here. |
| `keys` | array | Array of per-key rollup rows (self-describing, above). Empty array if disabled. |

**Disabled Envelope** (flag off):

When `CCDASH_ROUTING_FEEDBACK_ENABLED=false`, the response is deterministic across all transports:

```json
{
  "status": "ok",
  "data": {
    "enabled": false,
    "generated_at": null,
    "contract_id": "aos.routing.feedback",
    "contract_version": "1.0.0",
    "taxonomy_id": "aos.routing.task_class",
    "taxonomy_version": "1.0.0",
    "taxonomy_digest": "sha256:d96a0819b0a3a42d14eccc1421d3146b8364253d975d9d54f4f264d4b6adeaca",
    "mapping_id": "ccdash.skill_name_to_aos.routing.task_class",
    "mapping_version": "1.1.0",
    "mapping_digest": "sha256:3935a9805c9197564af645311018e7fc61aabe10a6a82098920e32329066c855",
    "mapped_count": 0,
    "unclassified_count": 0,
    "distinct_unmapped_skill_names": [],
    "skill_attributed_key_count": 0,
    "skill_unattributed_key_count": 0,
    "keys": []
  },
  "meta": { ... }
}
```

**HTTP Status**: Always `200 OK`, even when disabled. Consumers treat `enabled: false` as a valid
"feature exists but is off" state, never as an error condition.

**No pagination in v1**: The entire `keys` array is returned. For projects with many
rolling windows, implement client-side filtering and caching.

### Cache Control

| Flag | Behavior |
|---|---|
| `bypass_cache=false` (default) | Return cached data (server cache ~60s TTL, tunable via `CCDASH_QUERY_CACHE_TTL_SECONDS`). |
| `bypass_cache=true` | Force a fresh recomputation over the session window and skip the cache. Use sparingly. |

---

## Autonomous Worker: Flags and Guards

### Enabling / Disabling the Worker

The autonomous worker is **enabled by default** (`CCDASH_ROUTING_FEEDBACK_ENABLED=true`).
To disable it entirely, set:

```bash
export CCDASH_ROUTING_FEEDBACK_ENABLED=false
```

The entire feature (worker, read endpoint, capability string) goes dormant when this flag is off.
All three transports (REST, MCP, CLI) return the deterministic disabled envelope.

The periodic sweep is scheduled **only** under the `worker` runtime profile (the dedicated
`ccdash_worker` container in the compose stack). It is constructed under `worker`/`worker-watch`
but scheduled under `worker` alone, so the `worker-watch` container never double-runs it; the
`api`, `local`, and `test` profiles never construct it. Each tick processes sessions across
**every registered project** (`RoutingRollupSweepJob._resolve_projects_to_sweep` →
`workspace_registry.list_projects()` per ADR-006), independent of whichever single project the
worker's sync engine is bound to.

### Minimum Sample Size (Eligibility Gate)

One config flag controls the eligibility threshold for routing keys:

| Variable | Default | Notes |
|---|---|---|
| `CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` | 5 | Minimum session count for a key to set `eligible_for_adjustment: true`. |

**Interpretation**: A `(source_skill_name × model)` key with fewer than 5 sessions in the
window will emit `eligible_for_adjustment: false`. The router may apply its own (possibly
different) minimum-sample gate; the CCDash flag is advisory, not prescriptive.

**Example tuning:**

```bash
# More permissive: allow adjustment with just 1 observation
export CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE=1

# More conservative: require 20 observations
export CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE=20
```

### Rolling Window (Provider-Designed, Not Locked)

One config flag tunes the rolling aggregation window:

| Variable | Default | Notes |
|---|---|---|
| `CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS` | 30 | Rolling window length (in days) for aggregating sessions. |

**Interpretation**: Sessions are aggregated over the most recent N days. Older sessions are
excluded. Window_start and window_end are emitted on every key so consumers can normalize
across instances with different window sizes.

**Example tuning:**

```bash
# Shorter window: react faster to recent changes
export CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS=7

# Longer window: smooth out noise
export CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS=60
```

### Protected-Class and Unclassified Row Visibility

One config flag gates the emission of rows that are never addressable as routing keys:

| Variable | Default | Notes |
|---|---|---|
| `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS` | true | Include `_unclassified`, `orchestration`, `mode_d` rows in the response. |

**Interpretation**: When `true` (default), rows for protected task classes and unmapped skills
are included in `keys[]` as coverage-only (with `eligible_for_adjustment: false` hardcoded).
When `false`, these rows are omitted but the counters (`mapped_count`, `unclassified_count`)
still reflect the full accounting.

**Example tuning:**

```bash
# Exclude protected rows from response (cleaner API, less data)
export CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS=false

# Include them (operator debugging, full transparency)
export CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS=true
```

---

### `success_rate` Stale-Provider HALT Gate (DI-4e fix cycle 2)

One config flag withholds `success_rate` for providers whose `session_tool_usage` window is
confirmed stale, per the D-b4 live-verification gate
(`docs/project_plans/feature_contracts/enhancements/di-4e-routing-success-rate.md` AC2):

| Variable | Default | Notes |
|---|---|---|
| `CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS` | `openai` | Comma-separated, case-insensitive list of `provider` values (`derive_model_identity()["modelProvider"]`) whose `success_rate`/`success_rate_coverage_fraction` are unconditionally forced `null`/`0.0`. |

**Interpretation**: A key whose `provider` matches this list has `success_rate` withheld
regardless of how much genuine tool-usage attribution it has — enforced both at compute time
(so no future worker sweep persists a stale-family value) and at the persisted-read path (so an
already-persisted row is never served with one either, across REST/MCP/CLI). This is the
mechanism, not merely the documentation, behind the D-b4 HALT recorded 2026-08-10: the
gpt/codex-family's `session_tool_usage` window is still measurably dominated by stale
pre-`b51de27` rows (21.4% informative-key fraction / 0.04% error rate, independently re-confirmed
against the live node Postgres in fix cycle 2, vs. the fixed-parser 89.2% / 1.48% baseline). See
`routing-feedback-router-merge-handoff.md` §0a for the full record.

**Do not clear this flag as a workaround.** It is lifted only once the Codex
`session_tool_usage` backfill/resync follow-up (tracked separately — see the feature contract's
Follow-Up Recommendations) has run AND the D-b4 query has been re-run against the live window and
shown clean.

```bash
# Default posture -- withhold success_rate for the gpt/codex family (do not change without
# re-running the D-b4 query first).
export CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS=openai

# Post-backfill, once D-b4 has been re-run and shown clean -- lift the gate.
export CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS=
```

---

## Determinism and No-LLM Invariant

**Invariant #1 — Deterministic Aggregation**: Two consecutive sweeps over an unchanged
session window produce field-identical `routing_rollup` rows. No randomization, no dynamic
thresholds, no external calls. Aggregation is pure SQL + threshold arithmetic.

**Invariant #2 — No LLM on Compute Path**: The rollup computation makes zero LLM/model calls.
The worker imports nothing from `backend.adapters.agents` or model-client SDKs. This is
enforced by code review and CI-gated import audit (`test_routing_rollup_no_llm_imports.py`).

**Invariant #3 — Emit-Only, No Routing Actuation**: CCDash never routes, never dispatches,
never calls the delegation-router or any external system. The router always PULLs this surface;
CCDash never PUSHes. Evidence emission is unidirectional.

**Invariant #4 — Reversible by Flag Flip**: Disabling `CCDASH_ROUTING_FEEDBACK_ENABLED` stops
all new writes and causes the very next call on every transport to return the disabled envelope.
No residual state, no migration required to re-enable.

---

## Autonomous Worker Behavior

### When the Worker Runs

The worker is a scheduled background job on the `worker`-profile container that runs on a fixed
interval:

- **On schedule**: Every `CCDASH_ROUTING_FEEDBACK_SWEEP_INTERVAL_SECONDS` seconds (default `1800` =
  30 minutes; floored at 60s). The first tick runs shortly after the worker container starts.
- **Incremental + multi-project**: Each tick processes new/changed sessions since the last
  per-project watermark, across every registered project.

### What the Worker Emits

The worker emits **read-only observability logs** to stderr and structured logs:

```
[routing-rollup-worker] sweep event: {
  "timestamp": "2026-07-31T02:00:00Z",
  "project_id": "my-project",
  "rows_computed": 42,
  "mapped_keys": 38,
  "unclassified_keys": 4,
  "window_days": 30,
  "elapsed_seconds": 1.23
}
```

**No writeback**: The worker does NOT call any router APIs, does NOT modify agent state,
and does NOT submit jobs to op/MeatySkills. It logs only.

### Integration Gating

To integrate the routing feedback into the delegation-router, the router must:

1. Call `GET /api/v1/capabilities` and confirm `routing:feedback` is present.
2. Poll `GET /api/v1/routing/rollup?project_id=...` periodically or on-demand.
3. **Independently re-validate** each key's `source_skill_name → task_class` mapping via
   `validateFeedbackJoin()` against its own copy of the taxonomy (defense-in-depth).
4. Apply its own empirical merge math (bounded-adjustment cap, effective-score floor,
   decay blend, `RoutingRecord` provenance) — CCDash does not prescribe this logic.
5. Update its scorecard or decision engine based on merged evidence.

CCDash has no visibility into steps 4–5; the loop closes only when the router enables
`live_consumption` (currently disabled). Either way, CCDash's role ends at "emit correct evidence."

---

## Cross-Repo Contract Boundaries

### What CCDash Guarantees (Verifiable)

- **Mapping fidelity**: Every `task_class` is derived only through the pinned `aos.routing.feedback`
  v1.1.0 mapping; never a raw `skill_name` string. Digest parity is CI-enforced on every build.
- **Envelope completeness**: All 11 pinned envelope fields appear on every enabled response.
  Version/digest fields are present even when disabled.
- **No `_unclassified` in routing keys**: Unmapped skill names never appear as addressable
  `task_class` values; they are emitted with `task_class: "_unclassified"` and
  `eligible_for_adjustment: false` hardcoded.
- **Reversibility**: Disabling the flag stops all writes and causes deterministic disabled responses.

### What the Router Owns (Asserted Only)

Per the design-spec stub at `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md`:

- **Empirical merge algorithm** (bounded-adjustment cap, effective-score floor, decay blend,
  `RoutingRecord` provenance, `task_class`-level consolidation across multiple `source_skill_name`
  values sharing a class).
- **Model/provider cross-repo namespacing** (CCDash emits `model` and `provider` verbatim/derived;
  no canonical format is negotiated in this feature).
- **Live consumption enablement and rollback** (currently `live_consumption_disabled`).
- **Routing decision adjustment** (never CCDash's concern; CCDash never routes).

### Documented Deferred Items

Three design specs capture the cross-repo seams and open questions:

1. **Router Merge Handoff** (`routing-feedback-router-merge-handoff.md`): Names the empirical
   merge algorithm as a router-owned seam; specifies no implementation, only boundaries.
2. **Model/Provider Namespacing** (`routing-feedback-model-provider-namespacing.md`): Documents
   that `model` and `provider` are emitted verbatim/derived, not canonicalized; a future cross-repo
   negotiation point.
3. **Window/Decay Defaults** (`routing-feedback-window-decay-defaults.md`): Names the rolling-window
   and minimum-sample defaults as spike-anchored candidates, subject to empirical validation once
   the router enables live consumption.

---

## Hard Invariants (Non-Negotiable)

**Invariant #1 — No LLM on Compute Path**: The rollup computation makes zero LLM/model calls.
The worker and read endpoint compute deterministically from cached session data. This is enforced
by code review and import audit.

**Invariant #2 — Producer-Only, Never Actuating**: CCDash never routes, never pushes to external
systems, and never initiates a routing change. The router always PULLs; CCDash only emits evidence.

**Invariant #3 — Redaction-Passed Data Only**: All session data fed into the rollup is scrubbed
by the existing redaction layer before the routing feedback logic sees it.

**Invariant #4 — Contract Compliance**: Every response carries the full 11-field pinned envelope,
version fields, digest pins, and the CCDash-designed metric payload. Silent payload drift or
missing fields are contract violations.

---

## Troubleshooting

### Worker Not Running

**Symptom**: `CCDASH_ROUTING_FEEDBACK_ENABLED=true` but no sweep logs.

**Checklist**:
- Confirm the process is the `worker`-profile container (the sweep does NOT schedule under
  `api`, `local`, `test`, or even `worker-watch`).
- Check startup logs for `Started periodic routing-rollup sweep job (profile=worker interval=…s)`.
- Verify `CCDASH_ROUTING_FEEDBACK_ENABLED` is not set to a falsy value (default true).
- Confirm at least one session exists in some registered project (`GET /api/v1/sessions`).

### No Rollup in Endpoint Response

**Symptom**: `GET /api/v1/routing/rollup?project_id=...` returns `keys: []` even though
sessions exist.

**Checklist**:
- Confirm the project_id matches an active project (`GET /api/health/detail`).
- Verify `CCDASH_ROUTING_FEEDBACK_ENABLED=true` (check env vars or config logs).
- Check if sessions have `skill_name` and `model` fields populated (sparse data = sparse rollup).
- Run a manual backfill sweep to populate the `routing_rollup` table:
  ```bash
  backend/.venv/bin/python backend/scripts/routing_rollup_backfill.py --project {project_id}
  ```
- After backfill, retry the endpoint with `bypass_cache=true`.

### Mapping Digest Mismatch at CI

**Symptom**: CI test `test_routing_feedback_contract_parity` fails with digest mismatch.

**Checklist**:
- The vendored mapping file at
  `backend/application/services/agent_queries/routing_task_map_v1.json` may be stale.
- Update it by re-vendoring from the canonical source:
  `agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json`
- Update the digest constants in `backend/application/services/agent_queries/routing_feedback_contract.py`:
  - `MAPPING_DIGEST` must match the new file's SHA-256
  - `MAPPING_VERSION` may increment if the upstream version changed
- Re-run CI; test should pass.

### High Unclassified Count

**Symptom**: Many sessions are emitted with `task_class: "_unclassified"`, inflating
`unclassified_count`.

**Checklist**:
- This is expected if `skill_name` values do not match the pinned v1 mapping.
- Check the response's `distinct_unmapped_skill_names` array for which skills are not recognized.
- If a legitimate skill is missing from the mapping, report it to the router owner
  (`MeatySkills/meaty-agentic-ops`) for inclusion in the next mapping version.
- Unmapped skills are coverage-only and never addressable as routing keys, so they do not affect
  correctness—only visibility.

### Model or Provider Empty

**Symptom**: Some rollup keys have `model: null` or `provider: null`.

**Checklist**:
- Check if the source sessions were captured with `model` populated. Session-capture conventions:
  `backend/scripts/hooks/ccdash_capture_session_start.py`, launch-time env vars.
- `provider` is derived from `model`; if `model` is missing, `provider` is also null or derived
  from a best-effort fallback. This is a session-population issue, not a rollup bug.
- See `docs/guides/launch-time-capture-convention.md` for session capture setup.

### Eligible-for-Adjustment Always False

**Symptom**: All rollup keys have `eligible_for_adjustment: false` despite adequate sample counts.

**Checklist**:
- Confirm `CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` is set to a reasonable threshold (default `5`).
- Keys with `task_class: "_unclassified"`, `"orchestration"`, or `"mode_d"` always have
  `eligible_for_adjustment: false` hardcoded, regardless of sample count (coverage-only).
- Check that keys have `sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`.
- If sample counts are high but the flag is still false, check logs for warnings about protected classes.

---

## Backfill Script: Populating routing_rollup

To manually populate (or repopulate) the persisted `routing_rollup` table from existing sessions:

```bash
backend/.venv/bin/python backend/scripts/routing_rollup_backfill.py \
  --project {project_id} \
  [--since {iso_date}] \
  [--force]
```

**Options:**

| Flag | Meaning |
|---|---|
| `--project {id}` | (required) The project ID to backfill. |
| `--since {iso_date}` | (optional) Only process sessions modified after this date. |
| `--force` | (optional) Recompute ALL rollup rows, overwriting existing rows. |

**Example:**

```bash
# Backfill project 'my-project'
backend/.venv/bin/python backend/scripts/routing_rollup_backfill.py --project my-project

# Force a full recomputation
backend/.venv/bin/python backend/scripts/routing_rollup_backfill.py --project my-project --force

# Process only recent sessions
backend/.venv/bin/python backend/scripts/routing_rollup_backfill.py --project my-project --since 2026-07-25T00:00:00Z
```

After backfill, the endpoint will return all computed rollup keys.

---

## OpenAPI Specification

A pre-generated OpenAPI v3.1 specification for the `/api/v1` surface (including the
`routing:feedback` endpoint) lives at:

```
docs/openapi/ccdash-v1.json
```

To regenerate (e.g. after adding a new endpoint):

```bash
backend/.venv/bin/python scripts/regen-openapi-v1.py
```

Commit the updated file alongside your code change.

---

## Quick-Start Checklist for LAN Integration

1. **Deploy CCDash**: Ensure HTTP server is running (`npm run dev:backend` or similar).
2. **Discover capability**: Call `GET /api/v1/capabilities` and confirm `routing:feedback` is present.
3. **Query rollup** (PULL): Call `GET /api/v1/routing/rollup?project_id=<id>` to fetch rollup keys.
4. **Verify producer**: Check that `enabled: true` and `keys` array is not empty. If empty, ensure
   `CCDASH_ROUTING_FEEDBACK_ENABLED=true` and sessions exist with `skill_name` and `model` populated.
5. **Optionally backfill**: Run the backfill script if no keys appear.
6. **Autonomous worker** (on by default): The `worker`-profile container sweeps all registered
   projects on an interval and persists rollup rows; tune window and sample-size flags as needed,
   or set `CCDASH_ROUTING_FEEDBACK_ENABLED=false` to disable entirely.
7. **Validate mapping** (pre-integration): Call the endpoint, extract a sample key, and independently
   re-validate its `source_skill_name → task_class` mapping against the router's own copy of the taxonomy
   to confirm the seam integrity before enabling live consumption.
8. **(Out-of-scope) Router empirical merge**: The router-side logic (bounded-adjustment cap,
   effective-score floor, decay blend) is owned by MeatySkills/`ibm-main`; see the deferred-items
   design specs for seam boundaries.

---

## Reference

- **Consumer Contract**: `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md`
- **Router Merge Handoff** (deferred): `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md`
- **Model/Provider Namespacing** (deferred): `docs/project_plans/design-specs/routing-feedback-model-provider-namespacing.md`
- **Window/Decay Defaults** (deferred): `docs/project_plans/design-specs/routing-feedback-window-decay-defaults.md`
- **Implementation Plan**: `docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md`
- **External API Guide**: `docs/guides/external-api-lan-deployment.md`
- **CLAUDE.md (Key Conventions)**: See the `routing-feedback` bullet for hardcoded pointers.
