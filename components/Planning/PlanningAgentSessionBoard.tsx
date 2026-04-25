import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, FileText, GitBranch, LayoutGrid, Layers, RefreshCw, Settings2 } from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  PlanningAgentSessionBoard as PlanningAgentSessionBoardData,
  PlanningBoardGroup,
  PlanningAgentSessionCard,
  PlanningBoardGroupingMode,
  SessionActivityMarker,
  BoardSessionRelationship,
} from '@/types';
import { getSessionBoard } from '@/services/planning';
import { planningRouteFeatureModalHref } from '@/services/planningRoutes';
import { useData } from '@/contexts/DataContext';
import { usePlanningRoute } from './PlanningRouteLayout';
import { PlanningBoardToolbar } from './PlanningBoardToolbar';
import { Panel, Dot } from './primitives';

// ── Constants ─────────────────────────────────────────────────────────────────

/** How old (in ms) board data must be before the stale indicator appears. */
const BOARD_STALE_TTL_MS = 60_000;

// ── State dot colours and labels keyed by card state ──────────────────────────

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

// ── Relative time helper ──────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const secs = Math.floor((Date.now() - d.getTime()) / 1000);
  if (secs < 5) return 'just now';
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/** Same as relativeTime but accepts a Date (used for local fetchedAt tracking). */
function relativeDate(d: Date): string {
  return relativeTime(d.toISOString());
}

// ── Compact token display ─────────────────────────────────────────────────────

function fmtTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

// ── Activity marker icon ──────────────────────────────────────────────────────

const MARKER_SYMBOL: Record<SessionActivityMarker['markerType'], string> = {
  tool_call: '⚡',
  file_edit: '✎',
  command: '$',
  error: '✕',
  completion: '✓',
};

// ── Relationship kind labels ──────────────────────────────────────────────────

/** Human-readable label for each relationship kind. */
const RELATION_LABEL: Record<BoardSessionRelationship['relationType'], string> = {
  parent: 'parent',
  root: 'root',
  sibling: 'sibling',
  child: 'child',
};

// ── Card action row ───────────────────────────────────────────────────────────

/**
 * Shared CSS class string for compact icon-link buttons in the card action row.
 * Each link uses react-router-dom's `<Link>` for HashRouter-compatible navigation.
 */
const ACTION_LINK_CLS = cn(
  'inline-flex items-center justify-center rounded p-[3px]',
  'text-[color:var(--ink-3)] transition-colors',
  'hover:bg-[color:var(--bg-3)] hover:text-[color:var(--ink-1)]',
  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
);

/**
 * Compact row of navigational icon-links rendered at the bottom of each
 * SessionCard. Links are only rendered when the relevant data is present;
 * missing data means the link is absent, not disabled.
 *
 * Clicks call `e.stopPropagation()` so they don't trigger the card's own
 * `role="button"` selection handler.
 *
 * Links (in order):
 *   1. Transcript  → /sessions?session=<sessionId>
 *   2. Feature     → /planning?feature=<featureId>&modal=feature (modal-first per planning-routes)
 *   3. Phase ops   → same planning modal, with phase + panel params appended
 *   4. Parent/root → /sessions?session=<ancestorSessionId>  (right-aligned)
 */
