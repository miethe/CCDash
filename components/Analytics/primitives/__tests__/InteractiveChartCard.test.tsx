/**
 * InteractiveChartCard tests — dimension/metric/chart-type switching (driven
 * by URL search params via a real `<MemoryRouter>`, no mocking needed since
 * `useSearchParams` from react-router-dom works against an in-memory history
 * under SSR) and the empty-state contract for all-zero series.
 *
 * recharts' `ResponsiveContainer` renders as an empty zero-dimension
 * container (no throw) under vitest's default node environment — see
 * `components/Analytics/__tests__/AnalyticsDashboardResearchResilience.test.tsx`
 * L17-22. We therefore assert on controls and resolved data, never on
 * rendered SVG geometry.
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import {
  InteractiveChartCard,
  type ChartAxisOption,
  type ChartTypeOption,
  type InteractiveChartCardProps,
  type InteractiveChartDatum,
} from '../InteractiveChartCard';

const DIMENSIONS: ChartAxisOption[] = [
  { id: 'provider', label: 'Provider' },
  { id: 'model', label: 'Model' },
];
const METRICS: ChartAxisOption[] = [
  { id: 'tokens', label: 'Tokens' },
  { id: 'cost', label: 'Cost' },
];
const CHART_TYPES: ChartTypeOption[] = [
  { id: 'bar', label: 'Bar' },
  { id: 'pie', label: 'Pie' },
];

type PartialProps = Partial<InteractiveChartCardProps> & {
  resolveData: (dimensionId: string | undefined, metricId: string | undefined) => InteractiveChartDatum[];
};

function renderCard(props: PartialProps, initialEntries: string[] = ['/']): string {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={initialEntries}>
      <InteractiveChartCard
        title="Token usage"
        paramPrefix="usage"
        dimensions={DIMENSIONS}
        metrics={METRICS}
        chartTypes={CHART_TYPES}
        {...props}
      />
    </MemoryRouter>,
  );
}

/** True when the button whose visible text contains `label` carries aria-pressed="true". */
function buttonIsActive(html: string, label: string): boolean {
  const matches = [...html.matchAll(/<button([^>]*)>([\s\S]*?)<\/button>/g)];
  const match = matches.find((m) => m[2].includes(label));
  if (!match) throw new Error(`No <button> found containing "${label}"`);
  return match[1].includes('aria-pressed="true"');
}

describe('InteractiveChartCard — dimension/metric selection drives resolveData', () => {
  it('defaults to the first dimension/metric option', () => {
    const resolveData = vi.fn((): InteractiveChartDatum[] => [{ key: 'a', label: 'Anthropic', value: 10 }]);
    renderCard({ resolveData });
    expect(resolveData).toHaveBeenCalledWith('provider', 'tokens');
  });

  it('honours a non-default selection carried in the URL', () => {
    const resolveData = vi.fn((): InteractiveChartDatum[] => [{ key: 'm1', label: 'Sonnet', value: 5 }]);
    renderCard({ resolveData }, ['/?usageDim=model&usageMetric=cost']);
    expect(resolveData).toHaveBeenCalledWith('model', 'cost');
  });

  it('ignores an unknown dimension id in the URL and falls back to the default', () => {
    const resolveData = vi.fn((): InteractiveChartDatum[] => []);
    renderCard({ resolveData }, ['/?usageDim=not-a-real-option']);
    expect(resolveData).toHaveBeenCalledWith('provider', 'tokens');
  });

  it('reflects the active dimension/metric in the rendered controls', () => {
    const html = renderCard(
      { resolveData: () => [{ key: 'x', label: 'X', value: 1 }] },
      ['/?usageDim=model&usageMetric=cost'],
    );
    expect(buttonIsActive(html, 'Model')).toBe(true);
    expect(buttonIsActive(html, 'Provider')).toBe(false);
    expect(buttonIsActive(html, 'Cost')).toBe(true);
    expect(buttonIsActive(html, 'Tokens')).toBe(false);
  });
});

describe('InteractiveChartCard — chart-type selection', () => {
  it('defaults to the first chart-type option', () => {
    const html = renderCard({ resolveData: () => [{ key: 'a', label: 'A', value: 1 }] });
    expect(buttonIsActive(html, 'Bar')).toBe(true);
    expect(buttonIsActive(html, 'Pie')).toBe(false);
  });

  it('selects the chart type carried in the URL', () => {
    const html = renderCard(
      { resolveData: () => [{ key: 'a', label: 'A', value: 1 }] },
      ['/?usageChart=pie'],
    );
    expect(buttonIsActive(html, 'Pie')).toBe(true);
    expect(buttonIsActive(html, 'Bar')).toBe(false);
  });
});

describe('InteractiveChartCard — optional axes', () => {
  it('omits switchers and resolves undefined ids when no axis options are supplied', () => {
    const resolveData = vi.fn((): InteractiveChartDatum[] => [{ key: 'x', label: 'X', value: 1 }]);
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/']}>
        <InteractiveChartCard title="Single-series" paramPrefix="solo" resolveData={resolveData} />
      </MemoryRouter>,
    );
    expect(resolveData).toHaveBeenCalledWith(undefined, undefined);
    expect(html).not.toContain('role="group"');
  });
});

describe('InteractiveChartCard — empty-state contract', () => {
  it('renders an explicit empty message for an empty series', () => {
    const html = renderCard({
      resolveData: () => [],
      emptyMessage: 'No token data recorded yet.',
    });
    expect(html).toContain('No token data recorded yet.');
    expect(html).toContain('interactive-chart-empty-state');
  });

  it('renders the empty message when every series value is zero (Codex/OpenAI 0-token sessions)', () => {
    const html = renderCard({
      resolveData: () => [
        { key: 'openai', label: 'OpenAI', value: 0 },
        { key: 'anthropic', label: 'Anthropic', value: 0 },
      ],
      emptyMessage: 'No token data recorded yet.',
    });
    expect(html).toContain('No token data recorded yet.');
    expect(html).toContain('interactive-chart-empty-state');
  });

  it('renders the chart, not the empty state, once at least one value is non-zero', () => {
    const html = renderCard({
      resolveData: () => [
        { key: 'openai', label: 'OpenAI', value: 0 },
        { key: 'anthropic', label: 'Anthropic', value: 42 },
      ],
      emptyMessage: 'No token data recorded yet.',
    });
    expect(html).not.toContain('No token data recorded yet.');
    expect(html).not.toContain('interactive-chart-empty-state');
  });
});
