---
doc_type: quick_feature_plan
slug: analytics-provider-views
status: completed
runtime_smoke: passed
tier: 1
branch: feat/analytics-provider-views
base_branch: main
created: 2026-07-31
---

# Analytics: model-provider views + interactive chart pattern

## Request

1. Analytics page → Models + Tools: add a **model provider** graph view.
2. Start making graphs/tables **interactive** (switch views/comparisons) rather than static —
   beginning with token usage per provider, per-model usage.
3. Surface provider detail in the **Session Transcript** analytics tab and the
   **/planning/feature/{slug}** analytics tab.
4. Defer the app-wide graph restyle + analytics standardization as ITT nodes.

## Grounding finding (load-bearing — do not design around the original assumption)

The literal ask was "provider (ie subscription vs ICA)". **That split is not derivable from any
data CCDash holds today.** Verified against the live node PG (`10.42.10.76:5440`, 17,292 sessions)
and the raw JSONL corpus:

| Signal | State |
|---|---|
| `launcher` | **0 / 17,292** populated |
| `model_variant` | **0 / 17,292** |
| `profile`, `effort_tier` | **0 / 17,292** |
| `context_window` | **0 / 17,292** |
| `[1m]` suffix in JSONL `"model"` field | **never present** (0 occurrences) |
| JSONL gateway/auth discriminator | none — `userType:external` and `service_tier:standard` are uniform |
| `platform_type` | **17,292 / 17,292** — `Claude Code` 13,884 / `Codex` 3,408 |
| `model` / `model_slug` | 17,051 / 17,292 |

The launch-capture hook (`scripts/hooks/ccdash_capture_session_start.py`) exists and would capture
`CCDASH_LAUNCHER`, but nothing exports those env vars, so the sidecar is never written.

**Therefore provider is modelled as three orthogonal axes**, only two of which have data today:

- `providerVendor` — Anthropic / OpenAI / Google / Unknown (from model slug) — **live**
- `providerSurface` — Claude Code / Codex (from `platform_type`) — **live**
- `providerChannel` — subscription / ica / api / **unknown** (from `launcher`/`model_variant`) —
  **structurally wired, resolves to `unknown` for 100% of rows until capture is activated**

`providerChannel` is built now so the ICA split lights up with zero further FE/BE work the moment
capture lands. It is never faked or inferred.

## Constraints

- **Do not change the existing `modelProvider` semantics** in `backend/model_identity.py`
  (`_provider_label` → "Claude"/"OpenAI"/"Gemini"). It is consumed by session badges, `/api/sessions`,
  features, and analytics correlation. Provider identity is **additive**.
- Single derivation path per the `routing_rollup.apply_provider` docstring — one backend helper,
  one FE mirror, with a parity test.
- Codex sessions report **0 tokens** across the board — provider charts must render a real
  zero-token state for OpenAI, not hide the surface.

## Tasks

| ID | Task | Owner | Files |
|---|---|---|---|
| T-001 | `derive_provider_identity()` + tests | backend | `backend/model_identity.py`, `backend/tests/test_provider_identity.py` |
| T-002 | `provider` dimension on `/analytics/breakdown` + `/analytics/series`; `tokenUsage.byProvider` on `/analytics/artifacts` | backend | `backend/routers/analytics.py` |
| T-003 | FE provider util mirroring backend + parity test | frontend | `lib/providerIdentity.ts`, `lib/__tests__/providerIdentity.test.ts` |
| T-004 | Reusable interactive chart primitive (dimension × metric × chart-type switchers, URL-persisted, `aria-pressed`) | frontend | `components/Analytics/primitives/` |
| T-005 | Wire Models + Tools tab to the primitive + provider view | frontend | `components/Analytics/AnalyticsDashboard.tsx` |
| T-006 | Provider breakdown in Session Inspector analytics tab | frontend | `components/SessionInspector.tsx` |
| T-007 | Provider breakdown in feature analytics panel | frontend | `components/Planning/FeatureAnalyticsPanel.tsx` |
| T-008 | Deferred ITT nodes | orchestrator | — |

Waves: **W1** = T-001, T-002, T-003, T-004 · **W2** = T-005, T-006, T-007 · **W3** = gates, T-008.

## Runtime smoke — defects found and fixed

Unit tests could not catch any of these: recharts does not paint SVG under jsdom, so all three
were found only by driving the real app in a browser. Recorded because the same class of bug will
recur when the deferred app-wide rollout happens.

| # | Defect | Root cause | Fix |
|---|---|---|---|
| 1 | Pie chart rendered blank | recharts 3.x `<Pie>` renders **zero** `recharts-sector` paths for ~500–600ms after mount (unlike `<Bar>`, whose rects exist from frame 1) | `isAnimationActive={false}` on `<Pie>` (and defensively on `<Bar>`) |
| 2 | Horizontal bar drew axes but no bars, then **blanked the whole page** | `key={chartTypeId}` on `ResponsiveContainer` remounts its ResizeObserver mid-commit, driving recharts' internal layout store into an infinite `setState` loop | moved the remount key to the **wrapper div**; `ResponsiveContainer` is never keyed |
| 3 | `/planning/feature/{slug}?tab=analytics` looped and never rendered | Any route deriving its own state from `searchParams` each render (no local buffer) re-renders when a descendant writes params; that cascade retriggers the same recharts-internal loop. Affects `FeatureDetailShell` and `SessionInspector`; `AnalyticsDashboard` is safe because it buffers its tab in `useState` | `persistToUrl` is now **opt-in, default `false`**; only `AnalyticsDashboard` opts in (verified in-browser). Initial read from the URL still happens everywhere — a `useState` initializer never writes params, so shared links keep working |

Verified in-browser after the fixes: Models + Tools (bar/horizontal/pie + all switchers + URL
persistence), Session Inspector (Model Allocation + Provider Detail), feature analytics panel
(Provider Usage + Tokens by Provider).

## Verification

- Backend provider aggregation run against the **live node PG** (17,292 sessions) → 7 providers,
  correctly derived: Anthropic·Claude Code 13,457 / OpenAI·Codex 3,359 (0 tokens, truthful) /
  Unknown·Claude Code 426 / Google·Claude Code 8 / OpenAI·Claude Code 1. Every channel `unknown`.
- `GET /api/analytics/breakdown?dimension=provider` verified end-to-end on seeded data.
- `GET /api/analytics/artifacts` → `tokenUsage.byProvider` verified present and populated.
- Gates: tsc 34 (= pre-existing baseline, none in changed files); existing vitest suite
  **exactly** at baseline 15 files / 49 tests / 2293 total (zero regressions); 60 new FE tests pass;
  39 new backend tests pass; production build clean.

## Deferred (ITT nodes)

1. **App-wide interactive chart system** — roll the primitive to every chart (Dashboard,
   SessionInspector, Planning, TestVisualizer, research/artifacts tabs).
2. **Analytics logic + UI standardization** — shared `AnalyticsTable` primitive (Models+Tools
   copy-pastes the same table markup 6×), unify the two coexisting segmented-control idioms,
   consolidate the 4 duplicate `_aggregate_token_usage_by_model` implementations, retire the
   hardcoded `opus|sonnet|haiku|other` bucket that silently dumps Codex/Gemini/Fable into `other`.
3. **Launch-time capture activation** — the actual unlock for subscription-vs-ICA.
