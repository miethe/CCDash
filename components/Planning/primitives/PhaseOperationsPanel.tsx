import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, Loader2, RefreshCw, Rocket, X } from 'lucide-react';

import type { PhaseOperations, PlanningPhaseBatch, PhaseTaskItem, LaunchStartResponse } from '../../../types';
import { getPhaseOperations, PlanningApiError } from '../../../services/planning';
import { getLaunchCapabilities } from '../../../services/execution';
import {
  featurePlanningTopic,
} from '../../../services/live/topics';
import { useLiveInvalidation } from '../../../services/live/useLiveInvalidation';
import { BatchReadinessPill } from './BatchReadinessPill';
import { EffectiveStatusChips } from './EffectiveStatusChips';
import { MismatchBadge } from './MismatchBadge';
import { StatusChip } from './StatusChip';
import { statusVariant } from './variants';
import { PlanningLaunchSheet } from '../PlanningLaunchSheet';

export interface PhaseOperationsPanelProps {
  featureId: string;
  phaseNumber: number;
  projectId?: string;
  /** Optional fallback title if the query hasn't loaded yet. */
  fallbackTitle?: string;
  /** Optional compact mode that skips the outer card styling (caller provides it). */
  embedded?: boolean;
}

// ── Internal display helpers ──────────────────────────────────────────────────

const CARD = 'rounded-xl border border-panel-border bg-surface-overlay/70 p-4 space-y-3';
const SECTION_LABEL = 'text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5';

export interface PhaseOperationsBatchSectionProps {
  batches: PlanningPhaseBatch[];
  projectId?: string;
  onLaunch?: (batchId: string) => void;
}

/**
 * Renders the batch table section.
 */
