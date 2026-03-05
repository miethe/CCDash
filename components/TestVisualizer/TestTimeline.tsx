import React from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

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
      <div className={`rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-500 ${className}`.trim()}>
        No timeline data.
      </div>
    );
  }

  const data = toChartData(timeline);

  return (
    <div className={`rounded-xl border border-slate-800 bg-slate-900 p-4 ${className}`.trim()}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-200">Feature Timeline</h3>
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          {timeline.firstGreen && <span>First green: {new Date(timeline.firstGreen).toLocaleDateString()}</span>}
          {timeline.lastRed && <span>Last red: {new Date(timeline.lastRed).toLocaleDateString()}</span>}
        </div>
      </div>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(value: string) => value.slice(5)}
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value: number) => `${value}%`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#e2e8f0' }}
              labelStyle={{ color: '#cbd5e1' }}
              formatter={(value: number, key: string) => {
                if (key === 'passRate') return [`${value}%`, 'Pass Rate'];
                return [String(value), key];
              }}
            />
            <Line type="monotone" dataKey="passRate" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export type { TestTimelineProps };
