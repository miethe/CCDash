import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Bot, FileText, GitBranch, Layers, RefreshCw, Settings2 } from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  PlanningAgentSessionBoard,
  PlanningAgentSessionCard,
  SessionActivityMarker,
} from '@/types';
import { getFeatureSessionBoard } from '@/services/planning';
import { planningRouteFeatureModalHref } from '@/services/planningRoutes';
import { useData } from '@/contexts/DataContext';
import { usePlanningRoute } from './PlanningRouteLayout';
import { Dot } from './primitives';

// ── Constants ─────────────────────────────────────────────────────────────────

/** State order for horizontal lane columns. */
const STATE_COLUMN_ORDER: PlanningAgentSessionCard['state'][] = [
  'running',
  'thinking',
  'completed',
  'failed',
  'cancelled',
  'unknown',
];

/** Colour token per state. */
const STATE_DOT_COLOR: Record<PlanningAgentSessionCard['state'], string> = {
  running: 'var(--ok)',
  thinking: 'var(--brand)',
  completed: 'var(--ink-3)',
  failed: 'var(--err)',
  cancelled: 'var(--warn)',
  unknown: 'var(--ink-4)',
};

const STATE_LABEL: Record<PlanningAgentSessionCard['state'], string> = {
  running: 'running',
  thinking: 'thinking',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'cancelled',
  unknown: 'unknown',
};

const STATE_HEADER_COLOR: Record<PlanningAgentSessionCard['state'], string> = {
  running: 'var(--ok)',
  thinking: 'var(--brand)',
  completed: 'var(--ink-3)',
  failed: 'var(--err)',
  cancelled: 'var(--warn)',
  unknown: 'var(--ink-4)',
};

