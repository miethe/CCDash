import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  Bot,
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Check,
  FolderSearch,
  Link2,
  Network,
  PackageOpen,
  Play,
  RefreshCw,
  Send,
  Users,
  X,
} from 'lucide-react';

import { useData } from '../../contexts/DataContext';
import type { PlanDocument } from '../../types';
import { DocumentModal } from '../DocumentModal';
import type {
  FeaturePlanningContext,
  PlanningNode,
  PlanningNodeType,
  PlanningOpenQuestionItem,
  PlanningPhaseBatch,
  PlanningSpikeItem,
  PlanningTokenUsageByModel,
  PhaseContextItem,
} from '../../types';
import { getFeaturePlanningContext, PlanningApiError, resolvePlanningOpenQuestion } from '../../services/planning';
import { planningRouteFeatureModalHref } from '../../services/planningRoutes';
import { featurePlanningTopic } from '../../services/live/topics';
import { useLiveInvalidation } from '../../services/live/useLiveInvalidation';
import type { LiveConnectionStatus } from '../../services/live';
import {
  castPlanningStatus,
  LineageRow,
  MismatchBadge,
  BatchReadinessPill,
  StatusChip,
  statusVariant,
} from '@/components/shared/PlanningMetadata';
import {
  BtnGhost,
  BtnPrimary,
  Chip,
  Dot,
  ExecBtn,
  StatusPill,
} from './primitives/PhaseZeroPrimitives';
import { PlanningFeatureAgentLane } from './PlanningFeatureAgentLane';

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

type LineageKind = 'spec' | 'spike' | 'prd' | 'plan' | 'phase' | 'ctx' | 'report';
type DetailSectionKey = 'lineage' | 'spec' | 'phases' | 'tasks' | 'sessions' | 'blockers' | 'artifacts';
type ExecutionViewMode = 'batches' | 'dag';

interface LineageTileModel {
  kind: LineageKind;
  label: string;
  count: number;
  status: string | null;
  color: string;
  section: DetailSectionKey;
}

interface DerivedFeatureMeta {
  category?: string;
  slug?: string;
}

const LINEAGE_TILE_CONFIG: Array<Omit<LineageTileModel, 'count' | 'status'>> = [
  { kind: 'spec', label: 'SPEC', color: 'var(--spec)', section: 'spec' },
  { kind: 'spike', label: 'SPIKE', color: 'var(--spk)', section: 'spec' },
  { kind: 'prd', label: 'PRD', color: 'var(--prd)', section: 'artifacts' },
  { kind: 'plan', label: 'PLAN', color: 'var(--plan)', section: 'artifacts' },
  { kind: 'phase', label: 'PHASE', color: 'var(--prog)', section: 'phases' },
  { kind: 'ctx', label: 'CTX', color: 'var(--ctx)', section: 'artifacts' },
  { kind: 'report', label: 'REPORT', color: 'var(--rep)', section: 'artifacts' },
];

function representativeStatus(items: Array<{ status?: string; effectiveStatus?: string; rawStatus?: string }>): string | null {
  const priority = ['blocked', 'in-progress', 'in_progress', 'ready', 'approved', 'completed', 'draft', 'shaping', 'idea'];
  for (const status of priority) {
    if (items.some(item => (item.status || item.effectiveStatus || item.rawStatus) === status)) {
      return status;
    }
  }
  const first = items.find(item => item.status || item.effectiveStatus || item.rawStatus);
  return first ? (first.status || first.effectiveStatus || first.rawStatus || null) : null;
}

function countNodesByType(nodes: PlanningNode[], type: PlanningNodeType): number {
  return nodes.filter(node => node.type === type).length;
}

export function buildLineageTiles(context: FeaturePlanningContext): LineageTileModel[] {
  const nodes = context.graph.nodes ?? [];
  const specs = context.specs?.length ? context.specs : nodes.filter(node => node.type === 'design_spec');
  const prds = context.prds?.length ? context.prds : nodes.filter(node => node.type === 'prd');
  const plans = context.plans?.length ? context.plans : nodes.filter(node => node.type === 'implementation_plan');
  const ctxs = context.ctxs?.length ? context.ctxs : nodes.filter(node => node.type === 'context');
  const reports = context.reports?.length ? context.reports : nodes.filter(node => node.type === 'report');
  const spikes = context.spikes ?? [];
  const phases = context.phases?.length ? context.phases : nodes.filter(node => node.type === 'progress');

  const byKind: Record<LineageKind, { count: number; status: string | null }> = {
    spec: { count: specs.length || countNodesByType(nodes, 'design_spec'), status: representativeStatus(specs) },
    spike: { count: spikes.length, status: representativeStatus(spikes) },
    prd: { count: prds.length || countNodesByType(nodes, 'prd'), status: representativeStatus(prds) },
    plan: { count: plans.length || countNodesByType(nodes, 'implementation_plan'), status: representativeStatus(plans) },
    phase: { count: phases.length, status: representativeStatus(phases) },
    ctx: { count: ctxs.length || countNodesByType(nodes, 'context'), status: representativeStatus(ctxs) },
    report: { count: reports.length || countNodesByType(nodes, 'report'), status: representativeStatus(reports) },
  };

  return LINEAGE_TILE_CONFIG.map(config => ({
    ...config,
    count: byKind[config.kind].count,
    status: byKind[config.kind].status,
  }));
}

