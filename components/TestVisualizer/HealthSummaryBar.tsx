import React from 'react';

interface HealthSummaryBarProps {
  passed: number;
  failed: number;
  skipped: number;
  total?: number;
  className?: string;
  showLegend?: boolean;
}

const pct = (value: number, total: number): number => {
  if (total <= 0) return 0;
  return (value / total) * 100;
};

export const HealthSummaryBar: React.FC<HealthSummaryBarProps> = ({
  passed,
  failed,
  skipped,
  total,
  className = '',
  showLegend = true,
}) => {
  const normalizedTotal = total ?? passed + failed + skipped;
  const passedPct = pct(passed, normalizedTotal);
  const failedPct = pct(failed, normalizedTotal);
  const skippedPct = pct(skipped, normalizedTotal);

  return (
    <div className={`space-y-2 ${className}`.trim()}>
      <div
        className="h-2.5 w-full overflow-hidden rounded-full border border-slate-800 bg-slate-900"
        role="img"
        aria-label={`${passed} passed, ${failed} failed, ${skipped} skipped`}
      >
        <div className="flex h-full w-full">
          <div className="bg-emerald-500/90" style={{ width: `${passedPct}%` }} />
          <div className="bg-rose-500/90" style={{ width: `${failedPct}%` }} />
          <div className="bg-amber-500/90" style={{ width: `${skippedPct}%` }} />
        </div>
      </div>
      {showLegend && (
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            {passed} passed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-rose-500" />
            {failed} failed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-amber-500" />
            {skipped} skipped
          </span>
        </div>
      )}
    </div>
  );
};

export type { HealthSummaryBarProps };
