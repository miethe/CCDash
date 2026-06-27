/**
 * MPCC-503: Cross-project active-session board for the multi-project
 * command center.
 *
 * Reuses PlanningAgentSessionBoard grouping patterns (state/project/feature/
 * phase/agent/model).  Workers/subagents are shown as SUMMARIES under each
 * root card — not promoted to top-level cards.
 *
 * MPCC-602 Performance: When total visible cards > 250 the card list within
 * each column is virtualized using @tanstack/react-virtual (already a project
 * dependency).  Below the threshold plain rendering is used (avoids virtualizer
 * overhead for small sets).  Estimated card height is 90px (expanded ~140px).
 *
 * MPCC-604 Accessibility:
 *   - Board group headers use role="heading" aria-level="3".
 *   - Board list uses role="list" / role="listitem".
 *   - State dot pulse and refresh spinner respect prefers-reduced-motion.
 *   - Grouping toolbar buttons use aria-pressed.
 *   - Refresh button has aria-label.
 *   - Card keyboard handling: Enter/Space selects; cards have aria-label.
 */
import { memo, useCallback, useEffect, useId, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { AlertCircle, ChevronDown, ChevronRight, Clock, Globe, Layers, Loader2, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  AggregateSessionCard,
  AggregateBoardGroup,
  AggregateSessionWorkerSummary,
  MultiProjectSessionBoardResponse,
  PlanningBoardGroupingMode,
} from '@/types';
import { BtnGhost } from '../primitives';
import { formatLastActivity } from '@/lib/planningHelpers';

// Multi-project grouping extends V1 PlanningBoardGroupingMode with 'project'
// exported so callers can reference the extended type.
export type MultiProjectGroupingMode = PlanningBoardGroupingMode | 'project';

// ── Constants ─────────────────────────────────────────────────────────────────

/** Cards-per-column threshold above which @tanstack/react-virtual kicks in. */
const VIRTUALIZE_THRESHOLD = 250;

/** Estimated card height in px (collapsed). Slightly generous to avoid clipping. */
const CARD_ESTIMATE_PX = 90;

/** Number of overscan rows on each side of the visible window. */
const OVERSCAN = 4;

const STATE_DOT: Record<string, string> = {
  running: 'var(--ok)',
  thinking: 'var(--brand)',
  completed: 'var(--ink-3)',
  failed: 'var(--err)',
  cancelled: 'var(--warn)',
  unknown: 'var(--ink-4)',
};

const GROUPING_LABELS: Record<MultiProjectGroupingMode, string> = {
  state: 'state',
  project: 'project',
  feature: 'feature',
  phase: 'phase',
  agent: 'agent',
  model: 'model',
};

/**
 * When grouping by state, columns with these group keys start collapsed by
 * default (unless the user has manually toggled them).
 */
const DONE_STATE_KEYS = new Set(['completed', 'done', 'cancelled']);

/**
 * Returns the auto-collapse default for a column (before any manual override).
 * Columns start collapsed when they represent a done/completed state OR have
 * zero cards.
 */
function defaultGroupCollapsed(group: AggregateBoardGroup): boolean {
  if (group.cards.length === 0) return true;
  if (group.groupType === 'state' && DONE_STATE_KEYS.has(group.groupKey)) return true;
  return false;
}

function fallbackColor(projectId: string): string {
  let hash = 0;
  for (let i = 0; i < projectId.length; i++) {
    hash = projectId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash) % 360;
  return `oklch(65% 0.18 ${h})`;
}

// ── Worker summary row ─────────────────────────────────────────────────────────

const WorkerRow = memo(function WorkerRow({ worker }: { worker: AggregateSessionWorkerSummary }) {
  const dotColor = STATE_DOT[worker.state] ?? 'var(--ink-4)';
  return (
    <div
      className="flex items-center gap-1.5 py-0.5 pl-5"
      style={{ borderTop: '1px solid var(--line-1)', fontSize: 10 }}
    >
      <span
        className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: dotColor }}
        aria-hidden
      />
      <span className="planning-mono truncate text-[color:var(--ink-3)]">
        {worker.agentName || 'worker'}
      </span>
      <span className="planning-mono text-[color:var(--ink-4)] ml-auto shrink-0">
        {worker.state}
      </span>
      {(() => {
        const act = formatLastActivity(worker.lastActivityAt);
        return act ? (
          <span className="planning-mono text-[color:var(--ink-4)] shrink-0" title={act.title}>
            {act.label}
          </span>
        ) : null;
      })()}
    </div>
  );
});

