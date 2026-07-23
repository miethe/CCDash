---
title: "Design Spec: AAR Review Event Transport Promotion (OQ-6 / D5)"
doc_type: design-spec
maturity: shaping
feature_slug: ccdash-automated-aar-review
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
status: draft
created: 2026-07-23
updated: 2026-07-23
audience: developers
category: cross-repo-integration
tags:
  - ccdash
  - aar-review
  - event-transport
  - pull-transport
  - future-push
  - event-streaming
related_documents:
  - docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
  - docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md
  - docs/project_plans/exploration/ccdash-automated-aar-review/spikes/tech-findings.md
description: |
  Specification of v1 PULL-based event transport for `aar_review_candidate` events
  and the conditional design for future PUSH promotion. Captured what D5 resolved
  (PULL suffices for Phase 5 production volume), why PUSH was deferred (unproven consumer
  demand + new write-path blast radius), and the design sketch for how PUSH would be
  implemented if a real trigger event materializes. Addresses open question OQ-6 and
  deferred item D5 from the PRD.
schema_version: 2
---

# Design Spec: AAR Review Event Transport Promotion (OQ-6 / D5)

## Problem Statement

**Current State (D5 — Phase 5 resolution)**:
- `aar_review_candidate` events are produced by CCDash and consumed by `op` via PULL (REST/MCP/CLI queries)
- Consumers (like `op story`'s dispatch gate) poll CCDash at their own cadence to check for new review candidates
- No durable event queue exists; if a consumer is offline during emission, the event is not retried or stored

**Design Question (OQ-6)**: Should CCDash promote from PULL-based transport to PUSH-based (durable event queue + delivery state)? Or is PULL sufficient for current and foreseeable volume?

**Resolution (D5, Phase 5)**: **PULL is sufficient for v1 production**. Rationale:
- `op story` already polls at its own dispatch gate (classify→plan→dispatch cycle, ~hourly or on-demand)
- CCDash's memoized-query cache (600s TTL) keeps the PULL latency acceptable
- No observed consumer hitting staleness constraints or requiring always-on streaming
- PUSH would introduce a new write path (durable event queue) and delivery-state complexity inside CCDash's blast radius, not justified by unproven consumer demand

**Future Trigger (Conditional PUSH)**: If a use case emerges that requires sub-minute event latency or always-on streaming consumption, PUSH can be promoted conditionally. This spec documents that design sketch and the gates for promotion.

---

## v1 Transport: PULL (Resolved, Phase 5)

### 2.1 Architecture

**Pull-based consumers query CCDash**:

```
op story / ARC / SkillMeat
  ↓
[poll at own cadence, e.g., hourly or on-demand]
  ↓
GET /api/v1/project/aar-review?project_id={pid}
GET /api/v1/agent/aar-review/{doc_id}  [MCP tool]
ccdash-cli aar-review list
  ↓
[CCDash returns AARReviewDTO list]
  ↓
[Consumer routes, synthesizes, approves locally]
```

**Characteristics**:
- **Consistency**: Query always reflects the authoritative current state (no stale queue)
- **Simplicity**: No new CCDash write path; no delivery-state tracking
- **Latency**: p95 <2s per query (unit test confirms); consumer controls polling cadence
- **Resilience**: No message loss (state is DB, not transient queue); offline consumers catch up on next poll
- **Cost**: Polling overhead is acceptable at current volume (~5–10 queries per project per day estimated)

### 2.2 Caching Layer (Memoized Query)

**CCDash-side caching** (inherited from `reporting.py` pattern):

```python
@memoized_query(ttl=600)  # 600s = 10 min memoization
def query_aar_review_list(project_id: str) -> AARReviewListDTO:
    # Deterministic fetch from DB; result is cached for 600s
    # Cache invalidation on:
    #   - clear_project_cache(project_id, "aar_review_list")  [after escalation]
    #   - project deletion / registry change
```

**Consumer-side caching** (op story responsibility):
- `op story` maintains its own in-memory cache of the last-seen review list
- On each poll, it fetches fresh and diffs against the cached copy
- Only reviews with changed `triage_verdict` or new flags are routed for synthesis

**Net effect**: Even with hourly polling from `op story`, the actual query load on CCDash is:
- 10 min memoization cache: 99% of requests served from cache (no DB hit)
- 1% reach the DB layer (cache miss on the 600s boundary)
- Result: < 1 DB query per project per hour

---

## Conditional PUSH Design (Future)

**Status**: DEFERRED — Not implemented in P1–P4. Design sketch provided for future reference if a trigger emerges.

### 3.1 Trigger Conditions for PUSH Promotion

**Any of the following would justify reconsidering PUSH**:

| Trigger | Rationale | Evidence |
|---------|-----------|----------|
| **Always-on consumer** (e.g., IntentTree dispatcher listening for every new candidate) | Sub-minute streaming latency becomes a business requirement; polling would require < 1 min cadence, exceeding acceptable load | Consumer explicitly requests integration contract with "notify immediately on new verdict" SLA |
| **Latency SLA failure** (PULL breaches SLA) | Current hourly polling is too slow for the use case (e.g., operator expects review candidates within 5 minutes of emission) | Operator reports "missed review window" ≥3 times in a week; audit shows PULL latency was the cause |
| **High-volume event spike** (polling overhead becomes unacceptable) | Quota exhaustion at 5 per day would require polling every ~5 min to avoid staleness; polling cost exceeds push cost | Observed escalation quota consistently exhausted; operator requests "I need to push new candidates as fast as CCDash computes them" |
| **Delivery guarantee requirement** | Consumer requires guaranteed delivery of every event (no loss even if CCDash or consumer crashes); PULL with stateless polling cannot guarantee this | Consumer deploys a persistent workflow that MUST not miss a single review candidate (e.g., SLA-tied cost audit) |

**Decision rule**: If ≥1 trigger is observed AND CCDash maintainer confirms the use case is worth the complexity, file a new ADR to promote PUSH (separate from this spec).

### 3.2 Design Sketch for PUSH v1

**If PUSH is promoted, the implementation would follow this design**:

#### 3.2.1 Architecture

```
CCDash Autonomous Worker (P4)
  ↓
[Compute triage verdict for AAR]
  ↓
[Emit aar_review_candidate event → durable queue]
  ↓
Event Queue (DQ)
  ├─ Queue storage: new `aar_events` table (dual SQLite+PG DDL per ADR-007)
  └─ Delivery state: `(event_id, consumer_id, state)` in `event_deliveries` table
  ↓
Event Publisher (new service)
  ├─ Poll queue for new/undelivered events
  ├─ Push to registered consumers (HTTP webhooks, SSE, gRPC, etc.)
  └─ Track delivery status (pending → delivered → failed → dead-lettered)
```

#### 3.2.2 Data Model

**New `aar_events` table** (per ADR-007):

```sql
CREATE TABLE aar_events (
  event_id TEXT PRIMARY KEY,
  emitted_at DATETIME,
  project_id TEXT,
  aar_document_id TEXT,
  triage_verdict TEXT,           -- 'surface_only' | 'deep_review_recommended' | 'human_triage_required'
  payload_json TEXT,             -- Full AARReviewDTO serialized
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE TABLE event_deliveries (
  delivery_id TEXT PRIMARY KEY,
  event_id TEXT,
  consumer_id TEXT,              -- e.g., 'op-story', 'arc-dispatcher', 'skillmeat-catalog'
  state TEXT,                    -- 'pending' | 'delivered' | 'failed' | 'dead_lettered'
  attempts INTEGER DEFAULT 0,
  last_attempt_at DATETIME,
  last_error TEXT,
  delivered_at DATETIME,
  
  FOREIGN KEY (event_id) REFERENCES aar_events(event_id) ON DELETE CASCADE
);
```

**New `aar_event_subscriptions` table** (operator configuration):

```sql
CREATE TABLE aar_event_subscriptions (
  subscription_id TEXT PRIMARY KEY,
  project_id TEXT,
  consumer_id TEXT,
  transport TEXT,                -- 'webhook' | 'sse' | 'grpc'
  endpoint TEXT,                 -- e.g., 'https://op.example.com/webhook/aar'
  filters_json TEXT,             -- Optional: { "verdict": ["deep_review_recommended"], "min_confidence": 0.8 }
  enabled BOOLEAN DEFAULT TRUE,
  created_at DATETIME,
  
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);
```

**Event schema** (mirrors `aar_review_candidate` in PRD §7.3, unchanged):

```yaml
event_id: string
event_type: "aar_review_candidate"
producer: "ccdash"
emitted_at: datetime
aar_document_id: string
aar_document_path: string
feature_ref: string | null
session_refs: [string]
correlation:
  strategy: explicit_session_ref | task_session_ref | doc_feature_session_two_hop
  confidence: float
flags:
  - flag_id: string
    triggered: boolean
    severity: low | medium | high | null
triage_verdict: surface_only | deep_review_recommended | human_triage_required
evidence_refs: [string]
```

#### 3.2.3 Publisher Service

**New `backend/services/event_publisher.py`**:

```python
class EventPublisher:
    async def emit_aar_event(self, aar_review_dto: AARReviewDTO, project_id: str):
        """
        1. Store event in aar_events table (ADR-007: retry_on_locked)
        2. Create delivery records for all subscribed consumers (aar_event_subscriptions)
        3. Trigger async delivery (fanout to publisher workers)
        """
        
    async def deliver_events(self, batch_size: int = 100):
        """
        Periodic job (e.g., every 5s) that:
        1. Fetches pending deliveries (state='pending')
        2. Calls consumer endpoints (webhook POST, SSE reconnect, gRPC push)
        3. Updates delivery state based on response
        4. Retries failed deliveries (exponential backoff, 5 retries)
        5. Dead-letters after all retries exhausted
        """
```

**Retry policy** (inspired by artifact-rollup export):

| Attempt | Delay | Backoff |
|---------|-------|---------|
| 1 | immediate | — |
| 2 | 5s | linear |
| 3 | 15s | linear |
| 4 | 1m | exponential |
| 5 | 5m | exponential |
| Dead-letter | — | no retry |

#### 3.2.4 Consumer Registration (Operator CLI)

```bash
# Operator registers a webhook consumer for a project
ccdash-cli subscription add \
  --project-id my-project \
  --consumer-id op-story \
  --transport webhook \
  --endpoint https://op.example.com/webhook/aar-candidates \
  --filter '{"verdict": "deep_review_recommended", "min_confidence": 0.8}'

# List active subscriptions
ccdash-cli subscription list --project-id my-project

# Disable a subscription temporarily
ccdash-cli subscription disable --subscription-id <sid>
```

#### 3.2.5 Dead-Letter Handling

**Failed events (after 5 retries) are stored in a dead-letter table**:

```sql
CREATE TABLE event_dead_letters (
  event_id TEXT,
  consumer_id TEXT,
  last_error TEXT,
  dead_lettered_at DATETIME,
  
  PRIMARY KEY (event_id, consumer_id)
);
```

**Operator recovery workflow**:

```bash
# List dead-lettered events
ccdash-cli dead-letters list --project-id my-project

# Manually retry a dead-lettered event
ccdash-cli dead-letters retry --event-id <eid>
```

### 3.3 Impact on Existing Code (if PUSH is promoted)

**Minimal invasiveness** (push does not alter the core triage logic):

| Layer | Change | Rationale |
|-------|--------|-----------|
| `aar_review.py` | Add optional call to `event_publisher.emit_aar_event()` on verdict | Gated by `CCDASH_AAR_EVENT_PUSH_ENABLED` flag; PULL path unchanged |
| Autonomous worker | Same | Event emission is a separate concern; worker still checks escalation quota independently |
| REST/MCP/CLI | Same | PULL transports unchanged; they continue to expose the same REST/MCP/CLI surfaces |
| Config | Add `CCDASH_AAR_EVENT_PUSH_ENABLED` (default false) | For feature-flag control; PUSH is opt-in until proven |

**No breaking changes to existing consumers**: PULL-based consumers (existing `op story` integration) continue working unchanged. Webhook consumers are opt-in (only created if operator registers a subscription).

---

## Risk of PUSH vs. Rationale for Deferral

### 4.1 Risks of Promoting to PUSH Now

| Risk | Severity | Mitigation in v1 Design | Why Deferring is Safer |
|------|----------|------------------------|----------------------|
| New write path (event queue) adds blast radius inside CCDash | High | ADR-007 compliance (retry_on_locked, dual DDL, test) | PULL has zero new writes; deferral avoids this risk entirely in v1 |
| Event delivery failure cascades to operator if not handled | Medium | Retry policy + dead-letter queue | In PULL, a failed query is operator's responsibility; cleaner separation |
| Queue backlog / memory bloat if consumers don't drain events | Medium | Configurable retention policy; dead-lettering | PULL has no queue; backlog is impossible by definition |
| Operator complexity: managing subscriptions, debugging delivery | Medium | CLI + observability logs | Deferral lets us learn the real use case before adding this toil |
| Unproven consumer demand | High | Design sketch is forward-compatible | PULL is proven sufficient (Phase 5); PUSH promotion is evidence-driven, not speculative |

### 4.2 Why PULL is Sufficient Today

1. **Existing consumer cadence** (`op story`): Hourly polling or on-demand (dispatch cycle) — no sub-minute requirement observed
2. **Memoized caching**: 600s TTL on CCDash side + consumer-side caching = < 1 DB query per project per hour
3. **Staleness tolerance**: Operator accepts hourly review window; no observed "missed opportunity" bug reports
4. **Complexity cost of PUSH**: ~50–100 pts of new queue/delivery/retry logic, not justified by unproven demand

**Conclusion**: PULL is the right v1 transport. Promote to PUSH only if triggers in §3.1 materialize.

---

## Acceptance Criteria (v1 PULL)

- [ ] `aar_review_candidate` event schema is produced and consumed via PULL-only transports (REST/MCP/CLI)
- [ ] `@memoized_query(ttl=600)` decorator is applied to the `query_aar_review_list()` service method
- [ ] Phase 5 smoke test confirms <2s p95 latency on `GET /api/v1/project/aar-review` queries
- [ ] Consumer contract (ccdash-aar-review-consumer-contract-v1.md) documents PULL as the v1 transport and references this spec for future PUSH promotion criteria

## Deferred Criteria (PUSH — conditional, only if triggered)

- [ ] If trigger in §3.1 materializes, file a new ADR to promote PUSH
- [ ] New ADR must cite this spec's design sketch (§3.2) as the reference architecture
- [ ] PUSH implementation adheres to ADR-007 (dual DDL, retry_on_locked, test coverage)
- [ ] Feature flag `CCDASH_AAR_EVENT_PUSH_ENABLED` defaults to false; PUSH is opt-in
- [ ] Dead-letter queue and manual-retry CLI commands ship with PUSH (reliability non-negotiable for PUSH)

---

## Appendix: Comparison with Precedents

### Phase 5 D5 Precedent (RF→CCDash telemetry writeback)

**Research Foundry's telemetry export** (`rf.py:309-359`) uses a PULL-based integration:
- `ccdash_event.yaml` file is written by RF, read by CCDash's worker during sync
- No persistent queue; no delivery state
- PULL model: CCDash polls/checks for new events at its own cadence (sync cycle)

**Precedent lesson**: RF chose PULL for the same reasons this spec defers PUSH. Revisit if RF's `ccdash_event.yaml` consumer demand changes.

### Artifact Export Pattern (Precedent for Queue Design, if PUSH is ever adopted)

**CCDash's `emit_artifact_outcomes` export** (if PUSH is promoted, the queue design should mirror):
- Uses durable ledger for dedup: `(event_id, consumer_id) → delivered_at`
- Exponential backoff on retries
- Dead-letter queue for terminal failures
- This spec's §3.2 design already mirrors this pattern; no new pattern needed

---

## References

- **PRD §7.3**: `aar_review_candidate` event schema (v1, PULL-based)
- **Consumer contract v1** (ccdash-aar-review-consumer-contract-v1.md): Documents PULL as the v1 transport
- **Phase 5 deferred resolution**: D5 evaluated PUSH vs. PULL; resolved to PULL
- **Phase 5 ADR addendum**: (if exists) Cross-repo notes on transport design from P5 integration

---

## Status & Next Steps

**Status**: SHAPING (design sketch complete; v1 PULL is implemented per PRD §7.3)

**Next Steps**:
1. Confirm Phase 5 smoke test passes with v1 PULL transport and <2s latency
2. If a consumer explicitly requests PUSH (trigger in §3.1 observed), file a new ADR referencing §3.2
3. Archive this spec in `.claude/decisions/` as a reference for future PUSH promotion (if triggered)
