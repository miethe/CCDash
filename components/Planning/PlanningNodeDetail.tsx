import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  ChevronDown,
  ChevronRight,
  FolderSearch,
  Link2,
  PackageOpen,
  RefreshCw,
  Users,
} from 'lucide-react';

import { useData } from '../../contexts/DataContext';
import type {
  FeaturePlanningContext,
  PlanningNode,
  PlanningNodeType,
  PlanningPhaseBatch,
  PhaseContextItem,
} from '../../types';
import { getFeaturePlanningContext, PlanningApiError } from '../../services/planning';
import { featurePlanningTopic } from '../../services/live/topics';
import { useLiveInvalidation } from '../../services/live/useLiveInvalidation';
import type { LiveConnectionStatus } from '../../services/live';
import {
  castPlanningStatus,
  EffectiveStatusChips,
  LineageRow,
  MismatchBadge,
  BatchReadinessPill,
  StatusChip,
  statusVariant,
} from '@/components/shared/PlanningMetadata';

// ── Helpers ───────────────────────────────────────────────────────────────────

const NODE_TYPE_ORDER: PlanningNodeType[] = [
  'design_spec',
  'prd',
  'implementation_plan',
  'progress',
  'context',
  'tracker',
  'report',
];

function sortNodesByType(nodes: PlanningNode[]): PlanningNode[] {
  return [...nodes].sort(
    (a, b) => NODE_TYPE_ORDER.indexOf(a.type) - NODE_TYPE_ORDER.indexOf(b.type),
  );
}

// ── Small shared UI pieces ────────────────────────────────────────────────────

function LiveStatusDot({ status }: { status: LiveConnectionStatus }) {
  const configs: Record<LiveConnectionStatus, { color: string; label: string }> = {
    open:       { color: 'bg-emerald-400', label: 'Live' },
    connecting: { color: 'bg-amber-400 animate-pulse', label: 'Connecting' },
    backoff:    { color: 'bg-amber-500 animate-pulse', label: 'Reconnecting' },
    paused:     { color: 'bg-slate-400', label: 'Paused' },
    closed:     { color: 'bg-rose-400', label: 'Closed' },
    idle:       { color: 'bg-slate-500', label: 'Idle' },
  };
  const cfg = configs[status] ?? configs.idle;
  return (
    <span className="flex items-center gap-1.5" title={`Live updates: ${cfg.label}`}>
      <span className={`inline-block h-2 w-2 rounded-full ${cfg.color}`} />
      <span className="text-xs text-muted-foreground">{cfg.label}</span>
    </span>
  );
}

// ── Loading / Error / No-project shells ──────────────────────────────────────

function DetailSkeleton() {
  return (
    <div className="max-w-screen-xl space-y-6 animate-pulse">
      <div className="h-8 rounded bg-slate-700/40 w-1/2" />
      <div className="h-40 rounded-xl bg-slate-700/40" />
      <div className="h-40 rounded-xl bg-slate-700/40" />
      <div className="h-40 rounded-xl bg-slate-700/40" />
    </div>
  );
}

function DetailError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex max-w-lg items-start gap-3 rounded-xl border border-danger/40 bg-danger/5 px-6 py-5 shadow-sm">
      <AlertCircle size={18} className="mt-0.5 shrink-0 text-danger" />
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm text-danger-foreground">Failed to load feature planning context</p>
        <p className="mt-1 text-xs text-danger-foreground/70">{message}</p>
      </div>
      <button
        onClick={onRetry}
        className="flex shrink-0 items-center gap-1.5 rounded border border-danger/40 bg-danger/10 px-3 py-1.5 text-xs font-medium text-danger-foreground hover:bg-danger/20 transition-colors"
      >
        <RefreshCw size={12} />
        Retry
      </button>
    </div>
  );
}

function NoProjectShell() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="flex max-w-md flex-col items-center gap-4 rounded-xl border border-dashed border-panel-border bg-surface-elevated/40 px-10 py-10 text-center">
        <PackageOpen size={32} className="text-muted-foreground/50" />
        <div>
          <p className="text-sm font-medium text-muted-foreground">No project selected</p>
          <p className="mt-1.5 text-xs text-muted-foreground/70">
            Select a project from the sidebar to view feature planning detail.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Lineage Panel ─────────────────────────────────────────────────────────────

function LineagePanel({ nodes }: { nodes: PlanningNode[] }) {
  const sorted = sortNodesByType(nodes);
  if (sorted.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-panel-border px-4 py-4">
        <p className="text-xs text-muted-foreground/60 italic">No lineage nodes found.</p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-panel-border rounded-lg border border-panel-border overflow-hidden">
      {sorted.map((node) => (
        <LineageRow key={node.id} node={node} />
      ))}
    </div>
  );
}

