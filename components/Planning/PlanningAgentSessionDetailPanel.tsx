/**
 * PASB-302: PlanningAgentSessionDetailPanel
 *
 * An inline side/below-panel that appears when a card is selected on the
 * Planning Agent Session Board. Reuses content patterns from AgentDetailModal
 * without the modal overlay semantics — board interaction remains live.
 *
 * Sections:
 *   1. Session header — agent name, model, state dot, session ID
 *   2. Lineage tree  — parent → current → children from card.relationships
 *   3. Feature correlation — featureName, phase, task, batch from card.correlation
 *   4. Evidence list — sourceType, sourceLabel, confidence from card.correlation?.evidence
 *   5. Token context — tokensIn/Out + context window bar from card.tokenSummary
 *   6. Activity timeline — chronological markers with icons from card.activityMarkers
 *   7. Quick actions — transcript + feature planning links (CardActionRow patterns)
 *   8. Close button that calls onClose (deselects card)
 *
 * Accessibility:
 *   - role="complementary" + aria-label, NOT role="dialog" (avoids modal semantics)
 *   - Escape key handled by the board already; this component does NOT re-register it
 *   - Close button is the initial focus target when the panel mounts
 *   - Keyboard navigation stays within the board — no focus trap
 */

import { useEffect, useRef, type JSX } from 'react';
import { Link } from 'react-router-dom';
import {
  X,
  FileText,
  Layers,
  Settings2,
  GitBranch,
  GitMerge,
  GitCommit,
  ArrowUpRight,
  Zap,
  FilePen,
  Terminal,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Link2,
  BarChart2,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  PlanningAgentSessionCard,
  BoardSessionRelationship,
  SessionCorrelationEvidence,
  SessionActivityMarker,
} from '@/types';
import { planningRouteFeatureModalHref } from '@/services/planningRoutes';
import { Dot } from './primitives';

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

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

// ── Constants ──────────────────────────────────────────────────────────────────

const STATE_DOT_COLOR: Record<PlanningAgentSessionCard['state'], string> = {
  running: 'var(--ok)',
  thinking: 'var(--brand)',
  completed: 'var(--ink-3)',
  failed: 'var(--err)',
  cancelled: 'var(--warn)',
  unknown: 'var(--ink-4)',
};

const STATE_LABEL: Record<PlanningAgentSessionCard['state'], string> = {
  running: 'Running',
  thinking: 'Thinking',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  unknown: 'Unknown',
};

const EVIDENCE_CONFIDENCE_COLOR: Record<SessionCorrelationEvidence['confidence'], string> = {
  high: 'var(--ok)',
  medium: 'var(--brand)',
  low: 'var(--warn)',
  unknown: 'var(--ink-4)',
};

const EVIDENCE_CONFIDENCE_LABEL: Record<SessionCorrelationEvidence['confidence'], string> = {
  high: 'high',
  medium: 'med',
  low: 'low',
  unknown: '?',
};

const MARKER_ICON: Record<SessionActivityMarker['markerType'], JSX.Element> = {
  tool_call: <Zap size={10} aria-hidden />,
  file_edit: <FilePen size={10} aria-hidden />,
  command: <Terminal size={10} aria-hidden />,
  error: <AlertTriangle size={10} aria-hidden />,
  completion: <CheckCircle2 size={10} aria-hidden />,
};

const MARKER_COLOR: Record<SessionActivityMarker['markerType'], string> = {
  tool_call: 'var(--brand)',
  file_edit: 'var(--info, #60a5fa)',
  command: 'var(--ink-3)',
  error: 'var(--err)',
  completion: 'var(--ok)',
};

const RELATION_LABEL: Record<BoardSessionRelationship['relationType'], string> = {
  parent: 'parent',
  root: 'root',
  sibling: 'sibling',
  child: 'child',
};

const RELATION_ICON: Record<BoardSessionRelationship['relationType'], JSX.Element> = {
  parent: <GitBranch size={10} aria-hidden />,
  root: <GitMerge size={10} aria-hidden />,
  sibling: <GitCommit size={10} aria-hidden />,
  child: <ArrowUpRight size={10} aria-hidden />,
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="planning-mono mb-1.5 text-[9.5px] uppercase tracking-widest"
      style={{ color: 'var(--ink-4)' }}
    >
      {children}
    </p>
  );
}

