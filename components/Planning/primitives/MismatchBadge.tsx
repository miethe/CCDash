import { AlertTriangle } from 'lucide-react';

export interface MismatchBadgeProps {
  /** The mismatch state string (e.g. "mismatched", "reversed", "stale"). */
  state: string;
  /** Human-readable explanation for the mismatch. */
  reason: string;
  /** Optional evidence labels rendered as small inner chips (banner mode only). */
  evidenceLabels?: string[];
  /**
   * When true, renders a compact inline amber badge suited for card / list
   * contexts. When false (default), renders the full banner variant for headers.
   */
  compact?: boolean;
}

/**
 * Renders an amber mismatch indicator in two forms:
 * - `compact=true`  — a small inline chip with icon + state label.
 * - `compact=false` — the full banner with title, reason, and evidence chips.
 */
export function MismatchBadge({
  state,
  reason,
  evidenceLabels = [],
  compact = false,
}: MismatchBadgeProps) {
  if (compact) {
    return (
      <span
        className="inline-flex items-center gap-1 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-300"
        title={reason}
      >
        <AlertTriangle size={11} className="shrink-0 text-amber-400" />
        {state}
      </span>
    );
  }

  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
      <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-400" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-amber-300">Status mismatch detected</p>
        <p className="mt-0.5 text-xs text-amber-300/80">{reason}</p>
        {evidenceLabels.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {evidenceLabels.map((label, i) => (
              <span
                key={i}
                className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-amber-500/20 text-amber-300"
              >
                {label}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
