import React, { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';

import { ExecutionRun } from '@/types';

interface ExecutionApprovalDialogProps {
  open: boolean;
  run: ExecutionRun | null;
  loading?: boolean;
  onClose: () => void;
  onSubmit: (decision: 'approved' | 'denied', reason: string) => void;
}

export const ExecutionApprovalDialog: React.FC<ExecutionApprovalDialogProps> = ({
  open,
  run,
  loading = false,
  onClose,
  onSubmit,
}) => {
  const [reason, setReason] = useState('');

  useEffect(() => {
    if (!open) return;
    setReason('');
  }, [open, run?.id]);

  if (!open || !run) return null;

  return (
    <div className="fixed inset-0 z-[80] bg-black/50 backdrop-blur-[1px] flex items-center justify-center p-4">
      <div className="w-full max-w-2xl rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-amber-200">
            <AlertTriangle size={16} />
            <h3 className="text-sm font-semibold">Execution Approval Required</h3>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="p-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500 disabled:opacity-50"
          >
            <X size={14} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          <p className="text-sm text-slate-300">
            This command was classified as <span className="font-semibold text-amber-200">{run.riskLevel}</span> risk and is blocked pending approval.
          </p>
          <div className="rounded border border-slate-700 bg-slate-950 p-2">
            <p className="text-[11px] uppercase text-slate-500 mb-1">Command</p>
            <code className="text-xs text-emerald-300 break-all">{run.sourceCommand}</code>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2">
            <p className="text-[11px] uppercase text-slate-500 mb-1">Working Directory</p>
            <p className="text-xs text-slate-300 break-all">{run.cwd}</p>
          </div>
          <label className="block">
            <span className="text-[11px] uppercase text-slate-500">Reason (optional)</span>
            <textarea
              value={reason}
              onChange={event => setReason(event.target.value)}
              rows={3}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
              placeholder="Add rationale for audit trail"
            />
          </label>
        </div>

        <div className="px-4 py-3 border-t border-slate-800 flex items-center justify-end gap-2">
          <button
            onClick={() => onSubmit('denied', reason)}
            disabled={loading}
            className="px-3 py-1.5 rounded border border-rose-500/40 bg-rose-500/10 text-rose-100 text-xs disabled:opacity-50"
          >
            Deny
          </button>
          <button
            onClick={() => onSubmit('approved', reason)}
            disabled={loading}
            className="px-3 py-1.5 rounded border border-emerald-500/40 bg-emerald-500/15 text-emerald-100 text-xs disabled:opacity-50"
          >
            Approve and Run
          </button>
        </div>
      </div>
    </div>
  );
};
