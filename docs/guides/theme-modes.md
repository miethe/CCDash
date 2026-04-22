# Theme Modes Guide

Theme selection behavior, runtime contract, and implementation guidance for CCDash theme modes.

> Consolidated from the former top-level user and developer docs. `docs/project_plans/` content was intentionally left untouched.

## User Guide

Last updated: 2026-03-22

This guide explains how the standard CCDash theme modes work and what to expect from `dark`, `light`, and `system`.

### Where to change the theme

Open `Settings` and go to `General`.

Use the `Theme` selector to choose:

- `Dark`: always use the dark theme
- `Light`: always use the light theme
- `System`: follow your browser and operating system color preference

Your choice is saved locally in the browser and reused the next time CCDash opens.

### How `system` works

`System` does not pick a separate CCDash palette.

Instead, CCDash checks the current browser `prefers-color-scheme` value and resolves to either:

- `dark`
- `light`

If your operating system theme changes while CCDash is open and your preference is `system`, CCDash updates automatically.

### What changes with the theme

The standard theme modes now apply to the main shared product surfaces, including:

- app shell and navigation
- dashboard panels and shared cards
- analytics charts and chart tooltips
- content viewer and markdown/document previews
- Settings route, including the new theme selector

Model color overrides and other data-driven accent systems still behave independently from the base app theme.

### Persistence and first paint

CCDash applies the saved or system-resolved theme before the app fully renders, which reduces flashes of the wrong mode during startup.

That means:

- the correct mode should appear immediately on load
- browser-controlled surfaces such as scrollbars follow the active theme
- switching themes in Settings should update the app immediately

### Troubleshooting

1. If the app is not following your OS theme, confirm the Theme selector is set to `System`.
2. If a previous preference seems stuck, change the selector once and reload the page.
3. If one Settings subsection still looks less polished than shared surfaces in light mode, that is expected for some legacy controls while the remaining settings UI is migrated to the semantic token system.

### Related docs

- `README.md`
- `docs/guides/theme-modes.md`
- `docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md`

## Developer Reference

Last updated: 2026-03-22

This reference documents the runtime contract behind CCDash standard theme modes and the rollout constraints that future theme work should preserve.

### Delivered modes

CCDash now supports three user-facing theme preferences:

- `dark`
- `light`
- `system`

At runtime, `system` resolves to either `dark` or `light`.

### Primary files

- `index.html`
- `App.tsx`
- `contexts/ThemeContext.tsx`
- `lib/themeMode.ts`
- `components/Settings.tsx`
- `src/index.css`
- `lib/__tests__/themeMode.test.ts`
- `lib/__tests__/themeFoundationGuardrails.test.ts`

### Runtime contract

#### Storage

- storage key: `ccdash:theme-mode:v1`
- stored values: `dark`, `light`, `system`
- invalid or missing values fall back to `system`

#### Root document state

The resolved mode is reflected on `document.documentElement` through:

- the `dark` class when the resolved mode is `dark`
- `data-theme`
- `data-theme-preference`
- `style.colorScheme`

These attributes are the stable contract for future theme-aware integrations and diagnostics.

#### First-paint behavior

`index.html` performs the first theme resolution before React mounts. Keep that bootstrap aligned with `lib/themeMode.ts`.

If the runtime contract changes, update both places together.

### React integration

`ThemeProvider` owns the app-level theme state and exposes:

- `preference`
- `resolvedTheme`
- `setPreference`

Theme orchestration should stay centralized there.

Do not add page-local theme storage, direct `matchMedia` reads, or ad hoc root-class mutation in feature components.

### Settings integration

`components/Settings.tsx` is the user-facing control surface for theme changes.

Current behavior:

- the Theme selector writes through `ThemeContext`
- the selector is controlled from the active runtime state
- a small debug readout shows both saved preference and resolved mode for QA

### Styling guidance

Shared surfaces should continue to use semantic tokens and token-backed primitives.

Examples:

- `components/ui/surface.tsx`
- `components/ui/button.tsx`
- `components/ui/input.tsx`
- `components/ui/select.tsx`
- `lib/chartTheme.ts`

### Settings compatibility bridge

Some Settings subsections still contain older palette-literal utility classes.

To keep the route usable in light mode without blocking the rollout, `src/index.css` includes a scoped `.settings-legacy-theme` compatibility bridge that remaps those legacy classes onto semantic tokens only for the Settings surface in light mode.

Treat that bridge as rollout debt, not as the long-term pattern for new code.

### Regression coverage

Current theme regression coverage protects:

- theme preference parsing and DOM application in `lib/__tests__/themeMode.test.ts`
- first-paint bootstrap expectations
- required light/dark token presence
- shared chart adapter usage
- Settings selector wiring and compatibility bridge presence

When adding future theme work, prefer extending these guardrails over adding one-off checks.

### Follow-on work

The next theming phase can build on this contract to add user-defined or preset themes.

That work should:

- preserve the existing root runtime contract
- keep standard mode persistence and system resolution intact
- continue separating data-driven accent systems from the base app theme

### Related docs

- `docs/guides/theme-modes.md`
- `docs/project_plans/PRDs/refactors/ccdash-theme-system-modernization-v1.md`
- `docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md`
