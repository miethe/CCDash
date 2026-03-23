# Theme Modes User Guide

Last updated: 2026-03-22

This guide explains how the standard CCDash theme modes work and what to expect from `dark`, `light`, and `system`.

## Where to change the theme

Open `Settings` and go to `General`.

Use the `Theme` selector to choose:

- `Dark`: always use the dark theme
- `Light`: always use the light theme
- `System`: follow your browser and operating system color preference

Your choice is saved locally in the browser and reused the next time CCDash opens.

## How `system` works

`System` does not pick a separate CCDash palette.

Instead, CCDash checks the current browser `prefers-color-scheme` value and resolves to either:

- `dark`
- `light`

If your operating system theme changes while CCDash is open and your preference is `system`, CCDash updates automatically.

## What changes with the theme

The standard theme modes now apply to the main shared product surfaces, including:

- app shell and navigation
- dashboard panels and shared cards
- analytics charts and chart tooltips
- content viewer and markdown/document previews
- Settings route, including the new theme selector

Model color overrides and other data-driven accent systems still behave independently from the base app theme.

## Persistence and first paint

CCDash applies the saved or system-resolved theme before the app fully renders, which reduces flashes of the wrong mode during startup.

That means:

- the correct mode should appear immediately on load
- browser-controlled surfaces such as scrollbars follow the active theme
- switching themes in Settings should update the app immediately

## Troubleshooting

1. If the app is not following your OS theme, confirm the Theme selector is set to `System`.
2. If a previous preference seems stuck, change the selector once and reload the page.
3. If one Settings subsection still looks less polished than shared surfaces in light mode, that is expected for some legacy controls while the remaining settings UI is migrated to the semantic token system.

## Related docs

- `README.md`
- `docs/theme-modes-developer-reference.md`
- `docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md`
