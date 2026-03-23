# Theme Modes Developer Reference

Last updated: 2026-03-22

This reference documents the runtime contract behind CCDash standard theme modes and the rollout constraints that future theme work should preserve.

## Delivered modes

CCDash now supports three user-facing theme preferences:

- `dark`
- `light`
- `system`

At runtime, `system` resolves to either `dark` or `light`.

## Primary files

- `index.html`
- `App.tsx`
- `contexts/ThemeContext.tsx`
- `lib/themeMode.ts`
- `components/Settings.tsx`
- `src/index.css`
- `lib/__tests__/themeMode.test.ts`
- `lib/__tests__/themeFoundationGuardrails.test.ts`

## Runtime contract

### Storage

- storage key: `ccdash:theme-mode:v1`
- stored values: `dark`, `light`, `system`
- invalid or missing values fall back to `system`

### Root document state

The resolved mode is reflected on `document.documentElement` through:

- the `dark` class when the resolved mode is `dark`
- `data-theme`
- `data-theme-preference`
- `style.colorScheme`

These attributes are the stable contract for future theme-aware integrations and diagnostics.

### First-paint behavior

`index.html` performs the first theme resolution before React mounts. Keep that bootstrap aligned with `lib/themeMode.ts`.

If the runtime contract changes, update both places together.

## React integration

`ThemeProvider` owns the app-level theme state and exposes:

- `preference`
- `resolvedTheme`
- `setPreference`

Theme orchestration should stay centralized there.

Do not add page-local theme storage, direct `matchMedia` reads, or ad hoc root-class mutation in feature components.

## Settings integration

`components/Settings.tsx` is the user-facing control surface for theme changes.

Current behavior:

- the Theme selector writes through `ThemeContext`
- the selector is controlled from the active runtime state
- a small debug readout shows both saved preference and resolved mode for QA

## Styling guidance

Shared surfaces should continue to use semantic tokens and token-backed primitives.

Examples:

- `components/ui/surface.tsx`
- `components/ui/button.tsx`
- `components/ui/input.tsx`
- `components/ui/select.tsx`
- `lib/chartTheme.ts`

## Settings compatibility bridge

Some Settings subsections still contain older palette-literal utility classes.

To keep the route usable in light mode without blocking the rollout, `src/index.css` includes a scoped `.settings-legacy-theme` compatibility bridge that remaps those legacy classes onto semantic tokens only for the Settings surface in light mode.

Treat that bridge as rollout debt, not as the long-term pattern for new code.

## Regression coverage

Current theme regression coverage protects:

- theme preference parsing and DOM application in `lib/__tests__/themeMode.test.ts`
- first-paint bootstrap expectations
- required light/dark token presence
- shared chart adapter usage
- Settings selector wiring and compatibility bridge presence

When adding future theme work, prefer extending these guardrails over adding one-off checks.

## Follow-on work

The next theming phase can build on this contract to add user-defined or preset themes.

That work should:

- preserve the existing root runtime contract
- keep standard mode persistence and system resolution intact
- continue separating data-driven accent systems from the base app theme

## Related docs

- `docs/theme-modes-user-guide.md`
- `docs/project_plans/PRDs/refactors/ccdash-theme-system-modernization-v1.md`
- `docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md`
