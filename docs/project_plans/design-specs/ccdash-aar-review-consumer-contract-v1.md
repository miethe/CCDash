---
title: CCDash AAR Review Consumer Contract v1
doc_type: design-spec
feature_slug: ccdash-automated-aar-review
status: draft
created: 2026-07-22
updated: 2026-07-22
audience: developers
category: cross-repo-integration
tags:
  - ccdash
  - aar-review
  - op-integration
  - consumer-contract
  - pull-transport
related_documents:
  - docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
  - docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md
description: |
  Hand-off contract for op/agentic_meta_dev consumers of CCDash's AAR-review evidence.
  Specifies the PULL transport (REST/MCP/CLI), routing decision inputs, verdict semantics,
  and CCDash-side invariants. Consumers route based on `correlation.confidence` and
  `triage_verdict`; `human_triage_required` verdicts MUST route to human review only.
---

# CCDash AAR Review Consumer Contract v1

## Contract Overview

**Transport**: PULL (consumers query CCDash; CCDash never pushes or dispatches work)

**Canonical Source**: CCDash's REST/MCP/CLI surfaces expose the `aar_review_candidate` event schema verbatim.

**Consumer Responsibility**: op/ARC/SkillMeat own all synthesis, routing logic, swarm/ARC dispatch, recommendation authoring, and HITL gates. CCDash produces evidence only.

**CCDash Responsibility**: deterministic, model-free triage over already-ingested session data. Zero LLM calls. Zero autonomous dispatch or writeback.

---

## 1. Access Pattern (PULL)

### 1.1 REST Endpoint (Project-Wide List)

**The primary consumer PULL surface for listing all reviews in a project:**

```
GET /api/v1/project/aar-review?project_id={project_id}&bypass_cache={bool}
```

**Query Parameters:**
- `project_id` (required): the CCDash project identifier
- `bypass_cache` (optional, default false): skip query cache and fetch fresh data

**Response envelope** (ClientV1Envelope[AARReviewListDTO]):

```typescript
{
  "status": "ok" | "partial" | "error",
  "data": {
    "project_id": string,
    "total": number,
    "reviews": [
      // Each entry is an AARReviewDTO (see §3 for full schema)
      {
        "aar_document_id": string,
        "aar_document_path": string,
        "correlation": {
          "strategy": "explicit_session_ref" | "task_session_ref" | "doc_feature_session_two_hop",
          "confidence": number,
          "session_ids": [string],
          "feature_id": string | null
        },
        "triage_verdict": "surface_only" | "deep_review_recommended" | "human_triage_required",
        "flags": [
          {
            "flag_id": string,
            "triggered": boolean,
            "severity": "low" | "medium" | "high" | null,
            "evidence": [string]
          }
        ],
        "evidence_refs": [string],
        "generated_at": string  // ISO 8601
      }
    ]
  },
  "meta": {...}
}
```

**Note on structure**: No `success`, `error`, `request_id`, or pagination (`items`, `total_count`, `limit`, `offset`) fields. The `reviews` array contains all available reviews for the project. No `limit`/`offset` pagination is supported in v1.

### 1.2 MCP Tool (Single-Document Lookup)

Exposed as `ccdash_aar_review` (transport-neutral, single-document lookup):

```typescript
parameters:
  - document_id: string (required) — the AAR document identifier
  - project_id?: string (optional) — if not provided, inferred from context
```

**Returns**: A single `AARReviewDTO` for the specified document.

**Note**: This is a single-document lookup tool, not a project-wide list. Use the REST endpoint (§1.1) for project-wide filtering and browsing.

### 1.3 CLI Surface (Single-Document Lookup)

```bash
ccdash report aar-review --document <document_id> [--output json|md|text]
```

**Flags:**
- `--document` (required): the AAR document identifier
- `--output` or `--json` or `--md` (optional): output format (default: text)

**Returns**: Triage verdict and flags for the specified document.

**Note**: This is a single-document lookup command, not a project-wide list. The CLI does not support `--project` or `--filter-verdict` flags for listing; use the REST endpoint (§1.1) to poll all reviews in a project and filter client-side by `triage_verdict` if needed.

### 1.4 PROPOSED (Not Yet Implemented): Filtered Project-Wide List

**Future enhancement** (does not ship in P1-P3; marked explicitly to prevent integration against an unshipped surface):

```
GET /api/v1/project/aar-review/list?project_id=<id>&filter_verdict=deep_review_recommended&limit=50&offset=0
```

This surface would support `limit`, `offset`, and `filter_verdict` query parameters for paginated, verdict-filtered browsing. It is NOT available today. Consumers wanting to filter today must fetch all reviews via §1.1 and filter client-side.

### 1.5 Capability Advertisement

All CCDash servers advertise capability discovery on startup:

