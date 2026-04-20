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
  PlanDocument,
  PlanningMismatchStateValue,
  PlanningNode,
  PlanningNodeType,
  PlanningPhaseBatch,
  ProjectPlanningGraph,
} from '../../types';
import { getProjectPlanningGraph, PlanningApiError } from '../../services/planning';
import { PlanningNodeTypeIcon } from '@miethe/ui/primitives';
import { useData } from '../../contexts/DataContext';
import { DocumentModal } from '../DocumentModal';
import { BtnGhost, Chip, Panel, StatusPill } from './primitives';

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
  const status = variant === 'mismatch' ? 'blocked' : variant === 'ok' ? 'completed' : label;
  return <StatusPill status={status} aria-label={label} title={label} />;
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
        className="planning-chip px-1.5 py-0.5 text-[10px] font-medium text-[color:var(--brand)] transition-colors"
        style={{ background: 'color-mix(in oklab, var(--brand) 14%, transparent)', borderColor: 'var(--line-1)' }}
      >
        {slug}
      </button>
    );
  }
  return (
    <span className="planning-chip px-1.5 py-0.5 text-[10px] font-medium text-[color:var(--ink-2)]">
      {slug}
    </span>
  );
}

// ── Lineage (Left panel) ──────────────────────────────────────────────────────

interface FeatureCardProps {
  slug: string;
  nodes: PlanningNode[];
  onSelectFeature?: (featureId: string) => void;
  onNodeClick?: (node: PlanningNode) => void;
}

