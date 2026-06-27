import React, { useState, useRef } from 'react';
import { Activity, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { Surface } from './ui/surface';
import { cn } from '../lib/utils';
import type { ProjectActiveCountSummary } from '../types';
import { useSystemMetricsQuery } from '../services/queries/systemMetrics';

// ── Sub-components ─────────────────────────────────────────────────────────────

const STALE_ICON_CLASS = 'text-warning-foreground';

interface ProjectRowProps {
  entry: ProjectActiveCountSummary;
}

/** Single row in the expanded per-project breakdown table. */
const ProjectRow: React.FC<ProjectRowProps> = ({ entry }) => {
  // R-P2: is_stale === null → treat as true (show warning icon)
  const showStale = entry.is_stale !== false;
  const tooltip = entry.last_synced_at
    ? `Last synced: ${new Date(entry.last_synced_at).toLocaleString()}`
    : 'No sync timestamp available';

  return (
    <tr className="border-t border-border/50">
      <td className="py-1.5 pr-4 text-sm text-panel-foreground max-w-[180px] truncate">
        {entry.project_name}
      </td>
      <td className="py-1.5 pr-3 text-sm text-right tabular-nums text-panel-foreground">
        {/* R-P2: count === null → render em-dash */}
        {entry.count !== null ? entry.count.toLocaleString() : '—'}
      </td>
      <td className="py-1.5 text-center w-6">
        {showStale && (
          <span title={tooltip} className="inline-flex">
            <AlertTriangle size={13} className={STALE_ICON_CLASS} aria-label="Stale data" />
          </span>
        )}
      </td>
    </tr>
  );
};

// ── Main component ─────────────────────────────────────────────────────────────

/**
 * SystemMetricsChip — live system-wide agent count chip for the Dashboard.
 *
 * Collapsed: shows "Live now" label + total count.
 * Expanded: shows per-project breakdown table with stale indicators.
 *
 * Resilience contracts (R-P2 / T3-003):
 * - count === null → renders em-dash.
 * - per_project missing/empty → renders "breakdown unavailable" message.
 * - is_stale === null → treated as true (warning icon shown).
 * - Fetch failure → renders last-known total with "data may be outdated" indicator.
 * - status === "partial" → small "partial" badge next to total.
 * - Never throws to the React error boundary in any case.
 *
 * Polling is handled by TanStack Query (refetchInterval: 30 s).
 * The interval pauses automatically when the tab is hidden
 * (refetchIntervalInBackground defaults to false — no manual visibilitychange
 * listener needed).
 */
export const SystemMetricsChip: React.FC = () => {
  const { data, isLoading, isError, dataUpdatedAt } = useSystemMetricsQuery();

  // Normalize data with resilience fallbacks (R-P2).
  const total = typeof data?.total === 'number' ? data.total : null;
  const perProject = Array.isArray(data?.per_project) ? data.per_project : [];
  const status = data?.status ?? null;

  // lastKnownRef preserves the most recent good total for display on error.
  const lastKnownRef = useRef<number | null>(null);
  if (!isError && total !== null) {
    lastKnownRef.current = total;
  }

  // dataUpdatedAt is 0 when no successful fetch has completed yet.
  const lastFetchedAt = dataUpdatedAt > 0 ? new Date(dataUpdatedAt) : null;

  // expanded state — toggling does NOT re-fetch (uses in-memory state).
  const [expanded, setExpanded] = useState(false);

  const handleToggle = () => setExpanded((v) => !v);

  // Determine display total and whether we are showing stale/fallback data.
  const displayTotal = isError ? lastKnownRef.current : total;
  const showOutdatedBadge = isError && lastFetchedAt !== null;
  const showNeverFetched = isError && lastFetchedAt === null;

  const totalLabel =
    isLoading && displayTotal === null
      ? '—'
      : displayTotal !== null
        ? displayTotal.toLocaleString()
        : '—';

  const hasBreakdown = perProject.length > 0;

  return (
    <Surface tone="panel" padding="md" className="w-full">
      {/* Collapsed chip header — always visible */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity size={15} className="shrink-0 text-primary" />
          <span className="text-sm font-medium text-muted-foreground">Live now</span>
          <span
            className={cn(
              'text-sm font-bold tabular-nums text-panel-foreground',
              isLoading && displayTotal === null && 'animate-pulse text-muted-foreground',
            )}
          >
            {totalLabel}
          </span>

          {/* Partial status badge */}
          {status === 'partial' && (
            <span className="inline-flex items-center rounded border border-warning-border bg-warning/10 px-1.5 py-0.5 text-xs font-medium text-warning-foreground">
              partial
            </span>
          )}

          {/* Outdated data indicator (error + previous value available) */}
          {showOutdatedBadge && (
            <span className="text-xs text-muted-foreground italic">data may be outdated</span>
          )}

          {/* Never-fetched error (first load failed) */}
          {showNeverFetched && (
            <span className="text-xs text-muted-foreground italic">unavailable</span>
          )}
        </div>

        {/* Expand/collapse toggle */}
        <button
          type="button"
          onClick={handleToggle}
          aria-expanded={expanded}
          aria-label={expanded ? 'Collapse per-project breakdown' : 'Expand per-project breakdown'}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-panel-foreground/5 hover:text-panel-foreground"
        >
          {expanded ? (
            <>
              Collapse <ChevronUp size={13} />
            </>
          ) : (
            <>
              By project <ChevronDown size={13} />
            </>
          )}
        </button>
      </div>

      {/* Expanded breakdown panel — no re-fetch on toggle */}
      {expanded && (
        <div className="mt-3 border-t border-border/50 pt-3">
          {hasBreakdown ? (
            <table className="w-full">
              <thead>
                <tr>
                  <th className="pb-1.5 text-left text-xs font-medium text-muted-foreground">Project</th>
                  <th className="pb-1.5 text-right text-xs font-medium text-muted-foreground pr-3">Active</th>
                  <th className="pb-1.5 w-6" />
                </tr>
              </thead>
              <tbody>
                {perProject.map((entry) => (
                  <ProjectRow key={entry.project_id} entry={entry} />
                ))}
              </tbody>
            </table>
          ) : (
            /* R-P2: per_project missing or empty */
            <p className="text-xs text-muted-foreground">breakdown unavailable</p>
          )}
        </div>
      )}
    </Surface>
  );
};

export default SystemMetricsChip;