const MARKER_SYMBOL: Record<SessionActivityMarker['markerType'], string> = {
  tool_call: '⚡',
  file_edit: '✎',
  command: '$',
  error: '✕',
  completion: '✓',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const secs = Math.floor((Date.now() - d.getTime()) / 1000);
  if (secs < 5) return 'now';
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

// ── Mini action row ───────────────────────────────────────────────────────────

const ACTION_LINK_CLS = cn(
  'inline-flex items-center justify-center rounded p-[3px]',
  'text-[color:var(--ink-3)] transition-colors',
  'hover:bg-[color:var(--bg-3)] hover:text-[color:var(--ink-1)]',
  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
);

function LaneCardActionRow({ card }: { card: PlanningAgentSessionCard }) {
  const featureId = card.correlation?.featureId;
  const phaseNumber = card.correlation?.phaseNumber;

  const ancestorRel = card.relationships.find(
    (rel) => rel.relationType === 'parent' || rel.relationType === 'root',
  );

  const phaseOpsHref =
    featureId != null && phaseNumber != null
      ? `${planningRouteFeatureModalHref(featureId, 'overview')}&phase=${encodeURIComponent(phaseNumber)}&panel=phase-ops`
      : null;

  const hasAnyLink = Boolean(card.sessionId || featureId || phaseOpsHref || ancestorRel);
  if (!hasAnyLink) return null;

  function stopProp(e: React.MouseEvent | React.KeyboardEvent) {
    e.stopPropagation();
  }

  return (
    <div
      className="mt-1 flex items-center gap-0.5 border-t border-[color:var(--line-1)] pt-1"
      aria-label="Session navigation links"
      onClick={stopProp}
      onKeyDown={stopProp}
    >
      {card.sessionId && (
        <Link
          to={`/sessions?session=${encodeURIComponent(card.sessionId)}`}
          className={ACTION_LINK_CLS}
          aria-label="View session transcript"
          title="View session transcript"
        >
          <FileText size={10} aria-hidden />
        </Link>
      )}
      {featureId && (
        <Link
          to={planningRouteFeatureModalHref(featureId, 'overview')}
          className={ACTION_LINK_CLS}
          aria-label={`Open feature${card.correlation?.featureName ? ` ${card.correlation.featureName}` : ''} in planning view`}
          title={`Feature: ${card.correlation?.featureName ?? featureId}`}
        >
          <Layers size={10} aria-hidden />
        </Link>
      )}
      {phaseOpsHref && (
        <Link
          to={phaseOpsHref}
          className={ACTION_LINK_CLS}
          aria-label={`Open phase ${phaseNumber} operations panel`}
          title={`Phase ${phaseNumber} operations`}
        >
          <Settings2 size={10} aria-hidden />
        </Link>
      )}
      <span className="flex-1" aria-hidden />
      {ancestorRel && (
        <Link
          to={`/sessions?session=${encodeURIComponent(ancestorRel.relatedSessionId)}`}
          className={ACTION_LINK_CLS}
          aria-label={`View ${ancestorRel.relationType} session`}
          title={`${ancestorRel.relationType === 'root' ? 'Root' : 'Parent'} session: ${ancestorRel.relatedSessionId}`}
        >
          <GitBranch size={10} aria-hidden />
        </Link>
      )}
    </div>
  );
}

// ── Lane session card ─────────────────────────────────────────────────────────

interface LaneCardProps {
  card: PlanningAgentSessionCard;
  compact: boolean;
}

function LaneCard({ card, compact }: LaneCardProps) {
  const prevStateRef = useRef(card.state);
  const [liveMsg, setLiveMsg] = useState('');
  const [showFlash, setShowFlash] = useState(false);

  useEffect(() => {
    if (prevStateRef.current !== card.state) {
      setLiveMsg(`State changed to ${STATE_LABEL[card.state]}`);
      prevStateRef.current = card.state;
      setShowFlash(true);
      const t = setTimeout(() => {
        setLiveMsg('');
        setShowFlash(false);
      }, 3500);
      return () => clearTimeout(t);
    }
  }, [card.state]);

  const dotColor = STATE_DOT_COLOR[card.state] ?? 'var(--ink-4)';
  const isActive = card.state === 'running' || card.state === 'thinking';
  const phaseHint =
    card.correlation?.phaseNumber != null
      ? card.correlation.phaseTitle
        ? `P${card.correlation.phaseNumber}: ${card.correlation.phaseTitle}`
        : `Phase ${card.correlation.phaseNumber}`
      : null;
  const taskHint = card.correlation?.taskId ?? card.correlation?.taskTitle ?? null;
  const latestMarker =
    card.activityMarkers.length > 0 ? card.activityMarkers[card.activityMarkers.length - 1] : null;

  const ariaLabel = [
    card.agentName ?? 'Agent',
    card.model ? `model ${card.model}` : null,
    STATE_LABEL[card.state],
    card.startedAt ? `started ${relativeTime(card.startedAt)} ago` : null,
  ]
    .filter(Boolean)
    .join(', ');

  return (
    <div
      className={cn(
        'relative rounded-[var(--radius-sm)] border bg-[color:var(--bg-2)]',
        'transition-[border-color,background-color] duration-200 motion-reduce:transition-none',
        'planning-card-enter',
        showFlash && 'planning-card-flash',
        compact ? 'px-2 py-1.5' : 'px-2.5 py-2',
        'border-[color:var(--line-1)]',
        'hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)]',
      )}
      aria-label={ariaLabel}
    >
      {/* Row 1: state dot + session ID truncated + time */}
      <div className="flex items-center gap-1 min-w-0">
        <Dot
          style={{
            background: dotColor,
            flexShrink: 0,
            '--dot-color': dotColor,
          } as React.CSSProperties}
          aria-label={card.state}
          className={isActive ? 'planning-dot-live' : undefined}
        />
        <span
          className="planning-mono truncate text-[9.5px] text-[color:var(--ink-3)] flex-1 min-w-0"
          title={card.sessionId}
        >
          {card.sessionId.length > 10 ? `…${card.sessionId.slice(-8)}` : card.sessionId}
        </span>
        {card.startedAt && (
          <span className="planning-mono flex-shrink-0 text-[8.5px] text-[color:var(--ink-4)] tabular-nums">
            {relativeTime(card.startedAt)}
          </span>
        )}
      </div>

      {/* Row 2: agent name */}
      <div
        className={cn(
          'mt-0.5 truncate font-medium text-[color:var(--ink-1)]',
          compact ? 'text-[10.5px]' : 'text-[11px]',
        )}
        title={card.agentName}
      >
        {card.agentName ?? <span className="text-[color:var(--ink-4)]">—</span>}
      </div>

      {/* Row 3: model chip */}
      {card.model && (
        <div className="mt-1">
          <span
            className={cn(
              'planning-mono inline-flex items-center rounded px-1.5 py-[2px]',
              'border border-[color:var(--line-2)] bg-[color:var(--bg-3)]',
              'text-[8.5px] text-[color:var(--ink-3)] leading-none',
            )}
          >
            {card.model}
          </span>
        </div>
      )}

      {/* Row 4: phase/task hints */}
      {(phaseHint || taskHint) && (
        <div className="mt-1 flex items-center gap-1 flex-wrap min-w-0">
          {phaseHint && (
            <span
              className="text-[8.5px] text-[color:var(--ink-3)] truncate max-w-[110px]"
              title={phaseHint}
            >
              {phaseHint}
            </span>
          )}
          {taskHint && phaseHint && (
            <span className="text-[8.5px] text-[color:var(--ink-4)]" aria-hidden>·</span>
          )}
          {taskHint && (
            <span
              className="text-[8.5px] text-[color:var(--ink-3)] truncate max-w-[90px]"
              title={typeof taskHint === 'string' ? taskHint : undefined}
            >
              {taskHint}
            </span>
          )}
        </div>
      )}

      {/* Row 5: token summary + latest activity marker */}
      <div className="mt-1 flex items-center gap-1.5 min-w-0">
        {card.tokenSummary ? (
          <span
            className="planning-mono text-[8.5px] text-[color:var(--ink-4)] flex-shrink-0 tabular-nums"
            title={`${card.tokenSummary.tokensIn} in / ${card.tokenSummary.tokensOut} out`}
          >
            {fmtTokens(card.tokenSummary.tokensIn)}↑ {fmtTokens(card.tokenSummary.tokensOut)}↓
          </span>
        ) : null}
        <span className="flex-1" />
        {latestMarker && (
          <span
            className="flex-shrink-0 text-[9px] leading-none"
            title={`${latestMarker.markerType}: ${latestMarker.label}`}
            aria-label={latestMarker.label}
          >
            {MARKER_SYMBOL[latestMarker.markerType] ?? '·'}
          </span>
        )}
      </div>

      {/* Context window bar */}
      {card.tokenSummary?.contextWindowPct != null && (
        <div className="mt-1 h-[2px] w-full rounded-full overflow-hidden bg-[color:var(--bg-3)]" aria-hidden>
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${Math.min(100, Math.round(card.tokenSummary.contextWindowPct * 100))}%`,
              background:
                card.tokenSummary.contextWindowPct > 0.8
                  ? 'var(--err)'
                  : card.tokenSummary.contextWindowPct > 0.6
                    ? 'var(--warn)'
                    : 'var(--ok)',
            }}
          />
        </div>
      )}

      {/* Action links */}
      <LaneCardActionRow card={card} />

      {/* Live state-change region */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="mt-0.5 text-[8px] text-[color:var(--ink-4)] truncate"
        style={{ minHeight: '0.75rem' }}
      >
        {liveMsg}
      </div>
    </div>
  );
}

// ── State column ──────────────────────────────────────────────────────────────

interface LaneColumnProps {
  state: PlanningAgentSessionCard['state'];
  cards: PlanningAgentSessionCard[];
  compact: boolean;
}

function LaneColumn({ state, cards, compact }: LaneColumnProps) {
  const color = STATE_HEADER_COLOR[state];
  const label = STATE_LABEL[state];

  return (
    <div
      className={cn(
        'flex flex-shrink-0 flex-col rounded-[var(--radius)] border bg-[color:var(--bg-1)]',
        'border-[color:var(--line-1)]',
        'min-w-[168px] max-w-[210px]',
      )}
      aria-label={`${label} sessions: ${cards.length}`}
    >
      {/* Column header */}
      <div
        className={cn(
          'flex items-center justify-between border-b border-[color:var(--line-1)]',
          compact ? 'px-2.5 py-1.5' : 'px-2.5 py-2',
        )}
        style={{
          background: `color-mix(in oklab, ${color} 6%, var(--bg-1))`,
          borderTop: `2px solid ${color}`,
          borderRadius: 'var(--radius) var(--radius) 0 0',
        }}
      >
        <span
          className="planning-caps text-[9.5px] font-semibold"
          style={{ color }}
        >
          {label}
        </span>
        <span
          className={cn(
            'planning-mono ml-2 flex-shrink-0 rounded px-1.5 py-[2px] text-[9px] tabular-nums',
            'border border-[color:var(--line-2)] bg-[color:var(--bg-3)] text-[color:var(--ink-2)]',
          )}
        >
          {cards.length}
        </span>
      </div>

      {/* Cards */}
      <div
        className={cn(
          'flex flex-col overflow-y-auto',
          compact ? 'gap-1.5 p-2' : 'gap-2 p-2',
        )}
        style={{ maxHeight: 320 }}
      >
        {cards.length === 0 ? (
          <p className="py-3 text-center text-[10px] text-[color:var(--ink-4)]">—</p>
        ) : (
          cards.map((card) => (
            <LaneCard key={card.sessionId} card={card} compact={compact} />
          ))
        )}
      </div>
    </div>
  );
}

// ── Lane skeleton ─────────────────────────────────────────────────────────────

function LaneSkeleton() {
  return (
    <div className="flex gap-2" aria-busy="true" aria-label="Loading agent sessions">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="min-w-[168px] max-w-[210px] flex-shrink-0 rounded-[var(--radius)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)]"
        >
          <div className="flex items-center justify-between border-b border-[color:var(--line-1)] px-2.5 py-2">
            <div className="h-2.5 w-14 animate-pulse rounded bg-[color:var(--bg-3)]" />
            <div className="h-2.5 w-4 animate-pulse rounded bg-[color:var(--bg-3)]" />
          </div>
          <div className="flex flex-col gap-1.5 p-2">
            {Array.from({ length: 2 }).map((_, j) => (
              <div
                key={j}
                className="h-16 animate-pulse rounded-[var(--radius-sm)] bg-[color:var(--bg-2)]"
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type LaneFetchState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; board: PlanningAgentSessionBoard };

export interface PlanningFeatureAgentLaneProps {
  featureId: string;
  className?: string;
}

/**
 * A compact horizontal lane showing agent sessions correlated to a specific feature.
 * Grouped by session state (running → thinking → completed → failed).
 * Designed to sit within the feature detail drawer (PlanningNodeDetail).
 */
export function PlanningFeatureAgentLane({ featureId, className }: PlanningFeatureAgentLaneProps) {
  const { activeProject, sessions } = useData();
  const { density } = usePlanningRoute();
  const compact = density === 'compact';

  const [fetchState, setFetchState] = useState<LaneFetchState>({ phase: 'idle' });
  const [refreshing, setRefreshing] = useState(false);

  const prevSessionsRef = useRef(sessions);

  const load = useCallback(
    async (opts: { forceRefresh?: boolean } = {}) => {
      if (!featureId) {
        setFetchState({ phase: 'idle' });
        return;
      }

      const isBackground = fetchState.phase === 'ready';
      if (isBackground) {
        setRefreshing(true);
      } else {
        setFetchState({ phase: 'loading' });
      }

      try {
        const board = await getFeatureSessionBoard(
          featureId,
          activeProject?.id,
          'state',
          opts,
        );
        setFetchState({ phase: 'ready', board });
      } catch (err) {
        if (isBackground) {
          console.warn('[PlanningFeatureAgentLane] Background refresh failed:', err);
        } else {
          setFetchState({
            phase: 'error',
            message: err instanceof Error ? err.message : 'Failed to load sessions for this feature.',
          });
        }
      } finally {
        setRefreshing(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [featureId, activeProject?.id],
  );

  // Initial load and featureId change.
  useEffect(() => {
    void load();
  }, [load]);

  // Follow upstream poll ticks from AppRuntimeContext.
  useEffect(() => {
    if (prevSessionsRef.current === sessions) return;
    prevSessionsRef.current = sessions;
    void load();
  }, [sessions, load]);

  const handleRefresh = useCallback(() => {
    void load({ forceRefresh: true });
  }, [load]);

  // ── Derived counts ──────────────────────────────────────────────────────────

  const board = fetchState.phase === 'ready' ? fetchState.board : null;
  const totalCount = board?.totalCardCount ?? 0;
  const activeCount = board?.activeCount ?? 0;

  // Build a card map per state for the ordered columns.
  const cardsByState = new Map<PlanningAgentSessionCard['state'], PlanningAgentSessionCard[]>();
  if (board) {
    for (const group of board.groups) {
      const state = group.groupKey as PlanningAgentSessionCard['state'];
      if (!cardsByState.has(state)) {
        cardsByState.set(state, []);
      }
      for (const card of group.cards) {
        cardsByState.get(state)!.push(card);
      }
    }
  }

  // Only render columns that exist in the response, in the canonical order.
  const activeColumns = STATE_COLUMN_ORDER.filter(
    (state) => (cardsByState.get(state)?.length ?? 0) > 0,
  );

  // "View on Board" URL: main planning board filtered to this feature via grouping=feature.
  const viewOnBoardHref = `/planning/board#feature=${encodeURIComponent(featureId)}`;

  const isLoading = fetchState.phase === 'loading' || fetchState.phase === 'idle';

  // ── Header label ────────────────────────────────────────────────────────────

  const headerLabel =
    fetchState.phase === 'ready'
      ? activeCount > 0
        ? `Agent Sessions (${activeCount} active)`
        : totalCount > 0
          ? `Agent Sessions (${totalCount})`
          : 'Agent Sessions'
      : 'Agent Sessions';

  return (
    <div
      className={cn(
        'planning-panel overflow-hidden rounded-[var(--radius)]',
        className,
      )}
      style={{ borderLeft: '3px solid var(--brand)' }}
    >
      {/* Lane header */}
      <div
        className={cn(
          'flex items-center gap-2 border-b border-[color:var(--line-1)]',
          compact ? 'px-3 py-2' : 'px-4 py-2.5',
        )}
      >
        {/* Icon + title */}
        <span className="text-[color:var(--brand)] flex-shrink-0" aria-hidden>
          <Bot size={14} />
        </span>

        <h2 className="flex-1 min-w-0 text-sm font-semibold text-[color:var(--ink-0)] truncate">
          {headerLabel}
          {activeCount > 0 && (
            <Dot
              className="planning-dot-live ml-2 inline-block"
              style={{
                background: 'var(--ok)',
                '--dot-color': 'var(--ok)',
                verticalAlign: 'middle',
              } as React.CSSProperties}
              aria-label={`${activeCount} active`}
            />
          )}
        </h2>

        {/* Stale/refresh */}
        {fetchState.phase === 'ready' && (
          <span className="planning-mono text-[9px] text-[color:var(--ink-4)]" aria-live="polite">
            {refreshing ? 'refreshing…' : null}
          </span>
        )}

        {/* Refresh button */}
        <button
          type="button"
          onClick={handleRefresh}
          disabled={isLoading || refreshing}
          aria-label="Refresh agent sessions"
          title="Refresh"
          className={cn(
            'flex flex-shrink-0 items-center justify-center rounded-[var(--radius-sm)]',
            'border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-1',
            'text-[color:var(--ink-3)] transition-colors',
            'hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-2)] hover:text-[color:var(--ink-1)]',
            'disabled:cursor-not-allowed disabled:opacity-40',
          )}
        >
          <RefreshCw
            size={11}
            aria-hidden
            className={refreshing ? 'animate-spin' : undefined}
          />
        </button>

        {/* View on Board link */}
        <Link
          to={viewOnBoardHref}
          className={cn(
            'planning-mono inline-flex flex-shrink-0 items-center gap-1 rounded-[var(--radius-sm)]',
            'border border-[color:var(--line-1)] bg-[color:var(--bg-1)]',
            'px-2 py-1 text-[10px] text-[color:var(--ink-2)]',
            'transition-colors hover:border-[color:var(--brand)] hover:bg-[color:color-mix(in_oklab,var(--brand)_6%,var(--bg-1))] hover:text-[color:var(--brand)]',
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
          )}
          aria-label="View all sessions on the agent session board"
          title="View on Board"
        >
          Board
          <ArrowUpRight size={10} aria-hidden />
        </Link>
      </div>

      {/* Lane body */}
      <div className={cn('overflow-x-auto', compact ? 'p-2' : 'p-3')}>
        {isLoading ? (
          <LaneSkeleton />
        ) : fetchState.phase === 'error' ? (
          <div className="flex items-center gap-2.5 py-3">
            <span className="text-[11px] text-[color:var(--err)]">{fetchState.message}</span>
            <button
              type="button"
              onClick={() => void load({ forceRefresh: true })}
              className={cn(
                'planning-mono inline-flex items-center gap-1 rounded border border-[color:var(--line-2)]',
                'bg-[color:var(--bg-2)] px-2 py-1 text-[10px] text-[color:var(--ink-1)]',
                'hover:bg-[color:var(--bg-3)] transition-colors',
              )}
            >
              <RefreshCw size={10} aria-hidden />
              Retry
            </button>
          </div>
        ) : activeColumns.length === 0 ? (
          /* Empty state */
          <div
            className={cn(
              'flex items-center justify-center gap-2.5',
              'rounded border border-dashed border-[color:var(--line-1)]',
              compact ? 'py-4' : 'py-6',
            )}
            aria-label="No sessions linked to this feature"
          >
            <Bot size={15} style={{ color: 'var(--ink-4)' }} aria-hidden />
            <p className="text-[11px] text-[color:var(--ink-3)]">
              No sessions linked to this feature
            </p>
          </div>
        ) : (
          /* Horizontal state columns */
          <div
            className={cn('flex gap-2', refreshing && 'planning-board-refreshing')}
            style={{ width: 'max-content' }}
            role="region"
            aria-label={`Agent session lane: ${totalCount} sessions`}
            aria-busy={refreshing}
          >
            {activeColumns.map((state) => (
              <LaneColumn
                key={state}
                state={state}
                cards={cardsByState.get(state) ?? []}
                compact={compact}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
