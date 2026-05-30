/**
 * MPCC-505: Portfolio detail rail/drawer for multi-project command center.
 *
 * Opens a right-side drawer for a session or feature in ANY project,
 * identified by explicit project_id from URL state.  Opening detail DOES NOT
 * switch the active project — the rail reads data directly via project_id.
 *
 * Focus is returned to the originating card (via focusTargetRef) when the
 * drawer closes.
 *
 * Architecture:
 *   - Session detail: shows basic session metadata + actions scoped to project_id
 *   - Feature detail: shows the V1 CommandCenterDetailPanel with project badge
 *   - Future: full modal replacement once existing modal hooks are project-scoped
 */
import { useCallback, useEffect, useId, useRef } from 'react';
import { X, Globe, ExternalLink } from 'lucide-react';
import type { AggregateSessionCard, AggregateWorkItem } from '@/types';
import { BtnGhost, Panel } from '../primitives';
import { commandCenterDisplayName, commandCenterPlanPath } from './commandCenterUtils';
import { PhasePlanTable } from './PhasePlanTable';

// ── Types ──────────────────────────────────────────────────────────────────────

export type DetailTarget =
  | { kind: 'session'; sessionId: string; projectId: string; aggregateCard?: AggregateSessionCard }
  | { kind: 'workItem'; featureId: string; projectId: string; workItem?: AggregateWorkItem }
  | null;

