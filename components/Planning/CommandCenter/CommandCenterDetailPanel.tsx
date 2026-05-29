import { ExternalLink, GitBranch, X } from 'lucide-react';

import type { PlanningCommandCenterItem } from '@/types';
import { commandCenterDisplayName, commandCenterPlanPath, compactPath } from './commandCenterUtils';
import { PhasePlanTable } from './PhasePlanTable';
import { WorktreeGitStatePanel } from './WorktreeGitStatePanel';
import { ArtifactChip, BtnGhost, Chip, Panel, StatusPill } from '../primitives';

interface CommandCenterDetailPanelProps {
  item: PlanningCommandCenterItem | null;
  commandValue: string;
  onClose: () => void;
  onOpenPlan?: (path: string) => void;
}

export function CommandCenterDetailPanel({
  item,
  commandValue,
  onClose,
  onOpenPlan,
}: CommandCenterDetailPanelProps) {
  if (!item) return null;
  const planPath = commandCenterPlanPath(item);

  return (
    <div className="fixed inset-0 z-40 bg-black/45" role="dialog" aria-modal="true" aria-label={`Command center details for ${item.feature.featureId}`}>
      <div className="absolute inset-y-0 right-0 flex w-full max-w-[760px] flex-col border-l border-[color:var(--line-1)] bg-[color:var(--bg-0)] shadow-2xl">
        <Panel className="flex min-h-0 flex-1 flex-col rounded-none border-0">
          <div className="flex items-start justify-between gap-3 border-b border-[color:var(--line-1)] p-5">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill status={item.status.effectiveStatus || item.status.rawStatus || 'unknown'} />
                <Chip className="planning-mono text-[10px]">
                  <GitBranch size={12} aria-hidden />
                  {item.worktree?.branch || 'branch TBD'}
                </Chip>
              </div>
              <h2 className="mt-3 truncate text-[19px] font-semibold text-[color:var(--ink-0)]" title={commandCenterDisplayName(item)}>
                {commandCenterDisplayName(item)}
              </h2>
              <p className="planning-mono mt-1 truncate text-[11px] text-[color:var(--ink-4)]" title={item.feature.featureId}>
                {item.feature.featureId}
              </p>
            </div>
            <BtnGhost size="sm" onClick={onClose} aria-label="Close command center detail">
              <X size={14} aria-hidden />
              close
            </BtnGhost>
          </div>
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
            <section className="space-y-2">
              <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">next command</div>
              <pre className="planning-mono whitespace-pre-wrap rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-3 text-[11px] leading-relaxed text-[color:var(--ink-1)]">
                {commandValue || 'No next command resolved'}
              </pre>
              {item.command?.rationale ? (
                <p className="text-[11.5px] leading-relaxed text-[color:var(--ink-3)]">{item.command.rationale}</p>
              ) : null}
            </section>
            <section className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">target plan and guides</div>
                <BtnGhost size="xs" disabled={!planPath} onClick={() => onOpenPlan?.(planPath)}>
                  <ExternalLink size={12} aria-hidden />
                  open plan
                </BtnGhost>
              </div>
              <div className="space-y-2 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-3">
                <p className="planning-mono truncate text-[10.5px] text-[color:var(--ink-1)]" title={planPath}>
                  {planPath ? compactPath(planPath, 110) : 'target plan TBD'}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {item.artifacts.map((artifact) => (
                    <ArtifactChip
                      key={`${artifact.docType}:${artifact.path}`}
                      kind={artifact.docType}
                      label={artifact.docType === 'implementation_plan' ? 'plan' : artifact.docType || 'doc'}
                      active={artifact.path === planPath}
                      title={artifact.path}
                    />
                  ))}
                </div>
              </div>
            </section>
            <section className="space-y-2">
              <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">worktree and git state</div>
              <WorktreeGitStatePanel worktree={item.worktree} gitState={item.gitState} />
            </section>
            <section className="space-y-2">
              <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">phase plan</div>
              <PhasePlanTable rows={item.phaseRows} />
            </section>
            <section className="space-y-2">
              <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">launch and review context</div>
              <div className="grid gap-2 sm:grid-cols-2">
                <Chip className="planning-mono text-[10px]">batch {item.launchBatch?.label || item.launchBatch?.batchId || 'TBD'}</Chip>
                <Chip className="planning-mono text-[10px]">readiness {item.launchBatch?.readiness || 'needs context'}</Chip>
                <Chip className="planning-mono text-[10px]">PR {item.pullRequest?.number ?? 'none'}</Chip>
                <Chip className="planning-mono text-[10px]">review {item.pullRequest?.reviewStatus || 'not started'}</Chip>
              </div>
              {item.blockers.length ? (
                <div className="space-y-1">
                  {item.blockers.map((blocker) => (
                    <p key={`${blocker.severity}:${blocker.label}:${blocker.reason}`} className="text-[11px] text-[color:var(--warn)]">
                      {blocker.label || blocker.reason}
                    </p>
                  ))}
                </div>
              ) : null}
            </section>
          </div>
        </Panel>
      </div>
    </div>
  );
}
