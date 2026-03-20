import type { CSSProperties } from 'react';

type ChartSeriesTone =
  | 'primary'
  | 'secondary'
  | 'tertiary'
  | 'quaternary'
  | 'quinary'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info';

export interface ChartGradientStop {
  offset: string;
  stopColor: string;
  stopOpacity: number;
}

const cssColor = (variable: string, alpha?: number): string =>
  alpha === undefined ? `hsl(var(${variable}))` : `hsl(var(${variable}) / ${alpha})`;

export const CHART_SERIES_COLORS: Record<ChartSeriesTone, string> = {
  primary: cssColor('--chart-1'),
  secondary: cssColor('--chart-2'),
  tertiary: cssColor('--chart-3'),
  quaternary: cssColor('--chart-4'),
  quinary: cssColor('--chart-5'),
  success: cssColor('--success'),
  warning: cssColor('--warning'),
  danger: cssColor('--danger'),
  info: cssColor('--info'),
};

export const chartTheme = {
  grid: {
    strokeDasharray: '3 3',
    stroke: cssColor('--chart-grid'),
  },
  axis: {
    stroke: cssColor('--chart-axis'),
    axisLine: false,
    tickLine: false,
    tick: {
      fill: cssColor('--chart-axis'),
      fontSize: 12,
    },
  },
  tooltip: {
    contentStyle: {
      backgroundColor: cssColor('--chart-tooltip'),
      borderColor: cssColor('--panel-border'),
      borderRadius: '0.75rem',
      color: cssColor('--chart-tooltip-foreground'),
    } satisfies CSSProperties,
    itemStyle: {
      color: cssColor('--chart-tooltip-foreground'),
    } satisfies CSSProperties,
    labelStyle: {
      color: cssColor('--chart-tooltip-foreground'),
    } satisfies CSSProperties,
    cursor: {
      fill: cssColor('--surface-overlay', 0.45),
    },
  },
};

export const getChartSeriesColor = (tone: ChartSeriesTone): string => CHART_SERIES_COLORS[tone];

export const getChartGradientStops = (color: string): ChartGradientStop[] => [
  { offset: '5%', stopColor: color, stopOpacity: 0.32 },
  { offset: '95%', stopColor: color, stopOpacity: 0 },
];
