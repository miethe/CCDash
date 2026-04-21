# CCDash Planning Reskin v2 Worknotes

## Phase 0 Audit Notes

### T0-004: Planning payload audit (OQ-01)

- Planning feature data already carried `spikes` and `openQuestions` in feature `data_json`, but the transport-neutral planning context did not expose them consistently.
- Phase 7 extends `PlanningQueryService.get_feature_planning_context()` so the planning payload now surfaces:
  - `spikes`
  - `open_questions`
  - grouped artifact buckets (`specs`, `prds`, `plans`, `ctxs`, `reports`)
  - `ready_to_promote` and `is_stale`

### T0-006: Session-forensics token audit (OQ-02)

- Existing `FeatureForensicsDTO.total_tokens` already provided authoritative per-feature totals from linked sessions.
- The per-model breakdown was not previously exposed.
- Phase 7 adds `token_usage_by_model` with `{ opus, sonnet, haiku, other, total }` on both forensics and planning context payloads, derived via `backend.model_identity.derive_model_identity(...)[\"modelFamily\"]`.
