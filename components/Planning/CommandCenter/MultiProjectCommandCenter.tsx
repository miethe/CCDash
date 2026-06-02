/**
 * MPCC-501..505 / P5-001: Multi-project consolidated command center.
 *
 * Feature-flagged by runtime caps.multiProjectCommandCenterEnabled (P5-001).
 * When off, the parent (PlanningCommandCenter.tsx) renders normally.  When on,
 * this component is mounted alongside a mode toggle so users can switch between
 * single-project and portfolio views.
 *
 * Architecture:
 *   - Shell: feature-flag gate + mode toggle (MPCC-501)
 *   - Portfolio attention lenses: above-fold (rollup + capabilities = 2 requests) (P5-001 AC-1)
 *   - Project filter rail: per-project/group chips (MPCC-502)
 *   - Aggregate session board: cross-project active sessions — viewport-deferred (MPCC-503)
 *   - Work item board/list: cross-project command center items — viewport-deferred (MPCC-504)
 *   - Detail rail: session + feature drawers with explicit project_id (MPCC-505)
 *
 * URL state is managed by useMultiProjectCommandCenterState (MPCC-404).
 *
 * AC-1 (portfolio default, ≤2 above-fold requests): rollup + capabilities are
 * fetched eagerly.  The session board and work item list are viewport-deferred
 * via IntersectionObserver (reuses the useInView pattern from PlanningCommandCenter).
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { AlertCircle, Activity, Clock, TriangleAlert, ArrowRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AggregateSessionCard, AggregateWorkItem, ProjectWarning } from '@/types';
import type { MultiProjectGroupingMode } from './MultiProjectSessionBoard';
import {
  useMultiProjectCommandCenterQuery,
  useMultiProjectSessionBoardQuery,
  usePortfolioRollupQuery,
  type PortfolioRollupDTO,
  type PortfolioProject,
} from '@/services/queries/planning';
import {
  useMultiProjectCommandCenterState,
  toCommandCenterFilters,
  toSessionBoardFilters,
} from '@/lib/useMultiProjectCommandCenterState';
import { trackCommandCenterAction } from '@/services/planningTelemetry';
import { BtnGhost, Panel } from '../primitives';
import { MultiProjectFilterRail } from './MultiProjectFilterRail';
import { MultiProjectSessionBoard } from './MultiProjectSessionBoard';
import { MultiProjectWorkItemCard } from './MultiProjectWorkItemCard';
import { MultiProjectDetailRail, type DetailTarget } from './MultiProjectDetailRail';
import { CommandCenterToolbar } from './CommandCenterToolbar';
import type { CommandCenterFilters } from './CommandCenterToolbar';

// ── Viewport-defer hook (reuse Phase 4 IntersectionObserver pattern) ──────────

/**
 * Returns a ref to attach to a sentinel element and a boolean that flips to
 * true once (and stays true) when the element enters the viewport.
 * Reuses the same pattern as PlanningCommandCenter.tsx (T4-007).
 */
function useInView(rootMargin = '200px'): [React.RefCallback<Element>, boolean] {
  const [inView, setInView] = useState(false);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const ref = useCallback((el: Element | null) => {
    if (observerRef.current) {
      observerRef.current.disconnect();
      observerRef.current = null;
    }
    if (!el || inView) return;
    observerRef.current = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observerRef.current?.disconnect();
          observerRef.current = null;
        }
      },
      { rootMargin },
    );
    observerRef.current.observe(el);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, rootMargin]);

  useEffect(() => {
    return () => { observerRef.current?.disconnect(); };
  }, []);

  return [ref, inView];
}

// ── Portfolio attention lenses ─────────────────────────────────────────────────

interface AttentionLensProps {
  /** Icon element for the lens. */
  icon: React.ReactNode;
  label: string;
  /** Project IDs in this lens. */
  projectIds: string[];
  /** Per-project display map for resolving labels. */
  projectDisplayMap: Map<string, string>;
  /** Tailwind token class for accent colour (text + border). */
  accentClass: string;
  /** Tailwind bg token class for the badge. */
  bgClass: string;
}

