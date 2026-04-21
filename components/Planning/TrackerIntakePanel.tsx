import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileSearch,
  FileText,
  Inbox,
  RefreshCw,
  Tag,
} from 'lucide-react';

import type {
  FeatureSummaryItem,
  PlanDocument,
  PlanningMismatchStateValue,
  PlanningNode,
  PlanningNodeType,
  ProjectPlanningGraph,
  ProjectPlanningSummary,
} from '../../types';
import { getProjectPlanningGraph, PlanningApiError } from '../../services/planning';
import { useData } from '../../contexts/DataContext';
import { DocumentModal } from '../DocumentModal';

// ── Constants ─────────────────────────────────────────────────────────────────

const PROMOTION_READY_STATUSES = new Set([
  'ready',
  'ready-for-promotion',
  'promote-ready',
  'ready_to_promote',
  'approved',
  'mature',
]);

const DONE_STATUSES = new Set([
  'done',
  'completed',
  'closed',
  'resolved',
  'merged',
  'promoted',
]);

// ── Helpers ───────────────────────────────────────────────────────────────────

function isPromotionReady(node: PlanningNode): boolean {
  return PROMOTION_READY_STATUSES.has((node.effectiveStatus ?? '').trim().toLowerCase());
}

function isDerivedFromProgress(node: PlanningNode): boolean {
  return node.mismatchState?.state === 'derived';
}

function isOpenTrackerOrContext(node: PlanningNode): boolean {
  if (node.type !== 'tracker' && node.type !== 'context') return false;
  return !DONE_STATUSES.has((node.effectiveStatus ?? '').trim().toLowerCase());
}

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

function mismatchStateLabel(state: PlanningMismatchStateValue | string): string {
  switch (state) {
    case 'aligned': return 'Aligned';
    case 'derived': return 'Derived';
    case 'mismatched': return 'Mismatched';
    case 'blocked': return 'Blocked';
    case 'stale': return 'Stale';
    case 'reversed': return 'Reversed';
    case 'unresolved': return 'Unresolved';
    case 'unknown': return 'Unknown';
    default: return String(state);
  }
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatusChip({ label, variant = 'default' }: { label: string; variant?: 'default' | 'warn' | 'ok' | 'info' | 'danger' }) {
  const base = 'inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium leading-none shrink-0';
  const variants: Record<string, string> = {
    default: 'bg-slate-700/60 text-slate-300',
    warn:    'bg-amber-600/20 text-amber-400',
    ok:      'bg-emerald-600/20 text-emerald-400',
    info:    'bg-sky-600/20 text-sky-400',
    danger:  'bg-rose-600/20 text-rose-400',
  };
  return (
    <span className={`${base} ${variants[variant] ?? variants.default}`}>
      {label}
    </span>
  );
}

function NodeTypeChip({ type }: { type: PlanningNodeType }) {
  const iconProps = { size: 10, className: 'shrink-0' };
  let icon: React.ReactNode;
  switch (type) {
    case 'tracker': icon = <AlertCircle {...iconProps} />; break;
    case 'context': icon = <Tag {...iconProps} />; break;
    case 'design_spec': icon = <FileSearch {...iconProps} />; break;
    case 'prd': icon = <FileText {...iconProps} />; break;
    default: icon = <FileText {...iconProps} />; break;
  }
  return (
    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-700/50 text-slate-400 shrink-0">
      {icon}
      {nodeTypeLabel(type)}
    </span>
  );
}

function FeatureSlugChip({
  slug,
  onSelect,
}: {
  slug: string;
  onSelect?: () => void;
}) {
  if (onSelect) {
    return (
      <button
        type="button"
        onClick={onSelect}
        aria-label={`Navigate to feature ${slug}`}
        className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-info/10 text-info hover:bg-info/20 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-info shrink-0"
      >
        {slug}
      </button>
    );
  }
  return (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-700/40 text-muted-foreground shrink-0">
      {slug}
    </span>
  );
}

function PathLabel({ path }: { path: string }) {
  const short = path.length > 60 ? `…${path.slice(-57)}` : path;
  return (
    <span
      className="block truncate font-mono text-[10px] text-muted-foreground/50"
      title={path}
    >
      {short}
    </span>
  );
}

function EmptyTabState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center py-8 text-center">
      <p className="text-xs text-muted-foreground/60 italic">{message}</p>
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function TrackerSkeleton() {
  return (
    <div className="animate-pulse space-y-3 py-2">
      <div className="h-4 rounded bg-slate-700/40 w-2/5" />
      <div className="flex gap-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-7 rounded-full bg-slate-700/30 w-24" />
        ))}
      </div>
      <div className="h-px bg-slate-700/40" />
      <div className="space-y-2">
        <div className="h-10 rounded bg-slate-700/30" />
        <div className="h-10 rounded bg-slate-700/30" />
        <div className="h-10 rounded bg-slate-700/30" />
      </div>
    </div>
  );
}

