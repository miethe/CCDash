import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertCircle, ExternalLink, FileText, GitBranch, HelpCircle, LayoutGrid, Layers, Link2, RefreshCw, Settings2 } from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  PlanningAgentSessionBoard as PlanningAgentSessionBoardData,
  PlanningBoardGroup,
  PlanningAgentSessionCard,
  PlanningBoardGroupingMode,
  SessionActivityMarker,
  BoardSessionRelationship,
  SessionCorrelation,
  SessionCorrelationEvidence,
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

/** Valid grouping modes that can be set via URL. */
const VALID_GROUPING_MODES = new Set<PlanningBoardGroupingMode>([
  'state', 'feature', 'phase', 'agent', 'model',
]);

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

// ── Confidence tier styling ───────────────────────────────────────────────────

const CONFIDENCE_CONFIG = {
  high: {
    borderStyle: 'solid',
    borderColor: 'var(--brand)',
    badgeSymbol: null,
    badgeTitle: 'Explicitly linked',
    indicatorIcon: 'link' as const,
    dimCard: false,
  },
  medium: {
    borderStyle: 'solid',
    borderColor: 'color-mix(in oklab, var(--brand) 55%, var(--ink-3))',
    badgeSymbol: null,
    badgeTitle: 'Linked (medium confidence)',
    indicatorIcon: 'dot' as const,
    dimCard: false,
  },
  low: {
    borderStyle: 'dashed',
    borderColor: 'var(--warn)',
    badgeSymbol: '~',
    badgeTitle: 'Inferred link (low confidence)',
    indicatorIcon: 'tilde' as const,
    dimCard: true,
  },
  unknown: {
    borderStyle: 'dotted',
    borderColor: 'var(--ink-3)',
    badgeSymbol: '?',
    badgeTitle: 'Correlation confidence unknown',
    indicatorIcon: 'question' as const,
    dimCard: true,
  },
} as const;

// ── Evidence confidence labels ────────────────────────────────────────────────

const EVIDENCE_CONFIDENCE_LABEL: Record<SessionCorrelationEvidence['confidence'], string> = {
  high: 'high',
  medium: 'med',
  low: 'low',
  unknown: '?',
};

const EVIDENCE_CONFIDENCE_COLOR: Record<SessionCorrelationEvidence['confidence'], string> = {
  high: 'var(--ok)',
  medium: 'var(--brand)',
  low: 'var(--warn)',
  unknown: 'var(--ink-3)',
};

// ── Evidence tooltip ──────────────────────────────────────────────────────────

