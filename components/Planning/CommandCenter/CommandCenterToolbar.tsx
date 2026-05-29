import { Columns3, LayoutGrid, List, RefreshCw, Search } from 'lucide-react';

import { BtnGhost, Chip } from '../primitives';

export interface CommandCenterFilters {
  q: string;
  status: string;
  phase: string;
  sortBy: string;
  sortDirection: 'asc' | 'desc';
}

export type CommandCenterViewMode = 'list' | 'cards' | 'board';

interface CommandCenterToolbarProps {
  filters: CommandCenterFilters;
  viewMode: CommandCenterViewMode;
  total: number;
  loading?: boolean;
  onFiltersChange: (filters: CommandCenterFilters) => void;
  onViewModeChange: (viewMode: CommandCenterViewMode) => void;
  onRefresh: () => void;
}

function updateFilter(
  filters: CommandCenterFilters,
  patch: Partial<CommandCenterFilters>,
): CommandCenterFilters {
  return { ...filters, ...patch };
}

export function CommandCenterToolbar({
  filters,
  viewMode,
  total,
  loading = false,
  onFiltersChange,
  onViewModeChange,
  onRefresh,
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
          <option value="priority">priority</option>
          <option value="status">status</option>
          <option value="phase">phase</option>
          <option value="activity">activity</option>
        </select>
        <BtnGhost
          size="sm"
          onClick={() => onFiltersChange(updateFilter(filters, { sortDirection: filters.sortDirection === 'asc' ? 'desc' : 'asc' }))}
          aria-label="Toggle sort direction"
        >
          <List size={13} aria-hidden />
          {filters.sortDirection}
        </BtnGhost>
        <div className="planning-chip planning-mono border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-1 text-[10.5px]" role="group" aria-label="Command center view">
          {([
            ['list', List, 'List'],
            ['cards', LayoutGrid, 'Cards'],
            ['board', Columns3, 'Board'],
          ] as const).map(([mode, Icon, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() => onViewModeChange(mode)}
              className={[
                'inline-flex h-[24px] items-center gap-1 rounded-[var(--radius-sm)] px-2 transition-colors',
                viewMode === mode
                  ? 'bg-[color:var(--bg-3)] text-[color:var(--ink-0)]'
                  : 'text-[color:var(--ink-3)] hover:text-[color:var(--ink-1)]',
              ].join(' ')}
              aria-pressed={viewMode === mode}
            >
              <Icon size={12} aria-hidden />
              {label}
            </button>
          ))}
        </div>
        <BtnGhost size="sm" onClick={onRefresh} disabled={loading} aria-label="Refresh command center">
          <RefreshCw size={13} aria-hidden className={loading ? 'animate-spin' : undefined} />
          refresh
        </BtnGhost>
      </div>
    </div>
  );
}