```
GET /api/v1/capabilities
```

**Response**:

```typescript
{
  "capabilities": [
    "aar-review",
    "sessions:detail",
    "sessions:cross-project",
    ...
  ]
}
```

**Consumer contract**: Consumers MUST NOT hard-fail if the `aar-review` capability string is absent. Absent capability means the server predates this feature; present means the contract documented below is honored. Poll `/api/v1/capabilities` before using aar-review endpoints; treat unknown capability strings as "may not be supported yet."

---

## 2. Routing Decision Inputs

**Only two fields drive consumer routing decisions:**

1. **`correlation.confidence`** (float, 0.0-1.0)
   - Producer confidence that the AAR document describes the correlated session(s).
   - Confidence bands:
     - `< 0.64`: low confidence (explicit two-hop inference; ambiguous pairing)
     - `>= 0.64`: high confidence (explicit session ref, task-session correlation, or validated two-hop)

2. **`triage_verdict`** (enum: `surface_only | deep_review_recommended | human_triage_required`)
   - Deterministic classification; no model judgment applied.
   - Verdict decision table (§3.2 below).

**Everything else in the event is evidence context; routing decisions ignore all other fields.**

---

## 3. `aar_review_candidate` Event Schema (VERBATIM from PRD §7.3)

```yaml
# emitted by CCDash; consumed by op (P3). Inverse of rf.py:309-359's ccdash_event.yaml writeback.
schema_version: 1
event_type: aar_review_candidate
producer: ccdash
emitted_at: datetime             # ISO 8601
aar_document_id: str
aar_document_path: str
feature_ref: str | null
session_refs: [str]              # session_ids from correlation.session_ids
correlation:
  strategy: explicit_session_ref | task_session_ref | doc_feature_session_two_hop
  confidence: float
flags:
  - flag_id: str
    triggered: bool
    severity: low | medium | high | null
triage_verdict: surface_only | deep_review_recommended | human_triage_required
evidence_refs: [str]
guards:                          # P4 fields; null/absent in P1-P3 emissions
  provenance_excluded: bool | null      # true if this AAR/session pair was excluded by self-recursion guard 1
  dedup_key: str | null                 # "{aar_document_id}:{session_id}" per guard 2
```

---

## 4. Verdict Semantics & Routing Guarantees

### 4.1 The Routing Decision Table

| `correlation.confidence` | Any flag `severity: high`? | Verdict | **MUST Route To** |
|---|---|---|---|
| < 0.64 | — | `human_triage_required` | **HUMAN REVIEW ONLY** (never op council, never autonomous dispatch) |
| >= 0.64 | no | `surface_only` | Surface note / skip (low value) |
| >= 0.64 | yes | `deep_review_recommended` | **Eligible for op council routing** (if operator approves) |

### 4.2 `human_triage_required` — THE CRITICAL GUARDRAIL

**MANDATORY RULE — VIOLATION IS A COMPLIANCE FAILURE:**

> Any event with `triage_verdict: human_triage_required` **MUST NEVER** be routed to:
> - `op council` (autonomous ARC dispatch)
> - Any autonomous work queue or scheduler
> - Any SkillMeat/agents/skills mutation
> - Any IntentTree swarm dispatch

**Reason**: Low-confidence correlations (< 0.64) carry ambiguity; the AAR document may not describe the sessions it appears to describe. Automatic action on such ambiguity risks misdirected swarm work. Only a human can resolve the ambiguity.

**Consumer implementations**:
- Emit a structured log or alert flagging the verdict; route to a human review queue or dashboard.
- If the consumer has a gating checkpoint (e.g., `op classify→plan→dispatch`), the presence of `human_triage_required` is a **signal to the human**, not a gate bypass.
- Never consume `human_triage_required` verdicts and dispatch them to the next tier without explicit human acknowledgment.

### 4.3 `surface_only` — Informational

- Flag: low value, no high-severity flags.
- Consumer action: optional note in a report, dashboard surface, or skip entirely. No escalation.

### 4.4 `deep_review_recommended` — Eligible for Escalation

- Flag: one or more high-severity surface flags detected; confidence >= 0.64.
- Consumer action: eligible for op council routing if the operator approves. CCDash takes no action; `op` owns the dispatch decision.

---

## 5. CCDash-Side Invariants (Consumer Guarantees)

The consumer can rely unconditionally on these invariants:

### 5.1 Deterministic Triage, No LLM

- **Guarantee**: Every `triage_verdict` is computed via deterministic threshold/lookup/regex over already-ingested DB rows.
- **Verification**: No model-client import exists anywhere in `backend/application/services/agent_queries/aar_review.py` or its dependency graph.
- **Consequence**: Verdicts are reproducible, auditable, and cost-neutral to CCDash's recall path.