function EvidenceTooltip({ evidence }: { evidence: SessionCorrelationEvidence[] }) {
  return (
    <div
      className="evidence-tooltip-panel"
      role="tooltip"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      {evidence.length === 0 ? (
        <span className="evidence-tooltip-empty">No correlation evidence</span>
      ) : (
        <ul className="evidence-tooltip-list" aria-label="Correlation evidence">
          {evidence.map((ev, i) => (
            <li key={i} className="evidence-tooltip-item">
              <span className="evidence-tooltip-label">{ev.sourceLabel}</span>
              <span
                className="evidence-tooltip-conf"
                style={{ color: EVIDENCE_CONFIDENCE_COLOR[ev.confidence] }}
              >
                {EVIDENCE_CONFIDENCE_LABEL[ev.confidence]}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Confidence indicator ──────────────────────────────────────────────────────

function CorrelationIndicator({ correlation }: { correlation: SessionCorrelation }) {
  const cfg = CONFIDENCE_CONFIG[correlation.confidence];
  const isWeak = correlation.confidence === 'low' || correlation.confidence === 'unknown';

  return (
    <span className="evidence-tooltip-group" aria-label={cfg.badgeTitle}>
      {cfg.indicatorIcon === 'link' ? (
        <Link2
          size={9}
          className="flex-shrink-0"
          style={{ color: 'var(--brand)', opacity: 0.7 }}
          aria-hidden
        />
      ) : cfg.indicatorIcon === 'dot' ? (
        <span
          className="inline-block rounded-full flex-shrink-0"
          style={{
            width: 5,
            height: 5,
            background: 'color-mix(in oklab, var(--brand) 55%, var(--ink-3))',
            opacity: 0.8,
          }}
          aria-hidden
        />
      ) : cfg.indicatorIcon === 'tilde' ? (
        <span
          className="planning-mono flex-shrink-0 font-bold leading-none"
          style={{ fontSize: 9, color: 'var(--warn)', lineHeight: 1 }}
          aria-hidden
        >
          ~
        </span>
      ) : (
        <HelpCircle
          size={9}
          className="flex-shrink-0"
          style={{ color: 'var(--ink-3)' }}
          aria-hidden
        />
      )}

      {(isWeak || correlation.evidence.length > 0) && (
        <EvidenceTooltip evidence={correlation.evidence} />
      )}
    </span>
  );
}

// ── Left border accent ────────────────────────────────────────────────────────

function correlationLeftBorderStyle(
  correlation: SessionCorrelation | undefined,
): React.CSSProperties | undefined {
  if (!correlation) return undefined;
  const cfg = CONFIDENCE_CONFIG[correlation.confidence];
  return {
    borderLeftWidth: 2,
    borderLeftStyle: cfg.borderStyle as React.CSSProperties['borderLeftStyle'],
    borderLeftColor: cfg.borderColor,
  };
}

// ── Card action row ───────────────────────────────────────────────────────────

const ACTION_LINK_CLS = cn(
  'inline-flex items-center justify-center rounded p-[3px]',
  'text-[color:var(--ink-3)] transition-colors',
  'hover:bg-[color:var(--bg-3)] hover:text-[color:var(--ink-1)]',
  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
);

function CardActionRow({ card }: { card: PlanningAgentSessionCard }) {
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
      className={cn(
        'mt-1.5 flex items-center gap-0.5',
        'border-t border-[color:var(--line-1)] pt-1.5',
      )}
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
          <FileText size={11} aria-hidden />
        </Link>
      )}

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

      <span className="flex-1" aria-hidden />

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

  const correlationConf = card.correlation?.confidence;
  const isInferred = correlationConf === 'low' || correlationConf === 'unknown';
  const leftBorderStyle = correlationLeftBorderStyle(card.correlation);

  const ariaLabel = [
    card.agentName ?? 'Agent',
    card.model ? `model ${card.model}` : null,
    STATE_LABEL[card.state],
    featureSlug ? `feature ${featureSlug}` : null,
    card.startedAt ? `started ${relativeTime(card.startedAt)}` : null,
    card.correlation ? `correlation confidence ${card.correlation.confidence}` : null,
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
      key={showFlash ? flashKey : undefined}
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleMouseEnter}
      onBlur={handleMouseLeave}
      style={leftBorderStyle}
      className={cn(
        'relative rounded-[var(--radius-sm)] border',
        'cursor-pointer outline-none',
        'transition-[border-color,box-shadow,background-color,opacity] duration-200 motion-reduce:transition-none',
        'planning-card-enter',
        showFlash && 'planning-card-flash',
        compact ? 'px-2.5 py-2' : 'px-3 py-2.5',
        isInferred ? 'bg-[color:var(--bg-1)]' : 'bg-[color:var(--bg-2)]',
        !isHighlighted && !isWeakHighlighted && !isSelected && [
          'border-[color:var(--line-1)]',
          'hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)]',
          'focus-visible:border-[color:var(--brand)] focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]/30',
        ],
        isSelected && [
          'border-[color:var(--brand)]',
          'shadow-[0_0_0_2px_color-mix(in_oklab,var(--brand)_30%,transparent)]',
          'bg-[color:color-mix(in_oklab,var(--brand)_6%,var(--bg-2))]',
        ],
        isHighlighted && !isSelected && [
          'border-[color:color-mix(in_oklab,var(--brand)_55%,var(--line-1))]',
          'shadow-[0_0_0_1px_color-mix(in_oklab,var(--brand)_20%,transparent)]',
          'bg-[color:color-mix(in_oklab,var(--brand)_4%,var(--bg-2))]',
        ],
        isWeakHighlighted && !isHighlighted && !isSelected && [
          'border-dashed border-[color:color-mix(in_oklab,var(--brand)_30%,var(--line-1))]',
        ],
      )}
      aria-label={ariaLabel}
      aria-pressed={isSelected}
    >
      {/* Row 1: state dot + session ID + state label + correlation indicator + time */}
      <div className="flex items-center gap-1.5 min-w-0">
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
          className="planning-mono truncate text-[10px] text-[color:var(--ink-3)] flex-1 min-w-0"
          title={card.sessionId}
        >
          {card.sessionId.length > 12 ? `…${card.sessionId.slice(-10)}` : card.sessionId}
        </span>

        {card.correlation && (
          <CorrelationIndicator correlation={card.correlation} />
        )}

        <span
          className="flex-shrink-0 text-[9px] text-[color:var(--ink-4)] tabular-nums"
          aria-hidden="true"
        >
          {STATE_LABEL[card.state]}
        </span>
      </div>

      {/* Row 2: agent name */}
      <div
        className={cn(
          'mt-1 truncate font-medium',
          isInferred ? 'text-[color:var(--ink-2)]' : 'text-[color:var(--ink-1)]',
          compact ? 'text-[11px]' : 'text-[12px]',
        )}
        style={{ minHeight: compact ? '1rem' : '1.125rem' }}
        title={card.agentName}
      >
        {card.agentName ?? ''}
      </div>

      {/* Row 3: model chip + feature badge */}
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
              isInferred && 'opacity-75',
            )}
            title={featureSlug}
          >
            {featureSlug}
          </span>
        )}
      </div>

      {/* Row 4: phase / task hints */}
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

      {/* Row 5: token summary + time + activity marker */}
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

      {/* Context window bar */}
      <div className="mt-1.5" style={{ minHeight: '3px' }} aria-hidden="true">
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

      {/* Action row */}
      <CardActionRow card={card} />

      {/* Live state-transition region */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="mt-0.5 text-[9px] text-[color:var(--ink-4)] truncate"
        style={{ minHeight: '0.875rem' }}
      >
        {liveMsg}
      </div>

      {/* Relationship badge */}
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
  relationBadgeMap: Map<string, BoardSessionRelationship['relationType']>;
  onCardHover: (sessionId: string | null) => void;
  onCardSelect: (sessionId: string) => void;
  /** Whether this column's entity (feature/phase) is highlighted via a relationship. */
  isColumnHighlighted: boolean;
  /** Whether this column is highlighted via the URL ?highlight= param. */
  isUrlHighlighted: boolean;
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
  isUrlHighlighted,
}: BoardColumnProps) {
  const lowerFilter = filterText.toLowerCase();
  const visible = filterText
    ? group.cards.filter(
        (c) =>
          c.sessionId.toLowerCase().includes(lowerFilter) ||
          (c.agentName ?? '').toLowerCase().includes(lowerFilter),
      )
    : group.cards;

  // Feature-grouped columns get a clickable header link to the planning feature modal.
  const featureHeaderHref =
    group.groupType === 'feature'
      ? planningRouteFeatureModalHref(group.groupKey, 'overview')
      : null;

  const isHighlighted = isColumnHighlighted || isUrlHighlighted;

  return (
    <div
      className={cn(
        'flex min-w-[220px] max-w-[280px] flex-shrink-0 flex-col',
        'rounded-[var(--radius)] border bg-[color:var(--bg-1)]',
        'transition-[border-color,box-shadow] duration-200 motion-reduce:transition-none',
        isHighlighted
          ? 'border-[color:color-mix(in_oklab,var(--brand)_50%,var(--line-1))] shadow-[0_0_0_1px_color-mix(in_oklab,var(--brand)_15%,transparent)]'
          : 'border-[color:var(--line-1)]',
        isUrlHighlighted && 'shadow-[0_0_0_2px_color-mix(in_oklab,var(--brand)_25%,transparent)]',
      )}
    >
      <div
        className={cn(
          'flex items-center justify-between border-b',
          'transition-[border-color,background-color] duration-200 motion-reduce:transition-none',
          compact ? 'px-3 py-1.5' : 'px-3 py-2',
          isHighlighted
            ? 'border-[color:color-mix(in_oklab,var(--brand)_30%,var(--line-1))] bg-[color:color-mix(in_oklab,var(--brand)_5%,var(--bg-1))]'
            : 'border-[color:var(--line-1)]',
        )}
      >
        {/* Column title — clickable link when grouped by feature */}
        {featureHeaderHref ? (
          <Link
            to={featureHeaderHref}
            className={cn(
              'group flex min-w-0 flex-1 items-center gap-1',
              'truncate text-[11px] font-medium text-[color:var(--ink-1)]',
              'rounded transition-colors',
              'hover:text-[color:var(--brand)]',
              'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
            )}
            aria-label={`Open feature ${group.groupLabel} in planning view`}
            title={`View feature: ${group.groupLabel}`}
            onClick={(e) => e.stopPropagation()}
          >
            <span className="truncate">{group.groupLabel}</span>
            <ExternalLink
              size={9}
              aria-hidden
              className="flex-shrink-0 opacity-0 transition-opacity group-hover:opacity-50"
            />
          </Link>
        ) : (
          <span className="truncate text-[11px] font-medium text-[color:var(--ink-1)]">
            {group.groupLabel}
          </span>
        )}

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

// ── URL state helpers ─────────────────────────────────────────────────────────

/**
 * Reads the grouping mode from URL search params.
 * Falls back to 'state' when absent or invalid.
 */
function readGroupingFromParams(params: URLSearchParams): PlanningBoardGroupingMode {
  const raw = params.get('groupBy');
  if (raw && VALID_GROUPING_MODES.has(raw as PlanningBoardGroupingMode)) {
    return raw as PlanningBoardGroupingMode;
  }
  return 'state';
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

  // ── URL-driven grouping + highlight ──────────────────────────────────────────
  const [searchParams, setSearchParams] = useSearchParams();

  // Grouping is read from and written to the URL so the state is bookmarkable.
  const grouping = readGroupingFromParams(searchParams);

  // ?highlight=<featureId|groupKey> pre-selects a column when navigating from the feature lane.
  const urlHighlightId = searchParams.get('highlight') ?? null;

  const [filterText, setFilterText] = useState('');
  const [fetchState, setFetchState] = useState<FetchState>({ phase: 'idle' });
  const [refreshing, setRefreshing] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  // ── Relationship highlight state ────────────────────────────────────────────
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const sessionsRef = useRef(sessions);
  const prevSessionsRef = useRef(sessions);

  const load = useCallback(
    async (opts: { forceRefresh?: boolean } = {}) => {
      if (!activeProject?.id) {
        setFetchState({ phase: 'idle' });
        return;
      }
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

  useEffect(() => {
    sessionsRef.current = sessions;
  });

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (prevSessionsRef.current === sessions) return;
    prevSessionsRef.current = sessions;
    void load();
  }, [sessions, load]);

  const handleGroupingChange = useCallback(
    (mode: PlanningBoardGroupingMode) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('groupBy', mode);
          // Clear highlight when user manually changes grouping — no longer meaningful.
          next.delete('highlight');
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const handleManualRefresh = useCallback(() => {
    void load({ forceRefresh: true });
  }, [load]);

  // ── Relationship highlight derivation ────────────────────────────────────────

  const activeSessionId = selectedSessionId ?? hoveredSessionId;

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

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedSessionId(null);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const isGroupHighlighted = useCallback(
    (group: PlanningBoardGroup): boolean => {
      if (!activeSessionId) return false;
      if (group.groupType === 'feature' && highlightedFeatureIds.has(group.groupKey)) return true;
      if (group.groupType === 'phase' && highlightedPhaseKeys.has(group.groupKey)) return true;
      return false;
    },
    [activeSessionId, highlightedFeatureIds, highlightedPhaseKeys],
  );

  /** Returns true when the column's groupKey matches the URL ?highlight= param. */
  const isGroupUrlHighlighted = useCallback(
    (group: PlanningBoardGroup): boolean => {
      if (!urlHighlightId) return false;
      return group.groupKey === urlHighlightId;
    },
    [urlHighlightId],
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

        {fetchedAt && !refreshing && (
          <StaleIndicator fetchedAt={fetchedAt} />
        )}

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
                isUrlHighlighted={isGroupUrlHighlighted(group)}
              />
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}
