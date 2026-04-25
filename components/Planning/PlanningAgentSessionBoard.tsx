import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, LayoutGrid, RefreshCw } from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  PlanningAgentSessionBoard as PlanningAgentSessionBoardData,
  PlanningBoardGroup,
  PlanningAgentSessionCard,
  PlanningBoardGroupingMode,
} from '@/types';
import { getSessionBoard } from '@/services/planning';
import { useData } from '@/contexts/DataContext';
import { usePlanningRoute } from './PlanningRouteLayout';
import { PlanningBoardToolbar } from './PlanningBoardToolbar';
import { Panel, Dot } from './primitives';

// ── State dot colours keyed by card state ─────────────────────────────────────

const STATE_DOT_COLOR: Record<PlanningAgentSessionCard['state'], string> = {
  running: 'var(--ok)',
  thinking: 'var(--brand)',
  completed: 'var(--ink-3)',
  failed: 'var(--err)',
  cancelled: 'var(--warn)',
  unknown: 'var(--ink-4)',
};

// ── Placeholder card ──────────────────────────────────────────────────────────

function SessionCard({ card, compact }: { card: PlanningAgentSessionCard; compact: boolean }) {
  return (
    <div
      className={cn(
        'rounded-[var(--radius-sm)] border border-[color:var(--line-1)]',
        'bg-[color:var(--bg-2)] transition-colors hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)]',
        compact ? 'px-3 py-2' : 'px-3 py-2.5',
      )}
    >
      <div className="flex items-center gap-2">
        <Dot
          style={{ background: STATE_DOT_COLOR[card.state] ?? 'var(--ink-4)', flexShrink: 0 }}
          aria-label={card.state}
        />
        <span
          className="planning-mono truncate text-[10px] text-[color:var(--ink-2)]"
          title={card.sessionId}
        >
          {card.sessionId}
        </span>
      </div>
      {card.agentName && (
        <p
          className="mt-1 truncate text-[11px] text-[color:var(--ink-1)]"
          title={card.agentName}
        >
          {card.agentName}
        </p>
      )}
    </div>
  );
}

// ── Board column ──────────────────────────────────────────────────────────────

