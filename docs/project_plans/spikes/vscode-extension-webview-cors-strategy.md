---
title: "SPIKE: VSCode Extension Webview Architecture & CORS Strategy"
type: "spike"
status: "draft"
created: "2026-04-02"
time_box: "2 days"
parent_prd: "docs/project_plans/PRDs/features/vscode-ccdash-extension-v1.md"
tags: ["spike", "webview", "cors", "vscode", "extension", "csp"]
---

# SPIKE: VSCode Extension Webview Architecture & CORS Strategy

## Problem Statement

The VSCode CCDash extension needs to render rich UI (session lists, charts, detail views) inside VSCode webview panels. Webviews run in a sandboxed iframe with strict CSP and an opaque `vscode-webview://` origin, making direct `fetch()` to `localhost:8000` non-trivial. This spike determines the correct data-fetching architecture and build pipeline for the webview UI.

## Research Questions

### RQ1: Webview CORS behavior

- What origin does a VSCode webview report? (`vscode-webview://<id>`)
- Can `fetch("http://localhost:8000/api/sessions")` succeed from a webview?
- Does the browser security model inside Electron/VSCode block mixed-origin requests?
- What CORS headers would the FastAPI backend need to set if direct fetch is viable?

### RQ2: CSP configuration for React + Chart.js

- What is the default CSP for VSCode webviews?
- What directives are needed for: inline scripts (React), canvas (Chart.js), styles (Tailwind)?
- Can `nonce`-based script loading work with Vite-bundled output?
- What is the minimal CSP that allows React + a charting library without `unsafe-inline`?

### RQ3: API proxy strategy -- extension host vs backend CORS

**Option A: Extension host proxy**
- Extension host fetches from `localhost:8000`, forwards data to webview via `postMessage`
- Avoids CORS entirely; webview never makes network requests
- Extension host acts as a typed API client

**Option B: Backend CORS update**
- Add `vscode-webview://*` to FastAPI CORS allowed origins
- Webview fetches directly from backend
- Simpler webview code, but couples backend config to extension

Which approach is more maintainable? What are the security implications of each?

### RQ4: Shared design tokens with CCDash frontend

- Can Tailwind config (colors, spacing, border-radius) be extracted to a shared JSON/CSS file?
- Is it practical to share CSS custom properties between the web app and webview-ui?
- What level of visual consistency is achievable without full component sharing?
- Should the webview use the same Tailwind preset or a minimal subset?

### RQ5: webview-ui build tooling

- Vite is the natural choice (matches CCDash frontend tooling)
- How does Vite output integrate with `webview.html` and the `asWebviewUri` API?
- Can the build produce a single JS bundle + single CSS file for simplest webview loading?
- What is the recommended project structure (`webview-ui/` alongside `src/extension/`)?

### RQ6: postMessage API performance and patterns

- What is the latency of `postMessage` between extension host and webview?
- Is it fast enough for paginated data (hundreds of sessions)?
- What serialization overhead exists for large payloads (session detail with tool calls)?
- What message protocol pattern works best (request/response with correlation IDs)?

## Scope

### In Scope

- CORS behavior testing in a real VSCode webview
- CSP configuration for React + charting
- Proxy architecture decision (extension host vs direct fetch)
- Build pipeline recommendation for webview-ui
- Design token sharing feasibility assessment
- postMessage performance characterization

### Out of Scope

- Full webview UI implementation (beyond proof-of-concept session list)
- Component library extraction or `@miethe/ui` integration
- Authentication (CCDash is local-first)
- WebSocket or real-time streaming in webviews

## Approach

1. Create minimal VSCode extension with a webview panel
2. Attempt direct `fetch()` to CCDash backend, document CORS behavior
3. Implement extension host proxy pattern, measure postMessage round-trip
4. Configure CSP for React rendering with Vite-bundled output
5. Add a simple Chart.js canvas, verify CSP allows it
6. Extract CCDash Tailwind color tokens to shared JSON, apply in webview
7. Document findings and make recommendations

## Expected Outputs

- CORS strategy recommendation (proxy vs backend update) with trade-off analysis
- Minimal CSP configuration for React + charting in VSCode webviews
- webview-ui build pipeline recommendation (tooling, structure, output format)
- Shared design token extraction strategy (feasibility and approach)
- Proof-of-concept: webview displaying a session list from CCDash API

## Success Criteria

- A VSCode webview displays a list of CCDash sessions fetched from the backend API without CORS errors
- CSP configuration documented that allows React rendering and canvas-based charts
- Proxy vs direct-fetch decision made with at least 3 comparison dimensions
- Build pipeline produces a working webview from a Vite project

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| VSCode CSP blocks all useful patterns | High | Low | Test incrementally, start with most permissive viable CSP |
| postMessage latency too high for large payloads | Medium | Low | Benchmark early, paginate if needed |
| Vite output incompatible with webview loading | Medium | Low | Review existing VSCode+Vite examples (day 1) |
| Design token drift between web app and extension | Low | High | Automate extraction in build step, accept minor drift |

## Time Box

2 days. If CORS testing is not resolved by end of day 1, default to extension host proxy and document direct-fetch as follow-up.