// ── Aggregate session card ─────────────────────────────────────────────────────

interface AggregateSessionCardViewProps {
  aggregateCard: AggregateSessionCard;
  isSelected: boolean;
  onSelect: (sessionId: string) => void;
  onOpenDetail?: (sessionId: string, projectId: string) => void;
}

const AggregateSessionCardView = memo(function AggregateSessionCardView({
  aggregateCard,
  isSelected,
  onSelect,
  onOpenDetail,
}: AggregateSessionCardViewProps) {
  const { card, project, workers } = aggregateCard;
  const [workersExpanded, setWorkersExpanded] = useState(false);

  const color = project.projectColor || fallbackColor(project.projectId);
  const dotColor = STATE_DOT[card.state] ?? 'var(--ink-4)';
  const hasWorkers = workers.length > 0;
  const isRunning = card.state === 'running';

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect(card.sessionId);
      }
    },
    [onSelect, card.sessionId],
  );

  return (
    <div
      className={cn(
        'rounded-[var(--radius-sm)] overflow-hidden',
        // MPCC-604: reduced-motion — transition only when motion is OK
        'motion-safe:transition-all motion-safe:duration-150 cursor-pointer',
        isSelected
          ? 'ring-1 ring-[color:var(--brand)]'
          : 'hover:border-[color:var(--line-2)]',
      )}
      style={{
        border: '1px solid var(--line-1)',
        borderLeftWidth: 3,
        borderLeftColor: color,
        backgroundColor: isSelected ? 'var(--bg-2)' : 'var(--bg-1)',
      }}
      role="button"
      tabIndex={0}
      aria-selected={isSelected}
      aria-label={`Session ${card.sessionId} · ${card.state} · ${project.projectName}`}
      onClick={() => onSelect(card.sessionId)}
      onKeyDown={handleKeyDown}
      data-testid="aggregate-session-card"
      data-session-id={card.sessionId}
      data-project-id={project.projectId}
    >
      {/* Card header */}
      <div className="flex items-start gap-2 p-2.5">
        {/* State dot — pulse only when motion is OK */}
        <span
          className={cn(
            'mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full',
            isRunning && 'motion-safe:animate-pulse',
          )}
          style={{ backgroundColor: dotColor }}
          aria-hidden
        />

        {/* Main content */}
        <div className="min-w-0 flex-1">
          {/* Project + state row */}
          <div className="flex flex-wrap items-center gap-1 mb-0.5">
            <span
              className="planning-mono text-[10px] truncate max-w-[100px]"
              style={{ color }}
              title={project.projectName}
            >
              {project.projectName}
            </span>
            <span
              className="planning-mono text-[10px]"
              style={{ color: 'var(--ink-4)' }}
            >
              ·
            </span>
            <span
              className="planning-mono text-[10px]"
              style={{ color: dotColor }}
            >
              {card.state}
            </span>
          </div>

          {/* Feature correlation */}
          {card.correlation?.featureName && (
            <p
              className="planning-mono text-[11px] truncate"
              style={{ color: 'var(--ink-1)' }}
              title={card.correlation.featureName}
            >
              {card.correlation.featureName}
            </p>
          )}

          {/* Agent + model */}
          <div className="flex flex-wrap items-center gap-1 mt-1">
            {card.agentName && (
              <span className="planning-mono text-[10px]" style={{ color: 'var(--ink-3)' }}>
                {card.agentName}
              </span>
            )}
            {card.model && (
              <span
                className="planning-mono rounded px-1 text-[9.5px]"
                style={{ backgroundColor: 'var(--bg-3)', color: 'var(--ink-3)' }}
              >
                {card.model}
              </span>
            )}
            {(() => {
              const activityDisplay = formatLastActivity(card.lastActivityAt ?? card.startedAt ?? null);
              return activityDisplay ? (
                <span
                  className="planning-mono text-[10px] ml-auto"
                  style={{ color: 'var(--ink-4)' }}
                  title={activityDisplay.title}
                >
                  {activityDisplay.label}
                </span>
              ) : null;
            })()}
          </div>

          {/* Phase correlation */}
          {card.correlation?.phaseNumber != null && (
            <div className="mt-1 flex items-center gap-1">
              <span
                className="planning-mono rounded px-1 text-[9.5px]"
                style={{ backgroundColor: 'var(--bg-3)', color: 'var(--ink-3)' }}
              >
                phase {card.correlation.phaseNumber}
              </span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex shrink-0 flex-col items-end gap-1">
          {onOpenDetail && (
            <button
              type="button"
              className="planning-mono rounded p-0.5 text-[10px] text-[color:var(--ink-4)] hover:text-[color:var(--ink-1)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]"
              onClick={(e) => {
                e.stopPropagation();
                onOpenDetail(card.sessionId, project.projectId);
              }}
              aria-label={`Open detail for session ${card.sessionId}`}
              title="Open session detail"
            >
              detail
            </button>
          )}
        </div>
      </div>

      {/* Workers summary (collapsible) */}
      {hasWorkers && (
        <div>
          <button
            type="button"
            className="flex w-full items-center gap-1 px-2.5 py-1 text-[10px] text-[color:var(--ink-4)] hover:text-[color:var(--ink-2)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]"
            style={{ borderTop: '1px solid var(--line-1)' }}
            onClick={(e) => {
              e.stopPropagation();
              setWorkersExpanded((x) => !x);
            }}
            aria-expanded={workersExpanded}
            aria-label={`${workers.length} worker${workers.length !== 1 ? 's' : ''} for session ${card.sessionId}`}
          >
            {workersExpanded ? (
              <ChevronDown size={11} aria-hidden />
            ) : (
              <ChevronRight size={11} aria-hidden />
            )}
            <span className="planning-mono">{workers.length} worker{workers.length !== 1 ? 's' : ''}</span>
          </button>
          {workersExpanded && (
            <div>
              {workers.map((w) => (
                <WorkerRow key={w.sessionId} worker={w} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

// ── Virtualized card list ──────────────────────────────────────────────────────

/**
 * Renders a column's card list.  When cards.length > VIRTUALIZE_THRESHOLD the
 * list is virtualized with @tanstack/react-virtual to keep rendering fast for
 * large multi-project deployments.  Below the threshold plain rendering is used.
 */
interface CardListProps {
  cards: AggregateSessionCard[];
  selectedCardId: string | null;
  onCardSelect: (sessionId: string) => void;
  onOpenDetail?: (sessionId: string, projectId: string) => void;
}

const CardList = memo(function CardList({
  cards,
  selectedCardId,
  onCardSelect,
  onOpenDetail,
}: CardListProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const shouldVirtualize = cards.length > VIRTUALIZE_THRESHOLD;

  const virtualizer = useVirtualizer({
    count: cards.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => CARD_ESTIMATE_PX,
    overscan: OVERSCAN,
    // Only active when we actually virtualize; when not active the hook is still
    // called (hooks must not be conditional) but the output is unused.
    enabled: shouldVirtualize,
  });

  if (cards.length === 0) {
    return <p className="planning-mono text-[11px] text-[color:var(--ink-4)]">no sessions</p>;
  }

  if (!shouldVirtualize) {
    // Plain rendering for small sets — simplest, lowest overhead.
    return (
      <>
        {cards.map((aggCard) => (
          <AggregateSessionCardView
            key={aggCard.card.sessionId}
            aggregateCard={aggCard}
            isSelected={selectedCardId === aggCard.card.sessionId}
            onSelect={onCardSelect}
            onOpenDetail={onOpenDetail}
          />
        ))}
      </>
    );
  }

  // Virtualized rendering for large sets (>250 cards in a column).
  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  return (
    <div
      ref={parentRef}
      style={{ overflowY: 'auto', maxHeight: '70vh' }}
      aria-label={`${cards.length} session cards (scrollable)`}
    >
      <div
        style={{ height: totalSize, position: 'relative' }}
      >
        {virtualItems.map((virtualItem) => {
          const aggCard = cards[virtualItem.index];
          return (
            <div
              key={aggCard.card.sessionId}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualItem.start}px)`,
                paddingBottom: 8,
              }}
              data-index={virtualItem.index}
            >
              <AggregateSessionCardView
                aggregateCard={aggCard}
                isSelected={selectedCardId === aggCard.card.sessionId}
                onSelect={onCardSelect}
                onOpenDetail={onOpenDetail}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
});

// ── Board group column ─────────────────────────────────────────────────────────

interface BoardGroupColumnProps {
  group: AggregateBoardGroup;
  selectedCardId: string | null;
  onCardSelect: (sessionId: string) => void;
  onOpenDetail?: (sessionId: string, projectId: string) => void;
}

const BoardGroupColumn = memo(function BoardGroupColumn({
  group,
  selectedCardId,
  onCardSelect,
  onOpenDetail,
}: BoardGroupColumnProps) {
  const headingId = useId();

  // ── Collapse state ──────────────────────────────────────────────────────
  const [collapsed, setCollapsed] = useState(() => defaultGroupCollapsed(group));
  const [userToggled, setUserToggled] = useState(false);

  // If card count changes to/from zero and user hasn't touched this column,
  // re-evaluate the auto-default.
  useEffect(() => {
    if (!userToggled) {
      setCollapsed(defaultGroupCollapsed(group));
    }
  }, [group, userToggled]);

  const handleToggleCollapse = useCallback(() => {
    setCollapsed((prev) => !prev);
    setUserToggled(true);
  }, []);

  // ── Collapsed strip ─────────────────────────────────────────────────────
  if (collapsed) {
    return (
      <button
        type="button"
        onClick={handleToggleCollapse}
        aria-expanded={false}
        aria-label={`Expand ${group.groupLabel} column (${group.cardCount} cards)`}
        data-testid="board-group-column-collapsed"
        data-group-key={group.groupKey}
        className={cn(
          'flex w-10 flex-shrink-0 flex-col items-center justify-start gap-2',
          'rounded-[var(--radius,4px)] pt-3 pb-2',
          'cursor-pointer',
          'transition-colors duration-150',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
          'hover:opacity-80',
        )}
        style={{ backgroundColor: 'var(--bg-1)', border: '1px solid var(--line-1)' }}
      >
        <ChevronRight
          size={12}
          aria-hidden
          style={{ color: 'var(--ink-3)', flexShrink: 0 }}
        />
        <span
          className="planning-mono rounded px-1 text-[9px]"
          style={{ backgroundColor: 'var(--bg-2)', color: 'var(--ink-3)', border: '1px solid var(--line-2)', flexShrink: 0 }}
          aria-label={`${group.cardCount} cards`}
        >
          {group.cardCount}
        </span>
        <span
          className="planning-caps text-[10px]"
          style={{ writingMode: 'vertical-rl', textOrientation: 'mixed', color: 'var(--ink-3)' }}
        >
          {group.groupLabel}
        </span>
      </button>
    );
  }

  // ── Expanded column ─────────────────────────────────────────────────────
  return (
    <div
      className="flex min-w-[260px] max-w-[340px] flex-1 flex-col gap-2"
      data-testid="board-group-column"
      data-group-key={group.groupKey}
      aria-labelledby={headingId}
    >
      {/* Column header — role="heading" for screen readers */}
      <div className="flex items-center gap-1.5 pb-2" style={{ borderBottom: '1px solid var(--line-1)' }}>
        <h3
          id={headingId}
          role="heading"
          aria-level={3}
          className="planning-caps text-[10px] text-[color:var(--ink-3)] m-0 flex-1 truncate"
        >
          {group.groupLabel}
        </h3>
        <span
          className="planning-mono rounded px-1 text-[10px]"
          style={{ backgroundColor: 'var(--bg-2)', color: 'var(--ink-3)' }}
          aria-label={`${group.cardCount} cards`}
        >
          {group.cardCount}
        </span>
        {/* Collapse toggle */}
        <button
          type="button"
          onClick={handleToggleCollapse}
          aria-expanded={true}
          aria-label={`Collapse ${group.groupLabel} column`}
          className={cn(
            'flex h-5 w-5 flex-shrink-0 items-center justify-center rounded',
            'transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
          )}
          style={{ color: 'var(--ink-4)' }}
        >
          <ChevronDown
            size={11}
            aria-hidden
          />
        </button>
      </div>

      {/* Cards — virtualized when > VIRTUALIZE_THRESHOLD */}
      <CardList
        cards={group.cards}
        selectedCardId={selectedCardId}
        onCardSelect={onCardSelect}
        onOpenDetail={onOpenDetail}
      />
    </div>
  );
});

// ── Grouping toolbar ──────────────────────────────────────────────────────────

interface GroupingToolbarProps {
  grouping: MultiProjectGroupingMode;
  onGroupingChange: (grouping: MultiProjectGroupingMode) => void;
  totalCount: number;
  activeCount: number;
  onRefresh: () => void;
  loading: boolean;
  toolbarId: string;
}

function GroupingToolbar({
  grouping,
  onGroupingChange,
  totalCount,
  activeCount,
  onRefresh,
  loading,
  toolbarId,
}: GroupingToolbarProps) {
  const modes: MultiProjectGroupingMode[] = ['state', 'project', 'feature', 'phase', 'agent', 'model'];

  return (
    <div className="flex flex-wrap items-center gap-2 pb-3" style={{ borderBottom: '1px solid var(--line-1)' }}>
      <div className="flex items-center gap-1.5">
        <Globe size={13} style={{ color: 'var(--ink-3)' }} aria-hidden />
        <span id={toolbarId} className="planning-caps text-[10px] text-[color:var(--ink-3)]">portfolio sessions</span>
        <span
          className="planning-mono rounded px-1.5 text-[10px]"
          style={{ backgroundColor: 'var(--bg-2)', color: 'var(--ink-3)' }}
          aria-label={`${totalCount} total sessions`}
        >
          {totalCount} total
        </span>
        {activeCount > 0 && (
          <span
            className="planning-mono rounded px-1.5 text-[10px]"
            style={{ backgroundColor: 'color-mix(in oklab, var(--ok) 12%, var(--bg-2))', color: 'var(--ok)' }}
            aria-label={`${activeCount} active sessions`}
          >
            {activeCount} active
          </span>
        )}
      </div>

      {/* Grouping mode selector */}
      <div
        role="group"
        aria-label="Session grouping dimension"
        className="ml-auto flex items-center gap-0.5 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-0.5"
      >
        <span className="planning-mono px-1.5 text-[10px] text-[color:var(--ink-4)]" aria-hidden>group by</span>
        {modes.map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={grouping === mode}
            onClick={() => onGroupingChange(mode)}
            className={cn(
              'planning-mono rounded-[var(--radius-sm)] px-2 py-0.5 text-[10.5px] motion-safe:transition-colors',
              grouping === mode
                ? 'bg-[color:var(--bg-3)] text-[color:var(--ink-0)]'
                : 'text-[color:var(--ink-3)] hover:text-[color:var(--ink-1)]',
            )}
          >
            {GROUPING_LABELS[mode]}
          </button>
        ))}
      </div>

      <BtnGhost
        size="sm"
        onClick={onRefresh}
        disabled={loading}
        aria-label={loading ? 'Refreshing session board…' : 'Refresh session board'}
      >
        <RefreshCw
          size={13}
          aria-hidden
          className={loading ? 'motion-safe:animate-spin' : undefined}
        />
      </BtnGhost>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface MultiProjectSessionBoardProps {
  data: MultiProjectSessionBoardResponse | undefined;
  loading: boolean;
  error: Error | null;
  grouping: MultiProjectGroupingMode;
  selectedCardId: string | null;
  onGroupingChange: (grouping: MultiProjectGroupingMode) => void;
  onCardSelect: (sessionId: string | null) => void;
  onOpenDetail?: (sessionId: string, projectId: string) => void;
  onRefresh: () => void;
  className?: string;
}

export function MultiProjectSessionBoard({
  data,
  loading,
  error,
  grouping,
  selectedCardId,
  onGroupingChange,
  onCardSelect,
  onOpenDetail,
  onRefresh,
  className,
}: MultiProjectSessionBoardProps) {
  const boardId = useId();
  const toolbarId = useId();

  const handleCardSelect = useCallback(
    (sessionId: string) => {
      onCardSelect(selectedCardId === sessionId ? null : sessionId);
    },
    [onCardSelect, selectedCardId],
  );

  // Total visible card count across all groups (for virtualization decision).
  const totalVisible = data?.groups.reduce((acc, g) => acc + g.cards.length, 0) ?? 0;

  return (
    <div
      className={cn('space-y-4', className)}
      data-testid="multi-project-session-board"
      aria-labelledby={toolbarId}
    >
      <GroupingToolbar
        grouping={grouping}
        onGroupingChange={onGroupingChange}
        totalCount={data?.totalCardCount ?? 0}
        activeCount={data?.activeCount ?? 0}
        onRefresh={onRefresh}
        loading={loading}
        toolbarId={toolbarId}
      />

      {/* Loading */}
      {loading && !data && (
        <div
          className="flex min-h-[160px] items-center justify-center gap-2 text-[12px] text-[color:var(--ink-3)]"
          role="status"
          aria-live="polite"
        >
          <Loader2 size={16} className="motion-safe:animate-spin" aria-hidden />
          Loading active sessions across projects...
        </div>
      )}

      {/* Error */}
      {error && !data && (
        <div
          className="rounded-[var(--radius-sm)] border p-4"
          role="alert"
          style={{
            borderColor: 'color-mix(in oklab, var(--err) 35%, var(--line-1))',
            backgroundColor: 'color-mix(in oklab, var(--err) 8%, var(--bg-1))',
          }}
        >
          <div className="flex items-start gap-2 text-[12px]" style={{ color: 'var(--err)' }}>
            <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden />
            <p>{error.message}</p>
          </div>
          <BtnGhost className="mt-3" size="sm" onClick={onRefresh}>
            retry
          </BtnGhost>
        </div>
      )}

      {/* Partial-status warnings */}
      {data?.status === 'partial' && data.warnings.length > 0 && (
        <div className="space-y-0.5" role="status" aria-live="polite">
          {data.warnings.map((w, i) => (
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

      {/* Windowing perf note for large sets */}
      {data && totalVisible > VIRTUALIZE_THRESHOLD && (
        <p
          className="planning-mono text-[10px]"
          style={{ color: 'var(--ink-4)' }}
          aria-live="polite"
        >
          {totalVisible} cards — column scroll windows active
        </p>
      )}

      {/* Board — horizontal scroll for many columns */}
      {data && (
        <div
          className="overflow-x-auto pb-2"
          style={{ WebkitOverflowScrolling: 'touch' }}
        >
          <div
            id={boardId}
            className="flex gap-4"
            style={{ minWidth: 'min-content' }}
            role="list"
            aria-label="Session board groups"
          >
            {data.groups.map((group) => (
              <div key={group.groupKey} role="listitem">
                <BoardGroupColumn
                  group={group}
                  selectedCardId={selectedCardId}
                  onCardSelect={handleCardSelect}
                  onOpenDetail={onOpenDetail}
                />
              </div>
            ))}
            {data.groups.length === 0 && (
              <div className="flex min-h-[120px] w-full items-center justify-center">
                <div className="text-center">
                  <Layers size={24} className="mx-auto mb-2 text-[color:var(--ink-4)]" aria-hidden />
                  <p className="planning-mono text-[12px] text-[color:var(--ink-3)]">
                    No active sessions across projects
                  </p>
                  <p className="planning-mono mt-1 text-[11px] text-[color:var(--ink-4)]">
                    Sessions will appear here when agents are running
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Stale data indicator */}
      {loading && data && (
        <div className="flex items-center gap-1 text-[10.5px]" style={{ color: 'var(--ink-4)' }} aria-live="polite">
          <Clock size={11} aria-hidden />
          <span className="planning-mono">refreshing...</span>
        </div>
      )}
    </div>
  );
}
