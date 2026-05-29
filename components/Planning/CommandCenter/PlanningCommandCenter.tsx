import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';

import type { PlanningCommandCenterItem, PlanningCommandCenterPage } from '@/types';
import {
  getPlanningCommandCenter,
  PlanningCommandCenterApiError,
} from '@/services/planningCommandCenter';
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

interface PlanningCommandCenterProps {
  projectId?: string | null;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
}

type LoadState =
  | { phase: 'idle' | 'loading' }
  | { phase: 'ready'; page: PlanningCommandCenterPage }
  | { phase: 'error'; message: string };

const DEFAULT_FILTERS: CommandCenterFilters = {
  q: '',
  status: '',
  phase: '',
  sortBy: 'priority',
  sortDirection: 'desc',
};

function pageItemsKey(page: PlanningCommandCenterPage): string {
  return page.items.map(commandCenterItemKey).join('|');
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
  const [filters, setFilters] = useState<CommandCenterFilters>(DEFAULT_FILTERS);
  const [loadState, setLoadState] = useState<LoadState>({ phase: 'idle' });
  const [viewMode, setViewMode] = useState<CommandCenterViewMode>('list');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());
  const [detailFeatureId, setDetailFeatureId] = useState<string | null>(null);
  const [launchFeatureId, setLaunchFeatureId] = useState<string | null>(null);
  const [commandOverrides, setCommandOverrides] = useState<Record<string, string>>({});
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle');

  const load = useCallback(async () => {
    setLoadState((current) => (current.phase === 'ready' ? current : { phase: 'loading' }));
    try {
      const phase = filters.phase ? Number(filters.phase) : undefined;
      const page = await getPlanningCommandCenter({
        projectId: projectId ?? undefined,
        q: filters.q,
        status: filters.status,
        phase: Number.isFinite(phase) ? phase : undefined,
        sortBy: filters.sortBy,
        sortDirection: filters.sortDirection,
        pageSize: 50,
      });
      setLoadState({ phase: 'ready', page });
    } catch (error) {
      const message =
        error instanceof PlanningCommandCenterApiError
          ? `Planning Command Center API error (${error.status}): ${error.message}`
          : error instanceof Error
            ? error.message
            : 'Unable to load Planning Command Center data.';
      setLoadState({ phase: 'error', message });
    }
  }, [filters.phase, filters.q, filters.sortBy, filters.sortDirection, filters.status, projectId]);

  useEffect(() => {
    let cancelled = false;
    setLoadState((current) => (current.phase === 'ready' ? current : { phase: 'loading' }));
    getPlanningCommandCenter({
      projectId: projectId ?? undefined,
      q: filters.q,
      status: filters.status,
      phase: filters.phase ? Number(filters.phase) : undefined,
      sortBy: filters.sortBy,
      sortDirection: filters.sortDirection,
      pageSize: 50,
    })
      .then((page) => {
        if (!cancelled) setLoadState({ phase: 'ready', page });
      })
      .catch((error) => {
        if (cancelled) return;
        const message =
          error instanceof PlanningCommandCenterApiError
            ? `Planning Command Center API error (${error.status}): ${error.message}`
            : error instanceof Error
              ? error.message
              : 'Unable to load Planning Command Center data.';
        setLoadState({ phase: 'error', message });
      });
    return () => {
      cancelled = true;
    };
  }, [filters.phase, filters.q, filters.sortBy, filters.sortDirection, filters.status, projectId]);

  const page = loadState.phase === 'ready' ? loadState.page : null;
  const total = page?.total ?? page?.items.length ?? 0;
  const detailItem = page?.items.find((item) => item.feature.featureId === detailFeatureId) ?? null;
  const launchItem = page?.items.find((item) => item.feature.featureId === launchFeatureId) ?? null;
  const firstItemKey = useMemo(() => (page?.items[0] ? commandCenterItemKey(page.items[0]) : ''), [page]);

  const commandForItem = useCallback((item: PlanningCommandCenterItem): string => {
    return commandOverrides[commandCenterItemKey(item)] ?? item.command?.command ?? '';
  }, [commandOverrides]);

  useEffect(() => {
    if (!page || !firstItemKey) return;
    setExpandedIds((current) => {
      if (current.size > 0) return current;
      return new Set([firstItemKey]);
    });
  }, [firstItemKey, page, page ? pageItemsKey(page) : '']);

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

  return (
    <Panel className="p-5" data-testid="planning-command-center">
      <div className="space-y-4">
        <CommandCenterToolbar
          filters={filters}
          viewMode={viewMode}
          total={total}
          loading={loadState.phase === 'loading'}
          onFiltersChange={setFilters}
          onViewModeChange={changeViewMode}
          onRefresh={() => void load()}
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
        {loadState.phase === 'loading' || loadState.phase === 'idle' ? (
          <div className="flex min-h-[180px] items-center justify-center gap-2 rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] text-[12px] text-[color:var(--ink-3)]">
            <Loader2 size={16} className="animate-spin" aria-hidden />
            Loading command center...
          </div>
        ) : null}
        {loadState.phase === 'error' ? (
          <div className="rounded-[var(--radius-sm)] border border-[color:color-mix(in_oklab,var(--err)_35%,var(--line-1))] bg-[color:color-mix(in_oklab,var(--err)_10%,var(--bg-1))] p-4">
            <div className="flex items-start gap-2 text-[12px] text-[color:var(--err)]">
              <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden />
              <p>{loadState.message}</p>
            </div>
            <BtnGhost className="mt-3" size="sm" onClick={() => void load()}>
              retry
            </BtnGhost>
          </div>
        ) : null}
        {page && viewMode === 'list' ? (
          <CommandCenterListView
            items={page.items}
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
            items={page.items}
            commandOverrides={commandOverrides}
            onOpenLaunch={openLaunch}
            onOpenExecution={openExecution}
            onOpenPlan={openPlan}
            onOpenDetail={openDetail}
            onOpenPullRequest={openPullRequest}
          />
        ) : null}
        {page && viewMode === 'board' ? (
          <CommandCenterBoardView
            items={page.items}
            commandOverrides={commandOverrides}
            onOpenLaunch={openLaunch}
            onOpenExecution={openExecution}
            onOpenPlan={openPlan}
            onOpenDetail={openDetail}
            onOpenPullRequest={openPullRequest}
          />
        ) : null}
        {page?.warnings.length ? (
          <div className="space-y-1">
            {page.warnings.map((warning) => (
              <p key={warning} className="planning-mono text-[10.5px] text-[color:var(--warn)]">{warning}</p>
            ))}
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
            void load();
          }}
        />
      ) : null}
    </Panel>
  );
}
