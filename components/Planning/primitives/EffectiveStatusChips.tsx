import type { PlanningStatusProvenance } from '../../../types';
import { StatusChip } from './StatusChip';
import { statusVariant } from './variants';

export interface EffectiveStatusChipsProps {
  rawStatus: string;
  effectiveStatus?: string;
  isMismatch?: boolean;
  provenance?: PlanningStatusProvenance;
}

/**
 * Renders the raw status chip plus an optional `eff:` chip when rawStatus and
 * effectiveStatus differ. Wraps the raw chip in a hover tooltip showing
 * provenance source and reason when provenance is supplied.
 */
export function EffectiveStatusChips({
  rawStatus,
  effectiveStatus,
  isMismatch = false,
  provenance,
}: EffectiveStatusChipsProps) {
  const showEff = Boolean(effectiveStatus && effectiveStatus !== rawStatus);

  return (
    <div className="flex items-center gap-2">
      <div className="group relative">
        <StatusChip label={`raw: ${rawStatus}`} variant={statusVariant(rawStatus)} />
        {provenance && (
          <div className="pointer-events-none absolute right-0 top-full z-10 mt-1.5 hidden w-64 rounded-lg border border-panel-border bg-slate-900 p-3 shadow-xl group-hover:block">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase mb-1">
              Provenance
            </p>
            <p className="text-xs text-panel-foreground">Source: {provenance.source}</p>
            {provenance.reason && (
              <p className="mt-0.5 text-xs text-muted-foreground">{provenance.reason}</p>
            )}
          </div>
        )}
      </div>
      {showEff && (
        <StatusChip
          label={`eff: ${effectiveStatus}`}
          variant={isMismatch ? 'warn' : statusVariant(effectiveStatus!)}
        />
      )}
    </div>
  );
}
