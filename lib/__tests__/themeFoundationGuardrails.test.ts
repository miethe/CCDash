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
});
