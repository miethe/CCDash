import { GitBranch, GitCommitHorizontal } from 'lucide-react';

import type {
  PlanningCommandCenterGitState,
  PlanningCommandCenterWorktree,
} from '@/types';
import { compactPath } from './commandCenterUtils';
import { Chip, Dot } from '../primitives';

interface WorktreeGitStatePanelProps {
  worktree?: PlanningCommandCenterWorktree | null;
  gitState?: PlanningCommandCenterGitState | null;
}

function dirtyTone(gitState?: PlanningCommandCenterGitState | null): string {
  if (!gitState?.pathExists) return 'var(--ink-4)';
  if ((gitState.dirtyCount ?? 0) > 0) return 'var(--warn)';
  return 'var(--ok)';
}

export function WorktreeGitStatePanel({ worktree, gitState }: WorktreeGitStatePanelProps) {
  if (!worktree && !gitState) {
    return (
      <div className="rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] px-3 py-2 text-[11px] text-[color:var(--ink-4)]">
        No worktree context is linked yet.
      </div>
    );
  }

  return (
    <div
      className="grid gap-2 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-3 text-[11px] text-[color:var(--ink-2)] md:grid-cols-[1.3fr_1fr]"
      data-testid="command-center-worktree-git"
    >
      <div className="min-w-0 space-y-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <GitBranch size={13} style={{ color: 'var(--brand)' }} aria-hidden />
          <span className="planning-mono truncate text-[color:var(--ink-1)]" title={worktree?.branch || gitState?.upstream || ''}>
            {worktree?.branch || gitState?.upstream || 'branch unknown'}
          </span>
        </div>
        <div className="planning-mono truncate text-[10px] text-[color:var(--ink-4)]" title={worktree?.path || ''}>
          {worktree?.path ? compactPath(worktree.path, 92) : 'worktree path not recorded'}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Chip className="planning-mono text-[10px]">
          <Dot tone={dirtyTone(gitState)} />
          {gitState?.pathExists === false ? 'missing' : `${gitState?.dirtyCount ?? 0} dirty`}
        </Chip>
        <Chip className="planning-mono text-[10px]">
          <GitCommitHorizontal size={12} aria-hidden />
          {gitState?.head || 'head unknown'}
        </Chip>
        <Chip className="planning-mono text-[10px]">
          ahead {gitState?.ahead ?? 0} / behind {gitState?.behind ?? 0}
        </Chip>
      </div>
      {gitState?.warnings.length ? (
        <div className="md:col-span-2">
          {gitState.warnings.map((warning) => (
            <p key={warning} className="planning-mono text-[10px] text-[color:var(--warn)]">{warning}</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
