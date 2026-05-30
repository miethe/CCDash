# Auth Runtime Resilience — backend-unavailable must not show hosted sign-in wall

## Symptom
In local mode, the planning page (and any page) renders the "Hosted CCDash requires an
active browser session" sign-in wall plus a `500 (Internal Server Error)` console entry.

## Root cause (cross-layer, frontend)
The sign-in wall and the 500 are the **same** failure: the auth-session fetch failed
(backend down / unreachable / 5xx via the Vite dev proxy), not an auth misconfiguration.

Chain:
1. `AuthSessionContext.refreshSession()` does `Promise.all([getAuthMetadata(), getAuthSession()])`
   (`contexts/AuthSessionContext.tsx`). One rejection discards BOTH results.
2. `deriveAuthSessionStatus(null, error)` collapses any non-auth error (incl. 5xx / network)
   into `'unauthenticated'` — because `classifyAuthErrorStatus` returns `null` for anything
   other than 401/403 (`services/apiClient.ts`).
3. `isLocalRuntimeAuth(auth)` reads `session?.localMode || metadata?.localMode`; both null → false.
4. `Layout.tsx` gate `!canUseRuntimeWithoutHostedLogin && (unauthenticated || unauthorized)` fires.

Verified: a healthy `local` runtime returns 200 for `/api/auth/metadata`, `/api/auth/session`,
and `/api/agent/planning/command-center` with `localMode: true`. Symptom is NOT reproducible
with a live local backend. Port 8000 was down during the report.

## Fix contract
A local- or bearer-capable runtime must never fall into the hosted sign-in wall due to a
transient / 5xx / unreachable-backend error. Backend-unavailable degrades to a "backend
unavailable / retry" affordance, not a sign-in prompt. The sign-in wall requires a
**definitive** 401/403 classification from a reachable backend.

- Add `'unavailable'` to `AuthSessionStatus`.
- `deriveAuthSessionStatus`: 401→unauthenticated, 403→unauthorized, any other error→`'unavailable'`,
  authenticated session→authenticated, else→unauthenticated.
- `refreshSession`: `Promise.allSettled`; retain metadata on session failure (preserve last-known
  `localMode`); session result is authoritative for status.
- `Layout.tsx`: sign-in wall only on `unauthenticated || unauthorized`; `unavailable` (when runtime
  is not known-local) shows a Retry shell; known-local falls through to the app's existing
  "Backend disconnected — live updates paused" banner.

## Out of scope (follow-up)
`package.json` `dev:backend` runs `--runtime api`, which cannot boot with local storage
(raises in `backend/runtime/storage_contract.py`). Standalone `dev:backend` therefore leaves
the backend down. Tracked separately; not changed here.