### 5.2 Producer-Only, No Dispatch

- **Guarantee**: CCDash emits events and exposes query surfaces only. It never calls op/ARC/SkillMeat APIs, never schedules swarm work, never mutates SkillMeat catalogs or agent definitions.
- **Verification**: Codebase review confirms no `op_client`, `arc_client`, `swarm`, or `skillmeat_api` imports in CCDash's aar-review code.
- **Consequence**: CCDash is a source of truth (producer), not an orchestrator.

### 5.3 Redaction-Passed Input

- **Guarantee**: Every triage flag reads only from CCDash's `session_detail` endpoint (redaction-passed, not raw JSONL).
- **Verification**: Triage flags depend on `session_correlation.py`, `session_detail.py`, `entity_links` repositories only.
- **Consequence**: Sensitive data (credentials, API keys, personal information) present in raw sessions is already scrubbed before triage runs.

### 5.4 Missing Confidence Defaults to Human Triage

- **Guarantee**: If `correlation.confidence` is null, absent, or fails to resolve (zero sessions correlated), the triage verdict defaults to `human_triage_required`.
- **Verification**: Unit test in aar_review's test suite asserts the decision table for `confidence in {null, 0.0, 0.63, 0.64, 1.0}`.
- **Consequence**: Absence of confidence is a safe, defensible state — never auto-escalates.

### 5.5 Project Scoping via DB Registry

- **Guarantee**: All data returned by aar-review queries is scoped to the authenticated project (ADR-006, DB-authoritative registry).
- **Verification**: AuthContext in every REST/MCP/CLI request; routers enforce project_id scoping at the SQL layer.
- **Consequence**: No cross-project data leakage; multi-tenant safety.

---

## 6. Ownership & Boundaries

### 6.1 CCDash Owns

- Computing the 5 surface flags from session telemetry (deterministic derivation only)
- Resolving AAR documents to session corpora via `entity_links`
- Emitting `aar_review_candidate` events with confidence bands and evidence bundles
- Persisting triage history (P2 rollup table, CCDash-scoped)
- Exposing verdicts via REST/MCP/CLI transports

### 6.2 op/ARC/SkillMeat Own

- Classifying, planning, and dispatching based on verdicts
- Invoking ARC/council-review workflows for `deep_review_recommended` candidates
- Authoring recommendation text and new artifacts (skills, agents, config changes)
- All HITL gates and approvals
- Direct mutation of SkillMeat/agents/skills (never initiated by CCDash)
- Autonomous scheduling decisions (if any)

**Seam**: The `aar_review_candidate` event and its `correlation.confidence` + `triage_verdict` fields.

---

## 7. Resilience & Degradation

### 7.1 Capability Negotiation

Consumers calling `/api/v1/capabilities` before accessing aar-review endpoints must handle:

- **Server predates aar-review**: `"aar-review"` capability absent → aar-review endpoints may not exist.
  - Consumer action: skip aar-review queries; fall back to manual AAR triage or other evidence sources.

- **Server supports aar-review**: `"aar-review"` capability present → contract documented here is guaranteed.
  - Consumer action: proceed with aar-review queries per the routing decision table.

### 7.2 Missing/Null Fields in Verdicts

Event examples:

- `flags[].evidence` is an empty array or absent → flag was not triggered or evidence derivation was skipped.
  - Consumer action: render as "not triggered"; do not fail parsing.

- `correlation.feature_id` is null → correlation strategy is `explicit_session_ref` (no feature context).
  - Consumer action: render session-only context without a feature link; do not assume a feature exists.

- `guards.*` fields are all null or absent → P1-P3 emission (guards not yet enforced).
  - Consumer action: ignore guard fields; they are informational in P4+.

### 7.3 Transient Query Failures

Endpoints may return:

```json
{
  "success": false,
  "error": "project not found",
  "data": null
}
```

Consumer action: log the error; retry with exponential backoff or escalate to operator review if persistent.

---

## 8. Observability & Auditing

### 8.1 Structured Logs on Event Emission

Every `aar_review_candidate` event emission logs (structured JSON):

```json
{
  "timestamp": "ISO8601",
  "event_type": "aar_review_candidate_emitted",
  "aar_document_id": "...",
  "triage_verdict": "deep_review_recommended",
  "correlation_confidence": 0.96,
  "trace_id": "...",
  "span_id": "..."
}
```

**Content guarantee**: Never includes raw session JSONL, transcript text, or redacted fields. Only metadata and the triage verdict.

### 8.2 Consumer Observability

Consumers SHOULD log every decision point:

```json
{
  "timestamp": "ISO8601",
  "event": "aar_review_verdict_routed",
  "aar_document_id": "...",
  "verdict_received": "deep_review_recommended",
  "consumer_decision": "escalated_to_op_council",
  "trace_context": "inherited from CCDash event"
}
```