export function PhaseOperationsBatchSection({
  batches,
  projectId,
  onLaunch,
}: PhaseOperationsBatchSectionProps) {
  if (batches.length === 0) {
    return <p className="text-xs text-muted-foreground italic">No batches for this phase.</p>;
  }
  return (
    <div className="space-y-2">
      {batches.map(batch => (
        <div
          key={batch.batchId}
          className="flex flex-wrap items-start gap-3 rounded-lg border border-panel-border/50 bg-panel/30 px-3 py-2"
        >
          <span className="font-mono text-xs text-panel-foreground shrink-0">
            {batch.batchId}
          </span>
          <BatchReadinessPill
            readinessState={batch.readinessState}
            blockingNodeIds={batch.readiness?.blockingNodeIds}
            blockingTaskIds={batch.readiness?.blockingTaskIds}
          />
          {batch.assignedAgents?.length > 0 && (
            <span className="text-xs text-muted-foreground truncate max-w-[200px]">
              Agents: {batch.assignedAgents.join(', ')}
            </span>
          )}
          {batch.fileScopeHints?.length > 0 && (
            <span
              className="text-[10px] text-muted-foreground/70 truncate max-w-[200px]"
              title={batch.fileScopeHints.join(', ')}
            >
              Scope: {batch.fileScopeHints.slice(0, 2).join(', ')}
              {batch.fileScopeHints.length > 2 && ` +${batch.fileScopeHints.length - 2}`}
            </span>
          )}
          {onLaunch && (
            <button
              type="button"
              onClick={() => onLaunch(batch.batchId)}
              disabled={!projectId}
              title={!projectId ? 'Select a project to launch' : `Launch ${batch.batchId}`}
              className="ml-auto flex items-center gap-1 px-2 py-0.5 rounded border border-indigo-500/30 bg-indigo-600/10 text-indigo-300 text-[11px] hover:bg-indigo-600/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
            >
              <Rocket size={12} />
              Launch
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * Renders tasks grouped by batchId, sorted by batchId then taskId.
 */
export function PhaseOperationsTaskSection({ tasks }: { tasks: PhaseTaskItem[] }) {
  if (tasks.length === 0) {
    return <p className="text-xs text-muted-foreground italic">No tasks for this phase.</p>;
  }

  // Sort: batchId asc, then taskId asc
  const sorted = [...tasks].sort((a, b) => {
    const bc = (a.batchId ?? '').localeCompare(b.batchId ?? '');
    if (bc !== 0) return bc;
    return (a.taskId ?? '').localeCompare(b.taskId ?? '');
  });

  // Group by batchId
  const groups = new Map<string, PhaseTaskItem[]>();
  for (const task of sorted) {
    const bid = task.batchId || '(unassigned)';
    if (!groups.has(bid)) groups.set(bid, []);
    groups.get(bid)!.push(task);
  }

  return (
    <div className="space-y-3">
      {Array.from(groups.entries()).map(([batchId, batchTasks]) => (
        <div key={batchId}>
          <p className="text-[10px] font-mono text-muted-foreground/70 mb-1">{batchId}</p>
          <div className="space-y-1">
            {batchTasks.map(task => (
              <div
                key={task.taskId}
                className="flex flex-wrap items-center gap-2 rounded px-2 py-1.5 hover:bg-panel/50"
              >
                <span className="font-mono text-[10px] text-muted-foreground shrink-0 min-w-0 truncate max-w-[80px]" title={task.taskId}>
                  {task.taskId}
                </span>
                <span className="text-sm text-panel-foreground flex-1 min-w-0 truncate" title={task.title}>
                  {task.title}
                </span>
                <StatusChip label={task.status} variant={statusVariant(task.status)} />
                {task.assignees?.length > 0 && (
                  <span className="text-[10px] text-muted-foreground truncate max-w-[120px]">
                    {task.assignees.join(', ')}
                  </span>
                )}
                {task.blockers?.length > 0 && (
                  <span className="text-[10px] text-rose-400/80 truncate max-w-[120px]">
                    Blocked: {task.blockers.join(', ')}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Renders the dependency resolution summary as a compact key:value list.
 */
export function PhaseOperationsDependencySection({
  dependencyResolution,
}: {
  dependencyResolution: Record<string, unknown>;
}) {
  const entries = Object.entries(dependencyResolution)
    .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
    .slice(0, 6);

  if (entries.length === 0) return null;

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
      {entries.map(([key, val]) => (
        <div key={key} className="flex items-center gap-1.5 min-w-0">
          <dt className="text-[10px] text-muted-foreground truncate">{key}</dt>
          <dd className="text-[10px] font-mono text-panel-foreground">{String(val)}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Renders the progress evidence list.
 */
export function PhaseOperationsEvidenceSection({
  progressEvidence,
}: {
  progressEvidence: string[];
}) {
  if (progressEvidence.length === 0) return null;

  const visible = progressEvidence.slice(0, 8);
  return (
    <ul className="space-y-0.5">
      {visible.map((entry, i) => (
        <li key={i} className="font-mono text-[10px] text-muted-foreground/80 truncate" title={entry}>
          {entry.length > 80 ? `${entry.slice(0, 80)}…` : entry}
        </li>
      ))}
      {progressEvidence.length > 8 && (
        <li className="text-[10px] text-muted-foreground italic">
          +{progressEvidence.length - 8} more entries
        </li>
      )}
    </ul>
  );
}

export interface PhaseOperationsContentProps {
  data: PhaseOperations;
  projectId?: string;
  onLaunch?: (batchId: string) => void;
}

/**
 * Inner content renderer for PhaseOperationsPanel — accepts already-loaded data
 * and is separately testable via renderToStaticMarkup.
 */
export function PhaseOperationsContent({ data, projectId, onLaunch }: PhaseOperationsContentProps) {
  const isMismatch = data.rawStatus !== data.effectiveStatus && Boolean(data.effectiveStatus);

  // Collect all blocking ids across batches
  const allBlockingNodeIds = (data.phaseBatches ?? []).flatMap(
    b => b.readiness?.blockingNodeIds ?? [],
  );
  const allBlockingTaskIds = (data.phaseBatches ?? []).flatMap(
    b => b.readiness?.blockingTaskIds ?? [],
  );
  const hasBlockers = allBlockingNodeIds.length > 0 || allBlockingTaskIds.length > 0;

  const hasDependencies = Object.entries(data.dependencyResolution ?? {}).some(
    ([, v]) => typeof v === 'number' || typeof v === 'string',
  );

  return (
    <div className="space-y-4">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-panel-foreground truncate">
            {data.phaseTitle || data.phaseToken || `Phase ${data.phaseNumber}`}
          </p>
          <p className="text-[10px] font-mono text-muted-foreground mt-0.5">
            {data.phaseToken}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <EffectiveStatusChips
            rawStatus={data.rawStatus}
            effectiveStatus={data.effectiveStatus}
            isMismatch={isMismatch}
          />
          <BatchReadinessPill readinessState={data.readinessState} />
        </div>
      </div>

      {/* ── Batches ───────────────────────────────────────────────────── */}
      <section>
        <p className={SECTION_LABEL}>Batches</p>
        <PhaseOperationsBatchSection
          batches={data.phaseBatches ?? []}
          projectId={projectId}
          onLaunch={onLaunch}
        />
      </section>

      {/* ── Tasks ─────────────────────────────────────────────────────── */}
      <section>
        <p className={SECTION_LABEL}>Tasks</p>
        <PhaseOperationsTaskSection tasks={data.tasks ?? []} />
      </section>

      {/* ── Dependency Resolution ─────────────────────────────────────── */}
      {hasDependencies && (
        <section>
          <p className={SECTION_LABEL}>Dependency Resolution</p>
          <PhaseOperationsDependencySection dependencyResolution={data.dependencyResolution} />
        </section>
      )}

      {/* ── Progress Evidence ─────────────────────────────────────────── */}
      {(data.progressEvidence ?? []).length > 0 && (
        <section>
          <p className={SECTION_LABEL}>Progress Evidence</p>
          <PhaseOperationsEvidenceSection progressEvidence={data.progressEvidence} />
        </section>
      )}

      {/* ── Validation / Blockers ─────────────────────────────────────── */}
      {hasBlockers && (
        <MismatchBadge
          compact={false}
          state="blocked"
          reason="Batches have unresolved blockers"
          evidenceLabels={[...allBlockingNodeIds, ...allBlockingTaskIds].slice(0, 5)}
        />
      )}
    </div>
  );
}

/**
 * Self-contained panel that fetches PhaseOperations for a single phase and
 * renders batches, tasks, dependencies, progress evidence, and validation outcomes.
 *
 * Re-fetches when `featurePlanningTopic(featureId)` fires via useLiveInvalidation.
 */
export function PhaseOperationsPanel({
  featureId,
  phaseNumber,
  projectId,
  fallbackTitle,
  embedded = false,
}: PhaseOperationsPanelProps) {
  const [data, setData] = useState<PhaseOperations | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  // ── Launch state ──────────────────────────────────────────────────────────
  const [activeLaunchBatchId, setActiveLaunchBatchId] = useState<string | null>(null);
  const [launchBanner, setLaunchBanner] = useState<string | null>(null);
  const [launchEnabled, setLaunchEnabled] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const caps = await getLaunchCapabilities();
        if (!cancelled) setLaunchEnabled(Boolean(caps.enabled));
      } catch {
        if (!cancelled) setLaunchEnabled(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async () => {
    if (!featureId) return;
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const result = await getPhaseOperations(featureId, phaseNumber, { projectId });
      setData(result);
    } catch (err) {
      if (err instanceof PlanningApiError && err.status === 404) {
        setNotFound(true);
      } else {
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to load phase operations.',
        );
      }
    } finally {
      setLoading(false);
    }
  }, [featureId, phaseNumber, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useLiveInvalidation({
    topics: [featurePlanningTopic(featureId)],
    enabled: Boolean(featureId),
    onInvalidate: () => { void load(); },
  });

  // ── Skeleton ───────────────────────────────────────────────────────────────
  if (loading && !data) {
    return (
      <div className={embedded ? 'space-y-3' : CARD}>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 size={13} className="animate-spin" />
          <span>Loading phase operations…</span>
        </div>
        <div className="space-y-2">
          {[80, 60, 72].map(w => (
            <div key={w} className={`h-3 rounded bg-surface-muted animate-pulse`} style={{ width: `${w}%` }} />
          ))}
        </div>
      </div>
    );
  }

  // ── 404 empty state ────────────────────────────────────────────────────────
  if (notFound) {
    return (
      <div className={embedded ? '' : CARD}>
        <p className="text-xs text-muted-foreground italic">
          No planning detail available for this phase.
        </p>
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className={embedded ? 'space-y-2' : CARD}>
        <div className="flex items-start gap-2">
          <AlertCircle size={14} className="shrink-0 mt-0.5 text-rose-400" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-rose-400">
              {fallbackTitle ? `Error loading "${fallbackTitle}"` : 'Error loading phase operations'}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{error}</p>
          </div>
        </div>
        <button
          onClick={() => { void load(); }}
          className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-200"
        >
          <RefreshCw size={11} />
          Retry
        </button>
      </div>
    );
  }

  // ── Loaded ────────────────────────────────────────────────────────────────
  if (!data) return null;

  const handleLaunch = (batchId: string) => setActiveLaunchBatchId(batchId);
  const handleLaunched = (result: LaunchStartResponse) => {
    setLaunchBanner(`Run ${result.runId} queued`);
  };

  const contentNode = (
    <>
      {launchBanner && (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-indigo-500/30 bg-indigo-600/10 px-3 py-2 text-xs text-indigo-300 mb-3">
          <span>{launchBanner}</span>
          <button
            type="button"
            onClick={() => setLaunchBanner(null)}
            className="shrink-0 text-indigo-400/70 hover:text-indigo-200"
            aria-label="Dismiss"
          >
            <X size={12} />
          </button>
        </div>
      )}
      <PhaseOperationsContent
        data={data}
        projectId={projectId}
        onLaunch={launchEnabled ? handleLaunch : undefined}
      />
      {!launchEnabled && (
        <p className="mt-2 text-[10px] text-muted-foreground/70 italic">
          Plan-driven launch is disabled (CCDASH_LAUNCH_PREP_ENABLED=false).
        </p>
      )}
      {activeLaunchBatchId && projectId && (
        <PlanningLaunchSheet
          open={!!activeLaunchBatchId}
          projectId={projectId}
          featureId={featureId}
          phaseNumber={phaseNumber}
          batchId={activeLaunchBatchId}
          onClose={() => setActiveLaunchBatchId(null)}
          onLaunched={handleLaunched}
        />
      )}
    </>
  );

  if (embedded) {
    return contentNode;
  }

  return (
    <div className={CARD}>
      {contentNode}
    </div>
  );
}
