---
type: report
schema_version: 2
doc_type: report
report_category: wave-completion
prd: ccdash-core-remediation
feature_slug: ccdash-core-remediation
wave: 5
title: "Wave 5 Completion — P11 (launch-time profile/effort capture)"
status: completed
created: 2026-06-12
updated: 2026-06-12
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
commit_refs: [5602a38]
merge_commit: 5602a38
merge_branch: epic/ccdash-core-remediation
phases: [11]
---

# Wave 5 Completion Report

**Scope:** Wave 5 = phase **P11** (launch-time profile/effort capture, fast-follow).
**Branch:** `wave5/p11-capture` (off `epic/ccdash-core-remediation` HEAD `8efbe14`), squash-merged to epic.
**Squash commit:** `5602a38`.
**Pre-squash phased commits:** `dc4563d` (T11-001 decision) · `fbf5c01` (T11-002/003/008 hook+columns+docs) · `7066c07` (T11-004 parser) · `fc1062f` (T11-005 detail+FE) · `b4c2262` (T11-006 seam test) · `09f5561` (T11-007 bookkeeping).

## What P11 delivers

Captures attributes that exist **only at launch time** and cannot be recovered from JSONL transcripts — launcher identity, launch profile (`ica-delegate` on the `~/ica-claude.sh` path), effort tier, model variant — and threads them through the full session pipeline with strict **null-never-defaulted** semantics (unknown == absent == null).

## Per-task outcome

| Task | Title | Verdict | Evidence |
|------|-------|---------|----------|
| T11-001 | Capture transport decision (OQ-5) | ✅ | sidecar `<session-id>.capture.json` written by a fail-open SessionStart hook reading a `CCDASH_LAUNCH_*` env contract; co-located by JSONL stem; distinct from the Phase 5 workflow sidecar |
| T11-002 | Launch-time capture hook (fail-open) | ✅ | `scripts/hooks/ccdash_capture_session_start.py` — always exit 0; unknown==null; never blocks/alters launch (13 tests) |
| T11-003 | Dual-backend capture columns + parity | ✅ | nullable `launcher/profile/effort_tier/model_variant` on sqlite + postgres (SCHEMA_VERSION 35) + parity allowlist + assertion test |
| T11-004 | Parser ingestion → first-class fields | ✅ | `capture_sidecar.py` + parser promotion; null-tolerant/partial-safe; COALESCE-on-null upsert (idempotent); root-session only (13 tests) |
| T11-005 | Session-detail exposure + FE fallbacks (R-P2) | ✅ | `types.ts`, `api.py` list/get, `session_detail.py` snake→camel; SessionInspector "Not captured" fallbacks (19 tests) |
| T11-006 | Seam integrity (R-P3, integration_owner) | ✅ | `test_capture_seam_integrity.py` — no field dropped across sidecar→parser→DB(snake)→detail(camel); null/partial clean (23 tests) |
| T11-007 | Runtime smoke (R-P4) | ✅ | `runtime_smoke: verified-api-build` — see ruling below |
| T11-008 | Convention doc | ✅ | `docs/guides/launch-time-capture-convention.md` |

## Reviewer gate

**task-completion-validator (Tier 3 per-phase, read-only, ICA opus[1m]): APPROVED.**
Ran the full suite itself — **70 backend passed, 8 skipped** (Postgres-gated) **+ 19 component passed** — and verified every AC (AC-11.A..E) with file:line evidence. No snake↔camel drop, no launch-blocking path, no scope creep (capture sidecar kept distinct from the Phase 5 workflow sidecar). Three non-blocking advisories (below).

### R-P4 runtime-smoke ruling (reviewer-adjudicated: ACCEPTABLE)

Runtime was **available and exercised** (so `runtime_smoke: skipped` was correctly *not* claimed):
1. **Live HTTP server** (worktree code vs the 11 GB main cache DB, startup-sync/watcher off, port 8077): `GET /api/sessions?limit=1` and `GET /api/sessions/{id}` both returned all four capture keys **present-but-null** for an un-captured session — proving the api.py + session_detail wiring is live and the R-P2 null contract (present, not missing) holds.
2. **Production build** `npm run build` → `✓ built in 12.55s` (SessionInspector.tsx + types.ts bundle clean).
3. **19 component tests** asserting the field-coalescing source/logic + null fallback against the live contract shape.

The only unexecuted leg is a literal browser pixel-click, for which **no browser-automation harness exists in this environment**. The reviewer ruled this clears the R-P4 bar ("renders cleanly / no crash / no undefined") because the evidence is materially more than the gate's warned anti-pattern (a unit-test pass alone). Evidence: `.claude/worknotes/ccdash-core-remediation/phase-11-runtime-smoke.md`.

## Advisories (non-blocking, carried to Phase 12 awareness)

1. **Component tests are source-level proofs, not jsdom DOM-mount assertions** (no jsdom harness; consistent with P4-007/P4-009 precedent). Combined with the absent browser click, there is no DOM-level proof the four rows physically mount; residual is low (static JSX in an already-rendered forensics grid). The runtime-smoke doc was corrected to state this accurately. Consider a real RTL/jsdom render test when the harness lands.
2. **Capture rows render inside `SessionInspector`'s `SessionForensicsView`** (not the top-level header). Noted in the convention doc so a future reader knows where to look.
3. **Hook is operator-install only** (documented, not registered in any settings.json) — by design for fail-open/reversibility and the no-retro-backfill contract. No automated test exercises the *real* SessionStart→sidecar chain on a live launch (the seam test simulates the sidecar). Flag for Phase 12 rollup awareness.

## Process notes

- Agent tool overflows on this repo's CLAUDE.md → all delegation ran via ICA `--bare` bash (`claude-sonnet-4-6[1m]` for edits, `claude-opus-4-8[1m]` for the Tier 3 review) with root CLAUDE.md re-injected via `--append-system-prompt-file`.
- One delegate (initial T11-005) hung on a transient ICA gateway drop with a 0-byte log; per the ica-delegate skill a single drop warrants retry, not abandonment — the retry produced all changes cleanly. Lesson: monitor delegate disk-output/log-growth for early stall detection rather than blind-waiting.
- The live runtime smoke was driven by the orchestrator directly (boot → curl → build → teardown), not via a mutating delegate, against a throwaway port bound to loopback.
- Worktree venv hazard honored: backend tests run via the **main-repo** `backend/.venv` with cwd=worktree (worktree has no venv); named test files only (unscoped pytest collection hangs in this repo).
- No live transport modified — `~/ica-claude.sh` and `~/.claude/*` untouched; hook registration is documented operator guidance only.

## Remaining program scope

Wave 6 = **P12** (CLAUDE.md/ADR rollup) remains, per the plan `wave_plan`. The plan stays `in-progress`; this run was explicitly **W5 only**. P12 should pick up: the ADR-007 equivalence note (Wave 4 follow-up), an ADR for the launch-time capture convention (per the T11-001 memo §6), and the three advisories above.