This enables end-to-end tracing from AAR emission through consumer routing to outcome.

---

## 9. P1-P4 Stability

| Phase | Event Available | Guarantees |
|-------|---|---|
| **P1** | Yes (REST/MCP/CLI read-only) | `correlation.confidence` + `triage_verdict` routing inputs stable; `guards.*` fields null/absent. |
| **P2** | Yes (+ FE review surface) | Same routing inputs; rollup table persists history; no guard enforcement yet. |
| **P3** | Yes (cross-repo consumer spec locked) | Same routing inputs; op-side routing implementation active; no writeback yet. |
| **P4** | Yes (+ autonomous worker) | Same routing inputs; guards enforced; writeback only via `op approve`. |

**Consumer contract stability**: Routing decision inputs (`correlation.confidence`, `triage_verdict`) and the verdict decision table (§4.1) are **fixed** across all phases. New fields (e.g., `guards.*`) are added in later phases as non-breaking extensions (null/absent in prior phases).

---

## 10. Examples

### 10.1 Example: High-confidence Deep-Review Candidate

```json
{
  "schema_version": 1,
  "event_type": "aar_review_candidate",
  "producer": "ccdash",
  "emitted_at": "2026-07-22T14:30:00Z",
  "aar_document_id": "aar_abc123",
  "aar_document_path": ".claude/worknotes/my-feature/phase-2-aar.md",
  "feature_ref": "FEAT-456",
  "session_refs": ["sess_a", "sess_b"],
  "correlation": {
    "strategy": "task_session_ref",
    "confidence": 0.96,
    "session_ids": ["sess_a", "sess_b"],
    "feature_id": "FEAT-456"
  },
  "flags": [
    {
      "flag_id": "context_ballooning",
      "triggered": true,
      "severity": "high",
      "evidence": ["context utilization 92% in sess_a", "context utilization 88% in sess_b"]
    },
    {
      "flag_id": "missing_artifacts",
      "triggered": false,
      "severity": null,
      "evidence": []
    }
  ],
  "triage_verdict": "deep_review_recommended",
  "triage_reasons": [
    "context_ballooning severity:high detected in 2 sessions",
    "high confidence (0.96) task-session correlation"
  ],
  "evidence_refs": [
    "session:sess_a/context_window",
    "session:sess_b/context_window"
  ],
  "guards": null
}
```

**Consumer routing**:
- `correlation.confidence` = 0.96 (>= 0.64) ✓
- `triage_verdict` = `deep_review_recommended` ✓
- **Decision**: Eligible for op council routing. Operator approves → ARC invoked.

### 10.2 Example: Low-confidence, Routes to Human

```json
{
  "schema_version": 1,
  "event_type": "aar_review_candidate",
  "producer": "ccdash",
  "emitted_at": "2026-07-22T14:31:00Z",
  "aar_document_id": "aar_def456",
  "aar_document_path": ".claude/worknotes/other-feature/phase-1-aar.md",
  "feature_ref": null,
  "session_refs": ["sess_c"],
  "correlation": {
    "strategy": "doc_feature_session_two_hop",
    "confidence": 0.64,
    "session_ids": ["sess_c"],
    "feature_id": null
  },
  "flags": [
    {
      "flag_id": "generic_agent_vs_specialist",
      "triggered": true,
      "severity": "high",
      "evidence": ["used general-purpose agent where domain specialist available"]
    }
  ],
  "triage_verdict": "human_triage_required",
  "triage_reasons": [
    "two-hop correlation strategy carries inherent ambiguity; human confirmation required before escalation"
  ],
  "evidence_refs": [
    "session:sess_c/agent_selection"
  ],
  "guards": null
}
```

**Consumer routing**:
- `correlation.confidence` = 0.64 (>= 0.64, but at boundary)
- **But**: correlation strategy is `doc_feature_session_two_hop` (weakest; ambiguous pairing)
- `triage_verdict` = `human_triage_required`
- **Decision**: NEVER auto-escalate. Route to human review queue. Wait for operator judgment.

---

## 11. References & Related Docs

- **PRD** (north-star): `docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md` (sections 7.2, 7.3, 4.1 decision table, hard invariants)
- **ADR (accepted)**: `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md` (seam contract: producer/consumer boundary)
- **Precedent (producer/consumer pattern)**: `ccdash persona extract` contract + op-side consumer in agentic_meta_dev
- **Precedent (PULL pattern)**: RF→CCDash inverse; `rf.py:309-359` ccdash_event.yaml writeback

---

## 12. Change Log

- **2026-07-22**: Initial draft. Contract locked at P3 scope (PULL transport, routing inputs, verdict semantics, invariants).

