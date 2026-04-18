---
name: @miethe/ui test environment
description: Use @testing-library/react for @miethe/ui tests; react-dom/server.browser.js breaks in jsdom
type: feedback
---

Do not use `renderToStaticMarkup` from `react-dom/server` in @miethe/ui tests.

**Why:** Next.js + Jest resolves `react-dom/server` to the browser bundle (`react-dom-server.browser.development.js`), which requires `MessageChannel` — unavailable in Node.js jsdom. Every test suite using it fails to run with `ReferenceError: MessageChannel is not defined`.

**How to apply:** Use `@testing-library/react`'s `render()` + `screen` + `container.querySelector()` / `container.innerHTML` instead. This works cleanly in the jsdom environment configured by `jest.config.js` in `skillmeat/web/`.
