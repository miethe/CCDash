import { useCallback, useState } from 'react';
import { Check, Copy, ExternalLink, GitBranch, GitPullRequest, PanelRightOpen, Play, Terminal } from 'lucide-react';

import type { PlanningCommandCenterItem } from '@/types';
import {
  canLaunchCommandCenterItem,
  commandCenterDisplayName,
  commandCenterDoneLabel,
  commandCenterLaunchReadiness,
  commandCenterPlanPath,
  compactPath,
} from './commandCenterUtils';
import { ArtifactChip, BtnGhost, BtnPrimary, Chip, StatusPill } from '../primitives';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { formatLastActivity } from '@/lib/planningHelpers';

interface CommandCenterFeatureCardProps {
  item: PlanningCommandCenterItem;
  commandValue: string;
  onCopyCommand?: (command: string) => void;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

export function CommandCenterFeatureCard({
  item,
  commandValue,
  onCopyCommand,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: CommandCenterFeatureCardProps) {
  const featureId = item.feature.featureId;
  const planPath = commandCenterPlanPath(item);
  const doneLabel = commandCenterDoneLabel(item);
  const canLaunch = canLaunchCommandCenterItem(item);

  // Last-activity display (Issue 4)
  const lastActivityTimestamp = item.lastActivity?.timestamp;
  const lastActivityDisplay = formatLastActivity(
    typeof lastActivityTimestamp === 'string' ? lastActivityTimestamp : null,
  );

  // Local copied affordance for the command copy button
  const [cmdCopied, setCmdCopied] = useState(false);
  const handleCopyCommand = useCallback(() => {
    if (!commandValue) return;
    onCopyCommand?.(commandValue);
    setCmdCopied(true);
    window.setTimeout(() => setCmdCopied(false), 1600);
  }, [commandValue, onCopyCommand]);

  // Local copied affordance for branch copy
  const [branchCopied, setBranchCopied] = useState(false);
  const handleCopyBranch = useCallback(() => {
    const branch = item.worktree?.branch;
    if (!branch) return;
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(branch).then(() => {
        setBranchCopied(true);
        window.setTimeout(() => setBranchCopied(false), 1600);
      });
    }
  }, [item.worktree?.branch]);

  return (
    <TooltipProvider>
      <article
        className="relative flex min-h-[270px] flex-col rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-4"
        data-testid="command-center-feature-card"
      >
        {/* Status pill — absolute top-right, smaller */}
        <StatusPill
          status={item.status.effectiveStatus || item.status.rawStatus || 'unknown'}
          className="absolute top-2 right-2"
          style={{ fontSize: '9.5px', padding: '1px 5px' }}
        />

        {/* Title + slug — full-width zone, right-padded to avoid pill overlap */}
        <div className="min-w-0 pr-20">
          <h3
            className="truncate text-[14px] font-semibold text-[color:var(--ink-0)]"
            title={commandCenterDisplayName(item)}
          >
            {commandCenterDisplayName(item)}
          </h3>
          <p
            className="planning-mono mt-0.5 truncate text-[10.5px] text-[color:var(--ink-4)]"
            title={featureId}
          >
            {item.feature.featureSlug || featureId}
          </p>
        </div>

        <p className="mt-3 line-clamp-2 min-h-[34px] text-[11.5px] leading-relaxed text-[color:var(--ink-3)]">
          {item.feature.summary || 'No feature summary recorded.'}
        </p>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <Chip className="planning-mono justify-center text-[10px]">
            P{item.phase.currentPhase ?? '-'} / {item.phase.totalPhases || '-'}
          </Chip>
          <Chip className="planning-mono justify-center text-[10px]">
            {item.storyPoints.remaining}/{item.storyPoints.total} pts
          </Chip>
          <Chip className="planning-mono justify-center text-[10px]">{commandCenterLaunchReadiness(item)}</Chip>
        </div>

        {/* Next command box — tooltip wraps the whole box; copy button inside */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className="mt-3 cursor-default space-y-2 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] p-3"
              data-testid="command-center-next-command-box"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="planning-caps text-[9.5px] text-[color:var(--ink-4)]">next command</div>
                <button
                  type="button"
                  aria-label="Copy command"
                  disabled={!commandValue}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCopyCommand();
                  }}
                  className="shrink-0 rounded-[var(--radius-sm)] p-0.5 text-[color:var(--ink-3)] transition-colors hover:text-[color:var(--ink-0)] disabled:pointer-events-none disabled:opacity-40"
                  data-testid="command-center-copy-command-btn"
                >
                  {cmdCopied ? (
                    <Check size={11} aria-hidden style={{ color: 'var(--ok)' }} />
                  ) : (
                    <Copy size={11} aria-hidden />
                  )}
                </button>
              </div>
              <p
                className="planning-mono line-clamp-2 text-[10.5px] leading-relaxed text-[color:var(--ink-1)]"
                title={commandValue}
              >
                {commandValue || 'No next command resolved'}
              </p>
            </div>
          </TooltipTrigger>
          {commandValue ? (
            <TooltipContent
              side="bottom"
              className="max-w-[520px] whitespace-pre-wrap break-words rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-3 py-2 text-[10.5px] text-[color:var(--ink-1)] shadow-lg planning-mono"
              data-testid="command-center-command-tooltip"
            >
              {commandValue}
            </TooltipContent>
          ) : null}
        </Tooltip>

        {/* Branch row — click to copy branch name */}
        <div className="mt-3 space-y-2">
          <div className="flex min-w-0 items-center gap-2 text-[10.5px] text-[color:var(--ink-3)]">
            <GitBranch size={12} className="shrink-0" aria-hidden />
            {item.worktree?.branch ? (
              <button
                type="button"
                aria-label="Copy branch name"
                onClick={handleCopyBranch}
                className="planning-mono min-w-0 truncate cursor-pointer rounded-[var(--radius-sm)] px-0.5 text-left text-[10.5px] text-[color:var(--ink-3)] transition-colors hover:text-[color:var(--ink-0)]"
                title={item.worktree.branch}
                data-testid="command-center-branch-copy-btn"
              >
                {branchCopied ? (
                  <span className="text-[color:var(--ok)]">copied!</span>
                ) : (
                  item.worktree.branch
                )}
              </button>
            ) : (
              <span className="planning-mono truncate" title="">
                branch TBD
              </span>
            )}
            <span className="planning-mono shrink-0">{item.gitState?.head || 'commit TBD'}</span>
          </div>
          <div
            className="planning-mono truncate text-[10.5px] text-[color:var(--ink-4)]"
            title={planPath}
          >
            {planPath ? compactPath(planPath, 74) : 'target plan TBD'}
          </div>
          {/* Issue 4: Last-activity indicator */}
          {lastActivityDisplay ? (
            <div
              className="planning-mono text-[10px] text-[color:var(--ink-4)]"
              title={lastActivityDisplay.title}
              data-testid="command-center-last-activity"
            >
              {lastActivityDisplay.label}
            </div>
          ) : null}
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {item.artifacts.slice(0, 5).map((artifact) => (
            <ArtifactChip
              key={`${artifact.docType}:${artifact.path}`}
              kind={artifact.docType}
              label={artifact.docType === 'implementation_plan' ? 'plan' : artifact.docType || 'doc'}
              active={artifact.path === planPath}
            />
          ))}
        </div>
        {doneLabel ? (
          <Chip className="planning-mono mt-3 w-fit text-[10px]">{doneLabel}</Chip>
        ) : null}
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
          <BtnPrimary size="sm" disabled={!canLaunch} onClick={() => onOpenLaunch?.(featureId)}>
            <Play size={13} aria-hidden />
            launch
          </BtnPrimary>
          <BtnGhost size="sm" onClick={() => onOpenExecution?.(featureId)}>
            <Terminal size={13} aria-hidden />
            workbench
          </BtnGhost>
          <BtnGhost size="sm" disabled={!planPath} onClick={() => onOpenPlan?.(planPath)}>
            <ExternalLink size={13} aria-hidden />
            plan
          </BtnGhost>
          <BtnGhost
            size="sm"
            disabled={!item.pullRequest?.url}
            onClick={() => item.pullRequest?.url && onOpenPullRequest?.(item.pullRequest.url)}
          >
            <GitPullRequest size={13} aria-hidden />
            PR
          </BtnGhost>
          <BtnGhost size="sm" onClick={() => onOpenDetail?.(featureId)}>
            <PanelRightOpen size={13} aria-hidden />
            details
          </BtnGhost>
        </div>
      </article>
    </TooltipProvider>
  );
}