function BoardColumn({
  group,
  filterText,
  compact,
}: {
  group: PlanningBoardGroup;
  filterText: string;
  compact: boolean;
}) {
  const lowerFilter = filterText.toLowerCase();
  const visible = filterText
    ? group.cards.filter(
        (c) =>
          c.sessionId.toLowerCase().includes(lowerFilter) ||
          (c.agentName ?? '').toLowerCase().includes(lowerFilter),
      )
    : group.cards;

  return (
    <div
      className={cn(
        'flex min-w-[220px] max-w-[280px] flex-shrink-0 flex-col',
        'rounded-[var(--radius)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)]',
      )}
    >
      <div
        className={cn(
          'flex items-center justify-between border-b border-[color:var(--line-1)]',
          compact ? 'px-3 py-1.5' : 'px-3 py-2',
        )}
      >
        <span className="truncate text-[11px] font-medium text-[color:var(--ink-1)]">
          {group.groupLabel}
        </span>
        <span
          className={cn(
            'planning-mono ml-2 flex-shrink-0 rounded px-1.5 py-0.5 text-[10px]',
            'border border-[color:var(--line-2)] bg-[color:var(--bg-3)] text-[color:var(--ink-2)]',
          )}
        >
          {group.cardCount}
        </span>
      </div>

      <div
        className={cn(
          'flex flex-col overflow-y-auto',
          compact ? 'gap-1.5 p-2' : 'gap-2 p-2.5',
        )}
        style={{ maxHeight: 520 }}
      >
        {visible.length === 0 ? (
          <p className="py-4 text-center text-[11px] text-[color:var(--ink-4)]">
            {filterText ? 'No matches' : 'Empty'}
          </p>
        ) : (
          visible.map((card) => (
            <SessionCard key={card.sessionId} card={card} compact={compact} />
          ))
        )}
      </div>
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function BoardSkeleton() {
  return (
    <div className="flex gap-3" aria-busy="true" aria-label="Loading board">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="flex min-w-[220px] max-w-[280px] flex-shrink-0 flex-col rounded-[var(--radius)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)]"
        >
          <div className="flex items-center justify-between border-b border-[color:var(--line-1)] px-3 py-2">
            <div className="h-3 w-20 animate-pulse rounded bg-[color:var(--bg-3)]" />
            <div className="h-3 w-5 animate-pulse rounded bg-[color:var(--bg-3)]" />
          </div>
          <div className="flex flex-col gap-2 p-2.5">
            {Array.from({ length: 3 }).map((_, j) => (
              <div
                key={j}
                className="h-12 animate-pulse rounded-[var(--radius-sm)] bg-[color:var(--bg-2)]"
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type FetchState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; board: PlanningAgentSessionBoardData };

export interface PlanningAgentSessionBoardProps {
  className?: string;
}

export function PlanningAgentSessionBoard({ className }: PlanningAgentSessionBoardProps) {
  const { activeProject } = useData();
  const { density } = usePlanningRoute();
  const compact = density === 'compact';

  const [grouping, setGrouping] = useState<PlanningBoardGroupingMode>('state');
  const [filterText, setFilterText] = useState('');
  const [fetchState, setFetchState] = useState<FetchState>({ phase: 'idle' });

  const load = useCallback(
    async (opts: { forceRefresh?: boolean } = {}) => {
      if (!activeProject?.id) {
        setFetchState({ phase: 'idle' });
        return;
      }
      setFetchState((prev) => (prev.phase === 'ready' ? prev : { phase: 'loading' }));
      try {
        const board = await getSessionBoard(activeProject.id, grouping, opts);
        setFetchState({ phase: 'ready', board });
      } catch (err) {
        setFetchState({
          phase: 'error',
          message: err instanceof Error ? err.message : 'Failed to load session board.',
        });
      }
    },
    [activeProject?.id, grouping],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const handleGroupingChange = useCallback((mode: PlanningBoardGroupingMode) => {
    setGrouping(mode);
  }, []);

  return (
    <Panel className={cn('p-4', className)}>
      <PlanningBoardToolbar
        grouping={grouping}
        onGroupingChange={handleGroupingChange}
        filterText={filterText}
        onFilterTextChange={setFilterText}
        className="mb-3"
      />

      {fetchState.phase === 'loading' || fetchState.phase === 'idle' ? (
        <BoardSkeleton />
      ) : fetchState.phase === 'error' ? (
        <div className="flex flex-col items-center gap-3 py-10">
          <AlertCircle size={22} style={{ color: 'var(--err)' }} aria-hidden />
          <p className="text-[12px] text-[color:var(--ink-2)]">{fetchState.message}</p>
          <button
            type="button"
            onClick={() => void load({ forceRefresh: true })}
            className={cn(
              'flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[color:var(--line-2)]',
              'bg-[color:var(--bg-2)] px-3 py-1.5 text-[11px] text-[color:var(--ink-1)]',
              'hover:bg-[color:var(--bg-3)] transition-colors',
            )}
          >
            <RefreshCw size={11} aria-hidden />
            Retry
          </button>
        </div>
      ) : fetchState.board.groups.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-10">
          <LayoutGrid size={22} style={{ color: 'var(--ink-4)' }} aria-hidden />
          <p className="text-[12px] text-[color:var(--ink-3)]">No active agent sessions</p>
        </div>
      ) : (
        <div
          className="overflow-x-auto pb-2"
          role="region"
          aria-label="Agent session board"
        >
          <div className="flex gap-3" style={{ width: 'max-content' }}>
            {fetchState.board.groups.map((group) => (
              <BoardColumn
                key={group.groupKey}
                group={group}
                filterText={filterText}
                compact={compact}
              />
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}
