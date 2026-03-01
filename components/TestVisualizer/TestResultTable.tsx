import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { TestDefinition, TestResult, TestStatus } from '../../types';
import { TestStatusBadge } from './TestStatusBadge';

interface TestResultTableProps {
  results: TestResult[];
  definitions?: Record<string, TestDefinition>;
  isLoading?: boolean;
  className?: string;
}

type SortKey = 'status' | 'duration' | 'name';

const STATUS_ORDER: TestStatus[] = ['error', 'failed', 'xpassed', 'xfailed', 'skipped', 'running', 'unknown', 'passed'];

const formatDuration = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

const sortStatusIndex = (status: TestStatus): number => {
  const index = STATUS_ORDER.indexOf(status);
  return index >= 0 ? index : STATUS_ORDER.length;
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
  className = '',
}) => {
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [statusFilter, setStatusFilter] = useState<TestStatus | 'all'>('all');
  const [sortKey, setSortKey] = useState<SortKey>('status');
  const [ascending, setAscending] = useState(true);

  const availableStatuses = useMemo(() => {
    const unique = new Set<TestStatus>();
    results.forEach(result => unique.add(result.status));
    return Array.from(unique);
  }, [results]);

  const rows = useMemo(() => {
    const filtered = statusFilter === 'all' ? results : results.filter(result => result.status === statusFilter);
    const sorted = [...filtered].sort((a, b) => {
      if (sortKey === 'duration') {
        return ascending ? a.durationMs - b.durationMs : b.durationMs - a.durationMs;
      }
      if (sortKey === 'name') {
        const nameA = definitions[a.testId]?.name || a.testId;
        const nameB = definitions[b.testId]?.name || b.testId;
        return ascending ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA);
      }
      const scoreA = sortStatusIndex(a.status);
      const scoreB = sortStatusIndex(b.status);
      return ascending ? scoreA - scoreB : scoreB - scoreA;
    });
    return sorted;
  }, [results, statusFilter, sortKey, ascending, definitions]);

  const setSort = (nextKey: SortKey) => {
    if (nextKey === sortKey) {
      setAscending(prev => !prev);
      return;
    }
    setSortKey(nextKey);
    setAscending(true);
  };

  const toggleRow = (testId: string) => {
    setExpandedRows(prev => ({ ...prev, [testId]: !prev[testId] }));
  };

  if (isLoading) {
    return (
      <div className={`rounded-xl border border-slate-800 bg-slate-900 ${className}`.trim()}>
        <div className="space-y-2 p-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-10 animate-pulse rounded bg-slate-800" />
          ))}
        </div>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className={`rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-500 ${className}`.trim()}>
        No test results yet.
      </div>
    );
  }

  return (
    <div className={`rounded-xl border border-slate-800 bg-slate-900 ${className}`.trim()}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 p-3">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <label htmlFor="status-filter" className="font-semibold text-slate-300">Status</label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={event => setStatusFilter(event.target.value as TestStatus | 'all')}
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
          >
            <option value="all">All</option>
            {availableStatuses.map(status => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
        </div>
        <div className="text-xs text-slate-500">{rows.length} visible / {results.length} total</div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-950/40 text-xs uppercase tracking-wide text-slate-500">
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
            {rows.map(result => {
              const definition = definitions[result.testId];
              const expanded = Boolean(expandedRows[result.testId]);
              return (
                <React.Fragment key={`${result.runId}:${result.testId}`}>
                  <tr className="border-t border-slate-800 text-slate-300">
                    <td className="px-3 py-2 align-top">
                      <button
                        type="button"
                        onClick={() => toggleRow(result.testId)}
                        className="rounded border border-slate-700 bg-slate-800 p-1 text-slate-400 hover:text-slate-200"
                        aria-label={expanded ? 'Collapse row' : 'Expand row'}
                      >
                        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </button>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="font-medium text-slate-200">{definition?.name || result.testId}</div>
                      <div className="font-mono text-xs text-slate-500">{definition?.path || result.testId}</div>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <TestStatusBadge status={result.status} size="md" />
                    </td>
                    <td className="px-3 py-2 align-top text-slate-400">{formatDuration(result.durationMs)}</td>
                    <td className="px-3 py-2 align-top text-slate-400">{previewError(result.errorMessage)}</td>
                  </tr>
                  {expanded && (
                    <tr className="border-t border-slate-800/70 bg-slate-950/30">
                      <td colSpan={5} className="px-3 py-3">
                        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Full Error</p>
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
    </div>
  );
};

export type { TestResultTableProps };
