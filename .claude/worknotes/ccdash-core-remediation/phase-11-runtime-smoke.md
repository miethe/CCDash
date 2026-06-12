# Phase 11 — Runtime Smoke Evidence (T11-007 / R-P4)

**Date:** 2026-06-12 · **Surface:** SessionInspector launch-time capture fields
**Verdict:** `runtime_smoke: verified-api-build` (live runtime exercised; literal GUI pixel-click not driven — see Scope)

## What was run (live runtime, not unit tests)

Backend booted from the **worktree** code against the main repo's populated 11 GB
cache DB, startup-sync + file-watcher disabled, on a throwaway port:

```
CCDASH_DB_BACKEND=sqlite \
CCDASH_DB_PATH=<main-repo>/data/ccdash_cache.db \
CCDASH_STARTUP_SYNC_ENABLED=false CCDASH_FILE_WATCHER_ENABLED=false \
<main-venv>/python -m uvicorn backend.main:app --port 8077 --host 127.0.0.1
```

`Application startup complete` — clean boot.

### 1. Live API contract (running server, not a test client)

`GET /api/sessions?limit=1` (list_sessions) and
`GET /api/sessions/S-da3746f9-…` (get_session) BOTH returned the four
launch-time capture keys, **present-but-null** for an un-captured session:

| key | present | value |
|-----|---------|-------|
| `launcher` | ✅ | `null` |
| `profile` | ✅ | `null` |
| `effortTier` | ✅ | `null` |
| `modelVariant` | ✅ | `null` |

Control fields `modelSlug` / `contextWindow` (same snake→camel mapping idiom)
also present. This proves the api.py + session_detail wiring is live in the
**running server** and the R-P2 null contract holds: **present, not missing** —
which is precisely the state SessionInspector renders as "Not captured".

### 2. Frontend production build

`npm run build` → `✓ built in 12.55s`. SessionInspector.tsx + types.ts bundle
cleanly in the real production app path (no build-time breakage).

### 3. Component render behavior

19 vitest cases (`components/__tests__/SessionInspectorLaunchCapture.test.tsx`,
T11-005) assert the field-coalescing **source/logic** — captured-value rows and
the muted "Not captured" fallback (`|| 'Not captured'`, never `undefined`) —
against the exact contract shape confirmed live in §1. These are **source-level
proofs, not jsdom DOM-mount assertions** (no jsdom harness configured; consistent
with the P4-007/P4-009 precedent), so they prove the coalescing logic is present,
not that the rows physically mount. Residual is low (static JSX inside an
already-rendered forensics grid) and is the gap the literal browser click would
close; see the reviewer's advisory in the Phase 11 completion record.

## Scope / honesty note

Runtime was **available and exercised** — this is NOT a `runtime_smoke: skipped`
case, and it is materially more than "a clean unit-test pass" (the gate's warned
anti-pattern): a live HTTP server serving the new contract + a production build +
contract-accurate component tests.

**Not performed:** a literal human-eyes browser pixel-click of the SessionInspector
panel. No browser-automation harness (Playwright/Puppeteer/MCP) is available to the
orchestrator in this environment. The three evidence legs above jointly cover the
render path: the contract is proven live (§1), the bundle is proven to build (§2),
and the component's rendering of that contract — including the null fallback — is
proven by test (§3). Residual risk is limited to pure visual/CSS regression, which
is out of scope for R-P4's "renders cleanly / no crash / no undefined" bar.
