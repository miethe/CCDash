---
title: "Design Spec: op story Session Reference Frontmatter Contract (OQ-3)"
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
  - op-story
  - frontmatter
  - session-ref
  - cross-repo
related_documents:
  - docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
  - docs/project_plans/exploration/ccdash-automated-aar-review/spikes/tech-findings.md
  - docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md
description: |
  Specification of the cross-repo frontmatter contract for `op story`-produced AARs
  to support direct session reference (fast-path correlation). This design spec
  proposes frontmatter field(s) that would enable CCDash to correlate AARs directly
  to sessions without relying on the two-hop AAR→feature→session fallback, improving
  correlation confidence from 0.64–1.0 to 1.0 and reducing binding-constraint latency
  on entity-link freshness. Addresses open question OQ-3 from the PRD.
schema_version: 2
---

# Design Spec: op story Session Reference Frontmatter Contract (OQ-3)

## Problem Statement

**Current State (OQ-1 findings — Phase 1 sampling):**
- Of 9 real AARs sampled, **zero carried a direct session reference** in frontmatter
- AAR-to-session correlation is forced through a two-hop `AAR → feature_slug → [session_ids]` fallback
- This two-hop path carries correlation confidence band of **0.64–1.0** (per tech-findings.md)
- The binding constraint is **entity-link freshness**: two-hop accuracy degrades if the feature→session mapping is stale or incomplete

**Problem**: Without a direct, authored session reference in AAR frontmatter, CCDash cannot reach 1.0 correlation confidence on the AAR-review recall path. This blocks:
- Autonomous triage of AARs describing edge-case or low-feature-traffic sessions (which may not land in a feature roll-up)
- Reducing latency on the correlation check — today it must refresh entity-links before every triage query
- Using correlation confidence as a hard discriminator in the verdict decision table (§7.2 of the PRD)

**Hypothesis**: If `op story` emits a direct session-reference field in every AAR frontmatter, CCDash gains a first-class, explicit correlation strategy with 1.0 confidence. This would:
1. Eliminate the two-hop fallback for most AARs
2. Reduce entity-link staleness as a triage-path blocker (though the two-hop fallback remains for backward compat)
3. Enable the `explicit_session_ref` strategy (currently designed but untested in the wild)

---

## Proposed Frontmatter Contract

### 3.1 Field(s) to Add to `op story`-Produced AARs

**Primary field (recommended):**

```yaml
---
session_refs:
  - session_id: string              # one or more session IDs this AAR directly describes
  - session_id: string
---
```

**Alternative (if `op story` prefers brevity for single-session AARs):**

```yaml
session_ref: string              # single session ID (mutually exclusive with session_refs)
```

**Rationale for choice:**
- CCDash's existing session-key detection already includes both singular and plural variants (`SESSION_KEYS = ["session", "session_id", "sessionid", "sessions", "linked_sessions", "linkedsessions"]`; see `backend/application/services/agent_queries/aar_review.py` pattern)
- Using `session_refs` (plural) as the **canonical form** aligns with the multi-session-per-AAR possibility (AAR may synthesize multiple sessions into one narrative)
- Falls back to `session_id` (singular) for backward compat and single-session AARs
- No new parsing logic required in CCDash; existing variant loop covers both

### 3.2 Semantics

- **`session_refs` (list of strings)**: IDs of zero or more sessions this AAR claims to synthesize, analyze, or describe. Each ID is a CCDash session UUID.
- **`session_id` (string, alternative)**: Singular session ID for AARs describing exactly one session.
- **Zero session refs**: If an AAR omits both fields, it falls back to the two-hop strategy (current behavior — no breaking change).
- **Multiple session refs**: An AAR may list ≥1 session if the narrative synthesizes findings across multiple runs.
- **Stale refs**: If a `session_ref` does not exist in the CCDash DB (deleted or never ingested), correlation confidence degrades to the two-hop fallback for that ref; the verdict is not failed entirely.

### 3.3 Impact on CCDash Correlation Strategies

