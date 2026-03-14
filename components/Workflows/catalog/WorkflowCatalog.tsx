import React, { RefObject, useEffect, useMemo, useState } from 'react';
import { RefreshCcw, Search } from 'lucide-react';

import {
  WorkflowRegistryCorrelationState,
  WorkflowRegistryItem,
} from '../../../types';
import { CatalogFilterBar } from './CatalogFilterBar';
import { WorkflowListItem } from './WorkflowListItem';
import { formatInteger } from '../workflowRegistryUtils';

interface WorkflowCatalogProps {
  searchQuery: string;
  activeFilter: WorkflowRegistryCorrelationState | 'all';
  items: WorkflowRegistryItem[];
  total: number;
  loading: boolean;
  error: string;
  selectedId: string;
  searchInputRef: RefObject<HTMLInputElement | null>;
  onSearchQueryChange: (value: string) => void;
  onActiveFilterChange: (value: WorkflowRegistryCorrelationState | 'all') => void;
  onSelect: (itemId: string) => void;
  onRetry: () => void;
  onClearFilters: () => void;
}

const LoadingSkeleton: React.FC = () => (
  <div className="space-y-3">
    {Array.from({ length: 4 }).map((_, index) => (
      <div
        key={`workflow-catalog-skeleton-${index}`}
        className="rounded-[24px] border border-slate-800/80 bg-slate-950/50 p-4 animate-pulse"
      >
        <div className="h-4 w-40 rounded bg-slate-800" />
        <div className="mt-2 h-3 w-24 rounded bg-slate-900" />
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="h-20 rounded-2xl bg-slate-900" />
          <div className="h-20 rounded-2xl bg-slate-900" />
        </div>
        <div className="mt-4 space-y-2">
          <div className="h-6 rounded-xl bg-slate-900" />
          <div className="h-6 rounded-xl bg-slate-900" />
          <div className="h-6 rounded-xl bg-slate-900" />
        </div>
      </div>
    ))}
  </div>
);

export const WorkflowCatalog: React.FC<WorkflowCatalogProps> = ({
  searchQuery,
  activeFilter,
  items,
  total,
  loading,
  error,
  selectedId,
  searchInputRef,
  onSearchQueryChange,
  onActiveFilterChange,
  onSelect,
  onRetry,
  onClearFilters,
}) => {
  const [activeId, setActiveId] = useState(selectedId);

  useEffect(() => {
    if (selectedId) {
      setActiveId(selectedId);
      return;
    }
    if (!items.some(item => item.id === activeId)) {
      setActiveId(items[0]?.id || '');
    }
  }, [activeId, items, selectedId]);

  const filterCounts = useMemo(() => {
    const counts: Partial<Record<WorkflowRegistryCorrelationState | 'all', number>> = {
      all: total,
    };
    items.forEach(item => {
      counts[item.correlationState] = (counts[item.correlationState] || 0) + 1;
    });
    return counts;
  }, [items, total]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!items.length) return;
    const currentIndex = Math.max(0, items.findIndex(item => item.id === activeId));

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      const next = items[Math.min(items.length - 1, currentIndex + 1)];
      if (next) setActiveId(next.id);
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      const next = items[Math.max(0, currentIndex - 1)];
      if (next) setActiveId(next.id);
      return;
    }

    if (event.key === 'Enter' && activeId) {
      event.preventDefault();
      onSelect(activeId);
    }
  };

  return (
    <section className="rounded-[28px] border border-slate-800/80 bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.12),_rgba(15,23,42,0.98)_45%,_rgba(2,6,23,1)_100%)] p-4 md:p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Catalog</div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-100">Workflow Registry</h2>
          <p className="mt-1 text-sm text-slate-400">
            Search aliases, correlation states, and evidence without leaving the hub.
          </p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-950/70 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-colors hover:border-slate-500"
        >
          <RefreshCcw size={12} />
          Refresh
        </button>
      </div>

      <div className="mt-5 space-y-4">
        <label className="relative block">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            ref={searchInputRef}
            value={searchQuery}
            onChange={event => onSearchQueryChange(event.target.value)}
            placeholder="Search workflow names, aliases, or commands"
            className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 py-3 pl-10 pr-4 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-500 focus:border-indigo-500/40"
          />
        </label>

        <CatalogFilterBar
          activeFilter={activeFilter}
          counts={filterCounts}
          onChange={onActiveFilterChange}
        />

        <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
          <span>{formatInteger(total)} workflow entities</span>
          <span>Arrow keys move, Enter opens, `/` focuses search</span>
        </div>
      </div>

      <div
        className="mt-5 space-y-3 overflow-y-auto xl:max-h-[calc(100vh-21rem)]"
        onKeyDown={handleKeyDown}
        tabIndex={0}
      >
        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <div className="rounded-[24px] border border-rose-500/30 bg-rose-500/10 px-4 py-4 text-sm text-rose-100">
            <div className="font-semibold">Workflow catalog unavailable</div>
            <p className="mt-1 text-rose-100/80">{error}</p>
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-2 rounded-full border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-50"
            >
              Retry
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-[24px] border border-slate-800 bg-slate-950/60 px-4 py-6 text-center">
            <div className="text-base font-semibold text-slate-100">No workflows found</div>
            <p className="mt-2 text-sm text-slate-400">
              Try a different alias, remove the correlation filter, or refresh the cache.
            </p>
            <button
              type="button"
              onClick={onClearFilters}
              className="mt-4 inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-colors hover:border-slate-500"
            >
              Clear filters
            </button>
          </div>
        ) : (
          items.map(item => (
            <WorkflowListItem
              key={item.id}
              item={item}
              selected={item.id === selectedId}
              active={item.id === activeId}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </section>
  );
};
