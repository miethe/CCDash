import React from 'react';

import { TestStatus } from '../../types';

interface TestFiltersProps {
  statusFilter: TestStatus[];
  onStatusChange: (statuses: TestStatus[]) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  branchFilter: string;
  onBranchFilterChange: (branch: string) => void;
  runDateFrom: string;
  onRunDateFromChange: (value: string) => void;
  runDateTo: string;
  onRunDateToChange: (value: string) => void;
}

const STATUS_OPTIONS: TestStatus[] = ['failed', 'error', 'running', 'passed', 'skipped', 'xfailed', 'xpassed'];

const labelForStatus = (status: TestStatus): string => status.replace(/_/g, ' ');

export const TestFilters: React.FC<TestFiltersProps> = ({
  statusFilter,
  onStatusChange,
  searchQuery,
  onSearchChange,
  branchFilter,
  onBranchFilterChange,
  runDateFrom,
  onRunDateFromChange,
  runDateTo,
  onRunDateToChange,
}) => {
  const toggleStatus = (status: TestStatus) => {
    if (statusFilter.includes(status)) {
      onStatusChange(statusFilter.filter(item => item !== status));
      return;
    }
    onStatusChange([...statusFilter, status]);
  };

  return (
    <section className="space-y-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Test Filters</h3>

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Result Status</p>
        <div className="space-y-1.5">
          {STATUS_OPTIONS.map(status => (
            <label key={status} className="flex items-center gap-2 text-xs text-foreground">
              <input
                type="checkbox"
                checked={statusFilter.includes(status)}
                onChange={() => toggleStatus(status)}
                className="accent-indigo-500"
              />
              <span className="capitalize">{labelForStatus(status)}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Search</p>
        <input
          type="text"
          value={searchQuery}
          onChange={event => onSearchChange(event.target.value)}
          placeholder="Test name, id, run id..."
          className="w-full rounded border border-panel-border bg-surface-overlay px-2 py-1.5 text-xs text-panel-foreground placeholder:text-muted-foreground focus:border-focus focus:outline-none"
        />
      </div>

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Branch</p>
        <input
          type="text"
          value={branchFilter}
          onChange={event => onBranchFilterChange(event.target.value)}
          placeholder="main"
          className="w-full rounded border border-panel-border bg-surface-overlay px-2 py-1.5 text-xs text-panel-foreground placeholder:text-muted-foreground focus:border-focus focus:outline-none"
        />
      </div>

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Run Date</p>
        <div className="grid grid-cols-[36px_1fr] items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">From</span>
          <input
            type="date"
            value={runDateFrom}
            onChange={event => onRunDateFromChange(event.target.value)}
            className="w-full rounded border border-panel-border bg-surface-overlay px-2 py-1.5 text-xs text-panel-foreground focus:border-focus focus:outline-none"
          />
        </div>
        <div className="grid grid-cols-[36px_1fr] items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">To</span>
          <input
            type="date"
            value={runDateTo}
            onChange={event => onRunDateToChange(event.target.value)}
            className="w-full rounded border border-panel-border bg-surface-overlay px-2 py-1.5 text-xs text-panel-foreground focus:border-focus focus:outline-none"
          />
        </div>
      </div>
    </section>
  );
};

export type { TestFiltersProps };