**Addition to the existing 3-strategy taxonomy** (see `session_correlation.py` and `entity_links` in CCDash):

| Strategy | Confidence | Data Source | Notes |
|----------|-----------|-----------|-------|
| **explicit_session_ref** (NEW) | 1.0 | AAR frontmatter `session_refs[]` or `session_id` | Direct author-provided session ID(s); no fallback needed. |
| explicit_session_ref | 0.96 | AAR frontmatter `sessions:` / `linked_sessions:` (already handled) | Existing variant loop catches alternate spellings. |
| task_session_ref | 0.96 | AAR frontmatter `task_id` → resolve via task→session link | Existing; unchanged. |
| doc_feature_session_two_hop | 0.64–1.0 | AAR frontmatter `feature_slug` → feature→session entity-link | Existing fallback; remains active if explicit ref is absent. |

**Decision logic in CCDash** (no code change to existing strategies, only addition):

```python
# In aar_review.py / session_correlation.correlate_session_for_aar():
session_ids = []

# Try explicit session_refs first (NEW)
if "session_refs" in aar_frontmatter and aar_frontmatter["session_refs"]:
    session_ids = aar_frontmatter["session_refs"]  # confidence: 1.0
    strategy = "explicit_session_ref"
    confidence = 1.0
elif "session_id" in aar_frontmatter:  # (NEW, singular fallback)
    session_ids = [aar_frontmatter["session_id"]]
    strategy = "explicit_session_ref"
    confidence = 1.0
else:
    # Fall through to existing strategies (task_session_ref, doc_feature_session_two_hop)
    session_ids, strategy, confidence = existing_correlation_logic(...)
```

---

## Cross-Repo Implementation

### 4.1 Owner & Location

**`op story` side** (`agentic_meta_dev/op` repo, `op/story.py` circa line 1414-1458):
- When capturing an AAR via `op story capture <AAR-text>`, populate frontmatter with the session ID(s) the AAR is synthesizing
- Suggested field name: `session_refs:` (list)
- Fallback field name: `session_id:` (string, for single-session AARs)
- Source: `op story` already knows which sessions triggered the AAR-generation workflow; pass that context to the AAR's metadata

**CCDash side** (this repo, `backend/application/services/agent_queries/aar_review.py`):
- Add `session_refs` and `session_id` to the session-key lookup loop (currently: `SESSION_KEYS` tuple)
- Test the new `explicit_session_ref` strategy against a fixture AAR with frontmatter session refs
- No breaking changes; existing two-hop fallback remains for backward compat

### 4.2 Back-Compatibility & Migration

**Forward**: New AARs produced by `op story` will carry `session_refs`. Existing AARs in the wild already do not carry it (per OQ-1 findings). This is **non-breaking**:
- CCDash gracefully falls back to the two-hop strategy if `session_refs` is absent
- Correlation confidence for older AARs remains 0.64–1.0 (two-hop)
- No data migration needed; the lookup-logic change is append-only

**Consumer expectation**: Consumers of `aar_review_candidate` events (per the consumer contract, §7.3 of the PRD) will begin seeing `correlation.strategy == "explicit_session_ref"` and `confidence == 1.0` for new AARs. Clients MUST NOT assume `confidence < 1.0` for all AARs; they must evaluate the `confidence` field, not the strategy enum.

**No op story versioning needed**: The AAR frontmatter schema is document-shape, not a versioned API. `op story` may emit the new field immediately once this contract is accepted. CCDash's parser is permissive by design (unrecognized frontmatter keys are ignored).

---

## Expected Confidence Lift

**Baseline (OQ-1)**: 0 of 9 sampled AARs carry a session ref → 100% fall back to two-hop (confidence 0.64–1.0).

**Target**: Once `op story` adopts this contract:
- **New AARs**: 100% will carry `session_refs` → 100% achieve `explicit_session_ref` (1.0 confidence)
- **Existing AARs**: Unchanged; fall back to two-hop (0.64–1.0)
- **Blended confidence** (after N weeks): progressively improves as older AARs age out of active triage window

