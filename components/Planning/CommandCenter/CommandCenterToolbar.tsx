import { Columns3, LayoutGrid, List, RefreshCw, Search } from 'lucide-react';

import { BtnGhost, Chip } from '../primitives';

export interface CommandCenterFilters {
  q: string;
  status: string;
  phase: string;
  sortBy: string;
  sortDirection: 'asc' | 'desc';
  /** When true, the backend excludes terminal-status items. Defaults to true in the single-project center. */
  hideDone?: boolean;
}

export type CommandCenterViewMode = 'list' | 'cards' | 'board';

// T4-014: selectable page sizes
export const COMMAND_CENTER_PAGE_SIZES = [25, 50, 100] as const;
export type CommandCenterPageSize = (typeof COMMAND_CENTER_PAGE_SIZES)[number];

interface CommandCenterToolbarProps {
  filters: CommandCenterFilters;
  viewMode: CommandCenterViewMode;
  total: number;
  loading?: boolean;
  /** T4-014: current pageSize; renders a selector when provided. */
  pageSize?: CommandCenterPageSize;
  /**
   * Which view mode buttons to show as interactive. Modes not listed are
   * rendered disabled with a tooltip explaining unavailability. Defaults to
   * all three modes so single-project behaviour is unchanged.
   */
  availableViewModes?: CommandCenterViewMode[];
  onFiltersChange: (filters: CommandCenterFilters) => void;
  onViewModeChange: (viewMode: CommandCenterViewMode) => void;
  onRefresh: () => void;
  /** T4-014: called when the user selects a new page size. */
  onPageSizeChange?: (pageSize: number) => void;
  /** Called when the user toggles the "Show done" checkbox. When provided, the checkbox renders. */
  onHideDoneChange?: (hideDone: boolean) => void;
}

function updateFilter(
  filters: CommandCenterFilters,
  patch: Partial<CommandCenterFilters>,
): CommandCenterFilters {
  return { ...filters, ...patch };
}

const ALL_VIEW_MODES: CommandCenterViewMode[] = ['list', 'cards', 'board'];

export function CommandCenterToolbar({
  filters,
  viewMode,
  total,
  loading = false,
  pageSize,
  availableViewModes = ALL_VIEW_MODES,
  onFiltersChange,
  onViewModeChange,
  onRefresh,
  onPageSizeChange,
  onHideDoneChange,
}: CommandCenterToolbarProps) {
  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between" data-testid="command-center-toolbar">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="planning-caps text-[10px] text-[color:var(--ink-3)]">Planning Command Center</span>
          <Chip className="planning-mono text-[10px]">{total} live items</Chip>
          <Chip className="planning-mono text-[10px]">
            <LayoutGrid size={12} aria-hidden />
            project cockpit
          </Chip>
        </div>
        <p className="mt-1 max-w-[980px] text-[12px] text-[color:var(--ink-3)]">
          Feature status, target plans, next commands, worktrees, branches, commits, blockers, and launch context in one route-local surface.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[220px] flex-1 lg:flex-none">
          <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--ink-4)]" aria-hidden />
          <input
            value={filters.q}
            onChange={(event) => onFiltersChange(updateFilter(filters, { q: event.currentTarget.value }))}
            placeholder="Search features, plans, branches"
            className="planning-mono h-[32px] w-full rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] pl-8 pr-2 text-[11px] text-[color:var(--ink-1)] outline-none focus:border-[color:var(--brand)]"
          />
        </label>
        <select
          value={filters.status}
          onChange={(event) => onFiltersChange(updateFilter(filters, { status: event.currentTarget.value }))}
          className="planning-mono h-[32px] rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] px-2 text-[11px] text-[color:var(--ink-1)]"
          aria-label="Filter command center status"
        >
          <option value="">all status</option>
          <option value="ready">ready</option>
          <option value="active">active</option>
          <option value="blocked">blocked</option>
          <option value="done">done</option>
        </select>
        <select
          value={filters.sortBy}
          onChange={(event) => onFiltersChange(updateFilter(filters, { sortBy: event.currentTarget.value }))}
          className="planning-mono h-[32px] rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] px-2 text-[11px] text-[color:var(--ink-1)]"
          aria-label="Sort command center"
        >
          <option value="last_activity">Activity</option>
          <option value="status">Status</option>
          <option value="phase">Phase</option>
        </select>
        <BtnGhost
          size="sm"
          onClick={() => onFiltersChange(updateFilter(filters, { sortDirection: filters.sortDirection === 'asc' ? 'desc' : 'asc' }))}
          aria-label="Toggle sort direction"
        >
          <List size={13} aria-hidden />
          {filters.sortDirection}
        </BtnGhost>
        {/* "Show done" toggle — only renders when handler is provided */}
        {onHideDoneChange ? (
          <label className="flex cursor-pointer items-center gap-1.5 planning-mono text-[11px] text-[color:var(--ink-3)]">
            <input
              type="checkbox"
              checked={filters.hideDone === false}
              onChange={(e) => onHideDoneChange(!e.currentTarget.checked)}
              className="h-[14px] w-[14px] rounded accent-[color:var(--brand)]"
              aria-label="Show done items"
            />
            show done
          </label>
        ) : null}
        {/* T4-014: pageSize selector — only renders when handler is provided */}
        {onPageSizeChange ? (
          <select
            value={pageSize ?? 50}
            onChange={(event) => onPageSizeChange(Number(event.currentTarget.value))}
            className="planning-mono h-[32px] rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] px-2 text-[11px] text-[color:var(--ink-1)]"
            aria-label="Items per page"
          >
            {COMMAND_CENTER_PAGE_SIZES.map((size) => (
              <option key={size} value={size}>{size} / page</option>
            ))}
          </select>
        ) : null}
        <div className="planning-chip planning-mono border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-1 text-[10.5px]" role="group" aria-label="Command center view">
          {([
            ['list', List, 'List'],
            ['cards', LayoutGrid, 'Cards'],
            ['board', Columns3, 'Board'],
          ] as const).map(([mode, Icon, label]) => {
            const isAvailable = availableViewModes.includes(mode);
            return (
              <button
                key={mode}
                type="button"
                onClick={isAvailable ? () => onViewModeChange(mode) : undefined}
                disabled={!isAvailable}
                title={isAvailable ? undefined : 'Not available in portfolio view'}
                className={[
                  'inline-flex h-[24px] items-center gap-1 rounded-[var(--radius-sm)] px-2 transition-colors',
                  !isAvailable
                    ? 'cursor-not-allowed opacity-35 text-[color:var(--ink-4)]'
                    : viewMode === mode
                      ? 'bg-[color:var(--bg-3)] text-[color:var(--ink-0)]'
                      : 'text-[color:var(--ink-3)] hover:text-[color:var(--ink-1)]',
                ].join(' ')}
                aria-pressed={isAvailable ? viewMode === mode : undefined}
                aria-disabled={!isAvailable}
              >
                <Icon size={12} aria-hidden />
                {label}
              </button>
            );
          })}
        </div>
        <BtnGhost size="sm" onClick={onRefresh} disabled={loading} aria-label="Refresh command center">
          <RefreshCw size={13} aria-hidden className={loading ? 'animate-spin' : undefined} />
          refresh
        </BtnGhost>
      </div>
    </div>
  );
}
