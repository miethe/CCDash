import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';

import type { PlanningCommandCenterItem } from '@/types';
import {
  commandCenterItemKey,
  commandCenterLaunchBatchId,
  commandCenterLaunchPhase,
} from './commandCenterUtils';
import { trackCommandCenterAction } from '@/services/planningTelemetry';
import {
  CommandCenterToolbar,
  type CommandCenterFilters,
  type CommandCenterViewMode,
} from './CommandCenterToolbar';
import { CommandCenterListView } from './CommandCenterListView';
import { CommandCenterCardView } from './CommandCenterCardView';
import { CommandCenterBoardView } from './CommandCenterBoardView';
import { CommandCenterDetailPanel } from './CommandCenterDetailPanel';
import { PlanningLaunchSheet } from '../PlanningLaunchSheet';
import { BtnGhost, Panel } from '../primitives';
import { MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT } from '@/constants';
import { MultiProjectModeToggle, type CommandCenterMode } from './MultiProjectModeToggle';
import { MultiProjectCommandCenter } from './MultiProjectCommandCenter';
import { usePlanningCommandCenterQuery } from '@/services/queries/planning';
import { useLaunchCapabilitiesQuery } from '@/services/queries/capabilities';

// ── IntersectionObserver hook (viewport-deferred mounting) ────────────────────

/**
 * T4-007: Returns a ref to attach to the sentinel element and a boolean that
 * flips to true once (and stays true) when the element enters the viewport.
 * Using useCallback so the ref function is stable across renders.
 */
function useInView(): [React.RefCallback<Element>, boolean] {
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
      { rootMargin: '200px' },
    );
    observerRef.current.observe(el);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView]);

  useEffect(() => {
    return () => { observerRef.current?.disconnect(); };
  }, []);

  return [ref, inView];
}

// ─────────────────────────────────────────────────────────────────────────────

interface PlanningCommandCenterProps {
  projectId?: string | null;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
}

/**
 * MPCC-501 / P5-001: Shell wrapper that gates the multi-project mode toggle.
 *
 * AC-2 (runtime gate, no rebuild): reads runtime capability from
 * useLaunchCapabilitiesQuery(); falls back to MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT
 * while loading or when the server does not supply the flag.
 *
 * When multiProjectCommandCenterEnabled is true the default mode is 'multi'
 * (the portfolio control plane).  When false/absent the V1 single-project center
 * renders directly without a mode toggle (same as the old build-time branch).
 */
export function PlanningCommandCenterShell(props: PlanningCommandCenterProps) {
  // P5-001: read runtime capability flag.  While loading, caps is undefined so
  // we apply the DEFAULT (false) — resilience-by-default.
  const { data: caps } = useLaunchCapabilitiesQuery();
  const multiProjectEnabled =
    caps?.multiProjectCommandCenterEnabled ?? MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT;

  // AC-2: default mode to 'multi' when the runtime flag is on.
  // useState initializer is stable once mounted; the flag drives the INITIAL mode.
  // The user can still toggle back to 'single' via the mode toggle.
  const [mode, setMode] = useState<CommandCenterMode>(
    multiProjectEnabled ? 'multi' : 'single',
  );

  if (!multiProjectEnabled) {
    return <PlanningCommandCenter {...props} />;
  }

  return (
    <div className="space-y-3" data-testid="planning-command-center-shell">
      {/* Mode toggle — only renders when runtime flag is on */}
      <div className="flex items-center justify-end">
        <MultiProjectModeToggle mode={mode} onModeChange={setMode} />
      </div>

      {mode === 'single' ? (
        <PlanningCommandCenter {...props} />
      ) : (
        <MultiProjectCommandCenter
          onOpenExecution={
            props.onOpenExecution
              ? (featureId, _projectId) => props.onOpenExecution!(featureId)
              : undefined
          }
          onOpenPlan={props.onOpenPlan}
        />
      )}
    </div>
  );
}

const DEFAULT_FILTERS: CommandCenterFilters = {
  q: '',
  status: '',
  phase: '',
  sortBy: 'last_activity',
  sortDirection: 'desc',
  hideDone: true,
};

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
type PageSizeOption = (typeof PAGE_SIZE_OPTIONS)[number];

function pageItemsKey(items: PlanningCommandCenterItem[]): string {
  return items.map(commandCenterItemKey).join('|');
}

async function copyCommandToClipboard(command: string): Promise<void> {
  if (!command) return;
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(command);
  }
}

