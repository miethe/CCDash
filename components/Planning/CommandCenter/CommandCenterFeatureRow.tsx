import { ChevronDown, ChevronRight, FileText, GitBranch, ShieldAlert } from 'lucide-react';

import type { PlanningCommandCenterItem } from '@/types';
import {
  appendRelatedFileToCommand,
  commandCenterDisplayName,
  commandCenterDoneLabel,
  commandCenterLaunchReadiness,
  commandCenterPlanPath,
  compactPath,
} from './commandCenterUtils';
import { EditableCommandField } from './EditableCommandField';
import { PhasePlanTable } from './PhasePlanTable';
import { QuickCommandBar } from './QuickCommandBar';
import { RelatedFilesPicker } from './RelatedFilesPicker';
import { WorktreeGitStatePanel } from './WorktreeGitStatePanel';
import { ArtifactChip, Chip, StatusPill } from '../primitives';

interface CommandCenterFeatureRowProps {
  item: PlanningCommandCenterItem;
  expanded: boolean;
  commandValue: string;
  onToggleExpanded: (featureId: string) => void;
  onCommandChange: (featureId: string, command: string) => void;
  onCopyCommand?: (command: string) => void;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

function artifactLabel(docType: string): string {
  if (docType === 'implementation_plan') return 'plan';
  return docType || 'doc';
}

export function CommandCenterFeatureRow({
  item,
  expanded,
  commandValue,
  onToggleExpanded,
  onCommandChange,
  onCopyCommand,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: CommandCenterFeatureRowProps) {
  const featureId = item.feature.featureId;
  const displayName = commandCenterDisplayName(item);
  const planPath = commandCenterPlanPath(item);
  const doneLabel = commandCenterDoneLabel(item);
  const readiness = commandCenterLaunchReadiness(item);

  return (
    <article
      className="overflow-hidden rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)]"
      data-testid="command-center-feature-row"
    >
      <button
        type="button"
        className="grid w-full grid-cols-[minmax(220px,1.5fr)_minmax(120px,0.55fr)_minmax(120px,0.55fr)_minmax(140px,0.7fr)_minmax(220px,1fr)_minmax(180px,0.8fr)] items-stretch gap-0 text-left transition-colors hover:bg-[color:var(--bg-2)] max-xl:grid-cols-1"
        onClick={() => onToggleExpanded(featureId)}
        aria-expanded={expanded}
      >
        <div className="min-w-0 border-b border-[color:var(--line-1)] px-3 py-3 xl:border-b-0 xl:border-r">
          <div className="flex min-w-0 items-center gap-2">
            {expanded ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
            <div className="min-w-0">
              <h3 className="truncate text-[13px] font-semibold text-[color:var(--ink-0)]" title={displayName}>
                {displayName}
              </h3>
              <p className="planning-mono truncate text-[10.5px] text-[color:var(--ink-4)]" title={featureId}>
                {item.feature.featureSlug || featureId}
              </p>
            </div>
          </div>
          {item.feature.summary ? (
            <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-[color:var(--ink-3)]">
              {item.feature.summary}
            </p>
          ) : null}
        </div>
        <div className="space-y-2 border-b border-[color:var(--line-1)] px-3 py-3 xl:border-b-0 xl:border-r">
          <StatusPill status={item.status.effectiveStatus || item.status.rawStatus || 'unknown'} />
          {item.status.isMismatch ? <Chip className="planning-mono text-[9.5px]">mismatch</Chip> : null}
          {doneLabel ? <Chip className="planning-mono text-[9.5px]">{doneLabel}</Chip> : null}
        </div>
        <div className="space-y-1 border-b border-[color:var(--line-1)] px-3 py-3 xl:border-b-0 xl:border-r">
          <div className="planning-caps text-[9.5px] text-[color:var(--ink-4)]">phase</div>
          <div className="planning-mono text-[12px] text-[color:var(--ink-1)]">
            {item.phase.currentPhase ? `P${item.phase.currentPhase}` : 'not started'}
            {item.phase.totalPhases ? ` / ${item.phase.totalPhases}` : ''}
          </div>
          <div className="planning-tnum text-[10.5px] text-[color:var(--ink-3)]">
            {item.storyPoints.remaining}/{item.storyPoints.total} pts left
          </div>
        </div>
        <div className="space-y-2 border-b border-[color:var(--line-1)] px-3 py-3 xl:border-b-0 xl:border-r">
          <Chip className="planning-mono text-[10px]">
            <GitBranch size={12} aria-hidden />
            {item.worktree?.branch || 'branch TBD'}
          </Chip>
          <Chip className="planning-mono text-[10px]">
            {item.gitState?.head || 'commit TBD'}
          </Chip>
          <Chip className="planning-mono text-[10px]">{readiness}</Chip>
        </div>
        <div className="min-w-0 space-y-2 border-b border-[color:var(--line-1)] px-3 py-3 xl:border-b-0 xl:border-r">
          <div className="planning-mono truncate text-[10.5px] text-[color:var(--ink-1)]" title={commandValue}>
            {commandValue || 'No next command resolved'}
          </div>
          <div className="flex min-w-0 items-center gap-1.5 text-[10px] text-[color:var(--ink-4)]">
            <FileText size={12} className="shrink-0" aria-hidden />
            <span className="planning-mono truncate" title={planPath}>{planPath ? compactPath(planPath, 68) : 'target plan TBD'}</span>
          </div>
        </div>
        <div className="space-y-2 px-3 py-3">
          <div className="flex flex-wrap gap-1.5">
            {item.artifacts.slice(0, 4).map((artifact) => (
              <ArtifactChip
                key={`${artifact.docType}:${artifact.path}`}
                kind={artifact.docType}
                label={artifactLabel(artifact.docType)}
                active={artifact.path === planPath}
              />
            ))}
          </div>
          {item.blockers.length > 0 ? (
            <div className="flex items-start gap-1.5 text-[10.5px] text-[color:var(--warn)]">
              <ShieldAlert size={12} className="mt-0.5 shrink-0" aria-hidden />
              <span>{item.blockers[0].label || item.blockers[0].reason}</span>
            </div>
          ) : (
            <span className="planning-mono text-[10.5px] text-[color:var(--ok)]">unblocked</span>
          )}
        </div>
      </button>
      {expanded ? (
        <div className="grid gap-4 border-t border-[color:var(--line-1)] bg-[color:var(--bg-0)] p-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
          <div className="space-y-4">
            <EditableCommandField
              value={commandValue}
              originalValue={item.command?.command ?? ''}
              disabled={!item.capabilities.editCommand}
              onChange={(next) => onCommandChange(featureId, next)}
            />
            <QuickCommandBar
              item={item}
              command={commandValue}
              onCopy={onCopyCommand}
              onOpenLaunch={onOpenLaunch}
              onOpenExecution={onOpenExecution}
              onOpenPlan={onOpenPlan}
              onOpenDetail={() => onOpenDetail?.(featureId)}
              onOpenPullRequest={onOpenPullRequest}
            />
            <RelatedFilesPicker
              files={item.relatedFiles}
              onAddFile={(path) => onCommandChange(featureId, appendRelatedFileToCommand(commandValue, path))}
            />
          </div>
          <div className="space-y-4">
            <WorktreeGitStatePanel worktree={item.worktree} gitState={item.gitState} />
            <PhasePlanTable rows={item.phaseRows} />
          </div>
        </div>
      ) : null}
    </article>
  );
}