export function deriveFeatureMeta(context: FeaturePlanningContext, fallbackFeatureId?: string): DerivedFeatureMeta {
  const explicitSlug = context.slug || context.featureId || fallbackFeatureId;
  const allPaths = [
    ...(context.linkedArtifactRefs ?? []),
    ...(context.graph.nodes ?? []).map(node => node.path),
    ...(context.specs ?? []).map(item => item.filePath || item.canonicalPath),
    ...(context.prds ?? []).map(item => item.filePath || item.canonicalPath),
    ...(context.plans ?? []).map(item => item.filePath || item.canonicalPath),
  ].filter(Boolean);

  const categoryFromPath = allPaths
    .map(path => path.match(/project_plans\/(?:PRDs|implementation_plans|design-specs|design_specs)\/([^/]+)\//i)?.[1])
    .find(Boolean);

  const slugFromPath = allPaths
    .map(path => path.match(/([^/]+)\.md$/)?.[1])
    .find(Boolean);

  return {
    category: context.category || categoryFromPath,
    slug: explicitSlug || slugFromPath,
  };
}

function phaseDotState(status: string): 'completed' | 'in_progress' | 'blocked' | 'pending' {
  if (status === 'completed') return 'completed';
  if (status === 'in-progress' || status === 'in_progress') return 'in_progress';
  if (status === 'blocked') return 'blocked';
  return 'pending';
}

const MODEL_KEYS = ['opus', 'sonnet', 'haiku'] as const;
type ModelKey = (typeof MODEL_KEYS)[number];

const MODEL_COLORS: Record<ModelKey, string> = {
  opus: 'var(--m-opus)',
  sonnet: 'var(--m-sonnet)',
  haiku: 'var(--m-haiku)',
};

const MODEL_LABELS: Record<ModelKey, string> = {
  opus: 'Opus',
  sonnet: 'Sonnet',
  haiku: 'Haiku',
};

interface ExecutionTaskModel {
  id: string;
  title: string;
  status: string;
  agent: string;
  model: ModelKey;
  batchId: string;
  phaseId: string;
  phaseIndex: number;
  blocked: boolean;
}

interface ExecutionBatchModel {
  id: string;
  label: string;
  status: string;
  readinessState: string;
  agents: string[];
  tasks: ExecutionTaskModel[];
}

interface ExecutionPhaseModel {
  id: string;
  number: number;
  title: string;
  status: string;
  totalTasks: number;
  completedTasks: number;
  deferredTasks: number;
  progressPct: number;
  batches: ExecutionBatchModel[];
}

interface DagNodeModel {
  id: string;
  title: string;
  status: string;
  phaseId: string;
  phaseNumber: number;
  phaseTitle: string;
  batchId: string;
}

interface DagEdgeModel {
  sourceId: string;
  targetId: string;
  status: 'active' | 'blocked' | 'static';
}

interface DagModel {
  nodes: DagNodeModel[];
  edges: DagEdgeModel[];
}

function formatCompactNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1_000)}k`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function humanizeTaskId(taskId: string): string {
  const cleaned = taskId
    .replace(/^task[-_:]*/i, '')
    .replace(/^[tp]\d+[-_:]*/i, '')
    .replace(/[-_]+/g, ' ')
    .trim();
  if (!cleaned) return `Task ${taskId}`;
  return cleaned.replace(/\b\w/g, char => char.toUpperCase());
}

function normalizePhaseNumber(phase: PhaseContextItem, index: number): number {
  if (typeof phase.phaseNumber === 'number') return phase.phaseNumber;
  const token = `${phase.phaseToken || phase.phaseId || phase.phaseTitle}`.match(/(?:phase[-_\s]*)?(\d+)/i);
  return token ? Number(token[1]) : index + 1;
}

function agentToModel(agent: string | undefined, index: number): ModelKey {
  const normalized = (agent || '').toLowerCase();
  if (normalized.includes('opus')) return 'opus';
  if (normalized.includes('haiku')) return 'haiku';
  if (normalized.includes('sonnet')) return 'sonnet';
  return MODEL_KEYS[index % MODEL_KEYS.length];
}

function taskStatusForBatch(
  phase: PhaseContextItem,
  batch: PlanningPhaseBatch,
  taskId: string,
  taskIndex: number,
): string {
  if (batch.readiness?.blockingTaskIds?.includes(taskId)) return 'blocked';
  if (phase.effectiveStatus === 'completed') return 'completed';
  if (batch.readinessState === 'blocked') return 'blocked';
  if (phase.effectiveStatus === 'in-progress' || phase.effectiveStatus === 'in_progress') {
    return taskIndex < phase.completedTasks ? 'completed' : taskIndex === phase.completedTasks ? 'in-progress' : 'todo';
  }
  return batch.readinessState === 'ready' ? 'ready' : 'todo';
}

export function buildExecutionPhases(phases: PhaseContextItem[]): ExecutionPhaseModel[] {
  return phases.map((phase, phaseIndex) => {
    const number = normalizePhaseNumber(phase, phaseIndex);
    const totalTasks = Math.max(phase.totalTasks, phase.batches.reduce((sum, batch) => sum + (batch.taskIds?.length ?? 0), 0));
    const progressPct = totalTasks > 0 ? Math.round((phase.completedTasks / totalTasks) * 100) : 0;

    return {
      id: phase.phaseId || phase.phaseToken || `phase-${number}`,
      number,
      title: phase.phaseTitle || phase.phaseToken || `Phase ${number}`,
      status: phase.effectiveStatus || phase.rawStatus || 'unknown',
      totalTasks,
      completedTasks: phase.completedTasks,
      deferredTasks: phase.deferredTasks,
      progressPct: Math.max(0, Math.min(100, progressPct)),
      batches: phase.batches.map((batch, batchIndex) => {
        const agents = batch.assignedAgents?.length ? batch.assignedAgents : ['unassigned'];
        const tasks = (batch.taskIds ?? []).map((taskId, taskIndex) => {
          const agent = agents[taskIndex % agents.length] || 'unassigned';
          return {
            id: taskId,
            title: humanizeTaskId(taskId),
            status: taskStatusForBatch(phase, batch, taskId, taskIndex),
            agent,
            model: agentToModel(agent, taskIndex + batchIndex + phaseIndex),
            batchId: batch.batchId || `batch-${batchIndex + 1}`,
            phaseId: phase.phaseId || phase.phaseToken || `phase-${number}`,
            phaseIndex,
            blocked: Boolean(batch.readiness?.blockingTaskIds?.includes(taskId) || batch.readinessState === 'blocked'),
          };
        });

        return {
          id: batch.batchId || `batch-${batchIndex + 1}`,
          label: batch.batchId || String(batchIndex + 1),
          status: batch.readinessState || 'unknown',
          readinessState: batch.readinessState || 'unknown',
          agents,
          tasks,
        };
      }),
    };
  });
}

export function buildDependencyDag(phases: ExecutionPhaseModel[]): DagModel {
  const nodes: DagNodeModel[] = phases.flatMap(phase =>
    phase.batches.flatMap(batch =>
      batch.tasks.map(task => ({
        id: task.id,
        title: task.title,
        status: task.status,
        phaseId: phase.id,
        phaseNumber: phase.number,
        phaseTitle: phase.title,
        batchId: batch.id,
      })),
    ),
  );
  const nodeIds = new Set(nodes.map(node => node.id));
  const edges: DagEdgeModel[] = [];

  for (const phase of phases) {
    for (let i = 0; i < phase.batches.length - 1; i += 1) {
      const leftTasks = phase.batches[i].tasks;
      const rightTasks = phase.batches[i + 1].tasks;
      if (!leftTasks.length || !rightTasks.length) continue;
      for (const target of rightTasks) {
        const source = leftTasks[Math.min(rightTasks.indexOf(target), leftTasks.length - 1)];
        if (source && nodeIds.has(source.id) && nodeIds.has(target.id)) {
          edges.push({
            sourceId: source.id,
            targetId: target.id,
            status: target.blocked || target.status === 'blocked' ? 'blocked' : target.status === 'in-progress' ? 'active' : 'static',
          });
        }
      }
    }
  }

  for (let i = 0; i < phases.length - 1; i += 1) {
    const lastBatch = phases[i].batches[phases[i].batches.length - 1];
    const source = lastBatch?.tasks[lastBatch.tasks.length - 1];
    const target = phases[i + 1].batches[0]?.tasks[0];
    if (source && target && nodeIds.has(source.id) && nodeIds.has(target.id)) {
      edges.push({
        sourceId: source.id,
        targetId: target.id,
        status: target.blocked || target.status === 'blocked' ? 'blocked' : 'static',
      });
    }
  }

  return { nodes, edges };
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

function DrawerShell({ children }: { children: ReactNode }) {
  return (
    <aside
      className="fixed bottom-0 right-0 top-0 z-50 flex w-[min(920px,64vw)] min-w-[920px] max-w-[64vw] flex-col border-l border-[color:var(--line-2)] bg-[color:var(--bg-1)] shadow-[-20px_0_60px_rgba(0,0,0,0.4)] max-[1279px]:w-[min(640px,100vw)] max-[1279px]:min-w-0 max-[1279px]:max-w-[100vw]"
      aria-label="Planning feature detail"
      role="dialog"
      aria-modal="false"
    >
      {children}
    </aside>
  );
}

function DrawerStateHeader({ onClose, children }: { onClose: () => void; children?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[color:var(--line-1)] px-[22px] py-[18px]">
      <div className="min-w-0">{children}</div>
      <BtnGhost
        size="sm"
        onClick={onClose}
        aria-label="Close planning detail"
        className="shrink-0 px-2"
      >
        <X size={14} />
      </BtnGhost>
    </div>
  );
}

function DrawerBody({
  children,
  bodyRef,
}: {
  children: ReactNode;
  bodyRef?: RefObject<HTMLDivElement>;
}) {
  return (
    <div
      ref={bodyRef}
      className="flex-1 space-y-[18px] overflow-y-auto px-[22px] py-[18px]"
    >
      {children}
    </div>
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
        type="button"
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

function resolveDocumentByPath(documents: PlanDocument[], nodePath: string): PlanDocument | null {
  if (!nodePath) return null;
  return (
    documents.find(d => d.filePath === nodePath) ||
    documents.find(d => d.canonicalPath === nodePath) ||
    documents.find(d => nodePath.endsWith(d.filePath)) ||
    documents.find(d => d.filePath.endsWith(nodePath)) ||
    null
  );
}

function LineagePanel({
  nodes,
  documents,
  onSelectDoc,
}: {
  nodes: PlanningNode[];
  documents: PlanDocument[];
  onSelectDoc: (doc: PlanDocument) => void;
}) {
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
      {sorted.map((node) => {
        const doc = resolveDocumentByPath(documents, node.path || '');
        if (doc) {
          return (
            <button
              key={node.id}
              type="button"
              onClick={() => onSelectDoc(doc)}
              className="w-full text-left hover:bg-slate-700/20 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-info"
            >
              <LineageRow node={node} />
            </button>
          );
        }
        return <LineageRow key={node.id} node={node} />;
      })}
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
              {phase.phaseNumber != null
                ? `Phase ${phase.phaseNumber}${phase.phaseTitle || phase.phaseToken ? `: ${phase.phaseTitle || phase.phaseToken}` : ''}`
                : (phase.phaseTitle || phase.phaseToken)}
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

function LinkedArtifactsPanel({
  refs,
  documents,
  onSelectDoc,
}: {
  refs: string[];
  documents: PlanDocument[];
  onSelectDoc: (doc: PlanDocument) => void;
}) {
  if (refs.length === 0) {
    return (
      <p className="text-xs text-muted-foreground/60 italic">No linked artifacts.</p>
    );
  }
  return (
    <ul className="space-y-1">
      {refs.map((ref, i) => {
        const doc =
          documents.find(d => d.filePath === ref) ||
          documents.find(d => d.canonicalPath === ref) ||
          documents.find(d => ref.endsWith(d.filePath)) ||
          documents.find(d => d.filePath.endsWith(ref)) ||
          null;
        if (doc) {
          return (
            <li key={i}>
              <button
                type="button"
                onClick={() => onSelectDoc(doc)}
                className="flex w-full items-center gap-2 rounded text-xs text-info hover:text-info/80 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-info"
              >
                <Link2 size={11} className="shrink-0 text-info/60" />
                <span className="truncate font-mono text-left" title={ref}>{ref}</span>
              </button>
            </li>
          );
        }
        return (
          <li key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
            <Link2 size={11} className="shrink-0 text-info/60" />
            <span className="truncate font-mono" title={ref}>{ref}</span>
          </li>
        );
      })}
    </ul>
  );
}

// ── Section card wrapper ──────────────────────────────────────────────────────

function SectionCard({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
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

function CollapsibleSection({
  title,
  eyebrow,
  icon,
  color = 'var(--brand)',
  count,
  actions,
  open,
  onToggle,
  children,
  sectionRef,
}: {
  title: string;
  eyebrow?: string;
  icon: ReactNode;
  color?: string;
  count?: number;
  actions?: ReactNode;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
  sectionRef?: RefObject<HTMLElement>;
}) {
  return (
    <div
      ref={sectionRef as RefObject<HTMLDivElement>}
      className="planning-panel overflow-hidden rounded-[var(--radius)]"
      style={{ borderLeft: `3px solid ${color}` }}
    >
      <div className="flex items-center gap-2.5 border-b border-[color:var(--line-1)] px-4 py-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-label={`${open ? 'Collapse' : 'Expand'} ${title}`}
          className="flex rounded p-1 text-[color:var(--ink-2)] transition-colors hover:bg-[color:var(--bg-2)] hover:text-[color:var(--ink-0)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--info)]"
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <span className="shrink-0" style={{ color }}>{icon}</span>
        <div className="min-w-0 flex-1">
          {eyebrow ? (
            <div className="planning-caps text-[9.5px]" style={{ color }}>
              {eyebrow}
            </div>
          ) : null}
          <div className="flex items-center gap-2">
            <h2 className="truncate text-sm font-semibold text-[color:var(--ink-0)]">{title}</h2>
            {typeof count === 'number' ? (
              <span className="planning-mono planning-tnum rounded border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-1.5 text-[10px] text-[color:var(--ink-3)]">
                {count}
              </span>
            ) : null}
          </div>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
      {open ? <div className="px-4 py-4">{children}</div> : null}
    </div>
  );
}

function PhaseDot({
  status,
  label,
  title,
}: {
  status: string;
  label: string;
  title: string;
}) {
  const state = phaseDotState(status);
  const colorMap = {
    completed: 'var(--ok)',
    in_progress: 'var(--info)',
    blocked: 'var(--err)',
    pending: 'var(--ink-3)',
  };
  const color = colorMap[state];

  return (
    <span
      title={title}
      role="img"
      aria-label={`${title}: ${state.replace('_', ' ')}`}
      className="planning-mono relative inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] text-[7.5px] font-semibold"
      style={{
        color: state === 'completed' ? 'var(--bg-0)' : color,
        background: state === 'completed' ? color : `color-mix(in oklab, ${color} 8%, transparent)`,
        border: `1.5px solid ${color}`,
      }}
    >
      {state === 'completed' ? '✓' : state === 'blocked' ? '!' : label}
      {state === 'in_progress' ? (
        <span
          aria-hidden="true"
          className="absolute -inset-1 rounded-md border"
          style={{ borderColor: `color-mix(in oklab, ${color} 55%, transparent)` }}
        />
      ) : null}
    </span>
  );
}

function LineageStrip({
  tiles,
  phases,
  onSelect,
}: {
  tiles: LineageTileModel[];
  phases: PhaseContextItem[];
  onSelect: (tile: LineageTileModel) => void;
}) {
  return (
    <section>
      <div className="planning-caps mb-2.5 text-[10px] text-[color:var(--ink-3)]">
        Lineage - click to expand below
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
        {tiles.map(tile => {
          const muted = tile.count === 0;
          return (
            <button
              key={tile.kind}
              type="button"
              onClick={() => onSelect(tile)}
              disabled={muted}
              aria-label={`${tile.label}: ${tile.count} item${tile.count === 1 ? '' : 's'}${tile.status ? `, status ${tile.status}` : ''}`}
              className="planning-tile min-h-[88px] text-left transition-colors disabled:cursor-default disabled:opacity-45"
              style={{
                padding: 10,
                borderColor: `color-mix(in oklab, ${tile.color} 30%, var(--line-1))`,
                background: `linear-gradient(180deg, color-mix(in oklab, ${tile.color} ${muted ? 4 : 10}%, var(--bg-2)), var(--bg-2))`,
              }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="planning-mono planning-caps text-[10px]" style={{ color: tile.color }}>
                  {tile.label}
                </span>
                <span className="planning-mono planning-tnum rounded border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-1.5 text-[10px] text-[color:var(--ink-2)]">
                  x{tile.count}
                </span>
              </div>
              <div className="mt-2 min-h-[20px]">
                {tile.kind === 'phase' && tile.count > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {phases.slice(0, 12).map((phase, index) => (
                      <PhaseDot
                        key={phase.phaseId || phase.phaseToken || index}
                        status={phase.effectiveStatus || phase.rawStatus}
                        label={String(phase.phaseNumber ?? index + 1)}
                        title={phase.phaseTitle || phase.phaseToken || `Phase ${index + 1}`}
                      />
                    ))}
                  </div>
                ) : tile.status ? (
                  <StatusPill status={tile.status} />
                ) : (
                  <span className="text-[10px] text-[color:var(--ink-3)]">-</span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function SubHeader({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="planning-caps text-[10px]" style={{ color }}>{label}</div>
      <span className="planning-mono planning-tnum rounded border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-1.5 text-[10px] text-[color:var(--ink-3)]">
        {count}
      </span>
    </div>
  );
}

function EmptyMiniState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-[color:var(--line-1)] px-3 py-3 text-xs italic text-[color:var(--ink-3)]">
      {children}
    </div>
  );
}

function SpikeTile({
  spike,
  onExec,
}: {
  spike: PlanningSpikeItem;
  onExec: (label: string) => void;
}) {
  const id = spike.spikeId || 'SPIKE';
  return (
    <div className="group planning-tile flex min-h-[48px] items-center gap-2.5 px-3 py-2.5" style={{ borderLeft: '3px solid var(--spk)' }}>
      <span className="planning-mono planning-caps shrink-0 text-[10px] text-[color:var(--spk)]">{id}</span>
      <span className="min-w-0 flex-1 truncate text-xs text-[color:var(--ink-0)]" title={spike.title}>{spike.title || id}</span>
      <StatusPill status={spike.status || 'unknown'} />
      <ExecBtn
        compact
        aria-label={`Run ${id}`}
        title={`Run ${id}`}
        onClick={(event) => {
          event.stopPropagation();
          onExec(`running ${id} - ${spike.title || 'SPIKE'}`);
        }}
        className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
      />
    </div>
  );
}

function severityColor(severity: string): string {
  const normalized = severity.toLowerCase();
  if (normalized === 'high' || normalized === 'critical') return 'var(--err)';
  if (normalized === 'medium') return 'var(--warn)';
  if (normalized === 'low') return 'var(--info)';
  return 'var(--spec)';
}

function OpenQuestionTile({
  oq,
  onResolve,
}: {
  oq: PlanningOpenQuestionItem;
  onResolve: (oq: PlanningOpenQuestionItem, answer: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [answer, setAnswer] = useState(oq.answerText || '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const color = severityColor(oq.severity || 'medium');

  useEffect(() => {
    if (!editing) return;
    textareaRef.current?.focus();
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current || rootRef.current.contains(event.target as Node)) return;
      setEditing(false);
      setError(null);
      setAnswer(oq.answerText || '');
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [editing, oq.answerText]);

  const save = useCallback(async () => {
    const trimmed = answer.trim();
    if (!trimmed || pending) return;
    setPending(true);
    setError(null);
    try {
      await onResolve(oq, trimmed);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resolve open question.');
    } finally {
      setPending(false);
    }
  }, [answer, onResolve, oq, pending]);

  return (
    <div
      ref={rootRef}
      className="planning-tile overflow-hidden px-3 py-2.5"
      style={{
        borderLeft: `3px solid ${oq.resolved ? 'var(--ok)' : color}`,
        background: oq.resolved
          ? 'color-mix(in oklab, var(--ok) 8%, var(--bg-2))'
          : 'var(--bg-2)',
      }}
    >
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 h-8 w-1 shrink-0 rounded-full" style={{ background: oq.resolved ? 'var(--ok)' : color }} />
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <span className="planning-mono planning-caps text-[10px]" style={{ color }}>{oq.oqId || 'OQ'}</span>
            {oq.resolved ? (
              <span className="inline-flex items-center gap-1 text-[10px] text-[color:var(--ok)]">
                <Check size={11} />
                resolved
              </span>
            ) : (
              <span className="planning-caps text-[9px] text-[color:var(--ink-4)]">{oq.severity || 'medium'}</span>
            )}
          </div>
          <p className="text-xs leading-5 text-[color:var(--ink-0)]">{oq.question || 'Open question'}</p>
          {oq.resolved && oq.answerText ? (
            <p className="mt-2 rounded border border-[color:color-mix(in_oklab,var(--ok)_22%,transparent)] bg-[color:color-mix(in_oklab,var(--ok)_7%,transparent)] px-2 py-1.5 text-xs leading-5 text-[color:var(--ink-1)]">
              {oq.answerText}
            </p>
          ) : null}
          {!oq.resolved && !editing ? (
            <button
              type="button"
              onClick={() => {
                setEditing(true);
                setAnswer(oq.answerText || '');
              }}
              className="mt-2 inline-flex items-center gap-1.5 rounded border border-[color:var(--line-1)] px-2 py-1 text-[11px] text-[color:var(--spec)] transition-colors hover:bg-[color:var(--bg-3)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--info)]"
            >
              + answer
            </button>
          ) : null}
          {editing ? (
            <div className="mt-2 space-y-2">
              <textarea
                ref={textareaRef}
                value={answer}
                disabled={pending}
                onChange={event => setAnswer(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    setEditing(false);
                    setAnswer(oq.answerText || '');
                    setError(null);
                  }
                  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                    event.preventDefault();
                    void save();
                  }
                }}
                className="min-h-[88px] w-full resize-y rounded-md border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-3 py-2 text-xs leading-5 text-[color:var(--ink-0)] outline-none transition-colors placeholder:text-[color:var(--ink-4)] focus:border-[color:var(--info)] disabled:opacity-60"
                placeholder="Write the resolution..."
              />
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] text-[color:var(--ink-4)]">Cmd/Ctrl+Enter to save</span>
                <div className="flex items-center gap-1.5">
                  <BtnGhost
                    size="xs"
                    disabled={pending}
                    onClick={() => {
                      setEditing(false);
                      setAnswer(oq.answerText || '');
                      setError(null);
                    }}
                  >
                    Cancel
                  </BtnGhost>
                  <BtnPrimary size="xs" disabled={pending || !answer.trim()} onClick={() => void save()}>
                    <Send size={11} />
                    {pending ? 'Saving' : 'Save'}
                  </BtnPrimary>
                </div>
              </div>
              {error ? <p className="text-[11px] text-[color:var(--err)]">{error}</p> : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function SpecQuestionsSection({
  spikes,
  openQuestions,
  onResolveQuestion,
  onExec,
}: {
  spikes: PlanningSpikeItem[];
  openQuestions: PlanningOpenQuestionItem[];
  onResolveQuestion: (oq: PlanningOpenQuestionItem, answer: string) => Promise<void>;
  onExec: (label: string) => void;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="min-w-0 space-y-2">
        <SubHeader label="SPIKEs" count={spikes.length} color="var(--spk)" />
        {spikes.length === 0 ? (
          <EmptyMiniState>No SPIKEs on record.</EmptyMiniState>
        ) : (
          <div className="space-y-2">
            {spikes.map(spike => (
              <SpikeTile key={spike.spikeId || spike.title} spike={spike} onExec={onExec} />
            ))}
          </div>
        )}
      </div>
      <div className="min-w-0 space-y-2">
        <SubHeader label="Open Questions" count={openQuestions.length} color="var(--spec)" />
        {openQuestions.length === 0 ? (
          <EmptyMiniState>No open questions.</EmptyMiniState>
        ) : (
          <div className="space-y-2">
            {openQuestions.map(oq => (
              <OpenQuestionTile key={oq.oqId || oq.question} oq={oq} onResolve={onResolveQuestion} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SegmentButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="rounded px-2.5 py-1 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--info)]"
      style={{
        background: active ? 'var(--bg-3)' : 'transparent',
        color: active ? 'var(--ink-0)' : 'var(--ink-2)',
      }}
    >
      {children}
    </button>
  );
}

function ModelLegend({
  tokenUsage,
  totalTokens,
}: {
  tokenUsage?: PlanningTokenUsageByModel;
  totalTokens?: number;
}) {
  const total = tokenUsage?.total && tokenUsage.total > 0 ? tokenUsage.total : (totalTokens ?? 0);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-[color:var(--line-1)] bg-[color:var(--bg-2)] px-3 py-2 text-[10.5px] text-[color:var(--ink-2)]">
      <span className="planning-caps text-[9.5px] text-[color:var(--ink-4)]">models</span>
      {MODEL_KEYS.map(key => {
        const value = tokenUsage?.[key] ?? 0;
        const pct = total > 0 ? Math.round((value / total) * 100) : 0;
        return (
          <span key={key} className="inline-flex items-center gap-1.5">
            <Dot tone={MODEL_COLORS[key]} aria-hidden="true" />
            <span className="planning-mono text-[10.5px]" style={{ color: MODEL_COLORS[key] }}>
              {MODEL_LABELS[key]}
            </span>
            <span className="planning-mono planning-tnum text-[10px] text-[color:var(--ink-3)]">
              {formatCompactNumber(value)} · {pct}%
            </span>
          </span>
        );
      })}
      {tokenUsage?.other ? (
        <span className="planning-mono planning-tnum text-[10px] text-[color:var(--ink-3)]">
          other {formatCompactNumber(tokenUsage.other)}
        </span>
      ) : null}
      <span className="planning-mono planning-tnum ml-auto text-[10.5px]">
        <span className="text-[color:var(--ink-3)]">Σ </span>
        <span className="text-[color:var(--ink-0)]">{formatCompactNumber(total)}</span>
        <span className="text-[color:var(--ink-3)]"> tokens</span>
      </span>
    </div>
  );
}

function TaskRow({ task, onExec }: { task: ExecutionTaskModel; onExec: (label: string) => void }) {
  return (
    <div
      className="group grid items-center gap-2 rounded px-2 py-1.5 transition-colors hover:bg-[color:var(--bg-2)]"
      style={{
        gridTemplateColumns: 'minmax(58px, 74px) minmax(120px, 1fr) auto minmax(30px, auto) auto 24px',
        borderLeft: `2px solid ${MODEL_COLORS[task.model]}`,
        background: task.blocked ? 'color-mix(in oklab, var(--err) 9%, transparent)' : 'transparent',
      }}
    >
      <span className="planning-mono truncate text-[10.5px] text-[color:var(--ink-3)]" title={task.id}>{task.id}</span>
      <span className="truncate text-xs text-[color:var(--ink-0)]" title={task.title}>{task.title}</span>
      <span
        className="planning-mono max-w-[112px] truncate rounded border px-1.5 py-0.5 text-[9.5px]"
        title={`${task.agent} - ${MODEL_LABELS[task.model]}`}
        style={{
          color: MODEL_COLORS[task.model],
          borderColor: `color-mix(in oklab, ${MODEL_COLORS[task.model]} 40%, transparent)`,
          background: `color-mix(in oklab, ${MODEL_COLORS[task.model]} 10%, transparent)`,
        }}
      >
        <span className="sr-only">{MODEL_LABELS[task.model]} model: </span>
        {task.agent}
      </span>
      <span className="planning-mono planning-tnum text-right text-[10px] text-[color:var(--ink-4)]" title="Task token actuals unavailable in feature planning context">
        -
      </span>
      <StatusPill status={task.status || 'todo'} />
      <ExecBtn
        compact
        aria-label={`Run task ${task.id}`}
        title={`Run task ${task.id}`}
        onClick={(event) => {
          event.stopPropagation();
          onExec(`running ${task.id} - ${task.title}`);
        }}
        className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
      />
    </div>
  );
}

function BatchColumn({ batch, phase, onExec }: { batch: ExecutionBatchModel; phase: ExecutionPhaseModel; onExec: (label: string) => void }) {
  return (
    <div className="min-w-[220px] flex-1 rounded-md border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="planning-caps text-[9.5px] text-[color:var(--ink-3)]">batch {batch.label}</div>
          <div className="planning-mono text-[10px] text-[color:var(--ink-4)]">{batch.tasks.length} tasks · parallel</div>
        </div>
        <ExecBtn
          compact
          aria-label={`Run batch ${batch.label}`}
          title={`Run batch ${batch.label}`}
          onClick={(event) => {
            event.stopPropagation();
            onExec(`running Phase ${String(phase.number).padStart(2, '0')} batch ${batch.label}`);
          }}
        />
      </div>
      {batch.tasks.length === 0 ? (
        <EmptyMiniState>No task IDs in this batch.</EmptyMiniState>
      ) : (
        <div className="space-y-1">
          {batch.tasks.map(task => (
            <TaskRow key={task.id} task={task} onExec={onExec} />
          ))}
        </div>
      )}
    </div>
  );
}

function PhaseExecutionCard({ phase, onExec }: { phase: ExecutionPhaseModel; onExec: (label: string) => void }) {
  const color = phase.status === 'blocked'
    ? 'var(--err)'
    : phase.status === 'completed'
      ? 'var(--ok)'
      : phase.status === 'in-progress' || phase.status === 'in_progress'
        ? 'var(--plan)'
        : 'var(--prog)';

  return (
    <div className="planning-tile p-3.5" style={{ borderLeft: `3px solid ${color}` }}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2.5">
          <span className="planning-mono planning-caps text-[10.5px] text-[color:var(--ink-3)]">
            PHASE {String(phase.number).padStart(2, '0')}
          </span>
          <h3 className="m-0 min-w-0 truncate text-sm font-semibold text-[color:var(--ink-0)]">{phase.title}</h3>
          <StatusPill status={phase.status || 'unknown'} />
          <ExecBtn
            label="run phase"
            onClick={(event) => {
              event.stopPropagation();
              onExec(`running Phase ${String(phase.number).padStart(2, '0')} - ${phase.title}`);
            }}
          />
        </div>
        <div className="flex min-w-[190px] items-center gap-2">
          <span className="planning-mono planning-tnum text-[10.5px] text-[color:var(--ink-3)]">
            {phase.completedTasks}/{phase.totalTasks} · {phase.progressPct}%
          </span>
          <div className="h-1.5 min-w-[110px] flex-1 overflow-hidden rounded-full bg-[color:var(--bg-3)]">
            <div className="h-full rounded-full" style={{ width: `${phase.progressPct}%`, background: color }} />
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-2 xl:flex-row">
        {phase.batches.length === 0 ? (
          <EmptyMiniState>No batches defined.</EmptyMiniState>
        ) : (
          phase.batches.map(batch => (
            <BatchColumn key={batch.id} batch={batch} phase={phase} onExec={onExec} />
          ))
        )}
      </div>
    </div>
  );
}

function DependencyDagView({ phases }: { phases: ExecutionPhaseModel[] }) {
  const dag = useMemo(() => buildDependencyDag(phases), [phases]);
  const phaseGap = 28;
  const nodeW = 180;
  const nodeH = 48;
  const colGap = 46;
  const rowGap = 12;
  const pad = 16;
  const headerH = 42;

  const phaseBlocks = phases.map(phase => {
    const rows = Math.max(1, ...phase.batches.map(batch => Math.max(batch.tasks.length, 1)));
    const width = pad * 2 + Math.max(1, phase.batches.length) * nodeW + Math.max(0, phase.batches.length - 1) * colGap;
    const height = pad * 2 + headerH + rows * nodeH + Math.max(0, rows - 1) * rowGap;
    return { phase, rows, width, height };
  });
  const totalWidth = Math.max(640, ...phaseBlocks.map(block => block.width));
  let yCursor = 0;
  const blockTops = phaseBlocks.map(block => {
    const top = yCursor;
    yCursor += block.height + phaseGap;
    return top;
  });
  const totalHeight = Math.max(220, yCursor - phaseGap);

  const positions: Record<string, { x: number; y: number; w: number; h: number }> = {};
  phaseBlocks.forEach((block, blockIndex) => {
    const yStart = blockTops[blockIndex] + pad + headerH;
    block.phase.batches.forEach((batch, batchIndex) => {
      batch.tasks.forEach((task, taskIndex) => {
        positions[task.id] = {
          x: pad + batchIndex * (nodeW + colGap),
          y: yStart + taskIndex * (nodeH + rowGap),
          w: nodeW,
          h: nodeH,
        };
      });
    });
  });
  const nodeMap = new Map(dag.nodes.map(node => [node.id, node]));

  if (dag.nodes.length === 0) {
    return <EmptyMiniState>No task IDs available for DAG rendering.</EmptyMiniState>;
  }

  return (
    <div className="overflow-auto rounded-md border border-[color:var(--line-1)] bg-[color:var(--bg-0)]">
      <div className="relative" style={{ width: totalWidth, height: totalHeight }}>
        {phaseBlocks.map((block, blockIndex) => (
          <div
            key={block.phase.id}
            className="absolute border-b border-dashed border-[color:var(--line-1)]"
            style={{
              left: 0,
              top: blockTops[blockIndex],
              width: totalWidth,
              height: block.height,
            }}
          >
            <div className="absolute left-4 top-2.5 flex items-center gap-2">
              <span className="planning-mono planning-caps text-[10px] text-[color:var(--prog)]">
                PHASE {String(block.phase.number).padStart(2, '0')}
              </span>
              <span className="max-w-[320px] truncate text-xs font-medium text-[color:var(--ink-1)]">{block.phase.title}</span>
              <StatusPill status={block.phase.status || 'unknown'} />
            </div>
            {block.phase.batches.map((batch, batchIndex) => (
              <div
                key={batch.id}
                className="planning-caps absolute text-[9.5px] text-[color:var(--ink-4)]"
                style={{ left: pad + batchIndex * (nodeW + colGap), top: 29, width: nodeW }}
              >
                batch {batch.label} · parallel
              </div>
            ))}
          </div>
        ))}

        <svg width={totalWidth} height={totalHeight} className="pointer-events-none absolute inset-0">
          <defs>
            <marker id="planning-detail-dag-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M0 0 L10 5 L0 10 z" fill="currentColor" />
            </marker>
          </defs>
          {dag.edges.map((edge, index) => {
            const from = positions[edge.sourceId];
            const to = positions[edge.targetId];
            if (!from || !to) return null;
            const x1 = from.x + from.w;
            const y1 = from.y + from.h / 2;
            const x2 = to.x;
            const y2 = to.y + to.h / 2;
            const mx = (x1 + x2) / 2;
            const color = edge.status === 'blocked' ? 'var(--err)' : edge.status === 'active' ? 'var(--plan)' : 'var(--line-2)';
            return (
              <path
                key={`${edge.sourceId}-${edge.targetId}-${index}`}
                d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2 - 6} ${y2}`}
                fill="none"
                stroke={color}
                strokeWidth="1.4"
                strokeDasharray={edge.status === 'active' ? '5 4' : undefined}
                markerEnd="url(#planning-detail-dag-arrow)"
                style={{ color }}
              />
            );
          })}
        </svg>

        {dag.nodes.map(node => {
          const pos = positions[node.id];
          if (!pos) return null;
          const color = node.status === 'blocked' ? 'var(--err)' : node.status === 'completed' ? 'var(--ok)' : node.status === 'in-progress' ? 'var(--plan)' : 'var(--ink-2)';
          return (
            <div
              key={node.id}
              className="absolute flex flex-col justify-between rounded-md border bg-[color:var(--bg-2)] px-2.5 py-2"
              style={{
                left: pos.x,
                top: pos.y,
                width: pos.w,
                height: pos.h,
                borderColor: node.status === 'blocked' ? 'color-mix(in oklab, var(--err) 45%, var(--line-1))' : 'var(--line-1)',
                borderLeft: `3px solid ${color}`,
              }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="planning-mono truncate text-[10px] text-[color:var(--ink-3)]">{node.id}</span>
                <Dot tone={color} aria-hidden="true" />
                <span className="sr-only">Status {node.status}</span>
              </div>
              <div className="line-clamp-2 text-[11px] leading-[1.25] text-[color:var(--ink-0)]" title={nodeMap.get(node.id)?.title}>
                {node.title}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-[color:var(--line-1)] bg-[color:var(--bg-1)] px-3 py-2 text-[10.5px] text-[color:var(--ink-3)]">
        <span className="planning-caps text-[9.5px]">deps</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 bg-[color:var(--line-2)]" /> progression</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 bg-[color:var(--plan)]" /> active</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 bg-[color:var(--err)]" /> blocked</span>
        <span className="ml-auto">Batch columns show parallelizable task groups.</span>
      </div>
    </div>
  );
}

function ExecutionTasksSection({
  phases,
  tokenUsage,
  totalTokens,
  viewMode,
  onViewModeChange,
  onExec,
}: {
  phases: ExecutionPhaseModel[];
  tokenUsage?: PlanningTokenUsageByModel;
  totalTokens?: number;
  viewMode: ExecutionViewMode;
  onViewModeChange: (mode: ExecutionViewMode) => void;
  onExec: (label: string) => void;
}) {
  if (phases.length === 0) {
    return <EmptyMiniState>No execution phases available.</EmptyMiniState>;
  }

  return (
    <div className="space-y-3.5">
      <div className="flex justify-end">
        <div className="flex gap-1 rounded-md border border-[color:var(--line-1)] bg-[color:var(--bg-0)] p-1">
          <SegmentButton active={viewMode === 'batches'} onClick={() => onViewModeChange('batches')}>Batches</SegmentButton>
          <SegmentButton active={viewMode === 'dag'} onClick={() => onViewModeChange('dag')}>Dependency DAG</SegmentButton>
        </div>
      </div>
      {viewMode === 'batches' ? (
        <>
          <ModelLegend tokenUsage={tokenUsage} totalTokens={totalTokens} />
          <div className="space-y-3">
            {phases.map(phase => (
              <PhaseExecutionCard key={phase.id} phase={phase} onExec={onExec} />
            ))}
          </div>
        </>
      ) : (
        <DependencyDagView phases={phases} />
      )}
    </div>
  );
}

function BottomToast({ message, tone }: { message: string; tone: 'exec' | 'error' | 'success' }) {
  const color = tone === 'error' ? 'var(--err)' : tone === 'success' ? 'var(--ok)' : 'var(--brand)';
  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-[70] -translate-x-1/2 rounded-md border border-[color:var(--line-2)] bg-[color:var(--bg-0)] px-4 py-2.5 shadow-[0_16px_40px_rgba(0,0,0,0.35)]" aria-live="polite">
      <div className="flex items-center gap-2 text-xs text-[color:var(--ink-0)]">
        <Dot tone={color} aria-hidden="true" />
        <span className="planning-mono">{tone === 'exec' ? '▶ ' : ''}{message}</span>
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
  const { activeProject, documents } = useData();
  const [state, setState] = useState<DetailFetchState>({ phase: 'idle' });
  const [selectedDoc, setSelectedDoc] = useState<PlanDocument | null>(null);
  const [openQuestions, setOpenQuestions] = useState<PlanningOpenQuestionItem[]>([]);
  const [executionViewMode, setExecutionViewMode] = useState<ExecutionViewMode>('batches');
  const [toast, setToast] = useState<{ message: string; tone: 'exec' | 'error' | 'success' } | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const [openSections, setOpenSections] = useState<Record<DetailSectionKey, boolean>>({
    lineage: true,
    spec: true,
    phases: true,
    tasks: true,
    sessions: true,
    blockers: true,
    artifacts: true,
  });
  const bodyRef = useRef<HTMLDivElement>(null);
  const sectionRefs = {
    lineage: useRef<HTMLElement>(null),
    spec: useRef<HTMLElement>(null),
    phases: useRef<HTMLElement>(null),
    tasks: useRef<HTMLElement>(null),
    sessions: useRef<HTMLElement>(null),
    blockers: useRef<HTMLElement>(null),
    artifacts: useRef<HTMLElement>(null),
  };

  const closeDetail = useCallback(() => {
    navigate('/planning');
  }, [navigate]);

  const scrollToSection = useCallback((section: DetailSectionKey) => {
    setOpenSections(current => ({ ...current, [section]: true }));
    window.setTimeout(() => {
      const body = bodyRef.current;
      const target = sectionRefs[section].current;
      if (!body || !target) return;
      body.scrollTo({ top: Math.max(target.offsetTop - 16, 0), behavior: 'smooth' });
    }, 0);
  }, [sectionRefs]);

  const showToast = useCallback((message: string, tone: 'exec' | 'error' | 'success' = 'exec') => {
    if (toastTimerRef.current != null) {
      window.clearTimeout(toastTimerRef.current);
    }
    setToast({ message, tone });
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 2400);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current != null) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

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
      setOpenQuestions(context.openQuestions ?? []);
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
  const readyContext = state.phase === 'ready' ? state.context : null;
  const executionPhases = useMemo(
    () => buildExecutionPhases(readyContext?.phases ?? []),
    [readyContext?.phases],
  );
  const totalExecutionTasks = executionPhases.reduce((sum, phase) => sum + phase.totalTasks, 0);
  const handleExecToast = useCallback((label: string) => {
    showToast(label, 'exec');
  }, [showToast]);
  const handleResolveQuestion = useCallback(async (oq: PlanningOpenQuestionItem, answer: string) => {
    if (!featureId) return;
    try {
      const resolved = await resolvePlanningOpenQuestion(featureId, oq.oqId, answer);
      setOpenQuestions(current => current.map(item => (
        item.oqId === oq.oqId ? resolved : item
      )));
      showToast(`${oq.oqId || 'Open question'} resolved`, 'success');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to resolve open question.';
      showToast(message, 'error');
      throw err;
    }
  }, [featureId, showToast]);

  if (!activeProject) {
    return (
      <DrawerShell>
        <DrawerStateHeader onClose={closeDetail}>
          <p className="planning-caps text-[10px] text-[color:var(--ink-3)]">Planning detail</p>
        </DrawerStateHeader>
        <DrawerBody>
          <NoProjectShell />
        </DrawerBody>
      </DrawerShell>
    );
  }

  if (state.phase === 'idle' || state.phase === 'loading') {
    return (
      <DrawerShell>
        <DrawerStateHeader onClose={closeDetail}>
          <p className="planning-caps text-[10px] text-[color:var(--ink-3)]">Planning detail</p>
        </DrawerStateHeader>
        <DrawerBody>
          <DetailSkeleton />
        </DrawerBody>
      </DrawerShell>
    );
  }

  if (state.phase === 'error') {
    return (
      <DrawerShell>
        <DrawerStateHeader onClose={closeDetail}>
          <button
            type="button"
            onClick={closeDetail}
            className="flex items-center gap-2 text-xs text-[color:var(--ink-3)] transition-colors hover:text-[color:var(--ink-0)]"
          >
            <ArrowLeft size={13} />
            Back to Planning
          </button>
        </DrawerStateHeader>
        <DrawerBody>
          <DetailError message={state.message} onRetry={() => void loadContext()} />
        </DrawerBody>
      </DrawerShell>
    );
  }

  const { context } = state;
  const planningStatus = castPlanningStatus(context.planningStatus);
  const isMismatch = context.mismatchState !== 'aligned' && context.mismatchState !== 'unknown';
  const mismatchReason = planningStatus?.mismatchState?.reason ?? context.mismatchState;
  const evidenceLabels = planningStatus?.mismatchState?.evidence?.map(ev => ev.label) ?? [];
  const featureMeta = deriveFeatureMeta(context, featureId);
  const lineageTiles = buildLineageTiles(context);
  const visibleTags = (context.tags ?? []).slice(0, 3);
  const spikes = context.spikes ?? [];

  return (
    <DrawerShell>
      <header className="border-b border-[color:var(--line-1)] px-[22px] py-[18px]">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              {featureMeta.category ? (
                <span className="planning-caps text-[10px] text-[color:var(--ink-3)]">{featureMeta.category}</span>
              ) : null}
              {featureMeta.category && featureMeta.slug ? (
                <span className="text-[color:var(--ink-4)]">/</span>
              ) : null}
              {featureMeta.slug ? (
                <span className="planning-mono text-[11px] text-[color:var(--ink-2)]">{featureMeta.slug}</span>
              ) : null}
              {isMismatch ? (
                <Chip className="planning-mono border-[color:color-mix(in_oklab,var(--mag)_35%,transparent)] bg-[color:color-mix(in_oklab,var(--mag)_18%,transparent)] text-[10px] text-[color:var(--mag)]">
                  mismatch - {context.mismatchState}
                </Chip>
              ) : null}
              <LiveStatusDot status={liveStatus} />
            </div>
            <h1 id="planning-detail-title" className="planning-serif m-0 truncate text-[26px] font-medium italic tracking-[0] text-[color:var(--ink-0)]">
              {context.featureName || featureId}
            </h1>
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <StatusPill status={context.rawStatus || 'unknown'} />
              {context.rawStatus !== context.effectiveStatus ? (
                <>
                  <span className="text-[color:var(--ink-3)]">-&gt;</span>
                  <StatusPill status={context.effectiveStatus || 'unknown'} />
                </>
              ) : null}
              {context.complexity ? (
                <Chip className="planning-mono text-[10px]">{context.complexity}</Chip>
              ) : null}
              {visibleTags.map(tag => (
                <Chip key={tag} className="text-[10.5px]">{tag}</Chip>
              ))}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <BtnPrimary size="sm" onClick={() => handleExecToast(`running ${context.featureName || featureId || 'feature'}`)}>
              <Play size={13} />
              Execute
            </BtnPrimary>
            <BtnGhost size="sm" onClick={closeDetail} aria-label="Close planning detail" className="px-2">
              <X size={14} />
            </BtnGhost>
          </div>
        </div>
        {isMismatch ? (
          <div className="mt-3">
            <MismatchBadge state={context.mismatchState} reason={mismatchReason} evidenceLabels={evidenceLabels} />
          </div>
        ) : null}
      </header>

      <DrawerBody bodyRef={bodyRef}>
        <section ref={sectionRefs.lineage}>
          <LineageStrip
            tiles={lineageTiles}
            phases={context.phases}
            onSelect={(tile) => scrollToSection(tile.section)}
          />
        </section>

        <CollapsibleSection
          title="SPIKEs & Open Questions"
          eyebrow="Design Spec lineage"
          icon={<AlertCircle size={15} />}
          color="var(--spec)"
          count={spikes.length + openQuestions.length}
          open={openSections.spec}
          onToggle={() => setOpenSections(current => ({ ...current, spec: !current.spec }))}
          sectionRef={sectionRefs.spec}
        >
          <SpecQuestionsSection
            spikes={spikes}
            openQuestions={openQuestions}
            onResolveQuestion={handleResolveQuestion}
            onExec={handleExecToast}
          />
        </CollapsibleSection>

        {context.phases.length > 0 && (
          <CollapsibleSection
            title="Phases"
            eyebrow="Linked to plan"
            icon={<BookOpen size={15} />}
            color="var(--prog)"
            open={openSections.phases}
            onToggle={() => setOpenSections(current => ({ ...current, phases: !current.phases }))}
            sectionRef={sectionRefs.phases}
          >
            <div className="space-y-2">
              {context.phases.map((phase) => (
                <PhaseAccordion key={phase.phaseId} phase={phase} />
              ))}
            </div>
          </CollapsibleSection>
        )}

        {context.phases.length > 0 && (
          <CollapsibleSection
            title="Execution tasks"
            eyebrow="Linked to Plan"
            icon={<Network size={15} />}
            color="var(--plan)"
            count={totalExecutionTasks}
            open={openSections.tasks}
            onToggle={() => setOpenSections(current => ({ ...current, tasks: !current.tasks }))}
            sectionRef={sectionRefs.tasks}
          >
            <ExecutionTasksSection
              phases={executionPhases}
              tokenUsage={context.tokenUsageByModel}
              totalTokens={context.totalTokens}
              viewMode={executionViewMode}
              onViewModeChange={setExecutionViewMode}
              onExec={handleExecToast}
            />
          </CollapsibleSection>
        )}

        <CollapsibleSection
          title="Agent Sessions"
          eyebrow="Session forensics"
          icon={<Bot size={15} />}
          color="var(--brand)"
          open={openSections.sessions}
          onToggle={() => setOpenSections(current => ({ ...current, sessions: !current.sessions }))}
          sectionRef={sectionRefs.sessions}
        >
          {featureId && (
            <PlanningFeatureAgentLane featureId={featureId} />
          )}
        </CollapsibleSection>

        <CollapsibleSection
          title="Blockers"
          eyebrow="Planning health"
          icon={<AlertTriangle size={15} />}
          color="var(--warn)"
          open={openSections.blockers}
          onToggle={() => setOpenSections(current => ({ ...current, blockers: !current.blockers }))}
          sectionRef={sectionRefs.blockers}
        >
          <BlockersPanel
            blockedBatchIds={context.blockedBatchIds}
            nodes={context.graph.nodes}
          />
        </CollapsibleSection>

        <CollapsibleSection
          title="Linked Artifacts"
          eyebrow="Artifact lineage"
          icon={<Link2 size={15} />}
          color="var(--plan)"
          open={openSections.artifacts}
          onToggle={() => setOpenSections(current => ({ ...current, artifacts: !current.artifacts }))}
          sectionRef={sectionRefs.artifacts}
        >
          <LinkedArtifactsPanel
            refs={context.linkedArtifactRefs}
            documents={documents}
            onSelectDoc={setSelectedDoc}
          />
        </CollapsibleSection>

        <SectionCard
          title="Raw Lineage Nodes"
          icon={<FolderSearch size={15} />}
        >
          <LineagePanel
            nodes={sortNodesByType(context.graph.nodes)}
            documents={documents}
            onSelectDoc={setSelectedDoc}
          />
        </SectionCard>
      </DrawerBody>

      {selectedDoc && (
        <DocumentModal
          doc={selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onBack={() => setSelectedDoc(null)}
          onOpenFeature={(featureId) => {
            setSelectedDoc(null);
            navigate(planningRouteFeatureModalHref(featureId));
          }}
          backLabel="Planning Detail"
        />
      )}
      {toast ? <BottomToast message={toast.message} tone={toast.tone} /> : null}
    </DrawerShell>
  );
}