**Impact on autonomous triage (P4 of the PRD)**:
- Low-confidence two-hop pairings (0.64–0.85) can now be distinguished from guaranteed-direct ones (1.0)
- Escalation quota (Guard 3, §8.1 of PRD) can differentiate between "escalate high-confidence explicit ref" (1.0) vs. "escalate two-hop only if > N strong flags" (0.64–1.0)
- Self-recursion Guard 1 (provenance self-exclusion) benefits: if the AAR-review workflow's own sessions are tagged with a reserved `workflow_id`, the session_ref can be checked directly against that tag without needing entity-link lookups

---

## Open Questions & Risk

### 6.1 Open Questions

1. **Does `op story` already capture the session context at the time of AAR emission?**
   - **Expected**: Yes — `op story capture` is called in the context of a dispatch run, which references the root agent session or a feature run.
   - **Action**: Confirm with `op` maintainer that session context is available at the capture gate.

2. **Should every AAR emit `session_refs`, or is it optional?**
   - **Proposed**: Optional. An AAR describing a synthetic narrative across multiple project observations (not tied to a specific session) would omit it, falling back to two-hop or feature-only routing.
   - **Action**: Document in the `op story` PR that `session_refs` is an optional field for AARs that have a clear session anchor.

3. **What if `op story` produces an AAR that references a session that doesn't exist in CCDash yet (e.g., future or out-of-project session)?**
   - **Proposed**: Correlation confidence degrades to the two-hop fallback for that AAR. It is not a failure; it is a contract state (resilience note R-P2 in PRD §7.2).
   - **Action**: Test this in the integration smoke (P3) and document it in the consumer contract.

### 6.2 Risks

| Risk | Mitigation |
|------|-----------|
| `op story` forgets to populate `session_refs` on a new AAR | Falls back to two-hop (no breaking change). Recommend adding a data-validation step in `op story`'s own PR to surface missing refs as a lint warning. |
| CCDash's session-key loop is buggy and doesn't catch `session_refs` | Unit test in `test_aar_review_correlation.py` covers `session_refs` and `session_id` variants alongside existing keys. |
| Stale session ref (session deleted from CCDash after AAR was written) | Correlation confidence degrades to two-hop. Document as expected behavior. |

---

## Acceptance Criteria

- [ ] `op story` PR adds `session_refs` (list) and `session_id` (string, fallback) fields to AAR frontmatter capture, with documentation
- [ ] CCDash's `SESSION_KEYS` tuple updated to include `"session_refs"` and verified in the session-key-detection loop
- [ ] Unit test in `backend/tests/` covers `explicit_session_ref` strategy for both `session_refs` and `session_id` variant frontmatter
- [ ] Integration smoke (P3) includes a cross-repo test: capture an AAR in `op story` with embedded session_refs, fetch it via CCDash REST, verify `correlation.strategy == "explicit_session_ref"` and `confidence == 1.0`
- [ ] Consumer contract (§3 of `ccdash-aar-review-consumer-contract-v1.md`) updated to reference this spec and document the three confidence bands (0.64–1.0 two-hop, 0.96 task-session, 1.0 explicit)

---

## References

- **PRD §7.1** (Data Contracts — the 5 surface flags): context on why correlation confidence matters to triage verdict
- **tech-findings.md §Confidence & Residual Unknowns**: OQ-1 sampling data (0/9 real AARs carry direct session ref)
- **session_correlation.py**: existing correlation strategy implementation (3-strategy taxonomy)
- **entity_links**: document-linking backend that powers the two-hop fallback
- **consumer-contract-v1.md**: consumer-side expectations for correlation confidence bands

---

## Status & Next Steps

**Status**: SHAPING (ready for design review before `op story` implementation)

**Next Step**: 
1. Confirm with `op` maintainer that session context is available at AAR-capture gate (OQ 6.1.1)
2. Draft `op story` PR implementing `session_refs` population
3. Update CCDash's `SESSION_KEYS` constant and add unit test (P1 exit criteria)
4. Cross-repo integration smoke test in P3 validates the contract end-to-end
