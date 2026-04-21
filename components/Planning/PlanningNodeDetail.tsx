import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
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
  Play,
  RefreshCw,
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
  PlanningPhaseBatch,
  PhaseContextItem,
} from '../../types';
import { getFeaturePlanningContext, PlanningApiError } from '../../services/planning';
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
  StatusPill,
} from './primitives/PhaseZeroPrimitives';

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
type DetailSectionKey = 'lineage' | 'phases' | 'blockers' | 'artifacts';

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
  { kind: 'spec', label: 'SPEC', color: 'var(--spec)', section: 'artifacts' },
  { kind: 'spike', label: 'SPIKE', color: 'var(--spk)', section: 'artifacts' },
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
  open,
  onToggle,
  children,
  sectionRef,
}: {
  title: string;
  eyebrow?: string;
  icon: ReactNode;
  color?: string;
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
          <h2 className="truncate text-sm font-semibold text-[color:var(--ink-0)]">{title}</h2>
        </div>
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
  const [openSections, setOpenSections] = useState<Record<DetailSectionKey, boolean>>({
    lineage: true,
    phases: true,
    blockers: true,
    artifacts: true,
  });
  const bodyRef = useRef<HTMLDivElement>(null);
  const sectionRefs = {
    lineage: useRef<HTMLElement>(null),
    phases: useRef<HTMLElement>(null),
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
            <h1 className="planning-serif m-0 truncate text-[26px] font-medium italic tracking-[0] text-[color:var(--ink-0)]">
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
            <BtnPrimary size="sm" onClick={() => undefined}>
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
          backLabel="Planning Detail"
        />
      )}
    </DrawerShell>
  );
}
