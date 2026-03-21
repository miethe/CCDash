import React from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { chartTheme, getChartSeriesColor } from '../../lib/chartTheme';
import { FeatureTestTimeline } from '../../types';

interface TestTimelineProps {
  timeline: FeatureTestTimeline | null;
  className?: string;
}

const toChartData = (timeline: FeatureTestTimeline) =>
  timeline.timeline.map(point => ({
    date: point.date,
    passRate: Math.round(point.passRate * 100),
    passed: point.passed,
    failed: point.failed,
    skipped: point.skipped,
    signals: point.signals.length,
  }));

export const TestTimeline: React.FC<TestTimelineProps> = ({ timeline, className = '' }) => {
  if (!timeline || timeline.timeline.length === 0) {
    return (
      <div className={`rounded-xl border border-panel-border bg-panel p-6 text-sm text-muted-foreground ${className}`.trim()}>
        No timeline data.
      </div>
    );
  }

  const data = toChartData(timeline);

  return (
    <div className={`rounded-xl border border-panel-border bg-panel p-4 ${className}`.trim()}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-panel-foreground">Feature Timeline</h3>
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          {timeline.firstGreen && <span>First green: {new Date(timeline.firstGreen).toLocaleDateString()}</span>}
          {timeline.lastRed && <span>Last red: {new Date(timeline.lastRed).toLocaleDateString()}</span>}
        </div>
      </div>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid {...chartTheme.grid} vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(value: string) => value.slice(5)}
              {...chartTheme.axis}
            />
            <YAxis
              domain={[0, 100]}
              {...chartTheme.axis}
              tickFormatter={(value: number) => `${value}%`}
            />
            <Tooltip
              contentStyle={chartTheme.tooltip.contentStyle}
              itemStyle={chartTheme.tooltip.itemStyle}
              labelStyle={chartTheme.tooltip.labelStyle}
              cursor={chartTheme.tooltip.cursor}
              formatter={(value: number, key: string) => {
                if (key === 'passRate') return [`${value}%`, 'Pass Rate'];
                return [String(value), key];
              }}
            />
            <Line type="monotone" dataKey="passRate" stroke={getChartSeriesColor('primary')} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export type { TestTimelineProps };
