---
schema_version: 2
doc_type: design_spec
title: "Transcript Fetch On-Demand v1 - Design Spec"
status: draft
created: 2026-04-27
updated: 2026-04-27
feature_slug: transcript-fetch-on-demand
feature_version: "v1"
maturity: shaping
prd_ref: /docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md
plan_ref: /docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md
related_documents:
  - docs/project_plans/design-specs/runtime-performance-hardening-v1.md
  - docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md
  - docs/guides/query-cache-tuning-guide.md
references:
  user_docs: []
  context: []
  specs: []
  related_prds: []
tags: [performance, memory, ui, transcript, frontend]
owner: nick
priority: medium
risk_level: low
category: feature
---

# Transcript Fetch On-Demand v1 - Design Spec

**Status**: Shaping (direction known, needs detailed design)  
**Source**: Open Question OQ-1 from `runtime-performance-hardening-v1` PRD  
**Target Maturity**: Ready for PRD once UX/technical trade-offs are resolved

---

## Problem Statement

When the frontend session log list is capped at 5000 rows (per `runtime-performance-hardening-v1` FR-1), older transcript rows beyond the cap are discarded from memory. In v1, the UI shows an "older messages hidden" marker with a manual refresh button, allowing operators to reload the page and regain visibility into older logs.

However, this UX has limitations:
- **Manual refresh penalty**: Reloading the page requires the backend to re-parse and re-serve the entire transcript from disk, which is expensive for large session logs (100k+ rows).
- **Data loss perception**: The "hidden messages" indicator, while transparent, may cause concern that important diagnostic data is irretrievable.
- **No pagination**: Operators cannot selectively fetch historical windows (e.g., "rows 100–200" or "rows from T-10min to T-5min").

The design question is whether to add **on-demand, windowed transcript fetch** that allows operators to retrieve older rows efficiently without reloading the page—and if so, what mechanism and UX patterns should govern this feature.

---

## Open Questions

### OQ-1a: UX Pattern for On-Demand Fetch

**Directions explored:**

1. **Explicit "Load More" Button** (Top of list)
   - Pros: Clear affordance; operator intent explicit; can show "loading..." state
   - Cons: Adds UI element; requires scroll-to-top to trigger; may encourage fetching large windows

2. **Infinite Scroll / Scroll-to-Top Virtualization**
   - Pros: Seamless; familiar pattern; mirrors "load more at bottom" UX
   - Cons: Harder to control window size; risk of accidental large fetches; performance implications for virtualization

3. **Time-based Filter/Search UI**
   - Pros: Precise selection; operators can target known time windows; reduces over-fetching
   - Cons: Requires timestamp info on logs; more complex UI; may be overkill for simple diagnostic needs

4. **Hybrid: Marker + Optional Fetch**
   - Pros: v1 UX remains "manual refresh"; on-demand fetch is optional enhancement
   - Cons: Two code paths; increased complexity

**Decision required**: Which pattern aligns with operator workflows and CCDash UX conventions?

### OQ-1b: Latency Budget & Window Size

**Questions:**
- What is the acceptable latency for an on-demand fetch? (e.g., <200ms, <500ms, <1s?)
- Should the fetch be a single large window (all older logs) or paginated (e.g., 1000-row chunks)?
- How should the window size be configurable? (env var, per-query param, estimated from payload size?)

**Current assumptions (v1 `runtime-performance-hardening`):**
- 5000-row in-memory cap; older rows discarded
- Full transcript re-fetch on manual page reload takes N seconds (baseline unmeasured)

**Tradeoff**: Smaller windows (1000 rows) = lower latency but more round-trips. Larger windows (10k+ rows) = single fetch but potentially >1s latency and DOM overhead.

### OQ-1c: Cache Eviction Strategy

**Questions:**
- Should on-demand-fetched rows remain in memory, or evict after a TTL?
- If retained: does the 5000-row cap apply to all rows (including on-demand), or only auto-polled rows?
- How should operators detect when on-demand data is stale and needs refresh?

**Current state**: Frontend does not distinguish "auto-polled" vs "on-demand-fetched" rows; both are subject to the same memory cap.

**Tradeoff**: Retaining on-demand data increases memory but improves UX (no re-fetch); evicting it preserves the memory cap but requires re-fetch on scroll.

### OQ-1d: Backend Query Shape

**Questions:**
- Should the endpoint be `/api/agent/session/{session-id}/transcript?offset=X&limit=Y` (row-based)?
- Or time-based: `/api/agent/session/{session-id}/transcript?after=ISO8601&before=ISO8601`?
- Should the response include full row objects or a compact format (e.g., message + timestamp only)?

**Consideration**: Row-based pagination is simpler but requires knowing row count. Time-based pagination is more intuitive for operators but requires timestamp indexes.

---

## Explored Alternatives

