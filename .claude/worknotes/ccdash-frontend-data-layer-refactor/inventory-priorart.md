# Prior Art & Conventions Inventory — TanStack Query Migration

> Read-only inventory feeding the CCDash frontend data-layer refactor PRD + implementation plan.
> Source: Explore pass (2026-05-28). Written by orchestrator (agent write blocked by bg-isolation guard).

## 1. Prior data-loading redesign (Feature Surface) — partial prior art

`docs/guides/feature-surface-architecture.md` documents a fully-shipped two-tier hand-rolled cache across `services/featureSurfaceCache.ts` + `services/featureSurfaceFlag.ts`:

- **List tier** (`useFeatureSurface`): 50-entry LRU keyed by `projectId|normalizedQuery|page`, no TTL, invalidates on write events. (`feature-surface-architecture.md:65`)
- **Rollup tier**: 100-entry LRU keyed by `projectId|sortedIds|fields|freshnessToken`, 30s TTL with `isStale()` predicate. (`:66-67`)
- **Modal tier** (`useFeatureModalData`): 120-entry LRU keyed by `featureId|section|paramsHash`, no TTL, lazy per-tab. (`:111`)
- **Cross-cache invalidation bus** (`services/featureCacheBus.ts`): `publishFeatureWriteEvent` fans out deterministically. (`:129-139`)
- **Flag gate**: `CCDASH_FEATURE_SURFACE_V2_ENABLED` (backend env, default `true`); read via `/api/health` → `services/featureSurfaceFlag.ts:36-52`, NOT a `VITE_` var.

**TQ mapping**: list+rollup SWR mechanics, key-based invalidation, stale detection = TQ `queryKey` + `staleTime` + `invalidateQueries`. Modal lazy-load = `enabled: false` queries activated on tab click. featureCacheBus pub/sub = `queryClient.invalidateQueries`. Two-tier LRU → REPLACED by TQ in-process cache. The flag-gate convention (runtime health, not build-time VITE) SHOULD be replicated for the TQ migration flag.

## 2. Planning browser cache (hand-rolled SWR + LRU) — primary replacement target

`services/planning.ts`:
- Three module-scope `Map` stores: `PLANNING_BROWSER_CACHE` (project × freshness bucket × payload type), `PLANNING_FEATURE_CONTEXT_CACHE` (24 entries), `PLANNING_SESSION_BOARD_CACHE` (16 entries). (`:76-78`)
- Limits: 8 projects, 3 freshness keys/project, 3 payload types/freshness. (`:68-74`)
- `cacheProjectPlanningSummary` (`:231`): returns stale immediately, spawns background revalidation, fires `onRevalidated` callback — textbook SWR.
- Coarse invalidation `clearPlanningBrowserCache(projectId)` (`:289`), subscribed to `featureCacheBus` at module scope (`:315-318`).
- LRU eviction via `touchMapKey`/`trimMapToLimit` (`:137-150`).

Feature guide `.claude/worknotes/ccdash-planning-reskin-v2-interaction-performance-addendum/feature-guide.md`: "active-first cached loading", warm render < 250ms, cold p95 < 2s. Detail payloads demand-loaded only.

**TQ relevance**: entire module = manual `useQuery` + `staleTime` + background refetch + `invalidateQueries`. Primary replacement candidate. **Design attention needed**: the freshness-bucket keying (backend `dataFreshness` field) has no direct TQ analogue — fold into queryKey or use `staleTime`+manual invalidation.

## 3. Frontend test conventions — guardrail precedents to extend

Test locations: `components/__tests__/`, `components/{Planning,FeatureModal,Workflows}/__tests__/`, `components/Planning/primitives/__tests__/`, `contexts/__tests__/`, `lib/__tests__/`, `services/__tests__/`.