function AttentionLens({
  icon,
  label,
  projectIds,
  projectDisplayMap,
  accentClass,
  bgClass,
}: AttentionLensProps) {
  const count = projectIds.length;
  return (
    <div
      className={cn(
        'flex flex-col gap-1.5 rounded-[var(--radius-sm)] border p-3',
        'border-[color:var(--line-1)]',
      )}
      style={{ minWidth: 0 }}
    >
      <div className={cn('flex items-center gap-1.5 text-[11px] font-medium', accentClass)}>
        {icon}
        <span>{label}</span>
        {count > 0 && (
          <span
            className={cn('ml-auto rounded px-1.5 text-[10px] planning-mono', bgClass, accentClass)}
          >
            {count}
          </span>
        )}
      </div>
      {count === 0 ? (
        <p className="planning-mono text-[10.5px] text-[color:var(--ink-4)]">none</p>
      ) : (
        <ul className="space-y-0.5">
          {projectIds.slice(0, 5).map((pid) => (
            <li key={pid} className="planning-mono truncate text-[10.5px] text-[color:var(--ink-3)]">
              {projectDisplayMap.get(pid) ?? pid}
            </li>
          ))}
          {count > 5 && (
            <li className="planning-mono text-[10.5px] text-[color:var(--ink-4)]">
              +{count - 5} more
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

interface PortfolioAttentionLensesProps {
  rollup: PortfolioRollupDTO | undefined;
  isLoading: boolean;
}

/**
 * P5-001 AC-1: Four attention lenses rendered above fold.
 * Data from portfolioRollup.attention + per-project statusCounts/tokenTotal.
 * Every field has a defined fallback (missing → empty/zero).
 */
function PortfolioAttentionLenses({ rollup, isLoading }: PortfolioAttentionLensesProps) {
  // Build a display-name map from rollup projects for resolving project IDs.
  const projectDisplayMap = new Map<string, string>(
    (rollup?.projects ?? []).map((p: PortfolioProject) => [p.projectId, p.display || p.projectId]),
  );

  const attention = rollup?.attention ?? {
    activeNow: [],
    changedRecently: [],
    needsAttention: [],
    nextWork: [],
  };

  if (isLoading && !rollup) {
    return (
      <div
        className="flex items-center gap-2 text-[12px] text-[color:var(--ink-3)]"
        role="status"
        aria-live="polite"
      >
        <Loader2 size={14} className="motion-safe:animate-spin" aria-hidden />
        <span>Loading portfolio overview...</span>
      </div>
    );
  }

  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}
      role="region"
      aria-label="Portfolio attention lenses"
    >
      <AttentionLens
        icon={<Activity size={12} aria-hidden />}
        label="Active Now"
        projectIds={attention.activeNow}
        projectDisplayMap={projectDisplayMap}
        accentClass="text-[color:var(--ok)]"
        bgClass="bg-[color:color-mix(in_oklab,var(--ok)_12%,var(--bg-1))]"
      />
      <AttentionLens
        icon={<Clock size={12} aria-hidden />}
        label="Changed Recently"
        projectIds={attention.changedRecently}
        projectDisplayMap={projectDisplayMap}
        accentClass="text-[color:var(--accent)]"
        bgClass="bg-[color:color-mix(in_oklab,var(--accent)_12%,var(--bg-1))]"
      />
      <AttentionLens
        icon={<TriangleAlert size={12} aria-hidden />}
        label="Needs Attention"
        projectIds={attention.needsAttention}
        projectDisplayMap={projectDisplayMap}
        accentClass="text-[color:var(--warn)]"
        bgClass="bg-[color:color-mix(in_oklab,var(--warn)_12%,var(--bg-1))]"
      />
      <AttentionLens
        icon={<ArrowRight size={12} aria-hidden />}
        label="Next Work"
        projectIds={attention.nextWork}
        projectDisplayMap={projectDisplayMap}
        accentClass="text-[color:var(--ink-2)]"
        bgClass="bg-[color:var(--bg-2)]"
      />
    </div>
  );
}

// ── Per-project token summary strip ───────────────────────────────────────────

/**
 * Compact strip showing per-project active-sessions count and total tokens.
 * Rendered below the attention lenses, above the viewport-deferred sections.
 * Resilience: activeSessions/tokenTotal default to 0 when absent.
 */
function PortfolioProjectStrip({ projects }: { projects: PortfolioProject[] }) {
  if (projects.length === 0) return null;
  return (
    <div
      className="flex flex-wrap gap-2"
      role="list"
      aria-label="Per-project summaries"
    >
      {projects.map((p) => (
        <div
          key={p.projectId}
          role="listitem"
          className={cn(
            'flex items-center gap-2 rounded-[var(--radius-sm)] border px-2.5 py-1.5',
            'border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
            p.needsAttention && 'border-[color:color-mix(in_oklab,var(--warn)_40%,var(--line-1))]',
          )}
          style={{ minWidth: 0 }}
        >
          <span className="planning-mono max-w-[120px] truncate text-[11px] text-[color:var(--ink-2)]">
            {p.display || p.projectId}
          </span>
          {(p.activeSessions ?? 0) > 0 && (
            <span className="planning-mono text-[10px] text-[color:var(--ok)]">
              {p.activeSessions} active
            </span>
          )}
          {(p.tokenTotal ?? 0) > 0 && (
            <span className="planning-mono text-[10px] text-[color:var(--ink-4)]">
              {(p.tokenTotal / 1_000_000).toFixed(1)}M tok
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Map URL state filters into CommandCenterFilters for the toolbar. */
function toToolbarFilters(
  search: string | null,
  status: string | null,
  sort: string | null,
): CommandCenterFilters {
  return {
    q: search ?? '',
    status: status ?? '',
    phase: '',
    sortBy: sort ?? 'priority',
    sortDirection: 'desc',
  };
}

// ── Sub-components ─────────────────────────────────────────────────────────────

/**
 * Estimated row height for work item cards (collapsed).
 * Used by the virtualizer to allocate scroll space.
 */
const WORK_ITEM_ESTIMATE_PX = 140;

/**
 * Threshold above which the work item list is virtualized.
 * Below this count plain rendering is used (lower overhead for typical sets).
 */
const WORK_ITEM_VIRTUALIZE_THRESHOLD = 250;

interface WorkItemListProps {
  items: AggregateWorkItem[];
  commandOverrides: Record<string, string>;
  onOpenLaunch: (featureId: string, projectId: string) => void;
  onOpenExecution: (featureId: string, projectId: string) => void;
  onOpenPlan: (path: string) => void;
  onOpenDetail: (featureId: string, projectId: string) => void;
  onOpenPullRequest: (url: string) => void;
  onCopyCommand: (command: string) => void;
}

function WorkItemList({
  items,
  commandOverrides,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
  onCopyCommand,
}: WorkItemListProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const shouldVirtualize = items.length > WORK_ITEM_VIRTUALIZE_THRESHOLD;

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => WORK_ITEM_ESTIMATE_PX,
    overscan: 5,
    enabled: shouldVirtualize,
  });

  if (items.length === 0) {
    return (
      <div
        className="flex min-h-[160px] items-center justify-center rounded-[var(--radius-sm)] border border-dashed"
        style={{ borderColor: 'var(--line-1)' }}
      >
        <div className="text-center">
          <p className="planning-mono text-[12px] text-[color:var(--ink-3)]">No work items match filters</p>
          <p className="planning-mono mt-1 text-[11px] text-[color:var(--ink-4)]">Try clearing the project or status filter</p>
        </div>
      </div>
    );
  }

  if (!shouldVirtualize) {
    // Plain rendering for typical sets.
    return (
      <div className="space-y-3" role="list" aria-label="Cross-project work items">
        {items.map((workItem) => {
          const key = `${workItem.project.projectId}::${workItem.item.feature.featureId}`;
          const commandValue = commandOverrides[key] ?? workItem.item.command?.command ?? '';
          return (
            <div key={key} role="listitem">
              <MultiProjectWorkItemCard
                workItem={workItem}
                commandValue={commandValue}
                onCopyCommand={onCopyCommand}
                onOpenLaunch={onOpenLaunch}
                onOpenExecution={onOpenExecution}
                onOpenPlan={onOpenPlan}
                onOpenDetail={onOpenDetail}
                onOpenPullRequest={onOpenPullRequest}
              />
            </div>
          );
        })}
      </div>
    );
  }

  // Virtualized rendering for large sets (>250 items).
  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  return (
    <div
      ref={listRef}
      style={{ overflowY: 'auto', maxHeight: '80vh' }}
      role="list"
      aria-label={`Cross-project work items (${items.length} total, scrollable)`}
    >
      <div style={{ height: totalSize, position: 'relative' }}>
        {virtualItems.map((virtualItem) => {
          const workItem = items[virtualItem.index];
          const key = `${workItem.project.projectId}::${workItem.item.feature.featureId}`;
          const commandValue = commandOverrides[key] ?? workItem.item.command?.command ?? '';
          return (
            <div
              key={key}
              role="listitem"
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualItem.start}px)`,
                paddingBottom: 12,
              }}
              data-index={virtualItem.index}
            >
              <MultiProjectWorkItemCard
                workItem={workItem}
                commandValue={commandValue}
                onCopyCommand={onCopyCommand}
                onOpenLaunch={onOpenLaunch}
                onOpenExecution={onOpenExecution}
                onOpenPlan={onOpenPlan}
                onOpenDetail={onOpenDetail}
                onOpenPullRequest={onOpenPullRequest}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface MultiProjectCommandCenterProps {
  onOpenExecution?: (featureId: string, projectId: string) => void;
  onOpenPlan?: (path: string) => void;
  className?: string;
}

export function MultiProjectCommandCenter({
  onOpenExecution,
  onOpenPlan,
  className,
}: MultiProjectCommandCenterProps) {
  const urlState = useMultiProjectCommandCenterState();
  const { state, setProjectIds, setGroup, setSessionGrouping, setSelectedCardId, setModalFeatureId, setStatus, setSearch, setSort, setPage } = urlState;

  // commandOverrides is read-only in this component (no edit UI for multi-project);
  // we use a const record so command values fall back to item.command?.command.
  const [commandOverrides] = useState<Record<string, string>>({});
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle');
  const [detailTarget, setDetailTarget] = useState<DetailTarget>(null);
  // MPCC-505: Capture the element that had focus when the drawer opens so
  // focus can be returned on close, even without an explicit trigger ref.
  const lastFocusedRef = useRef<HTMLElement | null>(null);

  // Stable IDs for aria-labelledby on landmark sections.
  const portfolioHeadingId = useId();
  const projectFilterHeadingId = useId();
  const sessionBoardHeadingId = useId();
  const workItemHeadingId = useId();

  // ── Viewport-defer sentinels for heavy sub-views (P5-001 AC-1) ───────────────
  // Session board and work item list are deferred until they scroll into view.
  // The attention lenses + project strip are always above-fold (no deferral).

  const [sessionBoardSentinelRef, sessionBoardInView] = useInView('300px');
  const [workItemSentinelRef, workItemInView] = useInView('300px');

  // ── Query filters ────────────────────────────────────────────────────────────

  const ccFilters = toCommandCenterFilters(state);
  const sbFilters = toSessionBoardFilters(state);

  // ── Above-fold: portfolio rollup (P5-001 AC-1) ───────────────────────────────
  // Scoped to the selected project IDs from URL state.
  const selectedProjectIds = state.projectIds.length > 0 ? state.projectIds : undefined;

  const {
    data: rollupData,
    isLoading: rollupLoading,
  } = usePortfolioRollupQuery({
    projectIds: selectedProjectIds,
    enabled: true,
  });

  // ── Below-fold: aggregate command center + session board ─────────────────────

  const {
    data: ccData,
    isFetching: ccLoading,
    error: ccError,
    refetch: ccRefetch,
  } = useMultiProjectCommandCenterQuery({
    filters: ccFilters,
    projectListReady: true,
    // Viewport-deferred: only fetch when the work-item section scrolls into view.
    enabled: workItemInView,
  });

  const {
    data: sbData,
    isFetching: sbLoading,
    error: sbError,
    refetch: sbRefetch,
  } = useMultiProjectSessionBoardQuery({
    filters: {
      ...sbFilters,
      groupBy: state.sessionGrouping,
    },
    projectListReady: true,
    // Viewport-deferred: only fetch when the session board scrolls into view.
    enabled: sessionBoardInView,
  });

  // ── Handlers ─────────────────────────────────────────────────────────────────

  const copyCommand = useCallback(async (command: string) => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(command);
      }
      trackCommandCenterAction({ action: 'copy_command', hasCommand: Boolean(command), viewMode: 'cards' });
      setCopyState('copied');
      window.setTimeout(() => setCopyState('idle'), 1600);
    } catch {
      setCopyState('error');
    }
  }, []);

  const handleProjectSelect = useCallback(
    (projectId: string | null) => {
      if (projectId === null) {
        setProjectIds([]);
      } else {
        setProjectIds([projectId]);
      }
    },
    [setProjectIds],
  );

  const handleGroupSelect = useCallback(
    (group: string | null) => {
      setGroup(group);
    },
    [setGroup],
  );

  const handleSessionCardSelect = useCallback(
    (sessionId: string | null) => {
      setSelectedCardId(sessionId);
    },
    [setSelectedCardId],
  );

  const handleGroupingChange = useCallback(
    (grouping: MultiProjectGroupingMode) => {
      setSessionGrouping(grouping);
    },
    [setSessionGrouping],
  );

  const openSessionDetail = useCallback(
    (sessionId: string, projectId: string) => {
      // MPCC-505: Capture focus target before opening drawer so we can restore it on close.
      lastFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      // Find the aggregate card for context
      let aggregateCard: AggregateSessionCard | undefined;
      if (sbData) {
        for (const group of sbData.groups) {
          const found = group.cards.find((c: AggregateSessionCard) => c.card.sessionId === sessionId);
          if (found) { aggregateCard = found; break; }
        }
      }
      setDetailTarget({ kind: 'session', sessionId, projectId, aggregateCard });
      trackCommandCenterAction({ action: 'open_detail', featureId: sessionId, viewMode: 'cards' });
    },
    [sbData],
  );

  const openFeatureDetail = useCallback(
    (featureId: string, projectId: string) => {
      // MPCC-505: Capture focus target before opening drawer so we can restore it on close.
      lastFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      // Find the aggregate work item for context
      let workItem: AggregateWorkItem | undefined;
      if (ccData) {
        workItem = ccData.items.find(
          (i: AggregateWorkItem) => i.item.feature.featureId === featureId && i.project.projectId === projectId,
        );
      }
      setDetailTarget({ kind: 'workItem', featureId, projectId, workItem });
      setModalFeatureId(featureId);
      trackCommandCenterAction({ action: 'open_detail', featureId, viewMode: 'list' });
    },
    [ccData, setModalFeatureId],
  );

  const closeDetail = useCallback(() => {
    setDetailTarget(null);
    setModalFeatureId(null);
  }, [setModalFeatureId]);

  const handleToolbarFiltersChange = useCallback(
    (filters: CommandCenterFilters) => {
      if (filters.q !== state.search) setSearch(filters.q || null);
      if (filters.status !== state.status) setStatus(filters.status || null);
      if (filters.sortBy !== state.sort) setSort(filters.sortBy);
    },
    [state.search, state.status, state.sort, setSearch, setStatus, setSort],
  );

  // ── Pagination ───────────────────────────────────────────────────────────────

  const handlePageChange = useCallback(
    (page: number) => setPage(page),
    [setPage],
  );

  // ── Render ───────────────────────────────────────────────────────────────────

  const projectSummaries = ccData?.projectSummaries ?? sbData?.projectSummaries ?? [];
  const totalWorkItems = ccData?.pagination.total ?? 0;
  const toolbarFilters = toToolbarFilters(state.search, state.status, state.sort);

  const detailCommandValue =
    detailTarget?.kind === 'workItem'
      ? commandOverrides[`${detailTarget.projectId}::${detailTarget.featureId}`] ??
        detailTarget.workItem?.item.command?.command ??
        ''
      : '';

  return (
    <Panel className={cn('p-5', className)} data-testid="multi-project-command-center">
      <div className="space-y-5">

        {/* Toolbar (MPCC-501) — shared with V1 toolbar for consistent UX */}
        <CommandCenterToolbar
          filters={toolbarFilters}
          viewMode="list"
          total={totalWorkItems}
          loading={ccLoading}
          onFiltersChange={handleToolbarFiltersChange}
          onViewModeChange={() => void 0}
          onRefresh={() => { void ccRefetch(); void sbRefetch(); }}
        />

        {/* Copy state banner */}
        {copyState === 'copied' && (
          <div
            className="planning-mono rounded-[var(--radius-sm)] border px-3 py-2 text-[11px]"
            style={{
              borderColor: 'color-mix(in oklab, var(--ok) 35%, var(--line-1))',
              backgroundColor: 'color-mix(in oklab, var(--ok) 10%, var(--bg-1))',
              color: 'var(--ok)',
            }}
          >
            Command copied.
          </div>
        )}

        {/* P5-001 AC-1: Portfolio attention lenses (above fold — always rendered) */}
        <section aria-labelledby={portfolioHeadingId}>
          <h2
            id={portfolioHeadingId}
            className="planning-caps mb-2 text-[10px] text-[color:var(--ink-3)] m-0"
            style={{ fontWeight: 'inherit' }}
          >
            portfolio overview
          </h2>
          <div className="space-y-3">
            <PortfolioAttentionLenses rollup={rollupData} isLoading={rollupLoading} />
            {rollupData && rollupData.projects.length > 0 && (
              <PortfolioProjectStrip projects={rollupData.projects} />
            )}
          </div>
        </section>

        {/* Project filter rail (MPCC-502) */}
        {projectSummaries.length > 0 && (
          <section aria-labelledby={projectFilterHeadingId}>
            <h2
              id={projectFilterHeadingId}
              className="planning-caps mb-2 text-[10px] text-[color:var(--ink-3)] m-0"
              style={{ fontWeight: 'inherit' }}
            >
              projects
            </h2>
            <MultiProjectFilterRail
              projectSummaries={projectSummaries}
              selectedProjectIds={state.projectIds}
              selectedGroup={state.group}
              onProjectSelect={handleProjectSelect}
              onGroupSelect={handleGroupSelect}
              totalCount={totalWorkItems}
            />
          </section>
        )}

        {/* Active session board (MPCC-503) — viewport-deferred (P5-001 AC-1) */}
        <section aria-labelledby={sessionBoardHeadingId}>
          {/* Visually-hidden heading for the section landmark */}
          <h2
            id={sessionBoardHeadingId}
            className="sr-only"
          >
            Active sessions across projects
          </h2>
          {/* Sentinel: IntersectionObserver fires when this enters the viewport */}
          <div ref={sessionBoardSentinelRef} aria-hidden="true" style={{ height: 1 }} />
          <MultiProjectSessionBoard
            data={sbData}
            loading={sbLoading}
            error={sbError instanceof Error ? sbError : sbError ? new Error(String(sbError)) : null}
            grouping={state.sessionGrouping}
            selectedCardId={state.selectedCardId}
            onGroupingChange={handleGroupingChange}
            onCardSelect={handleSessionCardSelect}
            onOpenDetail={openSessionDetail}
            onRefresh={() => void sbRefetch()}
          />
        </section>

        {/* Work item divider */}
        <div style={{ borderTop: '1px solid var(--line-1)' }} />

        {/* Work item board (MPCC-504) — viewport-deferred (P5-001 AC-1) */}
        <section aria-labelledby={workItemHeadingId}>
          {/* Sentinel: IntersectionObserver fires when this enters the viewport */}
          <div ref={workItemSentinelRef} aria-hidden="true" style={{ height: 1 }} />
          <div className="mb-3 flex items-center gap-2">
            <h2
              id={workItemHeadingId}
              className="planning-caps text-[10px] text-[color:var(--ink-3)] m-0"
              style={{ fontWeight: 'inherit' }}
            >
              work items
            </h2>
            {ccData?.pagination && (
              <span
                className="planning-mono rounded px-1.5 text-[10px]"
                style={{ backgroundColor: 'var(--bg-2)', color: 'var(--ink-3)' }}
              >
                {ccData.pagination.total} total
              </span>
            )}
          </div>

          {/* Loading */}
          {ccLoading && !ccData && (
            <div
              className="flex min-h-[160px] items-center justify-center gap-2 text-[12px] text-[color:var(--ink-3)]"
              role="status"
              aria-live="polite"
            >
              <Loader2 size={16} className="motion-safe:animate-spin" aria-hidden />
              Loading work items across projects...
            </div>
          )}

          {/* Error */}
          {ccError && !ccData && (
            <div
              className="rounded-[var(--radius-sm)] border p-4"
              style={{
                borderColor: 'color-mix(in oklab, var(--err) 35%, var(--line-1))',
                backgroundColor: 'color-mix(in oklab, var(--err) 10%, var(--bg-1))',
              }}
            >
              <div
                className="flex items-start gap-2 text-[12px]"
                style={{ color: 'var(--err)' }}
              >
                <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden />
                <p>
                  {ccError instanceof Error ? ccError.message : 'Unable to load command center data.'}
                </p>
              </div>
              <BtnGhost className="mt-3" size="sm" onClick={() => void ccRefetch()}>
                retry
              </BtnGhost>
            </div>
          )}

          {/* Partial-status warnings */}
          {ccData?.status === 'partial' && ccData.warnings.length > 0 && (
            <div className="mb-3 space-y-0.5">
              {ccData.warnings.map((w: ProjectWarning, i: number) => (
                <p
                  key={i}
                  className="planning-mono text-[10.5px]"
                  style={{ color: w.severity === 'high' ? 'var(--err)' : 'var(--warn)' }}
                >
                  {w.projectId}: {w.message}
                </p>
              ))}
            </div>
          )}

          {/* Work item list */}
          {ccData && (
            <WorkItemList
              items={ccData.items}
              commandOverrides={commandOverrides}
              onOpenLaunch={(featureId, _projectId) => {
                // Launch is project-scoped; currently no parent handler provided for multi-project.
                trackCommandCenterAction({ action: 'open_launch_sheet', featureId, viewMode: 'list' });
              }}
              onOpenExecution={(featureId, projectId) => {
                trackCommandCenterAction({ action: 'open_execution_workbench', featureId, viewMode: 'list' });
                onOpenExecution?.(featureId, projectId);
              }}
              onOpenPlan={(path) => {
                trackCommandCenterAction({ action: 'open_plan', viewMode: 'list' });
                onOpenPlan?.(path);
              }}
              onOpenDetail={openFeatureDetail}
              onOpenPullRequest={(url) => {
                trackCommandCenterAction({ action: 'open_pr', hasPullRequest: Boolean(url), viewMode: 'list' });
                if (url) window.open(url, '_blank', 'noopener,noreferrer');
              }}
              onCopyCommand={copyCommand}
            />
          )}

          {/* Pagination */}
          {ccData?.pagination && ccData.pagination.hasMore && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <BtnGhost
                size="sm"
                disabled={state.page <= 1}
                onClick={() => handlePageChange(state.page - 1)}
                aria-label="Previous page"
              >
                prev
              </BtnGhost>
              <span className="planning-mono text-[11px] text-[color:var(--ink-3)]">
                page {state.page}
              </span>
              <BtnGhost
                size="sm"
                disabled={!ccData.pagination.hasMore}
                onClick={() => handlePageChange(state.page + 1)}
                aria-label="Next page"
              >
                next
              </BtnGhost>
            </div>
          )}
        </section>
      </div>

      {/* MPCC-505: Route-local detail rail — explicit project_id */}
      <MultiProjectDetailRail
        target={detailTarget}
        commandValue={detailCommandValue}
        onClose={closeDetail}
        onOpenPlan={onOpenPlan}
        focusTargetRef={lastFocusedRef}
      />
    </Panel>
  );
}
