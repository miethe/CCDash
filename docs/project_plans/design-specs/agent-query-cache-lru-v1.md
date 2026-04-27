---
schema_version: 2
doc_type: design_spec
title: "Agent Query Cache LRU Eviction Policy v1 - Design Spec"
status: draft
maturity: shaping
feature_slug: agent-query-cache-lru
feature_version: v1
prd_ref: /docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md
plan_ref: /docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md
created: 2026-04-27
updated: 2026-04-27
category: infrastructure
tags: [cache, memory, eviction, performance, deferred]
related_documents:
  - docs/project_plans/design-specs/runtime-performance-hardening-v1.md
  - docs/guides/query-cache-tuning-guide.md
  - docs/project_plans/implementation_plans/db-caching-layer-v1.md
references:
  user_docs: []
  context: []
  specs:
    - .claude/specs/cache-policy-patterns.md
  related_prds: []
owner: nick
contributors: []
---

# Agent Query Cache LRU Eviction Policy v1 — Design Spec

**Issue**: OQ-3 from runtime-performance-hardening-v1 PRD  
**Date**: 2026-04-27  
**Maturity**: Shaping (direction identified, structured outline ready for detailed design)

---

## Problem Statement

The current agent query cache in `backend/application/services/agent_queries/` and `backend/routers/cache.py` uses **TTL-only eviction**. Memory consumption is bounded per key (by TTL expiry), but unbounded across the total number of cached keys. A workspace with 50k sessions generating diverse query patterns can accumulate thousands of distinct cache entries over a 10-hour session, consuming hundreds of MB or more in the cache Dict/Redis backend.

The v1 performance hardening initiative raises the default TTL from 60s to 600s to align with the warmer refresh cycle. This increases per-entry residence time and amplifies the unbounded key-count problem.

**Soft eviction alternative**: Rather than hard-removing stale entries from cache, mark them for **revalidation** (fetch fresh, cache new result). This preserves cold-cache semantics while capping memory.

---

## Open Questions

1. **Eviction strategy**: Should we implement LRU (least recently used), LFU (least frequently used), or ARC (adaptive replacement cache)? Trade-off: LRU is simple and proven; LFU better suits hot-key patterns; ARC combines both but adds complexity.

2. **Max-entries threshold**: Should the cap be global (e.g., 5000 entries) or per-namespace (e.g., 500 per query type)? Global is simpler; per-namespace allows fine-tuning hot paths.

3. **Eviction mode**: Hard eviction (delete from cache, force recompute) vs. soft eviction (mark stale, serve with "revalidate" flag, lazy recompute). Hard is faster; soft preserves stale-while-revalidate semantics.

4. **Integration point**: Should eviction policy live in the cache abstraction (`backend/db/connection.py` or a new `cache_manager.py`)? Or as a middleware in query service layer?

5. **Monitoring**: Should we expose metrics (`ccdash_cache_eviction_total{strategy}`, `ccdash_cache_size_entries`) to detect when policies are active?

---

## Explored Alternatives

| Alternative | Pros | Cons | Notes |
|-------------|------|------|-------|
| **TTL-only (current)** | Simple; no eviction overhead; predictable cleanup | Unbounded key count; memory grows with cardinality of query patterns | Current state; addressed by v1 TTL raise but not long-term solution |
| **Pure LRU (fixed size)** | Standard, proven; memory strictly bounded | Cache churn if max-size too low; complexity in concurrent cache access | Consider for first iteration if soft-eviction deferred |
| **LFU + LRU hybrid (tiered)** | Hot entries stay longer; cold entries evicted sooner | Two-tier bookkeeping; tuning hit/miss thresholds | Good fit for agent-query patterns (some queries hot, many cold) |
| **ARC (adaptive)** | Adapts to workload (hot vs. cold); proven in databases | High complexity; mutable history structures; harder to debug | Overkill for initial iteration; revisit if hit rate issues persist |
| **Signed-cookie offload** | Move cache to client; no server memory | Requires client changes; stale data risk; size limits | Out-of-scope for v1; hybrid approach for future |

---

## Rationale for Deferral

OQ-3 was deferred from runtime-performance-hardening-v1 because:

1. **TTL raise may be sufficient**: Aligning TTL with warmer interval (600s) and implementing incremental link rebuild + batch workflow queries addresses most cold-window cache misses. If post-release metrics show hit rate ≥90% sustained, soft eviction is not critical.

2. **Complex to design well**: Choosing between LRU/LFU/ARC, setting thresholds, and testing concurrent access patterns requires deeper spike work. Deferring lets the performance hardening v1 ship faster.

3. **Monitoring required first**: Prometheus counters from v1 (Phase 4 observability) will surface cache metrics. Only after collecting data can we tune eviction policy thresholds confidently.

---

## Trigger for Promotion

Revisit and promote this spec to PRD if **post-v1 release metrics show**:

- **Cache hit rate < 90% sustained** over a 24-hour period in production-like load (workspace with 50k+ sessions)
- **Memory usage per cache entry trending upward** despite TTL tuning
- **User reports of stale query results** even with warmer enabled

**Measurement method**: Use new Prometheus counters from Phase 4 (`ccdash_query_cache_hit_total`, `ccdash_query_cache_entry_count`) + operator feedback.

---

## Preliminary Technical Direction (Shaping Only)

If promoted, recommend exploring:

1. **Soft-eviction LRU** (simplest first step):
   - Global max-entries threshold (e.g., 5000)
   - Track last-access timestamp on every hit
   - On insert: if cache size ≥ max, evict least-recently-used entry and mark it "revalidated-needed"
   - Queries hitting revalidation-needed entries fetch fresh, cache new result
   - Soft eviction preserves stale-while-revalidate semantics

2. **Instrumentation**:
   - `ccdash_cache_eviction_total{strategy=lru}` counter
   - `ccdash_cache_size_entries` gauge (current entry count)
   - `ccdash_cache_revalidate_needed_total` (soft evictions that required recompute)

3. **Rollout**:
   - Gate behind `CCDASH_QUERY_CACHE_LRU_ENABLED` (default `false`)
   - Soak period before flipping default
   - No breaking API changes (cache still returns latest data)

---

## Acceptance Criteria (Shaping Level)

- [x] Problem statement articulates unbounded key-count issue and TTL-raise context
- [x] Open questions cover strategy, threshold, mode, integration, monitoring
- [x] Explored alternatives table justifies deferral vs. other approaches
- [x] Trigger condition defined (hit rate < 90%, memory trending up)
- [x] Preliminary direction (soft LRU) sketched for promotion phase
- [x] Maturity = `shaping` ✓

---

## Next Steps (If Promoted)

1. **Spike**: Collect post-v1 cache metrics; measure hit rate and entry count in real deployment
2. **Research**: Evaluate LRU vs. LFU vs. ARC via benchmarks on CCDash query patterns
3. **Design**: Create detailed spec with threshold tuning, concurrency strategy, rollback plan
4. **Implement**: Add soft-eviction logic, counters, feature flag
5. **Test**: Verify cache behavior under sustained load; measure memory before/after

---

## References

- **Parent PRD**: `/docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md` § 12 Open Questions, OQ-3
- **Parent Plan**: `/docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md` § Deferred Items & In-Flight Findings Policy
- **Query Cache**: `backend/routers/cache.py`, `backend/application/services/agent_queries/`
- **Cache Tuning Guide**: `docs/guides/query-cache-tuning-guide.md`
