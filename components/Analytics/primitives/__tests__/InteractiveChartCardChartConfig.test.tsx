/**
 * Structural prop assertions for InteractiveChartCard's three chart-type
 * branches — added after a real-Chromium browser-smoke bug hunt found two
 * rendering defects that pure DOM/HTML-string assertions (see
 * InteractiveChartCard.test.tsx) could not have caught:
 *
 *  - Defect 2 (pie renders blank): root cause was recharts 3.x's `<Pie>`
 *    entrance animation, which renders zero `<path class="recharts-sector">`
 *    elements for ~500-600ms after every mount (confirmed via a puppeteer
 *    harness timing sweep — sectors were absent at t+400ms, present at
 *    t+~550ms). Fixed with `isAnimationActive={false}` on `<Pie>`.
 *  - Defect 3 (horizontalBar renders no bars) could not be reproduced in
 *    isolation, but the most plausible mechanism in the real (polling-heavy)
 *    app is the same class of bug: an in-flight recharts entrance animation
 *    getting interrupted mid-transition by an unrelated parent re-render.
 *    `isAnimationActive={false}` was defensively added to `<Bar>` too.
 *
 * `ResponsiveContainer` renders as an empty zero-dimension container under
 * vitest's default node environment (no real layout measurement — see
 * AnalyticsDashboardResearchResilience.test.tsx L17-22), so recharts never
 * actually paints its internal SVG here and DOM-string assertions cannot see
 * `layout`/`type`/`dataKey` (they're React props consumed internally by
 * recharts, not passed through as literal DOM attributes). To meaningfully
 * assert on them, this file mocks the `recharts` module with prop-recording
 * stubs and inspects exactly what InteractiveChartCard passes to `<BarChart>`,
 * `<XAxis>`, `<YAxis>`, `<CartesianGrid>`, `<Bar>`, and `<Pie>` — no real
 * chart geometry required.
 */
import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { capturedCalls } = vi.hoisted(() => {
  const calls: Array<{ component: string; props: Record<string, unknown> }> = [];
  return { capturedCalls: calls };
});

vi.mock('recharts', () => {
  const record =
    (component: string) =>
    (props: Record<string, unknown> & { children?: ReactNode }): ReactNode => {
      capturedCalls.push({ component, props });
      return props?.children ?? null;
    };
  return {
    Bar: record('Bar'),
    BarChart: record('BarChart'),
    CartesianGrid: record('CartesianGrid'),
    Cell: record('Cell'),
    Pie: record('Pie'),
    PieChart: record('PieChart'),
    ResponsiveContainer: record('ResponsiveContainer'),
    Tooltip: record('Tooltip'),
    XAxis: record('XAxis'),
    YAxis: record('YAxis'),
  };
});

// Imported AFTER the mock is registered so InteractiveChartCard picks up the stubs.
const { InteractiveChartCard } = await import('../InteractiveChartCard');
const CHART_TYPES = [
  { id: 'bar' as const, label: 'Bar' },
  { id: 'horizontalBar' as const, label: 'Horizontal' },
  { id: 'pie' as const, label: 'Pie' },
];
const SERIES = [
  { key: 'a', label: 'Anthropic · Claude Code', value: 4189188858 },
  { key: 'b', label: 'Unknown · Claude Code', value: 53312553 },
];

function callsFor(component: string): Array<Record<string, unknown>> {
  return capturedCalls.filter((c) => c.component === component).map((c) => c.props);
}

function renderAt(chartType: 'bar' | 'horizontalBar' | 'pie') {
  capturedCalls.length = 0;
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/?usageChart=${chartType}`]}>
      <InteractiveChartCard
        title="Token usage"
        paramPrefix="usage"
        chartTypes={CHART_TYPES}
        resolveData={() => SERIES}
      />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  capturedCalls.length = 0;
});

describe('InteractiveChartCard chart config — horizontalBar branch', () => {
  it('sets layout="vertical" on BarChart', () => {
    renderAt('horizontalBar');
    const barChartCalls = callsFor('BarChart');
    expect(barChartCalls).toHaveLength(1);
    expect(barChartCalls[0].layout).toBe('vertical');
  });

  it('sets XAxis type="number" and YAxis type="category" with dataKey="label"', () => {
    renderAt('horizontalBar');
    const xAxisCalls = callsFor('XAxis');
    const yAxisCalls = callsFor('YAxis');
    expect(xAxisCalls).toHaveLength(1);
    expect(yAxisCalls).toHaveLength(1);
    expect(xAxisCalls[0].type).toBe('number');
    expect(yAxisCalls[0].type).toBe('category');
    expect(yAxisCalls[0].dataKey).toBe('label');
  });

  it('disables Bar animation (defensive fix for interrupted-animation risk)', () => {
    renderAt('horizontalBar');
    const barCalls = callsFor('Bar');
    expect(barCalls).toHaveLength(1);
    expect(barCalls[0].isAnimationActive).toBe(false);
    expect(barCalls[0].dataKey).toBe('value');
  });
});

describe('InteractiveChartCard chart config — bar (vertical/default) branch', () => {
  it('sets layout="horizontal" on BarChart (recharts default column orientation)', () => {
    renderAt('bar');
    const barChartCalls = callsFor('BarChart');
    expect(barChartCalls).toHaveLength(1);
    expect(barChartCalls[0].layout).toBe('horizontal');
  });

  it('sets XAxis dataKey="label" with no explicit type (categorical default) and YAxis with no dataKey', () => {
    renderAt('bar');
    const xAxisCalls = callsFor('XAxis');
    const yAxisCalls = callsFor('YAxis');
    expect(xAxisCalls[0].dataKey).toBe('label');
    expect(xAxisCalls[0].type).toBeUndefined();
    expect(yAxisCalls[0].dataKey).toBeUndefined();
  });
});

describe('InteractiveChartCard chart config — pie branch', () => {
  it('passes dataKey="value" and nameKey="label" to Pie', () => {
    renderAt('pie');
    const pieCalls = callsFor('Pie');
    expect(pieCalls).toHaveLength(1);
    expect(pieCalls[0].dataKey).toBe('value');
    expect(pieCalls[0].nameKey).toBe('label');
  });

  it('disables Pie animation — root cause of the blank-pie-on-switch defect', () => {
    renderAt('pie');
    const pieCalls = callsFor('Pie');
    expect(pieCalls[0].isAnimationActive).toBe(false);
  });

  it('renders PieChart, never BarChart, when chartType=pie', () => {
    renderAt('pie');
    expect(callsFor('PieChart')).toHaveLength(1);
    expect(callsFor('BarChart')).toHaveLength(0);
  });
});
