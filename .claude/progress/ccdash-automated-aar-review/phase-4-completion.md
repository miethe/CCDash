# Phase 4 Completion Note — Read Surfaces: FE Panel + v1 LAN Endpoint + Capability

**Status:** COMPLETED · branch `feat/ccdash-automated-aar-review` · 2026-07-22
**Validator:** task-completion-validator — APPROVED (seam parity PASS). **Milestone (SC-7):** karen — **MET-WITH-CAVEATS**.

## What was built
- **v1 endpoint (T4-002 · AC-P4.4):** `GET /api/v1/project/aar-review` → `ClientV1Envelope[AARReviewListDTO]`
  ({project_id, total, reviews[§7.2 DTO]}); reads persisted `aar_reviews` via repo `get_by_project`,
  dedupes doc→session fan-out, `@memoized_query`, empty/failed → normalized empty payload (never HTTP error).
- **Capability (T4-003):** `"aar-review"` in `/api/v1/capabilities`.
- **FE panel (T4-001 · AC-P4.1/2/3):** `FeatureAARReviewPanel.tsx` — read-only; renders all 3 verdict
  states distinctly (token-driven); resilient to every optional §7.2 field; query hook
  `services/queries/aarReview.ts` + `queryKeys` + `types.ts` interfaces.
- **Seam (T4-004):** validator produced a field-for-field parity table — every §7.2 field the panel
  reads = a field the endpoint emits; consistent snake_case→camelCase adapter; endpoint path matches.

## Runtime smoke (T4-005) — `runtime_smoke: partial`
LIVE (backend `--runtime local` on :8000): `/api/v1/capabilities` → 200, `aar-review` present ✓;
`GET /api/v1/project/aar-review?project_id=<ccdash>` → 200, correct envelope, `total:0/reviews:[]`
(dev DB has no persisted rows — backfill not run + live-persist deferred); empty-project → 200 ✓.
The 3 verdict states + null resilience are covered by FE vitest (20/20) + backend round-trip tests
(incl. `human_triage_required`). Live browser render skipped: no browser automation in the
orchestration env AND no persisted rows to render (deferred persistence). Honest partial per the gate.

## karen milestone verdict (SC-7): MET-WITH-CAVEATS
Read loop structurally complete + honest; all 4 hard invariants verified REAL (no-LLM AST import test,
emit-only, no new CorePort, redaction-passed session_detail). Deferred live-persist is a legitimate,
well-tracked deferral (closes in P6), not an overclaim.

### Carry-forwards to later phases (from karen)
- **[P6 — HIGH]** `memoized_query` fingerprint does NOT track `aar_reviews` (self-disclosed in
  `_client_v1_aar_review.py:26-33`). The moment P6 wires live writes, cached reads go stale for up to
  the TTL. **P6 MUST tie live-write → cache invalidation as an explicit AC.** (Recorded in P6 tracker.)
- **[P6 — CRITICAL]** Live persistence (sweep worker / persist-on-compute) is the unrealized value —
  read surfaces are empty in prod until it lands.
- **[operational]** Run `aar_reviews_backfill.py` at least once per target project for non-empty demo.

## Files
FE: FeatureAARReviewPanel.tsx (+test), services/queries/aarReview.ts, services/queryKeys.ts, types.ts.
Backend: routers/client_v1.py, client_v1_models.py, _client_v1_aar_review.py (new), test_client_v1_aar_review.py (new).
