import { ExternalLink, GitBranch, GitPullRequest, PanelRightOpen, Play, Terminal } from 'lucide-react';

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

interface CommandCenterFeatureCardProps {
  item: PlanningCommandCenterItem;
  commandValue: string;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

export function CommandCenterFeatureCard({
  item,
  commandValue,
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

  return (
    <article
      className="flex min-h-[270px] flex-col rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-4"
      data-testid="command-center-feature-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-[14px] font-semibold text-[color:var(--ink-0)]" title={commandCenterDisplayName(item)}>
            {commandCenterDisplayName(item)}
          </h3>
          <p className="planning-mono mt-0.5 truncate text-[10.5px] text-[color:var(--ink-4)]" title={featureId}>
            {item.feature.featureSlug || featureId}
          </p>
        </div>
        <StatusPill status={item.status.effectiveStatus || item.status.rawStatus || 'unknown'} />
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
      <div className="mt-3 space-y-2 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] p-3">
        <div className="planning-caps text-[9.5px] text-[color:var(--ink-4)]">next command</div>
        <p className="planning-mono line-clamp-2 text-[10.5px] leading-relaxed text-[color:var(--ink-1)]" title={commandValue}>
          {commandValue || 'No next command resolved'}
        </p>
      </div>
      <div className="mt-3 space-y-2">
        <div className="flex min-w-0 items-center gap-2 text-[10.5px] text-[color:var(--ink-3)]">
          <GitBranch size={12} className="shrink-0" aria-hidden />
          <span className="planning-mono truncate" title={item.worktree?.branch || ''}>
            {item.worktree?.branch || 'branch TBD'}
          </span>
          <span className="planning-mono shrink-0">{item.gitState?.head || 'commit TBD'}</span>
        </div>
        <div className="planning-mono truncate text-[10.5px] text-[color:var(--ink-4)]" title={planPath}>
          {planPath ? compactPath(planPath, 74) : 'target plan TBD'}
        </div>
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
  );
}
