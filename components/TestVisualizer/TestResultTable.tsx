import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { TestDefinition, TestResult } from '../../types';
import { TestStatusBadge } from './TestStatusBadge';

interface TestResultTableProps {
  results: TestResult[];
  definitions?: Record<string, TestDefinition>;
  isLoading?: boolean;
  isLoadingMore?: boolean;
  total?: number;
  totalTestsOverall?: number;
  error?: string | null;
  hasMore?: boolean;
  onLoadMore?: () => void;
  sortKey?: SortKey;
  sortOrder?: 'asc' | 'desc';
  onSortChange?: (sortKey: SortKey, sortOrder: 'asc' | 'desc') => void;
  className?: string;
}

type SortKey = 'status' | 'duration' | 'name' | 'test_id';

const formatDuration = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

const previewError = (message: string): string => {
  const firstLine = (message || '').split('\n')[0].trim();
  if (!firstLine) return '—';
  return firstLine.length > 90 ? `${firstLine.slice(0, 90)}...` : firstLine;
};

export const TestResultTable: React.FC<TestResultTableProps> = ({
  results,
  definitions = {},
  isLoading = false,
  isLoadingMore = false,
  total,
  totalTestsOverall,
  error = null,
  hasMore = false,
  onLoadMore,
  sortKey = 'status',
  sortOrder = 'asc',
  onSortChange,
  className = '',
}) => {
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});

  const setSort = (nextKey: SortKey) => {
    if (!onSortChange) return;
    const nextOrder: 'asc' | 'desc' = nextKey === sortKey
      ? sortOrder === 'asc'
        ? 'desc'
        : 'asc'
      : 'asc';
    onSortChange(nextKey, nextOrder);
  };

  const toggleRow = (testId: string) => {
    setExpandedRows(prev => ({ ...prev, [testId]: !prev[testId] }));
  };

  if (isLoading) {
    return (
      <div className={`rounded-xl border border-panel-border bg-panel ${className}`.trim()}>
        <div className="space-y-2 p-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-10 animate-pulse rounded bg-surface-muted" />
          ))}
        </div>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className={`rounded-xl border border-panel-border bg-panel p-6 text-sm text-muted-foreground ${className}`.trim()}>
        No test results yet.
      </div>
    );
  }

  return (
    <div className={`rounded-xl border border-panel-border bg-panel ${className}`.trim()}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-panel-border p-3">
        <div className="text-xs text-muted-foreground">
          Server-sorted by <span className="font-semibold text-panel-foreground">{sortKey}</span> ({sortOrder})
        </div>
        <div className="text-xs text-muted-foreground">
          {results.length} loaded / {typeof total === 'number' ? total : results.length} total
          {typeof totalTestsOverall === 'number' && (
            <span> (out of {totalTestsOverall} total tests)</span>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-surface-overlay/70 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left">Details</th>
              <th className="px-3 py-2 text-left">
                <button type="button" className="font-semibold" onClick={() => setSort('name')}>Test</button>
              </th>
              <th className="px-3 py-2 text-left">
                <button type="button" className="font-semibold" onClick={() => setSort('status')}>Status</button>
              </th>
              <th className="px-3 py-2 text-left">
                <button type="button" className="font-semibold" onClick={() => setSort('duration')}>Duration</button>
              </th>
              <th className="px-3 py-2 text-left">Error Preview</th>
            </tr>
          </thead>
          <tbody>
            {results.map(result => {
              const definition = definitions[result.testId];
              const expanded = Boolean(expandedRows[result.testId]);
              return (
                <React.Fragment key={`${result.runId}:${result.testId}`}>
                  <tr className="border-t border-panel-border text-foreground">
                    <td className="px-3 py-2 align-top">
                      <button
                        type="button"
                        onClick={() => toggleRow(result.testId)}
                        className="rounded border border-panel-border bg-surface-muted p-1 text-muted-foreground hover:text-panel-foreground"
                        aria-label={expanded ? 'Collapse row' : 'Expand row'}
                      >
                        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </button>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="font-medium text-panel-foreground">{definition?.name || result.testId}</div>
                      <div className="font-mono text-xs text-muted-foreground">{definition?.path || result.testId}</div>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <TestStatusBadge status={result.status} size="md" />
                    </td>
                    <td className="px-3 py-2 align-top text-muted-foreground">{formatDuration(result.durationMs)}</td>
                    <td className="px-3 py-2 align-top text-muted-foreground">{previewError(result.errorMessage)}</td>
                  </tr>
                  {expanded && (
                    <tr className="border-t border-panel-border/80 bg-surface-overlay/60">
                      <td colSpan={5} className="px-3 py-3">
                        <div className="rounded-lg border border-panel-border bg-surface-overlay p-3">
                          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Full Error</p>
                          <pre className="whitespace-pre-wrap break-words font-mono text-xs text-rose-200">
                            {result.errorMessage || 'No error message.'}
                          </pre>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {(error || hasMore || isLoadingMore) && (
        <div className="flex items-center justify-between border-t border-panel-border px-3 py-2">
          <div className="text-xs text-rose-300">{error || ''}</div>
          {hasMore && onLoadMore && (
            <button
              type="button"
              onClick={onLoadMore}
              disabled={isLoadingMore}
              className="rounded border border-panel-border bg-surface-muted px-3 py-1.5 text-xs text-panel-foreground hover:border-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoadingMore ? 'Loading more…' : 'Load more'}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export type { TestResultTableProps };
