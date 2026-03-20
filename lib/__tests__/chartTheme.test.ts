import { describe, expect, it } from 'vitest';

import { chartTheme, getChartGradientStops, getChartSeriesColor } from '../chartTheme';

describe('chartTheme', () => {
  it('exposes token-backed axis and tooltip styles', () => {
    expect(chartTheme.grid.stroke).toBe('hsl(var(--chart-grid))');
    expect(chartTheme.axis.tick.fill).toBe('hsl(var(--chart-axis))');
    expect(chartTheme.tooltip.contentStyle.backgroundColor).toBe('hsl(var(--chart-tooltip))');
    expect(chartTheme.tooltip.contentStyle.borderColor).toBe('hsl(var(--panel-border))');
  });

  it('returns semantic series colors and gradient stops', () => {
    expect(getChartSeriesColor('primary')).toBe('hsl(var(--chart-1))');
    expect(getChartSeriesColor('success')).toBe('hsl(var(--success))');
    expect(getChartGradientStops('hsl(var(--chart-1))')).toEqual([
      { offset: '5%', stopColor: 'hsl(var(--chart-1))', stopOpacity: 0.32 },
      { offset: '95%', stopColor: 'hsl(var(--chart-1))', stopOpacity: 0 },
    ]);
  });
});
