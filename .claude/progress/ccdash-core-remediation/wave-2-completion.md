# CCDash Core Remediation — Wave 2 Completion Report

**Date**: 2026-06-11
**Wave**: W2 — phases P1, P4, P6, P7 (independent streams after Phase 0)
**Landed on**: `epic/ccdash-core-remediation` as squashed commit `0018978`
**Per-phase commits (pre-squash, branch `ccr/w2`)**: `727d7d4` (P6) → `5087a4b` (P4) → `7615567` (P1) → `77841dc` (P7) → `733956d` (gate fixup)
**Reviewer verdict**: APPROVED (opus, Bash-enabled, read-only)
**Tests**: 122 passed + 6 subtests (named-module sweep)

## Phase Summary

| Phase | Scope | Key outcome | Tests |
|-------|-------|-------------|-------|
| P1 | `agent_queries/session_detail.py` + `redaction.py` | Transport-neutral session-detail service; `project_id` enforced on every read; 5 include flags; cursor pagination (200/1000); layered redaction at single egress boundary (OQ-1). | 72 |
| P4 | `db/sync_engine.py` + `document_linking.py` | Family-scoped incremental link rebuild on watcher hot path; **causal-link proof** (no global scan); default `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` flipped `true`. | 15 |
| P6 | `routers/analytics.py` + `services/pricing_catalog.py` | Novel model IDs flagged `unpriced` (no silent Sonnet default); distinct Fable tier; `costPricingStatus` + `displayCostUsd`-null FE-fallback seam. | 16+ |
| P7 | `db/sync_engine.py` + `adapters/jobs/{durable_queue,runtime}.py` + `config.py` | `(project_id,trigger)` sync coalescing; recent-first backfill (OQ-3: N=200) with backfill==baseline parity; startup-timer hygiene. Composes on P4 routing. | 22 |

## Decisions resolved
- **OQ-1** (redaction): layered = secret-pattern scan + tool-name-aware field redaction; env-knobs fail-closed.
- **OQ-3** (recent-first window): N-most-recent, default `CCDASH_SYNC_RECENT_FIRST_N=200`, count-bounded + mtime tiebreak.

## Seam notes (for downstream waves)
- `get_session_detail(project_id, session_id, *, include, cursor, limit)` returns a redacted, transport-neutral bundle — **W3 P2 (REST)** and **W4 P3 (MCP/CLI)** consume this directly.
- P6 `costPricingStatus` ("priced"|"unpriced") is the FE badge trigger; FE must branch on it, not on `displayCostUsd` null-ness. P6 FE badge (T6-003) is a deferred FE-owner deliverable.

## Carry-forwards (non-blocking)
1. **AC 7.5 live-Postgres durable coalescing**: P7 durable-queue dedupe is proven via mocked repo; live-PG integration belongs to **Phase 9** (Postgres convergence gate, `depends_on: P7`). Validate there.
2. Unpriced model with an Anthropic-reported cost yields non-null `displayCostUsd` while status stays `unpriced` (deliberate; reported charge authoritative).

## Execution substrate note
Agent-tool subagents failed `Prompt is too long` on this repo (large `CLAUDE.md` auto-loads into every subagent). All implementation + review ran via **ICA `--bare` bash delegation** (sonnet[1m] implementers, opus[1m] reviewer, free-tier haiku for metadata) — the pre-authorized fallback.

## Plan status
Wave 2 of 6 complete. Remaining: W3 (P2,P5,P8) → W4 (P3,P9,P10) → W5 (P11) → W6 (P12). Plan stays `in-progress`.
