import React, { useMemo } from 'react';
import { Ban, RotateCcw, Square, Terminal } from 'lucide-react';

import { ExecutionRun, ExecutionRunEvent } from '@/types';

interface ExecutionRunPanelProps {
  run: ExecutionRun | null;
  events: ExecutionRunEvent[];
  loading?: boolean;
  onCancel: (run: ExecutionRun) => void;
  onRetry: (run: ExecutionRun) => void;
  onOpenApproval: (run: ExecutionRun) => void;
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

const fmt = (value: string): string => {
  const parsed = Date.parse(value || '');
  if (Number.isNaN(parsed)) return '—';
  return new Date(parsed).toLocaleString();
};

export const ExecutionRunPanel: React.FC<ExecutionRunPanelProps> = ({
  run,
  events,
  loading = false,
  onCancel,
  onRetry,
  onOpenApproval,
}) => {
  const output = useMemo(
    () => events.map(event => event.payloadText || '').filter(Boolean).join(''),
    [events],
  );

  if (!run) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-500">
        Select a run to view lifecycle events and output.
      </div>
    );
  }

  const canCancel = run.status === 'queued' || run.status === 'running';
  const canRetry = run.status === 'failed' || run.status === 'canceled' || run.status === 'blocked';
  const needsApproval = run.requiresApproval && run.status === 'blocked' && !run.approvedAt;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Active Run</p>
          <code className="text-sm text-emerald-300 break-all">{run.sourceCommand}</code>
        </div>
        <span className={`text-[10px] px-2 py-1 rounded border ${statusClass(run.status)}`}>{run.status}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
        <div className="rounded border border-slate-800 bg-slate-900/60 p-2">
          <p className="text-slate-500 uppercase text-[10px]">Working Dir</p>
          <p className="text-slate-300 break-all">{run.cwd}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/60 p-2">
          <p className="text-slate-500 uppercase text-[10px]">Policy</p>
          <p className="text-slate-300">{run.policyVerdict} • {run.riskLevel}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/60 p-2">
          <p className="text-slate-500 uppercase text-[10px]">Started</p>
          <p className="text-slate-300">{fmt(run.startedAt || run.createdAt)}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/60 p-2">
          <p className="text-slate-500 uppercase text-[10px]">Ended</p>
          <p className="text-slate-300">{fmt(run.endedAt)}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {needsApproval && (
          <button
            onClick={() => onOpenApproval(run)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-amber-500/40 bg-amber-500/15 text-amber-100 text-xs"
          >
            <Ban size={13} />
            Review Approval
          </button>
        )}
        {canCancel && (
          <button
            onClick={() => onCancel(run)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-rose-500/40 bg-rose-500/10 text-rose-100 text-xs"
          >
            <Square size={13} />
            Cancel
          </button>
        )}
        {canRetry && (
          <button
            onClick={() => onRetry(run)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-indigo-500/40 bg-indigo-500/15 text-indigo-100 text-xs"
          >
            <RotateCcw size={13} />
            Retry
          </button>
        )}
      </div>

      <div className="rounded border border-slate-800 bg-black/50 overflow-hidden">
        <div className="px-2 py-1 border-b border-slate-800 text-[11px] text-slate-400 uppercase tracking-wide flex items-center gap-1.5">
          <Terminal size={12} />
          Live Output
        </div>
        <pre className="m-0 p-3 text-[12px] leading-5 font-mono text-slate-200 max-h-[360px] overflow-auto whitespace-pre-wrap break-words">
          {loading ? 'Loading run output...' : (output || 'No output available yet.')}
        </pre>
      </div>
    </div>
  );
};
