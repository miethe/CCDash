import React from 'react';
import { Clock, Link2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { TestRun } from '../../types';
import { HealthSummaryBar } from './HealthSummaryBar';
import { TestStatusBadge } from './TestStatusBadge';

interface TestRunCardProps {
  run: TestRun;
  showSession?: boolean;
  compact?: boolean;
  className?: string;
}

const shortHash = (value: string, length = 7): string => (value || '').slice(0, length);

const formatDuration = (durationMs: number): string => {
  if (durationMs < 1000) return `${durationMs}ms`;
  const seconds = Math.floor(durationMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${mins}m ${rem}s`;
};

const toStatus = (status: TestRun['status']) => {
  if (status === 'failed') return 'failed';
  if (status === 'running') return 'running';
  return 'passed';
};

const triggerChipClass = (trigger: string): string => {
  if (trigger === 'ci') return 'border-cyan-500/35 bg-cyan-500/10 text-cyan-300';
  if (trigger === 'local') return 'border-slate-600/45 bg-slate-700/30 text-slate-300';
  return 'border-indigo-500/35 bg-indigo-500/10 text-indigo-300';
};

export const TestRunCard: React.FC<TestRunCardProps> = ({ run, showSession = false, compact = false, className = '' }) => {
  const navigate = useNavigate();

  const onOpenRun = () => {
    navigate(`/tests?runId=${encodeURIComponent(run.runId)}`);
  };

  const handleKeyDown: React.KeyboardEventHandler<HTMLElement> = event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpenRun();
    }
  };

  return (
    <article
      role="article"
      aria-label={`Test run ${shortHash(run.runId)}, ${run.passedTests} passed, ${run.failedTests} failed, ${run.skippedTests} skipped`}
      tabIndex={0}
      onClick={onOpenRun}
      onKeyDown={handleKeyDown}
      className={`min-w-[280px] rounded-xl border border-slate-800 bg-slate-900 p-4 transition-colors duration-150 hover:border-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${run.status === 'running' ? 'border-l-2 border-l-indigo-400 motion-safe:animate-pulse motion-reduce:animate-none' : ''} ${className}`.trim()}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-200">
            {shortHash(run.runId)}
          </span>
          <span className={`rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${triggerChipClass(run.trigger)}`}>
            {run.trigger}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <TestStatusBadge status={toStatus(run.status)} size="sm" />
          <span>{new Date(run.timestamp).toLocaleString()}</span>
        </div>
      </div>

      <HealthSummaryBar
        passed={run.passedTests}
        failed={run.failedTests}
        skipped={run.skippedTests}
        total={run.totalTests}
      />

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        {!compact && run.gitSha && (
          <span className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
            {shortHash(run.gitSha)}
          </span>
        )}
        {!compact && run.branch && (
          <span className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
            {run.branch}
          </span>
        )}
        <span className="inline-flex items-center gap-1 text-slate-500">
          <Clock size={12} aria-hidden="true" />
          {formatDuration(run.durationMs)}
        </span>
        {showSession && !compact && run.agentSessionId && (
          <Link
            to={`/sessions?session=${encodeURIComponent(run.agentSessionId)}`}
            className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300"
            onClick={event => event.stopPropagation()}
          >
            <Link2 size={12} aria-hidden="true" />
            Session
          </Link>
        )}
      </div>
    </article>
  );
};

export type { TestRunCardProps };