// ── Phase Batch Row ───────────────────────────────────────────────────────────

function PhaseBatchRow({ batch }: { batch: PlanningPhaseBatch }) {
  return (
    <div className="rounded-lg border border-panel-border/60 bg-slate-800/40 px-3 py-2.5 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-panel-foreground truncate">
          Batch {batch.batchId}
        </span>
        <BatchReadinessPill
          readinessState={batch.readinessState}
          blockingNodeIds={batch.readiness?.blockingNodeIds}
          blockingTaskIds={batch.readiness?.blockingTaskIds}
        />
      </div>
      {batch.assignedAgents?.length > 0 && (
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <Users size={10} />
          {batch.assignedAgents.join(', ')}
        </div>
      )}
      {batch.fileScopeHints?.length > 0 && (
        <div className="text-[10px] text-muted-foreground/70 truncate">
          Scope: {batch.fileScopeHints.join(', ')}
        </div>
      )}
    </div>
  );
}

// ── Phase Accordion ───────────────────────────────────────────────────────────

function PhaseAccordion({ phase }: { phase: PhaseContextItem }) {
  const [open, setOpen] = useState(false);
  const variant = statusVariant(phase.effectiveStatus);

  return (
    <div className="rounded-xl border border-panel-border overflow-hidden">
      <button
        className="flex w-full items-center justify-between gap-3 bg-surface-elevated px-4 py-3 text-left hover:bg-slate-700/30 transition-colors"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <div className="flex items-center gap-3 min-w-0">
          {open ? (
            <ChevronDown size={14} className="shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight size={14} className="shrink-0 text-muted-foreground" />
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium text-panel-foreground truncate">
              {phase.phaseTitle || phase.phaseToken}
            </p>
            <p className="text-[10px] text-muted-foreground">
              {phase.completedTasks}/{phase.totalTasks} tasks complete
              {phase.deferredTasks > 0 && ` · ${phase.deferredTasks} deferred`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {phase.isMismatch && <AlertTriangle size={12} className="text-amber-400" />}
          <StatusChip label={phase.effectiveStatus} variant={variant} />
        </div>
      </button>

      {open && (
        <div className="border-t border-panel-border bg-slate-900/30 px-4 py-3 space-y-2">
          {phase.batches.length === 0 ? (
            <p className="text-xs text-muted-foreground/60 italic">No batches defined.</p>
          ) : (
            phase.batches.map((batch) => (
              <PhaseBatchRow key={batch.batchId} batch={batch} />
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Blockers Panel ────────────────────────────────────────────────────────────

function BlockersPanel({ blockedBatchIds, nodes }: { blockedBatchIds: string[]; nodes: PlanningNode[] }) {
  const blockerNodes = nodes.filter(n =>
    ['blocked', 'reversed', 'stale'].includes(n.mismatchState?.state ?? ''),
  );

  if (blockedBatchIds.length === 0 && blockerNodes.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
        <span className="text-xs text-emerald-400">No blockers detected.</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {blockedBatchIds.length > 0 && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-4 py-3">
          <p className="text-xs font-medium text-rose-400 mb-1.5">Blocked batch IDs</p>
          <div className="flex flex-wrap gap-1.5">
            {blockedBatchIds.map(id => (
              <span
                key={id}
                className="rounded px-2 py-0.5 text-[10px] font-medium bg-rose-500/20 text-rose-300"
              >
                {id}
              </span>
            ))}
          </div>
        </div>
      )}
      {blockerNodes.map(node => (
        <div key={node.id} className="flex items-start gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5">
          <AlertTriangle size={13} className="mt-0.5 shrink-0 text-amber-400" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-amber-300 truncate">{node.title || node.id}</p>
            <p className="text-[10px] text-amber-300/70">{node.mismatchState?.state} — {node.mismatchState?.reason}</p>
            {node.mismatchState?.evidence?.map(ev => (
              <span
                key={ev.id}
                className="mr-1 inline-block rounded px-1.5 py-0.5 text-[10px] bg-amber-500/20 text-amber-300"
              >
                {ev.label}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Linked Artifacts ──────────────────────────────────────────────────────────

function LinkedArtifactsPanel({ refs }: { refs: string[] }) {
  if (refs.length === 0) {
    return (
      <p className="text-xs text-muted-foreground/60 italic">No linked artifacts.</p>
    );
  }
  return (
    <ul className="space-y-1">
      {refs.map((ref, i) => (
        <li key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
          <Link2 size={11} className="shrink-0 text-info/60" />
          <span className="truncate font-mono" title={ref}>{ref}</span>
        </li>
      ))}
    </ul>
  );
}

// ── Section card wrapper ──────────────────────────────────────────────────────

function SectionCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-panel-border bg-surface-elevated overflow-hidden">
      <div className="flex items-center gap-2.5 border-b border-panel-border px-4 py-3">
        <span className="text-info">{icon}</span>
        <h2 className="text-sm font-semibold text-panel-foreground">{title}</h2>
      </div>
      <div className="px-4 py-4">
        {children}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type DetailFetchState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; context: FeaturePlanningContext };

export function PlanningNodeDetail() {
  const { featureId } = useParams<{ featureId: string }>();
  const navigate = useNavigate();
  const { activeProject } = useData();
  const [state, setState] = useState<DetailFetchState>({ phase: 'idle' });

  const loadContext = useCallback(async () => {
    if (!featureId) {
      setState({ phase: 'idle' });
      return;
    }
    setState({ phase: 'loading' });
    try {
      const context = await getFeaturePlanningContext(featureId, {
        projectId: activeProject?.id,
      });
      setState({ phase: 'ready', context });
    } catch (err) {
      const message =
        err instanceof PlanningApiError
          ? `Planning API error (${err.status}): ${err.message}`
          : err instanceof Error
            ? err.message
            : 'Failed to load feature planning context.';
      setState({ phase: 'error', message });
    }
  }, [featureId, activeProject?.id]);

  useEffect(() => {
    void loadContext();
  }, [loadContext]);

  // Live invalidation
  const liveTopics = featureId ? [featurePlanningTopic(featureId)] : [];
  const liveStatus = useLiveInvalidation({
    topics: liveTopics,
    enabled: liveTopics.length > 0,
    onInvalidate: () => loadContext(),
  });

  if (!activeProject) {
    return (
      <div className="max-w-screen-xl space-y-6">
        <NoProjectShell />
      </div>
    );
  }

  if (state.phase === 'idle' || state.phase === 'loading') {
    return (
      <div className="max-w-screen-xl">
        <DetailSkeleton />
      </div>
    );
  }

  if (state.phase === 'error') {
    return (
      <div className="max-w-screen-xl space-y-4">
        <button
          onClick={() => navigate('/planning')}
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-panel-foreground transition-colors"
        >
          <ArrowLeft size={13} />
          Back to Planning
        </button>
        <DetailError message={state.message} onRetry={() => void loadContext()} />
      </div>
    );
  }

  const { context } = state;
  const planningStatus = castPlanningStatus(context.planningStatus);
  const isMismatch = context.mismatchState !== 'aligned' && context.mismatchState !== 'unknown';
  const mismatchReason = planningStatus?.mismatchState?.reason ?? context.mismatchState;
  const evidenceLabels = planningStatus?.mismatchState?.evidence?.map(ev => ev.label) ?? [];

  return (
    <div className="max-w-screen-xl space-y-5">
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-4">
          <button
            onClick={() => navigate('/planning')}
            className="flex items-center gap-2 rounded-lg border border-panel-border bg-surface-elevated px-3 py-1.5 text-xs text-muted-foreground hover:text-panel-foreground hover:bg-slate-700/30 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info"
          >
            <ArrowLeft size={13} />
            Back to Planning
          </button>
          <LiveStatusDot status={liveStatus} />
        </div>

        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-panel-foreground">
              {context.featureName || featureId}
            </h1>
            <p className="mt-0.5 text-xs font-mono text-muted-foreground/70">{featureId}</p>
          </div>

          {/* Status chips with provenance tooltip */}
          <EffectiveStatusChips
            rawStatus={context.rawStatus}
            effectiveStatus={context.effectiveStatus}
            isMismatch={isMismatch}
            provenance={planningStatus?.provenance}
          />
        </div>

        {/* Mismatch banner */}
        {isMismatch && (
          <MismatchBadge state={context.mismatchState} reason={mismatchReason} evidenceLabels={evidenceLabels} />
        )}
      </div>

      {/* Lineage */}
      <SectionCard
        title="Lineage"
        icon={<FolderSearch size={15} />}
      >
        <LineagePanel nodes={sortNodesByType(context.graph.nodes)} />
      </SectionCard>

      {/* Phases */}
      {context.phases.length > 0 && (
        <SectionCard
          title="Phases"
          icon={<BookOpen size={15} />}
        >
          <div className="space-y-2">
            {context.phases.map((phase) => (
              <PhaseAccordion key={phase.phaseId} phase={phase} />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Blockers */}
      <SectionCard
        title="Blockers"
        icon={<AlertTriangle size={15} />}
      >
        <BlockersPanel
          blockedBatchIds={context.blockedBatchIds}
          nodes={context.graph.nodes}
        />
      </SectionCard>

      {/* Linked Artifacts */}
      <SectionCard
        title="Linked Artifacts"
        icon={<Link2 size={15} />}
      >
        <LinkedArtifactsPanel refs={context.linkedArtifactRefs} />
      </SectionCard>
    </div>
  );
}
