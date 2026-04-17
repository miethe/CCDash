import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Clock,
  FolderSearch,
  RefreshCw,
} from 'lucide-react';

import type {
  PlanningMismatchStateValue,
  PlanningNode,
  PlanningNodeType,
  PlanningPhaseBatch,
  ProjectPlanningGraph,
} from '../../types';
import { getProjectPlanningGraph, PlanningApiError } from '../../services/planning';
import { PlanningNodeTypeIcon } from '@miethe/ui/primitives';

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

function formatGeneratedAt(value?: string): string {
  if (!value) return 'n/a';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

function groupByFeatureSlug(nodes: PlanningNode[]): Map<string, PlanningNode[]> {
  const map = new Map<string, PlanningNode[]>();
  for (const node of nodes) {
    const slug = node.featureSlug || '(unknown)';
    const existing = map.get(slug);
    if (existing) {
      existing.push(node);
    } else {
      map.set(slug, [node]);
    }
  }
  return map;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function nodeTypeLabel(type: PlanningNodeType): string {
  switch (type) {
    case 'design_spec': return 'Design Spec';
    case 'prd': return 'PRD';
    case 'implementation_plan': return 'Impl Plan';
    case 'progress': return 'Progress';
    case 'context': return 'Context';
    case 'tracker': return 'Tracker';
    case 'report': return 'Report';
    default: return type;
  }
}

function StatusBadge({ label, variant = 'default' }: { label: string; variant?: 'default' | 'mismatch' | 'ok' }) {
  const base = 'inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium leading-none';
  const colors: Record<string, string> = {
    default: 'bg-slate-700/60 text-slate-300',
    mismatch: 'bg-amber-600/20 text-amber-400',
    ok: 'bg-emerald-600/20 text-emerald-400',
  };
  return (
    <span className={`${base} ${colors[variant] ?? colors.default}`}>
      {label}
    </span>
  );
}

function FeatureSlugChip({
  slug,
  onClick,
}: {
  slug: string;
  onClick?: () => void;
}) {
  if (onClick) {
    return (
      <button
        onClick={onClick}
        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-info bg-info/10 hover:bg-info/20 transition-colors"
      >
        {slug}
      </button>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground bg-slate-700/40">
      {slug}
    </span>
  );
}

// ── Lineage (Left panel) ──────────────────────────────────────────────────────

interface FeatureCardProps {
  slug: string;
  nodes: PlanningNode[];
  onSelectFeature?: (featureId: string) => void;
}

function FeatureLineageCard({ slug, nodes, onSelectFeature }: FeatureCardProps) {
  const [expanded, setExpanded] = useState(false);
  const sorted = sortNodesByType(nodes);
  const hasMismatch = nodes.some(n => n.mismatchState?.isMismatch);

  return (
    <div className="rounded-lg border border-panel-border bg-surface-elevated overflow-hidden">
      <button
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-slate-700/30 transition-colors"
        onClick={() => setExpanded(e => !e)}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? (
            <ChevronDown size={13} className="shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight size={13} className="shrink-0 text-muted-foreground" />
          )}
          <span
            className="truncate text-xs font-medium text-panel-foreground hover:text-info transition-colors"
            onClick={(e) => {
              if (onSelectFeature) {
                e.stopPropagation();
                onSelectFeature(slug);
              }
            }}
          >
            {slug}
          </span>
          {hasMismatch && (
            <AlertTriangle size={11} className="shrink-0 text-amber-400" />
          )}
        </div>
        <span className="shrink-0 text-[10px] text-muted-foreground">{nodes.length} nodes</span>
      </button>

      {expanded && (
        <div className="border-t border-panel-border px-3 py-2 space-y-1">
          {sorted.map((node) => {
            const isMismatch = node.mismatchState?.isMismatch;
            const effectiveVariant = isMismatch ? 'mismatch' : 'ok';
            return (
              <div
                key={node.id}
                className="flex items-center gap-2 py-1 text-xs"
              >
                <span className="text-muted-foreground/70">
                  <PlanningNodeTypeIcon type={node.type} size={12} />
                </span>
                <span className="flex-1 truncate text-muted-foreground" title={node.title}>
                  {node.title || nodeTypeLabel(node.type)}
                </span>
                <div className="flex items-center gap-1 shrink-0">
                  <StatusBadge label={node.rawStatus} />
                  {node.effectiveStatus && node.effectiveStatus !== node.rawStatus && (
                    <StatusBadge label={node.effectiveStatus} variant={effectiveVariant} />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Attention rows ────────────────────────────────────────────────────────────

const STALE_STATES: PlanningMismatchStateValue[] = ['reversed', 'stale', 'unresolved'];

function AttentionRow({
  title,
  reason,
  slug,
  onSelectFeature,
}: {
  title: string;
  reason?: string;
  slug?: string;
  onSelectFeature?: (featureId: string) => void;
}) {
  return (
    <div className="flex items-start gap-2 py-1.5 text-xs border-b border-panel-border/50 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="truncate text-muted-foreground font-medium">{title}</p>
        {reason && (
          <p className="mt-0.5 truncate text-muted-foreground/60 text-[10px]">{reason}</p>
        )}
      </div>
      {slug && (
        <FeatureSlugChip
          slug={slug}
          onClick={onSelectFeature ? () => onSelectFeature(slug) : undefined}
        />
      )}
    </div>
  );
}

function AttentionSubPanel({
  title,
  children,
  count,
}: {
  title: string;
  children: React.ReactNode;
  count: number;
}) {
  if (count === 0) return null;
  return (
    <div className="rounded-lg border border-panel-border bg-surface-elevated overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-panel-border">
        <span className="text-xs font-medium text-panel-foreground">{title}</span>
        <span className="text-[10px] text-muted-foreground">{count}</span>
      </div>
      <div className="px-3 py-1">
        {children}
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyGraphState() {
  return (
    <div className="flex items-center justify-center rounded-xl border border-dashed border-panel-border bg-surface-elevated/40 p-10 text-center">
      <div>
        <FolderSearch size={28} className="mx-auto mb-3 text-muted-foreground/40" />
        <p className="text-sm font-medium text-muted-foreground">No lineage yet.</p>
        <p className="mt-1 text-xs text-muted-foreground/60">
          Add a PRD or design spec to seed the planning graph.
        </p>
      </div>
    </div>
  );
}

// ── Loading / Error ───────────────────────────────────────────────────────────

function GraphSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="h-6 rounded bg-slate-700/40 w-1/3" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <div className="h-10 rounded bg-slate-700/40" />
          <div className="h-10 rounded bg-slate-700/40" />
          <div className="h-10 rounded bg-slate-700/40" />
        </div>
        <div className="space-y-2">
          <div className="h-10 rounded bg-slate-700/40" />
          <div className="h-10 rounded bg-slate-700/40" />
        </div>
      </div>
    </div>
  );
}

function GraphError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-danger/40 bg-danger/5 px-4 py-3">
      <AlertCircle size={15} className="mt-0.5 shrink-0 text-danger" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-danger-foreground">{message}</p>
      </div>
      <button
        onClick={onRetry}
        className="flex shrink-0 items-center gap-1.5 rounded border border-danger/40 bg-danger/10 px-2 py-1 text-[10px] font-medium text-danger-foreground hover:bg-danger/20 transition-colors"
      >
        <RefreshCw size={10} />
        Retry
      </button>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface PlanningGraphPanelProps {
  projectId: string | null;
  onSelectFeature?: (featureId: string) => void;
}

type GraphFetchState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; graph: ProjectPlanningGraph };

export function PlanningGraphPanel({ projectId, onSelectFeature }: PlanningGraphPanelProps) {
  const [state, setState] = useState<GraphFetchState>({ phase: 'idle' });

  const loadGraph = useCallback(async () => {
    if (!projectId) {
      setState({ phase: 'idle' });
      return;
    }
    setState({ phase: 'loading' });
    try {
      const graph = await getProjectPlanningGraph({ projectId });
      setState({ phase: 'ready', graph });
    } catch (err) {
      const message =
        err instanceof PlanningApiError
          ? `Planning graph error (${err.status}): ${err.message}`
          : err instanceof Error
            ? err.message
            : 'Failed to load planning graph.';
      setState({ phase: 'error', message });
    }
  }, [projectId]);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  if (state.phase === 'idle' || state.phase === 'loading') {
    return <GraphSkeleton />;
  }

  if (state.phase === 'error') {
    return <GraphError message={state.message} onRetry={() => void loadGraph()} />;
  }

  const { graph } = state;

  if (graph.nodeCount === 0) {
    return <EmptyGraphState />;
  }

  // Grouped lineage
  const bySlug = groupByFeatureSlug(graph.nodes);
  const slugsWithMultipleTypes = Array.from(bySlug.entries())
    .filter(([, nodes]) => new Set(nodes.map(n => n.type)).size >= 2)
    .map(([slug]) => slug);

  // Attention: mismatched nodes (top 6)
  const mismatchNodes = graph.nodes
    .filter(n => n.mismatchState?.isMismatch)
    .slice(0, 6);

  // Blocked phase batches (top 6)
  const blockedBatches: PlanningPhaseBatch[] = graph.phaseBatches
    .filter((b) => b.readinessState === 'blocked')
    .slice(0, 6);

  // Stale/reversed nodes (top 6)
  const staleNodes = graph.nodes
    .filter(n => STALE_STATES.includes(n.mismatchState?.state as PlanningMismatchStateValue))
    .slice(0, 6);

  const hasAttention = mismatchNodes.length > 0 || blockedBatches.length > 0 || staleNodes.length > 0;

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span className="font-medium text-panel-foreground">
          {graph.nodeCount} nodes
          <span className="mx-1 text-panel-border">·</span>
          {graph.edgeCount} edges
          <span className="mx-1 text-panel-border">·</span>
          {graph.phaseBatches.length} batches
        </span>
        {graph.generatedAt && (
          <span className="flex items-center gap-1 text-muted-foreground/70">
            <Clock size={11} />
            Generated {formatGeneratedAt(graph.generatedAt)}
          </span>
        )}
        {state.phase === 'ready' && (
          <button
            onClick={() => void loadGraph()}
            className="ml-auto flex items-center gap-1 rounded border border-panel-border px-2 py-1 text-[10px] text-muted-foreground hover:text-panel-foreground hover:bg-slate-700/30 transition-colors"
          >
            <RefreshCw size={10} />
            Refresh
          </button>
        )}
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Left: Lineage by Feature */}
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Lineage by Feature
          </h3>
          {slugsWithMultipleTypes.length === 0 ? (
            <p className="text-xs text-muted-foreground/60 italic">No multi-node features detected.</p>
          ) : (
            <div className="space-y-1.5">
              {slugsWithMultipleTypes.map((slug) => (
                <FeatureLineageCard
                  key={slug}
                  slug={slug}
                  nodes={sortNodesByType(bySlug.get(slug) ?? [])}
                  onSelectFeature={onSelectFeature}
                />
              ))}
              {/* Also show single-type features if they exist */}
              {Array.from(bySlug.entries())
                .filter(([slug, nodes]) => !slugsWithMultipleTypes.includes(slug) && nodes.length > 0)
                .map(([slug, nodes]) => (
                  <FeatureLineageCard
                    key={slug}
                    slug={slug}
                    nodes={nodes}
                    onSelectFeature={onSelectFeature}
                  />
                ))}
            </div>
          )}
        </div>

        {/* Right: Attention */}
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Attention
          </h3>
          {!hasAttention ? (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5">
              <span className="text-xs text-emerald-400">All nodes aligned — no blockers or mismatches.</span>
            </div>
          ) : (
            <div className="space-y-2">
              <AttentionSubPanel title="Status Mismatches" count={mismatchNodes.length}>
                {mismatchNodes.map((node) => (
                  <AttentionRow
                    key={node.id}
                    title={node.title || node.id}
                    reason={node.mismatchState?.reason}
                    slug={node.featureSlug}
                    onSelectFeature={onSelectFeature}
                  />
                ))}
              </AttentionSubPanel>

              <AttentionSubPanel title="Blocked Batches" count={blockedBatches.length}>
                {blockedBatches.map((batch) => (
                  <AttentionRow
                    key={batch.batchId}
                    title={`Phase ${batch.phase} · Batch ${batch.batchId}`}
                    reason={batch.readiness?.reason}
                    slug={batch.featureSlug}
                    onSelectFeature={onSelectFeature}
                  />
                ))}
              </AttentionSubPanel>

              <AttentionSubPanel title="Reversed / Stale" count={staleNodes.length}>
                {staleNodes.map((node) => (
                  <AttentionRow
                    key={node.id}
                    title={node.title || node.id}
                    reason={node.mismatchState?.reason}
                    slug={node.featureSlug}
                    onSelectFeature={onSelectFeature}
                  />
                ))}
              </AttentionSubPanel>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
