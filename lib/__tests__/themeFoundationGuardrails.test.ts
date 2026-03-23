import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));

const GUARDED_SHARED_FILES = [
  'components/ui/surface.tsx',
  'components/ui/button.tsx',
  'components/ui/input.tsx',
  'components/ui/select.tsx',
  'components/ui/badge.tsx',
  'components/Layout.tsx',
  'components/Dashboard.tsx',
  'components/Analytics/AnalyticsDashboard.tsx',
  'components/Analytics/TrendChart.tsx',
  'components/content/UnifiedContentViewer.tsx',
  'components/featureStatus.ts',
  'lib/chartTheme.ts',
] as const;

const CHART_ADAPTER_FILES = [
  'components/Analytics/AnalyticsDashboard.tsx',
  'components/Analytics/TrendChart.tsx',
] as const;

const ROOT_THEME_BOOTSTRAP_FILES = [
  'index.html',
  'index.tsx',
] as const;

const REQUIRED_MODE_TOKENS = [
  '--app-background',
  '--panel',
  '--panel-border',
  '--sidebar',
  '--surface-muted',
  '--surface-overlay',
  '--chart-grid',
  '--chart-axis',
  '--chart-tooltip',
  '--scrollbar-thumb',
  '--viewer-shell',
  '--viewer-inner-surface',
  '--markdown-link',
  '--markdown-table-head',
] as const;

const DISALLOWED_SHARED_THEME_LITERALS =
  /\b(?:bg|text|border|ring|from|to|via|stroke|fill)-(?:slate|indigo|emerald|amber|rose|sky)-[A-Za-z0-9_./%\[\]-]+/g;

const readSource = (relativePath: string): string => readFileSync(resolve(root, relativePath), 'utf-8');

describe('theme foundation guardrails', () => {
  it('keeps guarded shared files free from raw palette utility regressions', () => {
    const regressions = GUARDED_SHARED_FILES.flatMap((relativePath) => {
      const matches = readSource(relativePath).match(DISALLOWED_SHARED_THEME_LITERALS) ?? [];
      return matches.map((match) => `${relativePath}: ${match}`);
    });

    expect(regressions).toEqual([]);
  });

  it('keeps shared analytics surfaces on the centralized chart adapter', () => {
    for (const relativePath of CHART_ADAPTER_FILES) {
      const source = readSource(relativePath);

      expect(source).toContain('chartTheme');
      expect(source).toContain('getChartSeriesColor');
    }
  });

  it('keeps theme bootstrap free from hard-forced dark mode', () => {
    const htmlSource = readSource(ROOT_THEME_BOOTSTRAP_FILES[0]);
    const entrySource = readSource(ROOT_THEME_BOOTSTRAP_FILES[1]);

    expect(htmlSource).toContain('ccdash:theme-mode:v1');
    expect(htmlSource).toContain('prefers-color-scheme: dark');
    expect(entrySource).not.toContain("classList.add('dark')");
    expect(entrySource).not.toContain("body.classList.add('dark')");
  });

  it('keeps shared theme tokens complete across light and dark mode blocks', () => {
    const cssSource = readSource('src/index.css');

    expect(cssSource).toContain('html {');
    expect(cssSource).toContain('color-scheme: light;');
    expect(cssSource).toContain('html.dark');
    expect(cssSource).toContain('color-scheme: dark;');

    const rootBlock = cssSource.match(/:root\s*\{([\s\S]*?)\n  \}/)?.[1] ?? '';
    const darkBlock = cssSource.match(/\.dark\s*\{([\s\S]*?)\n  \}/)?.[1] ?? '';

    expect(rootBlock).not.toBe('');
    expect(darkBlock).not.toBe('');

    for (const token of REQUIRED_MODE_TOKENS) {
      expect(rootBlock).toContain(token);
      expect(darkBlock).toContain(token);
    }
  });

  it('keeps the Settings theme control wired through the centralized theme provider', () => {
    const settingsSource = readSource('components/Settings.tsx');

    expect(settingsSource).toContain("useTheme");
    expect(settingsSource).toContain("value={preference}");
    expect(settingsSource).toContain("setPreference");
    expect(settingsSource).not.toContain('localStorage');
    expect(settingsSource).not.toContain("matchMedia('(prefers-color-scheme: dark)')");
  });

  it('keeps the settings light-mode compatibility bridge scoped to the settings surface', () => {
    const settingsSource = readSource('components/Settings.tsx');
    const cssSource = readSource('src/index.css');

    expect(settingsSource).toContain('settings-legacy-theme');
    expect(cssSource).toContain("html[data-theme='light'] .settings-legacy-theme");
  });
});