function TrackerInlineError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-danger/40 bg-danger/5 px-4 py-3">
      <AlertCircle size={14} className="mt-0.5 shrink-0 text-danger" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-danger-foreground">{message}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        aria-label="Retry loading tracker data"
        className="flex shrink-0 items-center gap-1.5 rounded border border-danger/40 bg-danger/10 px-2 py-1 text-[10px] font-medium text-danger-foreground hover:bg-danger/20 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-danger"
      >
        <RefreshCw size={10} />
        Retry
      </button>
    </div>
  );
}

// ── Tab A: Promotion Candidates ───────────────────────────────────────────────

interface PromotionNode {
  node: PlanningNode;
  bucket: 'ready' | 'derived';
}

function PromotionCandidatesTab({
  items,
  onSelectFeature,
  onNodeClick,
}: {
  items: PromotionNode[];
  onSelectFeature?: (featureId: string) => void;
  onNodeClick?: (node: PlanningNode) => void;
}) {
  if (items.length === 0) {
    return <EmptyTabState message="No specs are ready to promote yet." />;
  }

  const primaryItems = items.filter((i) => i.bucket === 'ready');
  const derivedItems = items.filter((i) => i.bucket === 'derived');

  return (
    <div className="space-y-4">
      {primaryItems.length > 0 && (
        <div className="space-y-1.5">
          {primaryItems.map(({ node }) => (
            <NodeRow
              key={node.id}
              node={node}
              showStatusPair
              onSelectFeature={onSelectFeature}
              onNodeClick={onNodeClick}
            />
          ))}
        </div>
      )}
      {derivedItems.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide font-semibold text-muted-foreground/60">
            Derived from progress — consider promoting
          </p>
          {derivedItems.map(({ node }) => (
            <NodeRow
              key={node.id}
              node={node}
              showStatusPair
              onSelectFeature={onSelectFeature}
              onNodeClick={onNodeClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Tab B: Stale Shaping ──────────────────────────────────────────────────────

interface StaleItem {
  type: 'node';
  node: PlanningNode;
}

function StaleShapingTab({
  items,
  onSelectFeature,
  onNodeClick,
}: {
  items: StaleItem[];
  onSelectFeature?: (featureId: string) => void;
  onNodeClick?: (node: PlanningNode) => void;
}) {
  if (items.length === 0) {
    return <EmptyTabState message="No stale shaping work detected." />;
  }
  return (
    <div className="space-y-1.5">
      {items.map(({ node }) => (
        <NodeRow
          key={node.id}
          node={node}
          showStatusPair
          showReason
          onSelectFeature={onSelectFeature}
          onNodeClick={onNodeClick}
        />
      ))}
    </div>
  );
}

// ── Tab C: Trackers ───────────────────────────────────────────────────────────

function TrackersTab({
  nodes,
  onSelectFeature,
  onNodeClick,
}: {
  nodes: PlanningNode[];
  onSelectFeature?: (featureId: string) => void;
  onNodeClick?: (node: PlanningNode) => void;
}) {
  if (nodes.length === 0) {
    return <EmptyTabState message="No open tracker or context notes." />;
  }
  return (
    <div className="space-y-1.5">
      {nodes.map((node) => (
        <NodeRow
          key={node.id}
          node={node}
          showTypeChip
          showStatusPair
          onSelectFeature={onSelectFeature}
          onNodeClick={onNodeClick}
        />
      ))}
    </div>
  );
}

// ── Tab D: Validation Warnings ────────────────────────────────────────────────

function ValidationWarningSubList({
  title,
  children,
  count,
}: {
  title: string;
  children: React.ReactNode;
  count: number;
}) {
  return (
    <div className="space-y-1">
      <h4 className="text-[10px] uppercase tracking-wide font-semibold text-muted-foreground/70">
        {title}
        {count > 0 && (
          <span className="ml-1.5 normal-case tracking-normal font-normal text-muted-foreground/50">
            ({count})
          </span>
        )}
      </h4>
      {count === 0 ? (
        <p className="text-xs text-muted-foreground/50 italic py-1">None detected.</p>
      ) : (
        <div className="space-y-1">{children}</div>
      )}
    </div>
  );
}

function FeatureSummaryRow({
  item,
  badge,
  onSelect,
}: {
  item: FeatureSummaryItem;
  badge?: React.ReactNode;
  onSelect?: () => void;
}) {
  const inner = (
    <div className="flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-slate-700/30 transition-colors">
      <div className="flex-1 min-w-0">
        <p className="truncate text-xs font-medium text-panel-foreground">{item.featureName || item.featureId}</p>
        <div className="mt-0.5 flex flex-wrap items-center gap-1">
          <StatusChip label={item.rawStatus || 'unknown'} />
          {item.effectiveStatus && item.effectiveStatus !== item.rawStatus && (
            <>
              <span className="text-[10px] text-muted-foreground/40">→</span>
              <StatusChip label={item.effectiveStatus} variant="warn" />
            </>
          )}
          {badge}
        </div>
      </div>
      <FeatureSlugChip
        slug={item.featureId}
        onSelect={onSelect}
      />
    </div>
  );

  return onSelect ? (
    <button
      type="button"
      onClick={onSelect}
      aria-label={`Navigate to feature ${item.featureName || item.featureId}`}
      className="w-full text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-info rounded-lg"
    >
      {inner}
    </button>
  ) : (
    <div>{inner}</div>
  );
}

function ValidationWarningsTab({
  mismatchedFeatures,
  reversedFeatures,
  blockedFeatures,
  onSelectFeature,
}: {
  mismatchedFeatures: FeatureSummaryItem[];
  reversedFeatures: FeatureSummaryItem[];
  blockedFeatures: FeatureSummaryItem[];
  onSelectFeature?: (featureId: string) => void;
}) {
  const allEmpty =
    mismatchedFeatures.length === 0 &&
    reversedFeatures.length === 0 &&
    blockedFeatures.length === 0;

  if (allEmpty) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-4 mt-2">
        <CheckCircle2 size={16} className="shrink-0 text-emerald-400" />
        <p className="text-xs text-emerald-400 font-medium">Planning validation looks clean.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ValidationWarningSubList title="Mismatched Features" count={mismatchedFeatures.length}>
        {mismatchedFeatures.map((item) => (
          <FeatureSummaryRow
            key={item.featureId}
            item={item}
            badge={
              <StatusChip
                label={mismatchStateLabel(item.mismatchState as PlanningMismatchStateValue)}
                variant="warn"
              />
            }
            onSelect={onSelectFeature ? () => onSelectFeature(item.featureId) : undefined}
          />
        ))}
      </ValidationWarningSubList>

      <ValidationWarningSubList title="Reversed Features" count={reversedFeatures.length}>
        {reversedFeatures.map((item) => (
          <FeatureSummaryRow
            key={item.featureId}
            item={item}
            badge={<StatusChip label="Reversed" variant="danger" />}
            onSelect={onSelectFeature ? () => onSelectFeature(item.featureId) : undefined}
          />
        ))}
      </ValidationWarningSubList>

      <ValidationWarningSubList title="Blocked Features" count={blockedFeatures.length}>
        {blockedFeatures.map((item) => (
          <FeatureSummaryRow
            key={item.featureId}
            item={item}
            badge={
              item.blockedPhaseCount > 0 ? (
                <StatusChip label={`${item.blockedPhaseCount} blocked phase${item.blockedPhaseCount !== 1 ? 's' : ''}`} variant="danger" />
              ) : undefined
            }
            onSelect={onSelectFeature ? () => onSelectFeature(item.featureId) : undefined}
          />
        ))}
      </ValidationWarningSubList>
    </div>
  );
}

// ── Shared NodeRow ─────────────────────────────────────────────────────────────

function NodeRow({
  node,
  showStatusPair = false,
  showReason = false,
  showTypeChip = false,
  onSelectFeature,
  onNodeClick,
}: {
  node: PlanningNode;
  showStatusPair?: boolean;
  showReason?: boolean;
  showTypeChip?: boolean;
  onSelectFeature?: (featureId: string) => void;
  onNodeClick?: (node: PlanningNode) => void;
}) {
  const slug = node.featureSlug;
  const reason = node.mismatchState?.reason;

  const inner = (
    <div className="rounded-lg border border-panel-border/60 bg-slate-800/40 px-3 py-2 space-y-1">
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <p className="truncate text-xs font-medium text-panel-foreground" title={node.title}>
            {node.title || nodeTypeLabel(node.type)}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
          {showTypeChip && <NodeTypeChip type={node.type} />}
          {slug && (
            <FeatureSlugChip
              slug={slug}
              onSelect={onSelectFeature && slug ? () => onSelectFeature(slug) : undefined}
            />
          )}
          {showStatusPair && (
            <>
              <StatusChip label={node.rawStatus || 'unknown'} />
              {node.effectiveStatus && node.effectiveStatus !== node.rawStatus && (
                <>
                  <span className="text-[10px] text-muted-foreground/40">→</span>
                  <StatusChip label={node.effectiveStatus} variant="ok" />
                </>
              )}
            </>
          )}
        </div>
      </div>
      {showReason && reason && (
        <p className="text-[10px] text-muted-foreground/60 truncate" title={reason}>
          {reason}
        </p>
      )}
      {node.path && <PathLabel path={node.path} />}
    </div>
  );

  if (onNodeClick) {
    return (
      <button
        type="button"
        onClick={() => onNodeClick(node)}
        className="w-full text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-info rounded-lg hover:opacity-80 transition-opacity"
      >
        {inner}
      </button>
    );
  }

  return inner;
}

// ── Tab definitions ────────────────────────────────────────────────────────────

type TabId = 'promotion' | 'stale' | 'trackers' | 'validation';

interface TabDef {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const TABS: TabDef[] = [
  { id: 'promotion',  label: 'Promotion Candidates', icon: <FileSearch size={12} /> },
  { id: 'stale',      label: 'Stale Shaping',        icon: <Clock size={12} /> },
  { id: 'trackers',   label: 'Trackers',              icon: <AlertCircle size={12} /> },
  { id: 'validation', label: 'Validation Warnings',  icon: <AlertTriangle size={12} /> },
];

// ── Tab counter badge ──────────────────────────────────────────────────────────

function TabBadge({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <span className="ml-1 inline-flex items-center justify-center rounded-full bg-slate-600/60 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-slate-300 min-w-[16px]">
      {count > 99 ? '99+' : count}
    </span>
  );
}

// ── Fetch state type ──────────────────────────────────────────────────────────

type GraphFetchState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; graph: ProjectPlanningGraph };

// ── Main component ────────────────────────────────────────────────────────────

export interface TrackerIntakePanelProps {
  projectId: string | null;
  summary: ProjectPlanningSummary;
  onSelectFeature?: (featureId: string) => void;
}

export function TrackerIntakePanel({
  projectId,
  summary,
  onSelectFeature,
}: TrackerIntakePanelProps) {
  const { documents } = useData();
  const [graphState, setGraphState] = useState<GraphFetchState>({ phase: 'idle' });
  const [activeTab, setActiveTab] = useState<TabId>('promotion');
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
      setGraphState({ phase: 'idle' });
      return;
    }
    setGraphState({ phase: 'loading' });
    try {
      const graph = await getProjectPlanningGraph({ projectId });
      setGraphState({ phase: 'ready', graph });
    } catch (err) {
      const message =
        err instanceof PlanningApiError
          ? `Tracker graph error (${err.status}): ${err.message}`
          : err instanceof Error
            ? err.message
            : 'Failed to load planning graph for tracker panel.';
      setGraphState({ phase: 'error', message });
    }
  }, [projectId]);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  // ── Derived data (computed once, not per-keystroke) ───────────────────────

  const tabData = useMemo(() => {
    const nodes: PlanningNode[] =
      graphState.phase === 'ready' ? graphState.graph.nodes : [];

    // Tab A — Promotion Candidates
    const promotionItems: PromotionNode[] = [];
    for (const node of nodes) {
      if (node.type !== 'design_spec') continue;
      if (isPromotionReady(node)) {
        promotionItems.push({ node, bucket: 'ready' });
      } else if (isDerivedFromProgress(node)) {
        promotionItems.push({ node, bucket: 'derived' });
      }
    }

    // Tab B — Stale Shaping (nodes)
    const staleNodeItems: StaleItem[] = nodes
      .filter(
        (n) =>
          (n.type === 'design_spec' || n.type === 'prd') &&
          (n.mismatchState?.state === 'stale' || n.mismatchState?.state === 'unresolved'),
      )
      .map((node) => ({ type: 'node' as const, node }));

    // Also include feature-level stale entries that don't overlap with node-level
    const staleNodeFeatureSlugs = new Set(staleNodeItems.map((i) => i.node.featureSlug));
    const staleFeatureSlugs = new Set(summary.staleFeatureIds ?? []);
    // Feature summaries whose featureId is in staleFeatureIds but not already covered
    const staleFeatureSummaryItems: StaleItem[] = (summary.featureSummaries ?? [])
      .filter(
        (fs) =>
          staleFeatureSlugs.has(fs.featureId) &&
          !staleNodeFeatureSlugs.has(fs.featureId),
      )
      .map((fs) => {
        // Create a synthetic PlanningNode-like for uniform rendering
        const syntheticNode: PlanningNode = {
          id: `feature-stale-${fs.featureId}`,
          type: 'prd',
          path: '',
          title: fs.featureName || fs.featureId,
          featureSlug: fs.featureId,
          rawStatus: fs.rawStatus,
          effectiveStatus: fs.effectiveStatus,
          mismatchState: {
            state: (fs.mismatchState as PlanningMismatchStateValue) ?? 'stale',
            reason: 'Feature marked stale at project level',
            isMismatch: fs.isMismatch,
            evidence: [],
          },
          updatedAt: '',
        };
        return { type: 'node' as const, node: syntheticNode };
      });
    const staleItems: StaleItem[] = [...staleNodeItems, ...staleFeatureSummaryItems];

    // Tab C — Trackers (open tracker/context nodes, sorted by updatedAt desc)
    const trackerNodes = nodes
      .filter(isOpenTrackerOrContext)
      .sort((a, b) => {
        const ta = a.updatedAt ? new Date(a.updatedAt).getTime() : 0;
        const tb = b.updatedAt ? new Date(b.updatedAt).getTime() : 0;
        return tb - ta;
      });

    // Tab D — Validation Warnings
    const mismatchedFeatures = (summary.featureSummaries ?? []).filter((f) => f.isMismatch);
    const reversedFeatures = (summary.featureSummaries ?? []).filter(
      (f) => f.mismatchState === 'reversed',
    );
    const blockedFeatures = (summary.featureSummaries ?? []).filter((f) => f.hasBlockedPhases);

    return {
      promotionItems,
      staleItems,
      trackerNodes,
      mismatchedFeatures,
      reversedFeatures,
      blockedFeatures,
      counts: {
        promotion: promotionItems.length,
        stale: staleItems.length,
        trackers: trackerNodes.length,
        validation: mismatchedFeatures.length + reversedFeatures.length + blockedFeatures.length,
      },
    };
  }, [graphState, summary]);

  const isLoading = graphState.phase === 'idle' || graphState.phase === 'loading';

  return (
    <section aria-label="Tracker and Intake">
      {/* Panel Header */}
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <Inbox size={16} className="shrink-0 text-info" />
          <h2 className="text-sm font-semibold text-panel-foreground">Tracker &amp; Intake</h2>
        </div>
        <p className="mt-0.5 pl-6 text-xs text-muted-foreground">
          Shaping backlog, promotion candidates, and validation signals
        </p>
      </div>

      {/* Loading state */}
      {isLoading && <TrackerSkeleton />}

      {/* Error state */}
      {graphState.phase === 'error' && (
        <TrackerInlineError
          message={graphState.message}
          onRetry={() => void loadGraph()}
        />
      )}

      {/* Ready state */}
      {graphState.phase === 'ready' && (
        <div className="space-y-3">
          {/* Tab bar */}
          <div
            role="tablist"
            aria-label="Tracker intake tabs"
            className="flex flex-wrap gap-1.5"
          >
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id;
              const count = tabData.counts[tab.id];
              return (
                <button
                  key={tab.id}
                  role="tab"
                  type="button"
                  aria-selected={isActive}
                  aria-controls={`tracker-tab-panel-${tab.id}`}
                  id={`tracker-tab-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  className={[
                    'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-info',
                    isActive
                      ? 'bg-info/15 text-info border border-info/30 shadow-sm'
                      : 'bg-slate-700/40 text-muted-foreground border border-transparent hover:bg-slate-700/60 hover:text-panel-foreground',
                  ].join(' ')}
                >
                  {tab.icon}
                  {tab.label}
                  <TabBadge count={count} />
                </button>
              );
            })}
          </div>

          {/* Tab panels */}
          <div className="pt-1">
            {/* Tab A */}
            <div
              role="tabpanel"
              id={`tracker-tab-panel-promotion`}
              aria-labelledby={`tracker-tab-promotion`}
              hidden={activeTab !== 'promotion'}
            >
              <PromotionCandidatesTab
                items={tabData.promotionItems}
                onSelectFeature={onSelectFeature}
                onNodeClick={handleNodeClick}
              />
            </div>

            {/* Tab B */}
            <div
              role="tabpanel"
              id={`tracker-tab-panel-stale`}
              aria-labelledby={`tracker-tab-stale`}
              hidden={activeTab !== 'stale'}
            >
              <StaleShapingTab
                items={tabData.staleItems}
                onSelectFeature={onSelectFeature}
                onNodeClick={handleNodeClick}
              />
            </div>

            {/* Tab C */}
            <div
              role="tabpanel"
              id={`tracker-tab-panel-trackers`}
              aria-labelledby={`tracker-tab-trackers`}
              hidden={activeTab !== 'trackers'}
            >
              <TrackersTab
                nodes={tabData.trackerNodes}
                onSelectFeature={onSelectFeature}
                onNodeClick={handleNodeClick}
              />
            </div>

            {/* Tab D */}
            <div
              role="tabpanel"
              id={`tracker-tab-panel-validation`}
              aria-labelledby={`tracker-tab-validation`}
              hidden={activeTab !== 'validation'}
            >
              <ValidationWarningsTab
                mismatchedFeatures={tabData.mismatchedFeatures}
                reversedFeatures={tabData.reversedFeatures}
                blockedFeatures={tabData.blockedFeatures}
                onSelectFeature={onSelectFeature}
              />
            </div>
          </div>
        </div>
      )}

      {selectedDoc && (
        <DocumentModal
          doc={selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onBack={() => setSelectedDoc(null)}
          onOpenFeature={(featureId) => {
            setSelectedDoc(null);
            onSelectFeature?.(featureId);
          }}
          backLabel="Tracker"
        />
      )}
    </section>
  );
}