export function PlanningCommandCenter({
  projectId,
  onOpenExecution,
  onOpenPlan,
}: PlanningCommandCenterProps) {
  // T4-007: Defer query/mount until scrolled into view.
  const [sentinelRef, inView] = useInView();

  const [filters, setFilters] = useState<CommandCenterFilters>(DEFAULT_FILTERS);
  // T4-014: pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSizeOption>(50);
  const [viewMode, setViewMode] = useState<CommandCenterViewMode>('list');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());
  const [detailFeatureId, setDetailFeatureId] = useState<string | null>(null);
  const [launchFeatureId, setLaunchFeatureId] = useState<string | null>(null);
  const [commandOverrides, setCommandOverrides] = useState<Record<string, string>>({});
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle');

  // T4-002: replace useEffect + LoadState with TanStack Query.
  // T4-007: `enabled` is additionally gated on inView.
  const {
    data: page,
    isLoading,
    isError,
    error,
    refetch,
  } = usePlanningCommandCenterQuery({
    projectId,
    q: filters.q,
    status: filters.status,
    phase: filters.phase ? Number(filters.phase) : undefined,
    sortBy: filters.sortBy,
    sortDirection: filters.sortDirection,
    page: currentPage,
    pageSize,
    hideDone: filters.hideDone,
    enabled: inView,
  });

  // Reset to page 1 whenever filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [filters.q, filters.status, filters.phase, filters.sortBy, filters.sortDirection, filters.hideDone]);

  const total = page?.total ?? page?.items.length ?? 0;
  const totalPages = pageSize > 0 ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  const items = page?.items ?? [];
  const detailItem = items.find((item) => item.feature.featureId === detailFeatureId) ?? null;
  const launchItem = items.find((item) => item.feature.featureId === launchFeatureId) ?? null;
  const firstItemKey = useMemo(() => (items[0] ? commandCenterItemKey(items[0]) : ''), [items]);

  const commandForItem = useCallback((item: PlanningCommandCenterItem): string => {
    return commandOverrides[commandCenterItemKey(item)] ?? item.command?.command ?? '';
  }, [commandOverrides]);

  // Auto-expand first item on initial load or page change
  useEffect(() => {
    if (!firstItemKey) return;
    setExpandedIds((current) => {
      if (current.size > 0) return current;
      return new Set([firstItemKey]);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstItemKey, pageItemsKey(items)]);

  const toggleExpanded = useCallback((featureId: string) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(featureId)) {
        next.delete(featureId);
      } else {
        next.add(featureId);
      }
      return next;
    });
  }, []);

  const changeCommand = useCallback((featureId: string, command: string) => {
    setCommandOverrides((current) => ({ ...current, [featureId]: command }));
  }, []);

  const copyCommand = useCallback(async (command: string) => {
    try {
      await copyCommandToClipboard(command);
      trackCommandCenterAction({ action: 'copy_command', hasCommand: Boolean(command), viewMode });
      setCopyState('copied');
      window.setTimeout(() => setCopyState('idle'), 1600);
    } catch {
      setCopyState('error');
    }
  }, [viewMode]);

  const changeViewMode = useCallback((nextViewMode: CommandCenterViewMode) => {
    setViewMode(nextViewMode);
    trackCommandCenterAction({ action: 'view_changed', viewMode: nextViewMode });
  }, []);

  const openDetail = useCallback((featureId: string) => {
    setDetailFeatureId(featureId);
    trackCommandCenterAction({ action: 'open_detail', featureId, viewMode });
  }, [viewMode]);

  const openLaunch = useCallback((featureId: string) => {
    setLaunchFeatureId(featureId);
    trackCommandCenterAction({ action: 'open_launch_sheet', featureId, viewMode });
  }, [viewMode]);

  const openExecution = useCallback((featureId: string) => {
    trackCommandCenterAction({ action: 'open_execution_workbench', featureId, viewMode });
    onOpenExecution?.(featureId);
  }, [onOpenExecution, viewMode]);

  const openPlan = useCallback((path: string) => {
    trackCommandCenterAction({ action: 'open_plan', viewMode });
    onOpenPlan?.(path);
  }, [onOpenPlan, viewMode]);

  const openPullRequest = useCallback((url: string) => {
    trackCommandCenterAction({ action: 'open_pr', hasPullRequest: Boolean(url), viewMode });
    if (typeof window !== 'undefined' && url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }, [viewMode]);

  const handleHideDoneChange = useCallback((hideDone: boolean) => {
    setFilters((prev) => ({ ...prev, hideDone }));
  }, []);

  const errorMessage = isError
    ? (error instanceof Error ? error.message : 'Unable to load Planning Command Center data.')
    : null;

  return (
    // T4-007: Sentinel wrapper — IntersectionObserver fires once on first viewport entry.
    <div ref={sentinelRef}>
    <Panel className="p-5" data-testid="planning-command-center">
      <div className="space-y-4">
        <CommandCenterToolbar
          filters={filters}
          viewMode={viewMode}
          total={total}
          loading={isLoading}
          pageSize={pageSize}
          onFiltersChange={(next) => { setFilters(next); }}
          onViewModeChange={changeViewMode}
          onRefresh={() => void refetch()}
          onPageSizeChange={(next) => { setPageSize(next as PageSizeOption); setCurrentPage(1); }}
          onHideDoneChange={handleHideDoneChange}
        />
        {copyState === 'copied' ? (
          <div className="planning-mono rounded-[var(--radius-sm)] border border-[color:color-mix(in_oklab,var(--ok)_35%,var(--line-1))] bg-[color:color-mix(in_oklab,var(--ok)_10%,var(--bg-1))] px-3 py-2 text-[11px] text-[color:var(--ok)]">
            Command copied.
          </div>
        ) : null}
        {copyState === 'error' ? (
          <div className="planning-mono rounded-[var(--radius-sm)] border border-[color:color-mix(in_oklab,var(--err)_35%,var(--line-1))] bg-[color:color-mix(in_oklab,var(--err)_10%,var(--bg-1))] px-3 py-2 text-[11px] text-[color:var(--err)]">
            Copy failed. Select the command text and copy manually.
          </div>
        ) : null}
        {isLoading ? (
          <div className="flex min-h-[180px] items-center justify-center gap-2 rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] text-[12px] text-[color:var(--ink-3)]">
            <Loader2 size={16} className="animate-spin" aria-hidden />
            Loading command center...
          </div>
        ) : null}
        {isError && errorMessage ? (
          <div className="rounded-[var(--radius-sm)] border border-[color:color-mix(in_oklab,var(--err)_35%,var(--line-1))] bg-[color:color-mix(in_oklab,var(--err)_10%,var(--bg-1))] p-4">
            <div className="flex items-start gap-2 text-[12px] text-[color:var(--err)]">
              <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden />
              <p>{errorMessage}</p>
            </div>
            <BtnGhost className="mt-3" size="sm" onClick={() => void refetch()}>
              retry
            </BtnGhost>
          </div>
        ) : null}
        {page && viewMode === 'list' ? (
          <CommandCenterListView
            items={items}
            expandedIds={expandedIds}
            commandOverrides={commandOverrides}
            onToggleExpanded={toggleExpanded}
            onCommandChange={changeCommand}
            onCopyCommand={copyCommand}
            onOpenLaunch={openLaunch}
            onOpenExecution={openExecution}
            onOpenPlan={openPlan}
            onOpenDetail={openDetail}
            onOpenPullRequest={openPullRequest}
          />
        ) : null}
        {page && viewMode === 'cards' ? (
          <CommandCenterCardView
            items={items}
            commandOverrides={commandOverrides}
            onCopyCommand={copyCommand}
            onOpenLaunch={openLaunch}
            onOpenExecution={openExecution}
            onOpenPlan={openPlan}
            onOpenDetail={openDetail}
            onOpenPullRequest={openPullRequest}
          />
        ) : null}
        {page && viewMode === 'board' ? (
          // Board view uses a wider responsive container that escapes the
          // global 1680px cap so the 5-column kanban has room to breathe.
          <div className="-mx-5 px-5">
            <div className="w-full" style={{ maxWidth: 'min(96vw, 2200px)', marginLeft: 'auto', marginRight: 'auto' }}>
              <CommandCenterBoardView
                items={items}
                commandOverrides={commandOverrides}
                onCopyCommand={copyCommand}
                onOpenLaunch={openLaunch}
                onOpenExecution={openExecution}
                onOpenPlan={openPlan}
                onOpenDetail={openDetail}
                onOpenPullRequest={openPullRequest}
              />
            </div>
          </div>
        ) : null}
        {page?.warnings.length ? (
          <div className="space-y-1">
            {page.warnings.map((warning) => (
              <p key={warning} className="planning-mono text-[10.5px] text-[color:var(--warn)]">{warning}</p>
            ))}
          </div>
        ) : null}
        {/* T4-014: Prev/Next pagination controls */}
        {page && totalPages > 1 ? (
          <div className="flex items-center justify-between pt-1">
            <span className="planning-mono text-[11px] text-[color:var(--ink-3)]">
              page {currentPage} / {totalPages}
              {' '}
              <span className="text-[color:var(--ink-4)]">({total} items)</span>
            </span>
            <div className="flex items-center gap-2">
              <BtnGhost
                size="sm"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                aria-label="Previous page"
              >
                prev
              </BtnGhost>
              <BtnGhost
                size="sm"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                aria-label="Next page"
              >
                next
              </BtnGhost>
            </div>
          </div>
        ) : null}
      </div>
      <CommandCenterDetailPanel
        item={detailItem}
        commandValue={
          detailItem
            ? commandForItem(detailItem)
            : ''
        }
        onClose={() => setDetailFeatureId(null)}
        onOpenPlan={openPlan}
      />
      {launchItem && commandCenterLaunchPhase(launchItem) && commandCenterLaunchBatchId(launchItem) ? (
        <PlanningLaunchSheet
          open={Boolean(launchItem)}
          projectId={projectId || page?.projectId || ''}
          featureId={launchItem.feature.featureId}
          phaseNumber={commandCenterLaunchPhase(launchItem) ?? 1}
          batchId={commandCenterLaunchBatchId(launchItem)}
          initialWorktreeContextId={launchItem.worktree?.contextId || undefined}
          initialCommandOverride={commandForItem(launchItem)}
          onClose={() => setLaunchFeatureId(null)}
          onLaunched={() => {
            setLaunchFeatureId(null);
            void refetch();
          }}
        />
      ) : null}
    </Panel>
    </div>
  );
}
