---
doc_type: worknote
feature_slug: ccdash-automated-aar-review
created: 2026-07-22
---

# OQ-1: Real-World AAR Correlation Prevalence

## Question

Do real `op story`-produced AAR docs carry a direct session/feature frontmatter ref, or do they rely
on the two-hop fallback (feature slug → entity_links → session)?

## Code Facts (as implemented, `aar_review.py`)

- `_correlate()` checks `entity_links` document→session links **first**; it only falls back to
  frontmatter session refs (keys checked: `session`, `session_id`, `sessionid`, `sessions`,
  `linked_sessions`, `linkedsessions`) when no entity_links session correlation exists.
- Feature correlation has **no** frontmatter fast path — it is always resolved via `entity_links`.
  There is no direct-feature-ref shortcut analogous to the session one.

## Method

Sampled 9 real AAR docs across three repos that produce AARs via the `op story` pipeline: CCDash,
skillmeat, and the agentic_meta_dev op-story inbox. For each doc, checked (a) presence of a
frontmatter key the code recognizes as a direct session ref, (b) presence of a code-recognized
direct feature ref, and (c) whether `feature_slug` (or equivalent) is present and thus two-hop
correlation is eligible via `entity_links`.

Sampled paths:

- CCDash: `.../ccdash-core-remediation/wave-4-aar.md`
- CCDash: `.../ccdash-db-design-remediation/aar.md`
- CCDash: `.../ccdash-runtime-deploy-remediation/after-action-report.md`
- CCDash: `docs/.../planning-command-center-v1-aar-2026-05-29.md`
- skillmeat: `.../loop-fixes/loop-aar.md`
- skillmeat: `.../artifact-git-deploy/execution-aar.md`
- skillmeat: `.../enterprise-live-source-ingestion/wave1-aar.md`
- skillmeat: `docs/.../unified-artifact-assembly-v1-aar.md`
- skillmeat: `docs/.../registry-core-w3-aar.md`

## Findings

| Metric | Count / 9 |
|---|---|
| Direct session ref (frontmatter) | 0 |
| Code-recognized direct feature ref | 0 |
| Two-hop-eligible via `feature_slug` → entity_link | 6 |
| No correlatable frontmatter identity at all | 3 |

- **0/9** had a direct session ref.
- **0/9** had a code-recognized direct feature ref.
- **6/9** were two-hop-eligible via `feature_slug` → entity_link, contingent on sync freshness.
- **3/9** had no correlatable frontmatter identity at all → correlation degrades to
  `surface_only`/none for these.

## Conclusion

Direct-ref correlation is effectively unused in the wild; two-hop (feature_slug → entity_links →
session) dominates and must remain the primary correlation path, not a degraded fallback.
`feature_slug`-only docs are the realistic default case, not the edge case. The binding constraint
on correlation confidence is **entity_links freshness** (has the sync engine run since the
session/doc link was created), not frontmatter completeness.

This directly justifies the OQ-2 resolution recorded in the ADR addendum
(`ccdash-automated-aar-review-proposed-adr.md`): gating the triage verdict on correlation
*strategy* (direct vs two-hop) rather than on confidence *value* would send nearly every real AAR to
`human_triage_required`, defeating autonomous triage before it starts. Confidence-value gating (with
a hard floor for missing/low confidence and an ambiguity check for unresolved multi-candidate
two-hop ties) is the correct discriminator.