function Divider() {
  return (
    <div
      className="w-full"
      style={{ height: 1, background: 'var(--line-1, #2d3347)' }}
      aria-hidden="true"
    />
  );
}

function EmptyHint({ label }: { label: string }) {
  return (
    <span className="planning-mono text-[10.5px]" style={{ color: 'var(--ink-4)' }}>
      {label}
    </span>
  );
}

function ConfidencePill({ confidence }: { confidence: SessionCorrelationEvidence['confidence'] }) {
  return (
    <span
      className="planning-mono inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-medium leading-none"
      style={{
        color: EVIDENCE_CONFIDENCE_COLOR[confidence],
        background: `color-mix(in oklab, ${EVIDENCE_CONFIDENCE_COLOR[confidence]} 12%, transparent)`,
      }}
    >
      {EVIDENCE_CONFIDENCE_LABEL[confidence]}
    </span>
  );
}

// ── Context window bar ────────────────────────────────────────────────────────

function ContextWindowBar({ pct }: { pct: number }) {
  const clampedPct = Math.min(100, Math.max(0, Math.round(pct * 100)));
  const barColor =
    pct > 0.8 ? 'var(--err)' : pct > 0.6 ? 'var(--warn)' : 'var(--ok)';

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="planning-mono text-[9.5px]" style={{ color: 'var(--ink-4)' }}>
          Context window
        </span>
        <span
          className="planning-mono text-[10.5px] font-semibold tabular-nums"
          style={{ color: barColor }}
        >
          {clampedPct}%
        </span>
      </div>
      <div
        className="h-[3px] w-full rounded-full overflow-hidden"
        style={{ background: 'var(--bg-3)' }}
        aria-label={`Context window ${clampedPct}% used`}
        role="meter"
        aria-valuenow={clampedPct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${clampedPct}%`, background: barColor }}
        />
      </div>
    </div>
  );
}

// ── Props ──────────────────────────────────────────────────────────────────────

export interface PlanningAgentSessionDetailPanelProps {
  card: PlanningAgentSessionCard;
  onClose: () => void;
  className?: string;
}

// ── Main component ────────────────────────────────────────────────────────────

export function PlanningAgentSessionDetailPanel({
  card,
  onClose,
  className,
}: PlanningAgentSessionDetailPanelProps): JSX.Element {
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // Move initial focus to close button when panel mounts.
  useEffect(() => {
    closeBtnRef.current?.focus();
  }, [card.sessionId]);

  const dotColor = STATE_DOT_COLOR[card.state] ?? 'var(--ink-4)';
  const isActive = card.state === 'running' || card.state === 'thinking';

  const featureId = card.correlation?.featureId;
  const phaseNumber = card.correlation?.phaseNumber;

  // Quick-action hrefs (mirroring CardActionRow in the board)
  const transcriptHref = card.sessionId
    ? `/sessions?session=${encodeURIComponent(card.sessionId)}`
    : null;

  const featureModalHref = featureId
    ? planningRouteFeatureModalHref(featureId, 'overview')
    : null;

  const phaseOpsHref =
    featureId != null && phaseNumber != null
      ? `${planningRouteFeatureModalHref(featureId, 'overview')}&phase=${encodeURIComponent(phaseNumber)}&panel=phase-ops`
      : null;

  // Lineage split: ancestor rels vs child rels
  const ancestorRels = card.relationships.filter(
    (r) => r.relationType === 'parent' || r.relationType === 'root',
  );
  const childRels = card.relationships.filter((r) => r.relationType === 'child');
  const siblingRels = card.relationships.filter((r) => r.relationType === 'sibling');

  // Chronological sort for activity markers (oldest first)
  const sortedMarkers = [...card.activityMarkers].sort((a, b) => {
    if (!a.timestamp || !b.timestamp) return 0;
    return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
  });

  return (
    <aside
      className={cn(
        // Entry animation — reuses planning-card-enter for slide-in
        'planning-card-enter',
        'rounded-[var(--radius)] border',
        'bg-[color:var(--bg-1)]',
        'border-[color:var(--brand)]',
        'shadow-[0_0_0_1px_color-mix(in_oklab,var(--brand)_20%,transparent),0_8px_24px_color-mix(in_oklab,var(--brand)_8%,transparent)]',
        'overflow-hidden',
        className,
      )}
      role="complementary"
      aria-label={`Session detail: ${card.agentName ?? card.sessionId}`}
      data-testid="session-detail-panel"
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div
        className="flex items-start justify-between gap-3 px-4 py-3"
        style={{
          borderBottom: '1px solid var(--line-1, #2d3347)',
          background: 'color-mix(in oklab, var(--brand) 5%, var(--bg-1))',
        }}
      >
        {/* State dot + agent name + session ID */}
        <div className="flex min-w-0 flex-1 items-start gap-2.5">
          <Dot
            style={{
              background: dotColor,
              flexShrink: 0,
              marginTop: 3,
              '--dot-color': dotColor,
            } as React.CSSProperties}
            aria-label={card.state}
            className={isActive ? 'planning-dot-live' : undefined}
          />
          <div className="min-w-0">
            <p
              className="truncate text-[12.5px] font-semibold leading-snug"
              style={{ color: 'var(--ink-0)' }}
              data-testid="detail-panel-agent-name"
            >
              {card.agentName ?? `Agent ${card.sessionId.slice(-8)}`}
            </p>
            <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
              {/* State label */}
              <span
                className="planning-mono text-[9.5px] font-medium"
                style={{ color: dotColor }}
              >
                {STATE_LABEL[card.state]}
              </span>
              {/* Model chip */}
              {card.model && (
                <>
                  <span
                    className="planning-mono text-[9px]"
                    style={{ color: 'var(--ink-4)' }}
                    aria-hidden
                  >
                    ·
                  </span>
                  <span
                    className="planning-mono text-[9.5px]"
                    style={{ color: 'var(--ink-3)' }}
                  >
                    {card.model}
                  </span>
                </>
              )}
            </div>
            <p
              className="planning-mono mt-1 truncate text-[9.5px]"
              style={{ color: 'var(--ink-4)' }}
              title={card.sessionId}
              data-testid="detail-panel-session-id"
            >
              {card.sessionId}
            </p>
          </div>
        </div>

        {/* Close button */}
        <button
          ref={closeBtnRef}
          type="button"
          onClick={onClose}
          className={cn(
            'flex-shrink-0 rounded p-1 transition-colors',
            'text-[color:var(--ink-3)] hover:text-[color:var(--ink-1)]',
            'border border-[color:var(--line-1)] hover:border-[color:var(--line-2)]',
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
          )}
          aria-label="Close session detail panel"
          data-testid="detail-panel-close-btn"
        >
          <X size={13} />
        </button>
      </div>

      {/* ── Scrollable body ────────────────────────────────────────────── */}
      <div className="overflow-y-auto" style={{ maxHeight: 520 }}>
        <div className="space-y-0">

          {/* 1. Lineage ─────────────────────────────────────────────────── */}
          <section className="px-4 py-3">
            <SectionLabel>Lineage</SectionLabel>
            {card.relationships.length === 0 ? (
              <EmptyHint label="No relationships" />
            ) : (
              <div className="space-y-1">
                {/* Ancestor relationships */}
                {ancestorRels.map((rel) => (
                  <Link
                    key={rel.relatedSessionId}
                    to={`/sessions?session=${encodeURIComponent(rel.relatedSessionId)}`}
                    className={cn(
                      'flex w-full items-center gap-2 rounded px-2 py-1',
                      'border border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
                      'text-[10.5px] transition-colors',
                      'hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)]',
                      'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
                    )}
                    data-testid={`lineage-${rel.relationType}-${rel.relatedSessionId}`}
                  >
                    <span style={{ color: 'var(--ink-3)' }}>
                      {RELATION_ICON[rel.relationType]}
                    </span>
                    <span
                      className="planning-mono text-[9.5px] w-10 flex-shrink-0"
                      style={{ color: 'var(--ink-4)' }}
                    >
                      {RELATION_LABEL[rel.relationType]}
                    </span>
                    <span
                      className="planning-mono flex-1 truncate text-[10px]"
                      style={{ color: 'var(--info, #60a5fa)' }}
                      title={rel.relatedSessionId}
                    >
                      {rel.agentName ?? rel.relatedSessionId.slice(-12)}
                    </span>
                    {rel.state && (
                      <span
                        className="planning-mono flex-shrink-0 text-[9px]"
                        style={{ color: 'var(--ink-4)' }}
                      >
                        {rel.state}
                      </span>
                    )}
                  </Link>
                ))}

                {/* Current session marker */}
                <div
                  className={cn(
                    'flex items-center gap-2 rounded px-2 py-1',
                    'border border-[color:var(--brand)]',
                    'bg-[color:color-mix(in_oklab,var(--brand)_6%,var(--bg-2))]',
                    'text-[10.5px]',
                  )}
                  aria-current="true"
                >
                  <Dot
                    style={{
                      background: dotColor,
                      flexShrink: 0,
                      '--dot-color': dotColor,
                    } as React.CSSProperties}
                    aria-hidden
                    className={isActive ? 'planning-dot-live' : undefined}
                  />
                  <span
                    className="planning-mono w-10 flex-shrink-0 text-[9.5px]"
                    style={{ color: 'var(--ink-4)' }}
                  >
                    current
                  </span>
                  <span
                    className="planning-mono flex-1 truncate text-[10px] font-medium"
                    style={{ color: 'var(--ink-1)' }}
                  >
                    {card.agentName ?? card.sessionId.slice(-12)}
                  </span>
                </div>

                {/* Sibling relationships */}
                {siblingRels.map((rel) => (
                  <Link
                    key={rel.relatedSessionId}
                    to={`/sessions?session=${encodeURIComponent(rel.relatedSessionId)}`}
                    className={cn(
                      'flex w-full items-center gap-2 rounded px-2 py-1',
                      'border border-dashed border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
                      'text-[10.5px] transition-colors',
                      'hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)]',
                      'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
                    )}
                    data-testid={`lineage-sibling-${rel.relatedSessionId}`}
                  >
                    <span style={{ color: 'var(--ink-4)' }}>
                      {RELATION_ICON.sibling}
                    </span>
                    <span
                      className="planning-mono w-10 flex-shrink-0 text-[9.5px]"
                      style={{ color: 'var(--ink-4)' }}
                    >
                      sibling
                    </span>
                    <span
                      className="planning-mono flex-1 truncate text-[10px]"
                      style={{ color: 'var(--ink-3)' }}
                      title={rel.relatedSessionId}
                    >
                      {rel.agentName ?? rel.relatedSessionId.slice(-12)}
                    </span>
                  </Link>
                ))}

                {/* Child relationships */}
                {childRels.map((rel) => (
                  <Link
                    key={rel.relatedSessionId}
                    to={`/sessions?session=${encodeURIComponent(rel.relatedSessionId)}`}
                    className={cn(
                      'flex w-full items-center gap-2 rounded px-2 py-1',
                      'border border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
                      'text-[10.5px] transition-colors',
                      'hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)]',
                      'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
                    )}
                    data-testid={`lineage-child-${rel.relatedSessionId}`}
                  >
                    <span style={{ color: 'var(--ink-3)' }}>
                      {RELATION_ICON.child}
                    </span>
                    <span
                      className="planning-mono w-10 flex-shrink-0 text-[9.5px]"
                      style={{ color: 'var(--ink-4)' }}
                    >
                      child
                    </span>
                    <span
                      className="planning-mono flex-1 truncate text-[10px]"
                      style={{ color: 'var(--info, #60a5fa)' }}
                      title={rel.relatedSessionId}
                    >
                      {rel.agentName ?? rel.relatedSessionId.slice(-12)}
                    </span>
                    {rel.state && (
                      <span
                        className="planning-mono flex-shrink-0 text-[9px]"
                        style={{ color: 'var(--ink-4)' }}
                      >
                        {rel.state}
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </section>

          <Divider />

          {/* 2. Feature correlation ──────────────────────────────────────── */}
          <section className="px-4 py-3">
            <SectionLabel>Feature Correlation</SectionLabel>
            {!card.correlation ? (
              <EmptyHint label="No correlation data" />
            ) : (
              <div className="space-y-2">
                {/* Feature name + confidence */}
                {(card.correlation.featureName ?? card.correlation.featureId) && (
                  <div className="flex items-center gap-2">
                    <Layers size={10} style={{ color: 'var(--brand)' }} aria-hidden />
                    {featureModalHref ? (
                      <Link
                        to={featureModalHref}
                        className="planning-mono truncate text-[10.5px] transition-opacity hover:opacity-80"
                        style={{ color: 'var(--brand)' }}
                        data-testid="detail-panel-feature-link"
                      >
                        {card.correlation.featureName ?? card.correlation.featureId}
                      </Link>
                    ) : (
                      <span
                        className="planning-mono truncate text-[10.5px]"
                        style={{ color: 'var(--brand)' }}
                      >
                        {card.correlation.featureName ?? card.correlation.featureId}
                      </span>
                    )}
                    {/* Overall confidence */}
                    <span className="ml-auto flex-shrink-0">
                      <ConfidencePill confidence={card.correlation.confidence} />
                    </span>
                  </div>
                )}

                {/* Phase + task + batch row */}
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {card.correlation.phaseNumber != null && (
                    <div>
                      <p
                        className="planning-mono text-[9px]"
                        style={{ color: 'var(--ink-4)' }}
                      >
                        phase
                      </p>
                      <p
                        className="planning-mono text-[10.5px] font-medium"
                        style={{ color: 'var(--ink-2)' }}
                        data-testid="detail-panel-phase"
                      >
                        {card.correlation.phaseTitle
                          ? `P${card.correlation.phaseNumber}: ${card.correlation.phaseTitle}`
                          : `Phase ${card.correlation.phaseNumber}`}
                      </p>
                    </div>
                  )}
                  {(card.correlation.taskId ?? card.correlation.taskTitle) && (
                    <div>
                      <p
                        className="planning-mono text-[9px]"
                        style={{ color: 'var(--ink-4)' }}
                      >
                        task
                      </p>
                      <p
                        className="planning-mono text-[10.5px] font-medium"
                        style={{ color: 'var(--ink-2)' }}
                        data-testid="detail-panel-task"
                      >
                        {card.correlation.taskTitle ?? card.correlation.taskId}
                      </p>
                    </div>
                  )}
                  {card.correlation.batchId && (
                    <div>
                      <p
                        className="planning-mono text-[9px]"
                        style={{ color: 'var(--ink-4)' }}
                      >
                        batch
                      </p>
                      <p
                        className="planning-mono text-[10.5px] font-medium"
                        style={{ color: 'var(--ink-2)' }}
                      >
                        {card.correlation.batchId}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          <Divider />

          {/* 3. Evidence ─────────────────────────────────────────────────── */}
          <section className="px-4 py-3">
            <SectionLabel>Evidence</SectionLabel>
            {!card.correlation || card.correlation.evidence.length === 0 ? (
              <EmptyHint label="No evidence items" />
            ) : (
              <ul
                className="space-y-1"
                aria-label="Correlation evidence"
                data-testid="detail-panel-evidence"
              >
                {card.correlation.evidence.map((ev, i) => (
                  <li
                    key={i}
                    className={cn(
                      'flex items-center gap-2 rounded px-2 py-1',
                      'border border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
                    )}
                  >
                    {/* Source type icon approximation */}
                    {ev.sourceType === 'explicit_link' ? (
                      <Link2 size={9} style={{ color: 'var(--ok)', flexShrink: 0 }} aria-hidden />
                    ) : ev.sourceType === 'lineage' ? (
                      <GitBranch
                        size={9}
                        style={{ color: 'var(--info, #60a5fa)', flexShrink: 0 }}
                        aria-hidden
                      />
                    ) : (
                      <HelpCircle
                        size={9}
                        style={{ color: 'var(--ink-4)', flexShrink: 0 }}
                        aria-hidden
                      />
                    )}
                    <span
                      className="planning-mono flex-1 truncate text-[10px]"
                      style={{ color: 'var(--ink-2)' }}
                      title={ev.detail ?? ev.sourceLabel}
                    >
                      {ev.sourceLabel}
                    </span>
                    <span
                      className="planning-mono flex-shrink-0 text-[9px]"
                      style={{ color: 'var(--ink-4)' }}
                    >
                      {ev.sourceType}
                    </span>
                    <ConfidencePill confidence={ev.confidence} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <Divider />

          {/* 4. Token context ────────────────────────────────────────────── */}
          <section className="px-4 py-3">
            <SectionLabel>Token Context</SectionLabel>
            {!card.tokenSummary ? (
              <EmptyHint label="No token data" />
            ) : (
              <div className="space-y-3">
                {/* Input / Output / Total grid */}
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <p
                      className="planning-mono text-[9px]"
                      style={{ color: 'var(--ink-4)' }}
                    >
                      Input
                    </p>
                    <p
                      className="planning-mono text-[12px] font-semibold tabular-nums"
                      style={{ color: 'var(--ink-1)' }}
                      data-testid="detail-panel-tokens-in"
                    >
                      {fmtTokens(card.tokenSummary.tokensIn)}
                    </p>
                  </div>
                  <div>
                    <p
                      className="planning-mono text-[9px]"
                      style={{ color: 'var(--ink-4)' }}
                    >
                      Output
                    </p>
                    <p
                      className="planning-mono text-[12px] font-semibold tabular-nums"
                      style={{ color: 'var(--ink-1)' }}
                      data-testid="detail-panel-tokens-out"
                    >
                      {fmtTokens(card.tokenSummary.tokensOut)}
                    </p>
                  </div>
                  <div>
                    <p
                      className="planning-mono text-[9px]"
                      style={{ color: 'var(--ink-4)' }}
                    >
                      Total
                    </p>
                    <p
                      className="planning-mono text-[12px] font-semibold tabular-nums"
                      style={{ color: 'var(--ink-1)' }}
                    >
                      {fmtTokens(card.tokenSummary.totalTokens)}
                    </p>
                  </div>
                </div>

                {/* Context window bar */}
                {card.tokenSummary.contextWindowPct != null && (
                  <ContextWindowBar pct={card.tokenSummary.contextWindowPct} />
                )}
              </div>
            )}
          </section>

          <Divider />

          {/* 5. Activity timeline ────────────────────────────────────────── */}
          <section className="px-4 py-3">
            <SectionLabel>Activity Timeline</SectionLabel>
            {sortedMarkers.length === 0 ? (
              <EmptyHint label="No activity markers" />
            ) : (
              <ol
                className="relative space-y-0 pl-3"
                aria-label="Activity timeline"
                data-testid="detail-panel-activity"
                style={{
                  borderLeft: '1px solid var(--line-1)',
                }}
              >
                {sortedMarkers.map((marker, i) => (
                  <li
                    key={i}
                    className="relative flex items-start gap-2 pb-2 last:pb-0"
                  >
                    {/* Timeline dot */}
                    <span
                      className="absolute -left-[5px] top-[3px] flex h-[9px] w-[9px] items-center justify-center rounded-full border"
                      style={{
                        background: 'var(--bg-1)',
                        borderColor: MARKER_COLOR[marker.markerType],
                        color: MARKER_COLOR[marker.markerType],
                      }}
                      aria-hidden
                    >
                      <span style={{ transform: 'scale(0.7)', display: 'flex' }}>
                        {MARKER_ICON[marker.markerType]}
                      </span>
                    </span>

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span
                          className="planning-mono truncate text-[10px] font-medium"
                          style={{ color: 'var(--ink-2)' }}
                          title={marker.detail ?? marker.label}
                        >
                          {marker.label}
                        </span>
                        {marker.timestamp && (
                          <span
                            className="planning-mono flex-shrink-0 text-[9px] tabular-nums"
                            style={{ color: 'var(--ink-4)' }}
                          >
                            {relativeTime(marker.timestamp)}
                          </span>
                        )}
                      </div>
                      {marker.detail && (
                        <p
                          className="planning-mono mt-0.5 line-clamp-2 text-[9.5px]"
                          style={{ color: 'var(--ink-4)' }}
                        >
                          {marker.detail}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <Divider />

          {/* 6. Quick actions ────────────────────────────────────────────── */}
          <section className="px-4 py-3">
            <SectionLabel>Quick Actions</SectionLabel>
            <div className="flex flex-wrap gap-1.5">
              {transcriptHref && (
                <Link
                  to={transcriptHref}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2.5 py-1.5',
                    'border border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
                    'planning-mono text-[10px] text-[color:var(--ink-2)]',
                    'transition-colors hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)] hover:text-[color:var(--ink-1)]',
                    'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
                  )}
                  aria-label="View session transcript"
                  data-testid="detail-panel-transcript-link"
                >
                  <FileText size={11} aria-hidden />
                  Transcript
                </Link>
              )}

              {featureModalHref && (
                <Link
                  to={featureModalHref}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2.5 py-1.5',
                    'border border-[color:color-mix(in_oklab,var(--brand)_40%,var(--line-1))]',
                    'bg-[color:color-mix(in_oklab,var(--brand)_8%,transparent)]',
                    'planning-mono text-[10px] text-[color:var(--brand)]',
                    'transition-colors hover:bg-[color:color-mix(in_oklab,var(--brand)_14%,transparent)]',
                    'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
                  )}
                  aria-label={`Open feature${card.correlation?.featureName ? ` ${card.correlation.featureName}` : ''} in planning view`}
                  data-testid="detail-panel-feature-plan-link"
                >
                  <Layers size={11} aria-hidden />
                  Feature Plan
                </Link>
              )}

              {phaseOpsHref && (
                <Link
                  to={phaseOpsHref}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2.5 py-1.5',
                    'border border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
                    'planning-mono text-[10px] text-[color:var(--ink-2)]',
                    'transition-colors hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)] hover:text-[color:var(--ink-1)]',
                    'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
                  )}
                  aria-label={`Open phase ${phaseNumber} operations panel`}
                  data-testid="detail-panel-phase-ops-link"
                >
                  <Settings2 size={11} aria-hidden />
                  Phase Ops
                </Link>
              )}

              {/* Fallback when there are no actions */}
              {!transcriptHref && !featureModalHref && !phaseOpsHref && (
                <EmptyHint label="No actions available" />
              )}
            </div>
          </section>
        </div>
      </div>

      {/* ── Footer: timing metadata ─────────────────────────────────────── */}
      {(card.startedAt ?? card.lastActivityAt) && (
        <div
          className="flex items-center justify-between gap-3 px-4 py-2"
          style={{
            borderTop: '1px solid var(--line-1, #2d3347)',
            background: 'var(--bg-0, var(--bg-1))',
          }}
        >
          {card.startedAt && (
            <span
              className="planning-mono text-[9px] tabular-nums"
              style={{ color: 'var(--ink-4)' }}
              title={`Started: ${new Date(card.startedAt).toLocaleString()}`}
            >
              Started {relativeTime(card.startedAt)}
            </span>
          )}
          {card.durationSeconds != null && (
            <span
              className="planning-mono text-[9px] tabular-nums"
              style={{ color: 'var(--ink-4)' }}
            >
              {card.durationSeconds < 60
                ? `${card.durationSeconds}s`
                : `${Math.round(card.durationSeconds / 60)}m`}
            </span>
          )}
          {card.lastActivityAt && (
            <span
              className="planning-mono ml-auto text-[9px] tabular-nums"
              style={{ color: 'var(--ink-4)' }}
              title={`Last activity: ${new Date(card.lastActivityAt).toLocaleString()}`}
            >
              Active {relativeTime(card.lastActivityAt)}
            </span>
          )}
        </div>
      )}
    </aside>
  );
}

// ── BarChart2 re-export for consumers that may want the metrics icon ───────────
export { BarChart2 as DetailPanelMetricsIcon };