function FeatureLineageCard({ slug, nodes, onSelectFeature, onNodeClick }: FeatureCardProps) {
  const [expanded, setExpanded] = useState(false);
  const sorted = sortNodesByType(nodes);
  const hasMismatch = nodes.some(n => n.mismatchState?.isMismatch);

  return (
    <Panel className="overflow-hidden">
      <button
        className="planning-row flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left transition-colors hover:bg-[color:var(--bg-3)]"
        onClick={() => setExpanded(e => !e)}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? (
            <ChevronDown size={13} className="shrink-0 text-[color:var(--ink-2)]" />
          ) : (
            <ChevronRight size={13} className="shrink-0 text-[color:var(--ink-2)]" />
          )}
          <span
            className="truncate text-xs font-medium text-[color:var(--ink-0)] transition-colors hover:text-[color:var(--brand)]"
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
            <AlertTriangle size={11} className="shrink-0 text-[color:var(--warn)]" />
          )}
        </div>
        <span className="planning-mono shrink-0 text-[10px] text-[color:var(--ink-2)]">{nodes.length} nodes</span>
      </button>

      {expanded && (
        <div className="border-t border-[color:var(--line-1)] px-3 py-2 space-y-1">
          {sorted.map((node) => {
            const isMismatch = node.mismatchState?.isMismatch;
            const effectiveVariant = isMismatch ? 'mismatch' : 'ok';
            const nodeRow = (
              <div className="planning-row flex items-center gap-2 py-1 text-xs">
                <span className="text-[color:var(--ink-2)]">
                  <PlanningNodeTypeIcon type={node.type} size={12} />
                </span>
                <span className="flex-1 truncate text-[color:var(--ink-1)]" title={node.title}>
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
            if (onNodeClick && node.path) {
              return (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => onNodeClick(node)}
                  className="w-full rounded text-left transition-colors hover:bg-[color:var(--bg-3)] focus-visible:outline-none"
                >
                  {nodeRow}
                </button>
              );
            }
            return <div key={node.id}>{nodeRow}</div>;
          })}
        </div>
      )}
    </Panel>
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
    <div
      className="planning-row flex items-start gap-2 border-b py-1.5 text-xs last:border-0"
      style={{ borderColor: 'color-mix(in oklab, var(--line-1) 70%, transparent)' }}
    >
      <div className="flex-1 min-w-0">
        <p className="truncate font-medium text-[color:var(--ink-1)]">{title}</p>
        {reason && (
          <p className="mt-0.5 truncate text-[10px] text-[color:var(--ink-3)]">{reason}</p>
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
    <Panel className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-[color:var(--line-1)] px-3 py-2">
        <span className="text-xs font-medium text-[color:var(--ink-0)]">{title}</span>
        <span className="planning-mono text-[10px] text-[color:var(--ink-2)]">{count}</span>
      </div>
      <div className="px-3 py-1">
        {children}
      </div>
    </Panel>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyGraphState() {
  return (
    <Panel
      className="flex items-center justify-center border-dashed p-10 text-center"
      style={{ background: 'color-mix(in oklab, var(--bg-1) 70%, transparent)' }}
    >
      <div>
        <FolderSearch size={28} className="mx-auto mb-3 text-[color:var(--ink-3)]" />
        <p className="text-sm font-medium text-[color:var(--ink-2)]">No lineage yet.</p>
        <p className="mt-1 text-xs text-[color:var(--ink-3)]">
          Add a PRD or design spec to seed the planning graph.
        </p>
      </div>
    </Panel>
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
  const { documents } = useData();
  const [state, setState] = useState<GraphFetchState>({ phase: 'idle' });
  const [selectedDoc, setSelectedDoc] = useState<PlanDocument | null>(null);

  const handleNodeClick = useCallback((node: PlanningNode) => {
    if (!node.path) return;
    const doc =
      documents.find(d => d.filePath === node.path) ||
      documents.find(d => d.canonicalPath === node.path) ||
      documents.find(d => node.path!.endsWith(d.filePath)) ||
      documents.find(d => d.filePath.endsWith(node.path!)) ||
      null;
    if (doc) setSelectedDoc(doc);
  }, [documents]);

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
      <div className="flex flex-wrap items-center gap-3 text-xs text-[color:var(--ink-2)]">
        <span className="planning-mono font-medium text-[color:var(--ink-0)]">
          {graph.nodeCount} nodes
          <span className="mx-1 text-[color:var(--line-2)]">·</span>
          {graph.edgeCount} edges
          <span className="mx-1 text-[color:var(--line-2)]">·</span>
          {graph.phaseBatches.length} batches
        </span>
        {graph.generatedAt && (
          <Chip className="text-[color:var(--ink-2)]">
            <Clock size={11} />
            Generated {formatGeneratedAt(graph.generatedAt)}
          </Chip>
        )}
        {state.phase === 'ready' && (
          <BtnGhost
            onClick={() => void loadGraph()}
            className="ml-auto planning-mono px-2 py-1 text-[10px]"
          >
            <RefreshCw size={10} />
            Refresh
          </BtnGhost>
        )}
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Left: Lineage by Feature */}
        <div className="space-y-2">
          <h3 className="planning-caps text-xs font-semibold text-[color:var(--ink-2)]">
            Lineage by Feature
          </h3>
          {slugsWithMultipleTypes.length === 0 ? (
            <p className="text-xs italic text-[color:var(--ink-3)]">No multi-node features detected.</p>
          ) : (
            <div className="space-y-1.5">
              {slugsWithMultipleTypes.map((slug) => (
                <FeatureLineageCard
                  key={slug}
                  slug={slug}
                  nodes={sortNodesByType(bySlug.get(slug) ?? [])}
                  onSelectFeature={onSelectFeature}
                  onNodeClick={handleNodeClick}
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
                    onNodeClick={handleNodeClick}
                  />
                ))}
            </div>
          )}
        </div>

        {/* Right: Attention */}
        <div className="space-y-2">
          <h3 className="planning-caps text-xs font-semibold text-[color:var(--ink-2)]">
            Attention
          </h3>
          {!hasAttention ? (
            <Panel
              className="flex items-center gap-2 px-3 py-2.5"
              style={{
                borderColor: 'color-mix(in oklab, var(--ok) 28%, var(--line-1))',
                background: 'color-mix(in oklab, var(--ok) 8%, transparent)',
              }}
            >
              <span className="text-xs text-[color:var(--ok)]">All nodes aligned — no blockers or mismatches.</span>
            </Panel>
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

      {selectedDoc && (
        <DocumentModal
          doc={selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onBack={() => setSelectedDoc(null)}
          backLabel="Planning Graph"
        />
      )}
    </div>
  );
}
