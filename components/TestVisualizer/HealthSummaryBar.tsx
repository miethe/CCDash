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
        className="h-2.5 w-full overflow-hidden rounded-full border border-panel-border bg-panel"
        role="img"
        aria-label={`${passed} passed, ${failed} failed, ${skipped} skipped`}
      >
        <div className="flex h-full w-full">
          <div className="bg-success/90" style={{ width: `${passedPct}%` }} />
          <div className="bg-danger/90" style={{ width: `${failedPct}%` }} />
          <div className="bg-warning/90" style={{ width: `${skippedPct}%` }} />
        </div>
      </div>
      {showLegend && (
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-success" />
            {passed} passed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-danger" />
            {failed} failed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-warning" />
            {skipped} skipped
          </span>
        </div>
      )}
    </div>
  );
};

export type { HealthSummaryBarProps };
