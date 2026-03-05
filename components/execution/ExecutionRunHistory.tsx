import React from 'react';
import { RefreshCw } from 'lucide-react';

import { ExecutionRun } from '@/types';

interface ExecutionRunHistoryProps {
  runs: ExecutionRun[];
  selectedRunId: string;
  loading?: boolean;
  onSelect: (runId: string) => void;
  onRefresh: () => void;
}

const statusClass = (status: string): string => {
  const normalized = (status || '').toLowerCase();
  if (normalized === 'succeeded') return 'text-emerald-200 border-emerald-500/40 bg-emerald-500/15';
  if (normalized === 'failed') return 'text-rose-200 border-rose-500/40 bg-rose-500/15';
  if (normalized === 'running') return 'text-amber-200 border-amber-500/40 bg-amber-500/15';
  if (normalized === 'canceled') return 'text-slate-200 border-slate-500/40 bg-slate-500/15';
  if (normalized === 'blocked') return 'text-orange-200 border-orange-500/40 bg-orange-500/15';
  return 'text-indigo-200 border-indigo-500/40 bg-indigo-500/15';
};

const riskClass = (risk: string): string => {
  const normalized = (risk || '').toLowerCase();
  if (normalized === 'high') return 'text-rose-300';
  if (normalized === 'medium') return 'text-amber-300';
  return 'text-emerald-300';
};

const fmt = (value: string): string => {
  const parsed = Date.parse(value || '');
  if (Number.isNaN(parsed)) return '—';
  return new Date(parsed).toLocaleString();
};

export const ExecutionRunHistory: React.FC<ExecutionRunHistoryProps> = ({
  runs,
  selectedRunId,
  loading = false,
  onSelect,
  onRefresh,
}) => (
  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 space-y-3">
    <div className="flex items-center justify-between gap-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">Run History</p>
      <button
        onClick={onRefresh}
        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded border border-slate-700 text-slate-300 hover:border-slate-500"
      >
        <RefreshCw size={12} />
        Refresh
      </button>
    </div>

    {loading && <div className="text-xs text-slate-400">Loading runs...</div>}
    {!loading && runs.length === 0 && <div className="text-xs text-slate-500">No runs yet for this feature.</div>}
    {!loading && runs.length > 0 && (
      <div className="space-y-2 max-h-[320px] overflow-auto pr-1">
        {runs.map(run => (
          <button
            key={run.id}
            onClick={() => onSelect(run.id)}
            className={`w-full text-left rounded-md border p-2 transition-colors ${
              selectedRunId === run.id
                ? 'border-indigo-500/60 bg-indigo-500/10'
                : 'border-slate-800 bg-slate-900/70 hover:border-slate-700'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <code className="text-[11px] text-cyan-200 truncate">{run.sourceCommand}</code>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${statusClass(run.status)}`}>
                {run.status}
              </span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-slate-500">
              <span className={riskClass(run.riskLevel)}>{run.riskLevel} risk</span>
              <span>{fmt(run.createdAt)}</span>
            </div>
          </button>
        ))}
      </div>
    )}
  </div>
);
