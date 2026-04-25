import { Search } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { PlanningBoardGroupingMode } from '@/types';
import { usePlanningRoute } from './PlanningRouteLayout';
import { BtnGhost } from './primitives';

// ── State filter type ─────────────────────────────────────────────────────────

export type StateFilter = 'all' | 'active' | 'recent';

const STATE_FILTER_OPTIONS: { value: StateFilter; label: string; title: string }[] = [
  { value: 'all', label: 'All', title: 'Show all sessions' },
  { value: 'active', label: 'Active', title: 'Show only running or thinking sessions' },
  { value: 'recent', label: 'Recent', title: 'Show sessions active in the last 10 minutes' },
];

// ── Grouping options ──────────────────────────────────────────────────────────

const GROUPING_OPTIONS: { value: PlanningBoardGroupingMode; label: string }[] = [
  { value: 'state', label: 'State' },
  { value: 'feature', label: 'Feature' },
  { value: 'phase', label: 'Phase' },
  { value: 'agent', label: 'Agent' },
  { value: 'model', label: 'Model' },
];

export interface PlanningBoardToolbarProps {
  grouping: PlanningBoardGroupingMode;
  onGroupingChange: (mode: PlanningBoardGroupingMode) => void;
  filterText: string;
  onFilterTextChange: (value: string) => void;
  stateFilter: StateFilter;
  onStateFilterChange: (f: StateFilter) => void;
  className?: string;
}

export function PlanningBoardToolbar({
  grouping,
  onGroupingChange,
  filterText,
  onFilterTextChange,
  stateFilter,
  onStateFilterChange,
  className,
}: PlanningBoardToolbarProps) {
  const { density } = usePlanningRoute();

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-3',
        density === 'compact' ? 'py-1.5' : 'py-2.5',
        className,
      )}
    >
      {/* Grouping chips */}
      <div
        className="planning-chip planning-mono border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-1 text-[10.5px]"
        role="group"
        aria-label="Group sessions by"
      >
        {GROUPING_OPTIONS.map(({ value, label }) => (
          <BtnGhost
            key={value}
            type="button"
            size="xs"
            aria-pressed={grouping === value}
            onClick={() => onGroupingChange(value)}
            className={cn(
              'min-w-[62px] justify-center px-2.5',
              grouping === value &&
                'border-[color:var(--line-2)] bg-[color:var(--bg-3)] text-[color:var(--ink-0)]',
            )}
          >
            {label}
          </BtnGhost>
        ))}
      </div>

      {/* State filter chips */}
      <div
        className="planning-chip planning-mono border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-1 text-[10.5px]"
        role="group"
        aria-label="Filter sessions by state"
      >
        {STATE_FILTER_OPTIONS.map(({ value, label, title }) => (
          <BtnGhost
            key={value}
            type="button"
            size="xs"
            aria-pressed={stateFilter === value}
            title={title}
            onClick={() => onStateFilterChange(value)}
            className={cn(
              'min-w-[52px] justify-center px-2.5',
              stateFilter === value &&
                'border-[color:var(--line-2)] bg-[color:var(--bg-3)] text-[color:var(--ink-0)]',
            )}
          >
            {label}
          </BtnGhost>
        ))}
      </div>

      {/* Search input */}
      <div className="relative flex-1 min-w-[180px] max-w-[320px]">
        <Search
          size={12}
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2"
          style={{ color: 'var(--ink-3)' }}
          aria-hidden
        />
        <input
          type="search"
          value={filterText}
          onChange={(e) => onFilterTextChange(e.target.value)}
          placeholder="Filter sessions…"
          aria-label="Filter board sessions"
          className={cn(
            'w-full rounded-[var(--radius-sm)] border border-[color:var(--line-1)]',
            'bg-[color:var(--bg-1)] pl-7 pr-3 text-[11px] text-[color:var(--ink-1)]',
            'placeholder:text-[color:var(--ink-4)] outline-none',
            'focus:border-[color:var(--line-2)] focus:bg-[color:var(--bg-2)]',
            'transition-colors',
            density === 'compact' ? 'py-1' : 'py-1.5',
          )}
        />
      </div>
    </div>
  );
}