interface MultiProjectDetailRailProps {
  target: DetailTarget;
  commandValue?: string;
  onClose: () => void;
  onOpenPlan?: (path: string) => void;
  /** Ref to the element that triggered the drawer — focus returns here on close. */
  focusTargetRef?: React.RefObject<HTMLElement>;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fallbackColor(projectId: string): string {
  let hash = 0;
  for (let i = 0; i < projectId.length; i++) {
    hash = projectId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash) % 360;
  return `oklch(65% 0.18 ${h})`;
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

// ── Session detail content ────────────────────────────────────────────────────

interface SessionDetailContentProps {
  sessionId: string;
  projectId: string;
  projectColor: string;
  projectName: string;
  aggregateCard?: AggregateSessionCard;
}

function SessionDetailContent({
  sessionId,
  projectId,
  projectColor,
  projectName,
  aggregateCard,
}: SessionDetailContentProps) {
  const card = aggregateCard?.card;
  const workers = aggregateCard?.workers ?? [];

  return (
    <div className="space-y-5">
      {/* Session ID + state */}
      <section className="space-y-2">
        <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">session</div>
        <p className="planning-mono text-[12px] text-[color:var(--ink-1)]">{sessionId}</p>
        {card && (
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="planning-mono rounded px-2 py-0.5 text-[11px]"
              style={{
                backgroundColor: 'var(--bg-2)',
                color:
                  card.state === 'running'
                    ? 'var(--ok)'
                    : card.state === 'failed'
                      ? 'var(--err)'
                      : 'var(--ink-2)',
              }}
            >
              {card.state}
            </span>
            {card.model && (
              <span
                className="planning-mono rounded px-2 py-0.5 text-[11px]"
                style={{ backgroundColor: 'var(--bg-2)', color: 'var(--ink-3)' }}
              >
                {card.model}
              </span>
            )}
          </div>
        )}
      </section>

      {/* Correlation */}
      {card?.correlation && (
        <section className="space-y-1.5">
          <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">feature context</div>
          {card.correlation.featureName && (
            <p className="text-[13px] text-[color:var(--ink-1)]">{card.correlation.featureName}</p>
          )}
          <p className="planning-mono text-[11px] text-[color:var(--ink-4)]">
            {card.correlation.featureId}
          </p>
          {card.correlation.phaseNumber != null && (
            <span
              className="inline-block planning-mono rounded px-1.5 py-0.5 text-[10.5px]"
              style={{ backgroundColor: 'var(--bg-2)', color: 'var(--ink-3)' }}
            >
              phase {card.correlation.phaseNumber}
            </span>
          )}
        </section>
      )}

      {/* Timing */}
      {card && (
        <section className="space-y-1.5">
          <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">timing</div>
          <dl className="space-y-1 text-[12px]">
            {card.startedAt && (
              <div className="flex items-center justify-between gap-2">
                <dt className="planning-mono text-[color:var(--ink-3)]">started</dt>
                <dd className="planning-mono text-[color:var(--ink-1)]">{relativeTime(card.startedAt)}</dd>
              </div>
            )}
            {card.lastActivityAt && (
              <div className="flex items-center justify-between gap-2">
                <dt className="planning-mono text-[color:var(--ink-3)]">last activity</dt>
                <dd className="planning-mono text-[color:var(--ink-1)]">{relativeTime(card.lastActivityAt)}</dd>
              </div>
            )}
            {card.tokenSummary && (
              <div className="flex items-center justify-between gap-2">
                <dt className="planning-mono text-[color:var(--ink-3)]">tokens</dt>
                <dd className="planning-mono text-[color:var(--ink-1)]">
                  {((card.tokenSummary.totalTokens ?? 0) / 1000).toFixed(1)}k
                </dd>
              </div>
            )}
          </dl>
        </section>
      )}

      {/* Workers */}
      {workers.length > 0 && (
        <section className="space-y-1.5">
          <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">
            workers ({workers.length})
          </div>
          <div className="space-y-1">
            {workers.map((w) => (
              <div
                key={w.sessionId}
                className="flex items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1 text-[11px]"
                style={{ backgroundColor: 'var(--bg-2)' }}
              >
                <span className="planning-mono text-[color:var(--ink-2)] truncate flex-1">
                  {w.agentName || w.sessionId}
                </span>
                <span
                  className="planning-mono text-[10px] shrink-0"
                  style={{ color: w.state === 'running' ? 'var(--ok)' : 'var(--ink-3)' }}
                >
                  {w.state}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Actions */}
      <section className="space-y-2">
        <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">actions</div>
        <div className="flex flex-wrap gap-2">
          <a
            href={`#/sessions?session=${encodeURIComponent(sessionId)}&project_id=${encodeURIComponent(projectId)}`}
            className="planning-mono inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-2)] px-2.5 py-1.5 text-[11px] text-[color:var(--ink-2)] hover:text-[color:var(--ink-0)] transition-colors"
          >
            <ExternalLink size={11} aria-hidden />
            open session
          </a>
        </div>
        <p
          className="planning-mono text-[10.5px]"
          style={{ color: 'var(--ink-4)' }}
        >
          Session is in project <span style={{ color: projectColor }}>{projectName}</span>.
          Viewing does not change your active project.
        </p>
      </section>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

/** Focusable element selector for focus-trap cycling. */
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export function MultiProjectDetailRail({
  target,
  commandValue = '',
  onClose,
  onOpenPlan,
  focusTargetRef,
}: MultiProjectDetailRailProps) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const headingId = useId();

  // Return focus to trigger element on close
  const handleClose = useCallback(() => {
    onClose();
    // Focus return after close — deferred so drawer is unmounted first
    window.setTimeout(() => {
      focusTargetRef?.current?.focus();
    }, 50);
  }, [onClose, focusTargetRef]);

  // Escape key closes; Tab is trapped within the drawer.
  useEffect(() => {
    if (!target) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        handleClose();
        return;
      }

      // Focus trap: cycle Tab/Shift+Tab within the drawer panel.
      if (e.key === 'Tab') {
        const drawer = drawerRef.current;
        if (!drawer) return;
        const focusable = Array.from(
          drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
        ).filter((el) => !el.closest('[aria-hidden="true"]'));
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [target, handleClose]);

  // Focus the drawer when it opens
  useEffect(() => {
    if (target) {
      window.setTimeout(() => drawerRef.current?.focus(), 50);
    }
  }, [target]);

  if (!target) return null;

  const projectColor =
    (target.kind === 'session'
      ? target.aggregateCard?.project.projectColor
      : target.workItem?.project.projectColor) || fallbackColor(target.projectId);
  const projectName =
    (target.kind === 'session'
      ? target.aggregateCard?.project.projectName
      : target.workItem?.project.projectName) || target.projectId;

  return (
    <div
      className="fixed inset-0 z-40"
      style={{ backgroundColor: 'rgba(0,0,0,0.45)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
    >
      {/* Backdrop click closes */}
      <div
        className="absolute inset-0"
        onClick={handleClose}
        onKeyDown={(e) => e.key === 'Escape' && handleClose()}
        role="presentation"
        tabIndex={-1}
        aria-hidden
      />

      {/* Drawer panel */}
      <div
        ref={drawerRef}
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex w-full max-w-[760px] flex-col"
        style={{
          borderLeft: '1px solid var(--line-1)',
          backgroundColor: 'var(--bg-0)',
          outline: 'none',
        }}
        data-testid="multi-project-detail-rail"
        data-project-id={target.projectId}
      >
        <Panel className="flex min-h-0 flex-1 flex-col rounded-none border-0">
          {/* Header */}
          <div
            className="flex items-center justify-between gap-3 p-5"
            style={{ borderBottom: '1px solid var(--line-1)' }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <Globe size={14} style={{ color: 'var(--ink-3)', flexShrink: 0 }} aria-hidden />

              {/* Project identity badge */}
              <div
                className="flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-0.5"
                style={{
                  backgroundColor: `color-mix(in oklab, ${projectColor} 12%, var(--bg-2))`,
                  border: `1px solid color-mix(in oklab, ${projectColor} 30%, var(--line-1))`,
                }}
              >
                <span
                  className="inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: projectColor }}
                  aria-hidden
                />
                <span
                  className="planning-mono truncate text-[11px]"
                  style={{ color: 'var(--ink-2)' }}
                  title={projectName}
                >
                  {projectName}
                </span>
              </div>

              <h2
                id={headingId}
                className="planning-mono m-0 text-[10px]"
                style={{ color: 'var(--ink-4)', fontWeight: 'inherit' }}
              >
                {target.kind === 'session' ? 'session detail' : 'feature detail'}
              </h2>
            </div>

            <BtnGhost size="sm" onClick={handleClose} aria-label="Close detail rail">
              <X size={14} aria-hidden />
              close
            </BtnGhost>
          </div>

          {/* Content */}
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            {target.kind === 'session' ? (
              <SessionDetailContent
                sessionId={target.sessionId}
                projectId={target.projectId}
                projectColor={projectColor}
                projectName={projectName}
                aggregateCard={target.aggregateCard}
              />
            ) : target.kind === 'workItem' && target.workItem ? (
              <div className="space-y-5">
                <section className="space-y-2">
                  <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">feature</div>
                  <p className="text-[18px] font-semibold text-[color:var(--ink-0)]">
                    {commandCenterDisplayName(target.workItem.item)}
                  </p>
                  <p className="planning-mono text-[11px] text-[color:var(--ink-4)]">
                    {target.workItem.item.feature.featureId}
                  </p>
                </section>
                <section className="space-y-2">
                  <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">next command</div>
                  <pre className="planning-mono whitespace-pre-wrap rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-3 text-[11px] leading-relaxed text-[color:var(--ink-1)]">
                    {commandValue || 'No next command resolved'}
                  </pre>
                </section>
                {target.workItem.item.phaseRows && target.workItem.item.phaseRows.length > 0 && (
                  <section className="space-y-2">
                    <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">phases</div>
                    <PhasePlanTable rows={target.workItem.item.phaseRows} />
                  </section>
                )}
                {(() => {
                  const planPath = commandCenterPlanPath(target.workItem.item);
                  return onOpenPlan && planPath ? (
                    <section>
                      <button
                        type="button"
                        className="planning-mono inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-2)] px-2.5 py-1.5 text-[11px] text-[color:var(--ink-2)] hover:text-[color:var(--ink-0)] transition-colors"
                        onClick={() => onOpenPlan(planPath)}
                      >
                        open plan
                      </button>
                    </section>
                  ) : null;
                })()}
              </div>
            ) : (
              <div className="flex min-h-[160px] items-center justify-center">
                <p
                  className="planning-mono text-[12px]"
                  style={{ color: 'var(--ink-3)' }}
                >
                  Detail not available for this item.
                </p>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
