/**
 * MPCC-501..505: Multi-project consolidated command center.
 *
 * Feature-flagged by MULTI_PROJECT_COMMAND_CENTER_ENABLED.  When off, the
 * parent (PlanningCommandCenter.tsx) renders normally.  When on, this
 * component is mounted alongside a mode toggle so users can switch between
 * single-project and portfolio views.
 *
 * Architecture:
 *   - Shell: feature-flag gate + mode toggle (MPCC-501)
 *   - Project filter rail: per-project/group chips (MPCC-502)
 *   - Aggregate session board: cross-project active sessions (MPCC-503)
 *   - Work item board/list: cross-project command center items (MPCC-504)
 *   - Detail rail: session + feature drawers with explicit project_id (MPCC-505)
 *
 * URL state is managed by useMultiProjectCommandCenterState (MPCC-404).
 */
import { useCallback, useId, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { AlertCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AggregateSessionCard, AggregateWorkItem, ProjectWarning } from '@/types';
import type { MultiProjectGroupingMode } from './MultiProjectSessionBoard';
import {
  useMultiProjectCommandCenterQuery,
  useMultiProjectSessionBoardQuery,
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
  const projectFilterHeadingId = useId();
  const sessionBoardHeadingId = useId();
  const workItemHeadingId = useId();

  // ── Query filters ────────────────────────────────────────────────────────────

  const ccFilters = toCommandCenterFilters(state);
  const sbFilters = toSessionBoardFilters(state);

  // ── Aggregate data hooks ─────────────────────────────────────────────────────

  const {
    data: ccData,
    isFetching: ccLoading,
    error: ccError,
    refetch: ccRefetch,
  } = useMultiProjectCommandCenterQuery({
    filters: ccFilters,
    projectListReady: true,
    enabled: true,
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
    enabled: true,
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

        {/* Active session board (MPCC-503) */}
        <section aria-labelledby={sessionBoardHeadingId}>
          {/* Visually-hidden heading for the section landmark */}
          <h2
            id={sessionBoardHeadingId}
            className="sr-only"
          >
            Active sessions across projects
          </h2>
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

        {/* Work item board (MPCC-504) */}
        <section aria-labelledby={workItemHeadingId}>
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