function CardActionRow({ card }: { card: PlanningAgentSessionCard }) {
  const featureId = card.correlation?.featureId;
  const phaseNumber = card.correlation?.phaseNumber;

  // Find the first parent or root relationship for the ancestor link.
  const ancestorRel = card.relationships.find(
    (rel) => rel.relationType === 'parent' || rel.relationType === 'root',
  );

  // Phase operations: requires both featureId and phaseNumber. The panel is
  // opened as an overlay within the planning page via query-param routing.
  const phaseOpsHref =
    featureId != null && phaseNumber != null
      ? `${planningRouteFeatureModalHref(featureId, 'overview')}&phase=${encodeURIComponent(phaseNumber)}&panel=phase-ops`
      : null;

  // Bail out entirely if nothing will render — keeps cards compact when there
  // is no navigable context attached to this session.
  const hasAnyLink = Boolean(card.sessionId || featureId || phaseOpsHref || ancestorRel);
  if (!hasAnyLink) return null;

  // Prevent clicks/keyboard events from bubbling to the card's role="button".
  function stopProp(e: React.MouseEvent | React.KeyboardEvent) {
    e.stopPropagation();
  }

  return (
    <div
      className={cn(
        'mt-1.5 flex items-center gap-0.5',
        'border-t border-[color:var(--line-1)] pt-1.5',
      )}
      aria-label="Session navigation links"
      onClick={stopProp}
      onKeyDown={stopProp}
    >
      {/* 1. Transcript — always present when sessionId exists */}
      {card.sessionId && (
        <Link
          to={`/sessions?session=${encodeURIComponent(card.sessionId)}`}
          className={ACTION_LINK_CLS}
          aria-label="View session transcript"
          title="View session transcript"
        >
          <FileText size={11} aria-hidden />
        </Link>
      )}

      {/* 2. Feature planning context — requires correlation.featureId */}
      {featureId && (
        <Link
          to={planningRouteFeatureModalHref(featureId, 'overview')}
          className={ACTION_LINK_CLS}
          aria-label={`Open feature${card.correlation?.featureName ? ` ${card.correlation.featureName}` : ''} in planning view`}
          title={`Feature: ${card.correlation?.featureName ?? featureId}`}
        >
          <Layers size={11} aria-hidden />
        </Link>
      )}

      {/* 3. Phase operations — requires both featureId and phaseNumber */}
      {phaseOpsHref && (
        <Link
          to={phaseOpsHref}
          className={ACTION_LINK_CLS}
          aria-label={`Open phase ${phaseNumber} operations panel`}
          title={`Phase ${phaseNumber} operations`}
        >
          <Settings2 size={11} aria-hidden />
        </Link>
      )}

      {/* Push ancestor link to the right */}
      <span className="flex-1" aria-hidden />

      {/* 4. Parent / root session link */}
      {ancestorRel && (
        <Link
          to={`/sessions?session=${encodeURIComponent(ancestorRel.relatedSessionId)}`}
          className={ACTION_LINK_CLS}
          aria-label={`View ${ancestorRel.relationType} session${ancestorRel.agentName ? ` (${ancestorRel.agentName})` : ''}`}
          title={`${ancestorRel.relationType === 'root' ? 'Root' : 'Parent'} session: ${ancestorRel.relatedSessionId}${ancestorRel.agentName ? ` — ${ancestorRel.agentName}` : ''}`}
        >
          <GitBranch size={11} aria-hidden />
        </Link>
      )}
    </div>
  );
}

// ── Rich session card ─────────────────────────────────────────────────────────

interface SessionCardProps {
  card: PlanningAgentSessionCard;
  compact: boolean;
  isHighlighted: boolean;
  isWeakHighlighted: boolean;
  isSelected: boolean;
  /** The relationship badge to show on this card (sent from the hovered/selected card). */
  relationBadge?: BoardSessionRelationship['relationType'];
  onHover: (sessionId: string | null) => void;
  onSelect: (sessionId: string) => void;
}

