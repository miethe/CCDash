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
  selected?: boolean;
  onSelect?: (run: TestRun) => void;
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
  if (trigger === 'ci') return 'border-info-border bg-info/10 text-info-foreground';
  if (trigger === 'local') return 'border-panel-border bg-surface-muted text-muted-foreground';
  return 'border-success-border bg-success/10 text-success-foreground';
};

export const TestRunCard: React.FC<TestRunCardProps> = ({
  run,
  showSession = false,
  compact = false,
  className = '',
  selected = false,
  onSelect,
}) => {
  const navigate = useNavigate();

  const onOpenRun = () => {
    if (onSelect) {
      onSelect(run);
      return;
    }
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
      aria-current={selected ? 'true' : undefined}
      tabIndex={0}
      onClick={onOpenRun}
      onKeyDown={handleKeyDown}
      className={`min-w-[280px] rounded-xl border bg-panel p-4 text-panel-foreground transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus/30 focus-visible:ring-offset-2 focus-visible:ring-offset-app-background ${selected ? 'border-info-border bg-info/10' : 'border-panel-border hover:border-hover'} ${run.status === 'running' ? 'border-l-2 border-l-info motion-safe:animate-pulse motion-reduce:animate-none' : ''} ${className}`.trim()}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded border border-panel-border bg-surface-overlay/80 px-2 py-0.5 font-mono text-xs text-panel-foreground">
            {shortHash(run.runId)}
          </span>
          <span className={`rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${triggerChipClass(run.trigger)}`}>
            {run.trigger}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
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

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {!compact && run.gitSha && (
          <span className="rounded border border-panel-border bg-surface-overlay/80 px-1.5 py-0.5 font-mono text-[10px] text-panel-foreground">
            {shortHash(run.gitSha)}
          </span>
        )}
        {!compact && run.branch && (
          <span className="rounded border border-panel-border bg-surface-overlay/80 px-1.5 py-0.5 font-mono text-[10px] text-panel-foreground">
            {run.branch}
          </span>
        )}
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <Clock size={12} aria-hidden="true" />
          {formatDuration(run.durationMs)}
        </span>
        {showSession && !compact && run.agentSessionId && (
          <Link
            to={`/sessions?session=${encodeURIComponent(run.agentSessionId)}`}
            className="inline-flex items-center gap-1 text-info-foreground hover:text-info"
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