**Architecture guardrail pattern (KEY precedent — source-reading assertions):**
- `contexts/__tests__/dataArchitecture.test.ts:10-30` — reads source, asserts `DataContext` is a composition facade with no `createContext()`/`fetch()`. Extensible to "no raw fetch inside TQ query fns" / "no useQuery outside designated hooks".
- `components/__tests__/ProjectBoardEagerLoop.test.tsx:266-297` (P3-004) — reads `ProjectBoard.tsx` source, asserts banned symbols absent + required imports present. Copy verbatim to enforce "no hand-rolled LRU after migration".
- `components/__tests__/FeatureSurfaceRegressionMatrix.test.tsx:537-590` (P5-004) — multi-component matrix: source-read + static-render + fetch-spy. Model for a cross-component "no hand-rolled fetch" gate.
- `services/__tests__/featureSurfaceDecoupling.test.ts:144` (G1-001) — behavioral guardrail: verifies v2 path calls bounded endpoint + invalidation re-fetches via correct fn.

**Test command**: `npm run test` → `vitest run`.

## 4. Build/bundle setup + Next.js migration coupling

- **`@/` alias**: `vite.config.ts:89-91` → repo root. Maps cleanly to Next `tsconfig paths` — no change needed.
- **`/api` proxy**: `vite.config.ts:54-59` → `http://127.0.0.1:8000` (or `CCDASH_API_PROXY_TARGET`). Next equivalent = `rewrites` in `next.config.ts`.
- **Router**: `HashRouter` from react-router-dom across **~30 files** (`App.tsx:2,65,105`). **SSR-hostile**: `contexts/AppRuntimeContext.tsx:43` reads `window.location.hash` at MODULE scope. Next App Router migration requires replacing HashRouter with `useRouter`/`Link` across ~30 files + converting module-scope `window.location.hash` reads to server-safe equivalents. **This is the primary SSR blocker.**
- **Lazy routes**: `App.tsx:11-44` — all top-level routes `React.lazy()` via `lazyNamed`. Already code-split; compatible with Next dynamic imports.
- **Other SSR-hostile**: `ModelColorsContext.tsx:44,59`, `ThemeContext.tsx:21-47` already guard with `typeof window === 'undefined'`. `AuthSessionContext.tsx:192-193` uses `window.location.assign` inside a callback (safe).
- **Tailwind**: v3.4.17 (`package.json:79`, `tailwind.config.js:1`).

## 5. Feature flags (frontend) — convention to follow

VITE flags read via `readBoolEnv(import.meta.env.VITE_CCDASH_*)` at CALL time (not module scope):

| Flag | Default | Location |
|---|---|---|
| `VITE_CCDASH_MEMORY_GUARD_ENABLED` | true | `lib/featureFlags.ts:23` |
| `VITE_CCDASH_LIVE_EXECUTION_ENABLED` | true | `services/live/config.ts:10` |
| `VITE_CCDASH_LIVE_SESSIONS_ENABLED` | true | `services/live/config.ts:14` |
| `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED` | false | `services/live/config.ts:18` |
| `VITE_CCDASH_LIVE_FEATURES_ENABLED` | false | `services/live/config.ts:22` |
| `VITE_CCDASH_API_BASE_URL` | /api | `vite.config.ts:64` |
| `CCDASH_FEATURE_SURFACE_V2_ENABLED` | true (backend→/api/health) | `services/featureSurfaceFlag.ts:36` |

**Convention for TQ migration flag**: prefer the `CCDASH_FEATURE_SURFACE_V2_ENABLED` pattern (backend env → `/api/health` → dedicated flag module with optimistic-true default) when per-deploy progressive rollout is wanted; a build-time `VITE_` var is acceptable for simpler dev-vs-prod gating.

## 6. Net guidance for the plan

- TWO hand-rolled SWR caches (feature surface + planning) already exist and BOTH should be replaced by TQ, not coexist. This is a consolidation, not a greenfield add.
- The source-reading guardrail test pattern is the enforcement mechanism for "no regression to hand-rolled caches" and "no eager-fetch-at-root".
- Next.js migration is gated behind the HashRouter→App Router conversion across ~30 files — large, distinct, sequence it last.
