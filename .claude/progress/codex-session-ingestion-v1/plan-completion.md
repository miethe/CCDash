---
doc_type: report
report_category: plan-completion
feature_slug: codex-session-ingestion-v1
status: completed
created: 2026-06-28
updated: 2026-06-28
---

# Codex Session Ingestion v1 — Plan Completion Report

**Branch:** `feat/codex-session-ingestion-v1` (base `419c355`) → squash-merged to `main`.
**Execution model:** sequential (no `wave_plan`); one phase at a time, specialist-delegated.

## Design decisions (operator)

| ID | Choice | Note |
|----|--------|------|
| D1 | **D1-a** — `projects.repo_path` + `resolve_project_for_cwd` (exact→longest-prefix) | as recommended |
| D2 | **D2-b** — Unattributed bucket | realized as `project_id = ''` (NULL infeasible under `sessions` composite PK `(project_id, id)`) |
| D3 | **D3-b** — last-N-days backfill then live reconcile | `CCDASH_CODEX_BACKFILL_DAYS` (default 7; 0 = full) |
| + | Operator add: **unmistakable session origin** on cards + inspector + filter | folded into Phase 3 |

## Phase summary

| Phase | Scope | Commit | Tests |
|-------|-------|--------|-------|
| 1 | `projects.repo_path` (dual DDL v37→v38) + pure `resolve_project_for_cwd` | `0ae76fc` | 13/13 |
| 2 | `CCDASH_CODEX_INGEST_ENABLED`/`_SESSIONS_PATH`; `sync_codex_sessions` attribution; D2-b `project_id=''`; `sessions.cwd` (v38→v39); idempotency; flag-off no-op | `4aece15` | 6/6 |
| 3 | `derive_session_source` codex branch + title derivation; FE Codex chip + Unattributed badge (cards + inspector) + Origin filter; resilience fallback | `bfd481b` | 23 + 35 |
| 4 | Worker startup backfill + periodic reconcile scan (gated); `CCDASH_CODEX_BACKFILL_DAYS`; launchd/.env templates | `74686c5` | 11/11 |
| fix | `source_origin` Origin filter wired end-to-end (apiClient + api.py + both session repos) | `2ba5350` | +new; 63/63 all-codex |

## Reviewer gate

`task-completion-validator` (Tier 2): initial verdict **CHANGES_REQUESTED** (Origin filter no-op) → fix applied → **APPROVED**. All AC1–AC6 pass; dual-DDL parity, composite-PK/FK safety of `project_id=''`, ADR-007, and FE resilience confirmed on disk. Final: **63/63** codex backend tests, **35/35** FE Vitest, no new tsc errors in changed files.

## Deferred / out-of-band

- **AC4 full runtime smoke** (node UI `http://10.42.10.76:3010`) requires a **node redeploy** to land this code (node was at `bb8996a`). Tracked as a post-merge operator step — not a merge gate. FE runtime smoke was `deferred-to-phase-4` and is satisfied at code/contract level (Vitest + tsc + build).
- Low-severity reviewer notes (non-blocking): `_extract_codex_cwd` scan-lines magic constant; first-deploy latency of the codex reconcile stat-scan over ~1.7k files.

## Operator action required

1. Enable on the worker host: set `CCDASH_CODEX_INGEST_ENABLED=1` (default off) — see `deploy/local-streaming/stream.env.example` / `.env.example`.
2. Ensure registered projects have `repo_path` populated (re-run `scripts/register_claude_projects.py` or recreate via `/api/projects`).
3. Redeploy the agentic node to the merged `main` SHA to complete AC4.