function SessionCard({
  card,
  compact,
  isHighlighted,
  isWeakHighlighted,
  isSelected,
  relationBadge,
  onHover,
  onSelect,
}: SessionCardProps) {
  const prevStateRef = useRef(card.state);
  const [liveMsg, setLiveMsg] = useState('');
  // flashKey increments on each state change to restart the CSS animation via key prop.
  const [flashKey, setFlashKey] = useState(0);
  const [showFlash, setShowFlash] = useState(false);

  useEffect(() => {
    if (prevStateRef.current !== card.state) {
      setLiveMsg(`State changed to ${STATE_LABEL[card.state]}`);
      prevStateRef.current = card.state;
      setFlashKey((k) => k + 1);
      setShowFlash(true);
      const t = setTimeout(() => {
        setLiveMsg('');
        setShowFlash(false);
      }, 4000);
      return () => clearTimeout(t);
    }
  }, [card.state]);

  const dotColor = STATE_DOT_COLOR[card.state] ?? 'var(--ink-4)';
  const isActive = card.state === 'running' || card.state === 'thinking';

  const featureSlug = card.correlation?.featureId ?? card.correlation?.featureName;
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
    featureSlug ? `feature ${featureSlug}` : null,
    card.startedAt ? `started ${relativeTime(card.startedAt)}` : null,
    isSelected ? 'selected' : null,
    isHighlighted ? 'related session' : null,
  ]
    .filter(Boolean)
    .join(', ');

  const handleMouseEnter = useCallback(() => onHover(card.sessionId), [card.sessionId, onHover]);
  const handleMouseLeave = useCallback(() => onHover(null), [onHover]);
  const handleClick = useCallback(() => onSelect(card.sessionId), [card.sessionId, onSelect]);
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect(card.sessionId);
      }
    },
    [card.sessionId, onSelect],
  );

  return (
    <div
      // flashKey forces a remount of the animation class when state changes.
      key={showFlash ? flashKey : undefined}
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleMouseEnter}
      onBlur={handleMouseLeave}
      className={cn(
        'relative rounded-[var(--radius-sm)] border',
        'bg-[color:var(--bg-2)] cursor-pointer outline-none',
        'transition-[border-color,box-shadow,background-color] duration-200 motion-reduce:transition-none',
        // Entry fade-in: cards animate in on mount; reduced-motion users get instant display.
        'planning-card-enter',
        // State-transition flash: briefly highlights card border/bg when state changes.
        showFlash && 'planning-card-flash',
        compact ? 'px-2.5 py-2' : 'px-3 py-2.5',
        // Default (no highlight state)
        !isHighlighted && !isWeakHighlighted && !isSelected && [
          'border-[color:var(--line-1)]',
          'hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)]',
          'focus-visible:border-[color:var(--brand)] focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]/30',
        ],
        // Selected — strongest ring
        isSelected && [
          'border-[color:var(--brand)]',
          'shadow-[0_0_0_2px_color-mix(in_oklab,var(--brand)_30%,transparent)]',
          'bg-[color:color-mix(in_oklab,var(--brand)_6%,var(--bg-2))]',
        ],
        // Strong highlight (related, not selected)
        isHighlighted && !isSelected && [
          'border-[color:color-mix(in_oklab,var(--brand)_55%,var(--line-1))]',
          'shadow-[0_0_0_1px_color-mix(in_oklab,var(--brand)_20%,transparent)]',
          'bg-[color:color-mix(in_oklab,var(--brand)_4%,var(--bg-2))]',
        ],
        // Weak highlight (low-confidence relationship)
        isWeakHighlighted && !isHighlighted && !isSelected && [
          'border-dashed border-[color:color-mix(in_oklab,var(--brand)_30%,var(--line-1))]',
        ],
      )}
      aria-label={ariaLabel}
      aria-pressed={isSelected}
    >
      {/* Row 1: state dot + session ID + state label + time */}
      <div className="flex items-center gap-1.5 min-w-0">
        <Dot
          style={{
            background: dotColor,
            flexShrink: 0,
            // Used by the planning-dot-live CSS animation for the ring color.
            '--dot-color': dotColor,
          } as React.CSSProperties}
          aria-label={card.state}
          className={isActive ? 'planning-dot-live' : undefined}
        />
        <span
          className="planning-mono truncate text-[10px] text-[color:var(--ink-3)] flex-1 min-w-0"
          title={card.sessionId}
        >
          {card.sessionId.length > 12 ? `…${card.sessionId.slice(-10)}` : card.sessionId}
        </span>
        <span
          className="flex-shrink-0 text-[9px] text-[color:var(--ink-4)] tabular-nums"
          aria-hidden="true"
        >
          {STATE_LABEL[card.state]}
        </span>
      </div>

      {/* Row 2: agent name (fixed slot — always rendered to avoid reflow) */}
      <div
        className={cn(
          'mt-1 truncate font-medium text-[color:var(--ink-1)]',
          compact ? 'text-[11px]' : 'text-[12px]',
        )}
        style={{ minHeight: compact ? '1rem' : '1.125rem' }}
        title={card.agentName}
      >
        {card.agentName ?? ''}
      </div>

      {/* Row 3: model chip + feature badge (fixed slot) */}
      <div
        className="mt-1.5 flex items-center gap-1 flex-wrap"
        style={{ minHeight: '1.25rem' }}
      >
        {card.model && (
          <span
            className={cn(
              'planning-mono inline-flex items-center rounded px-1.5 py-0.5',
              'border border-[color:var(--line-2)] bg-[color:var(--bg-3)]',
              'text-[9px] text-[color:var(--ink-3)] leading-none flex-shrink-0',
            )}
          >
            {card.model}
          </span>
        )}
        {featureSlug && (
          <span
            className={cn(
              'inline-flex items-center rounded px-1.5 py-0.5',
              'border border-[color:color-mix(in_oklab,var(--brand)_40%,var(--line-1))]',
              'bg-[color:color-mix(in_oklab,var(--brand)_8%,transparent)]',
              'text-[9px] text-[color:var(--brand)] leading-none truncate max-w-[100px]',
            )}
            title={featureSlug}
          >
            {featureSlug}
          </span>
        )}
      </div>

      {/* Row 4: phase / task hints (fixed slot) */}
      <div
        className="mt-1 flex items-center gap-1 flex-wrap"
        style={{ minHeight: '1.125rem' }}
      >
        {phaseHint && (
          <span
            className="text-[9px] text-[color:var(--ink-3)] truncate max-w-[120px]"
            title={phaseHint}
          >
            {phaseHint}
          </span>
        )}
        {taskHint && phaseHint && (
          <span className="text-[9px] text-[color:var(--ink-4)]" aria-hidden>·</span>
        )}
        {taskHint && (
          <span
            className="text-[9px] text-[color:var(--ink-3)] truncate max-w-[100px]"
            title={typeof taskHint === 'string' ? taskHint : undefined}
          >
            {taskHint}
          </span>
        )}
      </div>

      {/* Row 5: token summary + time + activity marker (fixed slot) */}
      <div
        className="mt-1.5 flex items-center gap-2 min-w-0"
        style={{ minHeight: '1rem' }}
      >
        {card.tokenSummary ? (
          <span
            className="planning-mono text-[9px] text-[color:var(--ink-4)] flex-shrink-0"
            title={`${card.tokenSummary.tokensIn} in / ${card.tokenSummary.tokensOut} out`}
          >
            {fmtTokens(card.tokenSummary.tokensIn)}↑{' '}
            {fmtTokens(card.tokenSummary.tokensOut)}↓
          </span>
        ) : (
          <span className="flex-shrink-0 text-[9px] text-transparent select-none" aria-hidden>
            — —
          </span>
        )}

        <span className="flex-1" />

        {card.startedAt && (
          <span className="planning-mono text-[9px] text-[color:var(--ink-4)] flex-shrink-0">
            {relativeTime(card.startedAt)}
          </span>
        )}

        {latestMarker && (
          <span
            className="flex-shrink-0 text-[10px] leading-none"
            title={`${latestMarker.markerType}: ${latestMarker.label}`}
            aria-label={latestMarker.label}
          >
            {MARKER_SYMBOL[latestMarker.markerType] ?? '·'}
          </span>
        )}
      </div>

      {/* Context window bar (fixed slot — rendered regardless, hidden when no data) */}
      <div
        className="mt-1.5"
        style={{ minHeight: '3px' }}
        aria-hidden="true"
      >
        {card.tokenSummary?.contextWindowPct != null && (
          <div
            className="h-[2px] w-full rounded-full overflow-hidden bg-[color:var(--bg-3)]"
            title={`Context window: ${Math.round(card.tokenSummary.contextWindowPct * 100)}%`}
          >
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
      </div>

      {/* Action row: navigational links (omitted entirely when no data is available) */}
      <CardActionRow card={card} />

      {/* Live state-transition region — fixed height, invisible when idle */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="mt-0.5 text-[9px] text-[color:var(--ink-4)] truncate"
        style={{ minHeight: '0.875rem' }}
      >
        {liveMsg}
      </div>

      {/* Relationship badge — appears on related cards when hovered/selected card has relationships */}
      {relationBadge && (
        <div
          className={cn(
            'absolute top-1.5 right-1.5',
            'inline-flex items-center rounded px-1 py-0.5',
            'border border-[color:color-mix(in_oklab,var(--brand)_40%,var(--line-1))]',
            'bg-[color:color-mix(in_oklab,var(--brand)_12%,var(--bg-2))]',
            'text-[8px] leading-none text-[color:var(--brand)] font-medium',
            'transition-opacity duration-200 motion-reduce:transition-none',
          )}
          aria-label={`Relationship: ${RELATION_LABEL[relationBadge]}`}
        >
          {RELATION_LABEL[relationBadge]}
        </div>
      )}
    </div>
  );
}

// ── Board column ──────────────────────────────────────────────────────────────

interface BoardColumnProps {
  group: PlanningBoardGroup;
  filterText: string;
  compact: boolean;
  highlightedSessionIds: Set<string>;
  weakHighlightedSessionIds: Set<string>;
  selectedSessionId: string | null;
  /** Maps session ID → relationship kind for badge display. */
  relationBadgeMap: Map<string, BoardSessionRelationship['relationType']>;
  onCardHover: (sessionId: string | null) => void;
  onCardSelect: (sessionId: string) => void;
  /** Whether this column's entity (feature/phase) is highlighted via a relationship. */
  isColumnHighlighted: boolean;
}

function BoardColumn({
  group,
  filterText,
  compact,
  highlightedSessionIds,
  weakHighlightedSessionIds,
  selectedSessionId,
  relationBadgeMap,
  onCardHover,
  onCardSelect,
  isColumnHighlighted,
}: BoardColumnProps) {
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
        'rounded-[var(--radius)] border bg-[color:var(--bg-1)]',
        'transition-[border-color,box-shadow] duration-200 motion-reduce:transition-none',
        isColumnHighlighted
          ? 'border-[color:color-mix(in_oklab,var(--brand)_50%,var(--line-1))] shadow-[0_0_0_1px_color-mix(in_oklab,var(--brand)_15%,transparent)]'
          : 'border-[color:var(--line-1)]',
      )}
    >
      <div
        className={cn(
          'flex items-center justify-between border-b',
          'transition-[border-color,background-color] duration-200 motion-reduce:transition-none',
          compact ? 'px-3 py-1.5' : 'px-3 py-2',
          isColumnHighlighted
            ? 'border-[color:color-mix(in_oklab,var(--brand)_30%,var(--line-1))] bg-[color:color-mix(in_oklab,var(--brand)_5%,var(--bg-1))]'
            : 'border-[color:var(--line-1)]',
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
            <SessionCard
              key={card.sessionId}
              card={card}
              compact={compact}
              isHighlighted={highlightedSessionIds.has(card.sessionId)}
              isWeakHighlighted={weakHighlightedSessionIds.has(card.sessionId)}
              isSelected={selectedSessionId === card.sessionId}
              relationBadge={relationBadgeMap.get(card.sessionId)}
              onHover={onCardHover}
              onSelect={onCardSelect}
            />
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

// ── Stale indicator ───────────────────────────────────────────────────────────

/**
 * Tiny muted timestamp shown when board data is older than BOARD_STALE_TTL_MS.
 * Ticks every 15 seconds so the relative label stays fresh without thrashing.
 */
function StaleIndicator({ fetchedAt }: { fetchedAt: Date }) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 15_000);
    return () => clearInterval(id);
  }, []);

  const age = Date.now() - fetchedAt.getTime();
  if (age < BOARD_STALE_TTL_MS) return null;

  return (
    <span
      className="planning-mono text-[9.5px] text-[color:var(--ink-4)] tabular-nums"
      title={`Board data last fetched at ${fetchedAt.toLocaleTimeString()}`}
      aria-label={`Board data is stale, last fetched ${relativeDate(fetchedAt)}`}
    >
      stale · {relativeDate(fetchedAt)}
    </span>
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
  const { activeProject, sessions } = useData();
  const { density } = usePlanningRoute();
  const compact = density === 'compact';

  const [grouping, setGrouping] = useState<PlanningBoardGroupingMode>('state');
  const [filterText, setFilterText] = useState('');
  const [fetchState, setFetchState] = useState<FetchState>({ phase: 'idle' });
  // Whether a background refresh is in-flight (distinct from the initial load).
  const [refreshing, setRefreshing] = useState(false);
  // Timestamp of the last successful board fetch, for the stale indicator.
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  // ── Relationship highlight state ────────────────────────────────────────────
  /** Session ID currently hovered (or null). */
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null);
  /** Session ID locked by click (persists until another click or Escape). */
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  // Track the sessions reference to detect upstream poll ticks without capturing
  // the full array in closure state (avoids spurious re-renders on identity-stable arrays).
  const sessionsRef = useRef(sessions);
  const prevSessionsRef = useRef(sessions);

  const load = useCallback(
    async (opts: { forceRefresh?: boolean } = {}) => {
      if (!activeProject?.id) {
        setFetchState({ phase: 'idle' });
        return;
      }
      // Background refresh: keep existing board visible, show spinner instead.
      const isBackgroundRefresh = fetchState.phase === 'ready' && !opts.forceRefresh;
      const isManualRefresh = fetchState.phase === 'ready' && opts.forceRefresh;

      if (isBackgroundRefresh || isManualRefresh) {
        setRefreshing(true);
      } else {
        setFetchState((prev) => (prev.phase === 'ready' ? prev : { phase: 'loading' }));
      }

      try {
        const board = await getSessionBoard(activeProject.id, grouping, opts);
        setFetchState({ phase: 'ready', board });
        setFetchedAt(new Date());
      } catch (err) {
        // On background refresh failure, preserve existing board — don't replace with error.
        if (isBackgroundRefresh || isManualRefresh) {
          console.warn('[PlanningAgentSessionBoard] Background refresh failed:', err);
        } else {
          setFetchState({
            phase: 'error',
            message: err instanceof Error ? err.message : 'Failed to load session board.',
          });
        }
      } finally {
        setRefreshing(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeProject?.id, grouping],
  );

  // Keep sessionsRef in sync so the effect below can read current without
  // being listed as a dependency (avoids retriggering load on every render).
  useEffect(() => {
    sessionsRef.current = sessions;
  });

  // Initial load and grouping/project change.
  useEffect(() => {
    void load();
  }, [load]);

  // Upstream poll tick: when the sessions array reference changes (AppRuntimeContext
  // refreshes every 30 s), re-fetch the board without force so the SWR cache in
  // getSessionBoard can deduplicate concurrent requests.
  useEffect(() => {
    if (prevSessionsRef.current === sessions) return;
    prevSessionsRef.current = sessions;
    // Only trigger a background refresh once we've already loaded once.
    void load();
  }, [sessions, load]);

  const handleGroupingChange = useCallback((mode: PlanningBoardGroupingMode) => {
    setGrouping(mode);
  }, []);

  const handleManualRefresh = useCallback(() => {
    void load({ forceRefresh: true });
  }, [load]);

  // ── Relationship highlight derivation ────────────────────────────────────────

  /** Selected takes priority over hovered for driving the highlight graph. */
  const activeSessionId = selectedSessionId ?? hoveredSessionId;

  /** O(1) card lookup rebuilt only when board data changes. */
  const cardBySessionId = useMemo<Map<string, PlanningAgentSessionCard>>(() => {
    if (fetchState.phase !== 'ready') return new Map();
    const map = new Map<string, PlanningAgentSessionCard>();
    for (const group of fetchState.board.groups) {
      for (const card of group.cards) {
        map.set(card.sessionId, card);
      }
    }
    return map;
  }, [fetchState]);

  /**
   * Derive highlight sets from the active card's relationships.
   * BoardSessionRelationship has no numeric confidence — 'sibling' is treated
   * as weak (dashed border), the rest as strong.
   */
  const {
    highlightedSessionIds,
    weakHighlightedSessionIds,
    relationBadgeMap,
    highlightedFeatureIds,
    highlightedPhaseKeys,
  } = useMemo(() => {
    const highlighted = new Set<string>();
    const weakHighlighted = new Set<string>();
    const badgeMap = new Map<string, BoardSessionRelationship['relationType']>();
    const featureIds = new Set<string>();
    const phaseKeys = new Set<string>();

    const activeCard = activeSessionId ? cardBySessionId.get(activeSessionId) : undefined;
    if (activeCard) {
      for (const rel of activeCard.relationships) {
        const isWeak = rel.relationType === 'sibling';
        if (isWeak) {
          weakHighlighted.add(rel.relatedSessionId);
        } else {
          highlighted.add(rel.relatedSessionId);
        }
        if (!badgeMap.has(rel.relatedSessionId)) {
          badgeMap.set(rel.relatedSessionId, rel.relationType);
        }
      }
      if (activeCard.correlation?.featureId) {
        featureIds.add(activeCard.correlation.featureId);
      }
      if (activeCard.correlation?.phaseNumber != null) {
        phaseKeys.add(String(activeCard.correlation.phaseNumber));
      }
    }

    return {
      highlightedSessionIds: highlighted,
      weakHighlightedSessionIds: weakHighlighted,
      relationBadgeMap: badgeMap,
      highlightedFeatureIds: featureIds,
      highlightedPhaseKeys: phaseKeys,
    };
  }, [activeSessionId, cardBySessionId]);

  const handleCardHover = useCallback((sessionId: string | null) => {
    setHoveredSessionId(sessionId);
  }, []);

  const handleCardSelect = useCallback((sessionId: string) => {
    setSelectedSessionId((prev) => (prev === sessionId ? null : sessionId));
  }, []);

  // Escape clears the persistent selection.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedSessionId(null);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  /** Returns true when a column's entity key matches the active card's correlation. */
  const isGroupHighlighted = useCallback(
    (group: PlanningBoardGroup): boolean => {
      if (!activeSessionId) return false;
      if (group.groupType === 'feature' && highlightedFeatureIds.has(group.groupKey)) return true;
      if (group.groupType === 'phase' && highlightedPhaseKeys.has(group.groupKey)) return true;
      return false;
    },
    [activeSessionId, highlightedFeatureIds, highlightedPhaseKeys],
  );

  const isInitialLoad = fetchState.phase === 'loading' || fetchState.phase === 'idle';

  return (
    <Panel className={cn('p-4', className)}>
      {/* Toolbar row with refresh button appended */}
      <div className="flex items-center gap-2 mb-3">
        <PlanningBoardToolbar
          grouping={grouping}
          onGroupingChange={handleGroupingChange}
          filterText={filterText}
          onFilterTextChange={setFilterText}
          className="flex-1 min-w-0"
        />

        {/* Stale indicator */}
        {fetchedAt && !refreshing && (
          <StaleIndicator fetchedAt={fetchedAt} />
        )}

        {/* Manual refresh button */}
        <button
          type="button"
          onClick={handleManualRefresh}
          disabled={refreshing || isInitialLoad}
          aria-label="Refresh session board"
          title="Refresh session board"
          className={cn(
            'flex flex-shrink-0 items-center justify-center',
            'rounded-[var(--radius-sm)] border border-[color:var(--line-1)]',
            'bg-[color:var(--bg-1)] p-1.5 text-[color:var(--ink-3)]',
            'transition-colors hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-2)] hover:text-[color:var(--ink-1)]',
            'disabled:cursor-not-allowed disabled:opacity-40',
          )}
        >
          <RefreshCw
            size={12}
            aria-hidden
            className={refreshing ? 'animate-spin' : undefined}
          />
        </button>
      </div>

      {isInitialLoad ? (
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
          className={cn('overflow-x-auto pb-2', refreshing && 'planning-board-refreshing')}
          role="region"
          aria-label="Agent session board"
          aria-busy={refreshing}
        >
          <div className="flex gap-3" style={{ width: 'max-content' }}>
            {fetchState.board.groups.map((group) => (
              <BoardColumn
                key={group.groupKey}
                group={group}
                filterText={filterText}
                compact={compact}
                highlightedSessionIds={highlightedSessionIds}
                weakHighlightedSessionIds={weakHighlightedSessionIds}
                selectedSessionId={selectedSessionId}
                relationBadgeMap={relationBadgeMap}
                onCardHover={handleCardHover}
                onCardSelect={handleCardSelect}
                isColumnHighlighted={isGroupHighlighted(group)}
              />
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}