### 1. Full Retention with Virtualization (Rejected in v1)

**Approach**: Keep all transcript rows in memory; use react-virtual to render only visible rows (DOM node cap).

**Pros:**
- No fetch logic needed; all rows available instantly
- Single source of truth (in-memory array)
- Simplest implementation

**Cons:**
- Memory still grows unbounded (5000+ rows = ~5MB+ depending on log sizes)
- JavaScript array with 100k+ rows causes GC pressure and memory leaks
- Solved in v1 by capping at 5000 rows per FR-1

**Status**: Shipped (ring-buffer truncation is the v1 solution)

---

### 2. Ring-Buffer with Truncation Marker (Shipped in v1)

**Approach** (from `runtime-performance-hardening-v1` FR-1):
- Cap `session.logs` to 5000 rows using ring-buffer semantics
- Drop oldest rows when exceeding cap
- Emit `transcriptTruncated` marker in UI showing "older messages hidden"
- Manual page reload re-fetches full transcript from backend

**Pros:**
- Solves unbounded memory growth
- Simple; no new fetch logic
- Transparent to operators (marker visible)

**Cons:**
- Expensive re-fetch on reload (re-parse entire JSONL on backend)
- "Hidden messages" marker may concern users
- No selective fetch option

**Status**: Shipped in `runtime-performance-hardening-v1` Phase 1

---

### 3. Lazy Windowing on Scroll (Partial)

**Approach**: On frontend scroll-to-top, fetch next window of older rows from backend.

**Pros:**
- No explicit UI button needed; transparent to operator
- Fetch happens on demand (operator-driven)
- Memory cap can be dynamic (older on-demand rows evict if cap exceeded)

**Cons:**
- Virtualization + infinite scroll is complex; interaction model unclear
- Risk of "rubber-band" scrolling during fetch
- Hard to signal to operator that fetch is in progress or stale

**Status**: Not pursued in v1; deferred to OQ-1 design spec

---

### 4. On-Demand Fetch from DB (Candidate for OQ-1)

**Approach**: Add backend endpoint `/api/agent/session/{id}/transcript-history?offset=X&limit=Y` to fetch older transcript rows directly from the cached DB.

**Pros:**
- Efficient; queries DB instead of re-parsing JSONL
- Operator-controlled (explicit button or time-based filter)
- Can be cached/throttled easily
- Doesn't interfere with ring-buffer memory cap

**Cons:**
- Adds new backend query surface
- Requires row-offset tracking or timestamp indexing
- UI must handle "loading" + error states
- Potential for stale data if DB is out of sync with filesystem

**Status**: Candidate for follow-on spec; deferred pending UX decision

---

## Promotion Criteria

This design spec should be promoted to a PRD when:

1. **Operator feedback received**: Post v1 release, gather feedback on the "older messages hidden" UX from operators running 24+ hour sessions. If complaints are widespread, escalate to PRD.

2. **Memory cap proves insufficient**: If the 5000-row cap is too aggressive and operators report loss of critical diagnostic data, on-demand fetch becomes a necessity rather than convenience.

3. **Use case clarification**: Once OQ-1a (UX pattern) is resolved via stakeholder discussion or spike, a concrete PRD can be scoped.

**Promotion trigger thresholds:**
- 3+ operator issues/complaints about transcript truncation loss OR
- Evidence that 5000-row cap is insufficient for any common workflow OR
- Stakeholder decision to ship on-demand fetch as part of a broader "transcript UX improvements" initiative

**Promotion path**: Convert this design spec to a PRD at `/docs/project_plans/PRDs/features/transcript-fetch-on-demand-v1.md` with:
- Resolved OQ-1a, OQ-1b, OQ-1c, OQ-1d decisions
- Clear acceptance criteria for chosen UX pattern
- API shape + response contracts
- Test plan for latency budget validation
- Rollout plan (feature flag if needed)

---

## Next Steps for Detailed Design

When promoting to PRD, address:

1. **OQ-1a Resolution**: Conduct stakeholder meeting; decide on "Load More" vs "Infinite Scroll" vs "Time Filter" vs "Hybrid"
2. **OQ-1b Resolution**: Define latency SLA (e.g., <200ms) and window size strategy (1k, 5k, full)
3. **OQ-1c Resolution**: Document cache eviction rules and retention TTL (if any)
4. **OQ-1d Resolution**: Design backend endpoint shape; add database indexes if time-based fetch is chosen
5. **Spike if needed**: If complexity is high, consider a spike to prototype chosen UX pattern with load testing

---

## Tags & Metadata

- **Category**: Feature
- **Priority**: Medium (deferred; nice-to-have post-v1)
- **Risk Level**: Low (no impact on current v1 delivery)
- **Maturity**: Shaping (direction clear, design unresolved)
- **Related Items**: OQ-1 from `runtime-performance-hardening-v1` PRD
