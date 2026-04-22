/**
 * P15-004: AgentDetailModal
 *
 * Opens when a roster row is clicked. Displays enriched details for a single
 * AgentSession:
 *   - Display name (displayAgentType-first) + subagent type badge
 *   - Root/parent session relationship + Orchestrator badge for roots
 *   - Session deep-link to /sessions page
 *   - Feature links (from linkedFeatureIds)
 *   - Phase/task context chips (from phaseHints, taskHints)
 *   - Model name
 *   - Token / context usage when present
 *
 * Accessibility:
 *   - role="dialog" + aria-modal="true"
 *   - Focus trapped inside; initial focus on close button
 *   - ESC key closes + restores focus to the row that opened it
 */

import { useEffect, useRef, type JSX } from 'react';
import { Link } from 'react-router-dom';
import { X, ExternalLink, GitBranch, Cpu, Activity, Layers } from 'lucide-react';

import type { AgentSession, Feature } from '@/types';
import { humanizeAgentType } from './PlanningAgentRosterPanel';
import { planningRouteFeatureModalHref } from '@/services/planningRoutes';

// ── Helpers ────────────────────────────────────────────────────────────────────

function sessionHref(sessionId: string): string {
  return `/sessions?session=${encodeURIComponent(sessionId)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function contextPct(session: AgentSession): string | null {
  if (session.contextUtilizationPct != null) {
    return `${(session.contextUtilizationPct * 100).toFixed(1)}%`;
  }
  if (session.currentContextTokens != null && session.contextWindowSize != null && session.contextWindowSize > 0) {
    const pct = (session.currentContextTokens / session.contextWindowSize) * 100;
    return `${pct.toFixed(1)}%`;
  }
  return null;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="planning-mono mb-1.5 text-[10px] uppercase tracking-widest"
      style={{ color: 'var(--ink-4)' }}
    >
      {children}
    </p>
  );
}

function EmptyHint({ label }: { label: string }) {
  return (
    <span
      className="planning-mono text-[11px]"
      style={{ color: 'var(--ink-4)' }}
    >
      {label}
    </span>
  );
}

function Chip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'phase' | 'task' }) {
  const toneStyles: Record<string, React.CSSProperties> = {
    neutral: {
      background: 'color-mix(in oklab, var(--ink-3) 12%, transparent)',
      color: 'var(--ink-2)',
    },
    phase: {
      background: 'color-mix(in oklab, var(--info, #60a5fa) 12%, transparent)',
      color: 'var(--info, #60a5fa)',
    },
    task: {
      background: 'color-mix(in oklab, var(--ok) 12%, transparent)',
      color: 'var(--ok)',
    },
  };

  return (
    <span
      className="planning-mono inline-flex items-center rounded px-2 py-0.5 text-[10.5px] font-medium"
      style={toneStyles[tone]}
    >
      {children}
    </span>
  );
}

// ── AgentDetailModalContent (pure, exported for tests) ────────────────────────

export interface AgentDetailModalContentProps {
  session: AgentSession;
  features: Feature[];
}

export function AgentDetailModalContent({
  session,
  features,
}: AgentDetailModalContentProps): JSX.Element {
  // Derived values
  const displayName =
    (session.displayAgentType != null && session.displayAgentType !== '')
      ? humanizeAgentType(session.displayAgentType)
      : (session.agentId ?? session.title?.split(' ')[0] ?? `Agent ${session.id.slice(0, 6)}`);

  const subtype =
    session.subagentType ?? session.displayAgentType ?? null;

  const isRoot =
    !session.parentSessionId ||
    session.parentSessionId === session.id ||
    session.rootSessionId === session.id;

  const linkedFeatures = features.filter(
    (f) => session.linkedFeatureIds?.includes(f.id),
  );

  const totalTokensIn = session.tokensIn ?? 0;
  const totalTokensOut = session.tokensOut ?? 0;
  const ctxPct = contextPct(session);

  return (
    <div className="px-5 py-4 space-y-5 text-sm">

      {/* ── Identity ──────────────────────────────────────────────────── */}
      <section>
        <SectionLabel>Identity</SectionLabel>
        <div className="flex flex-wrap items-center gap-2">
          {isRoot && (
            <span
              className="planning-mono inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10.5px] font-semibold"
              style={{
                background: 'color-mix(in oklab, var(--ok) 16%, transparent)',
                color: 'var(--ok)',
                border: '1px solid color-mix(in oklab, var(--ok) 30%, transparent)',
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: 'currentColor',
                }}
              />
              Orchestrator
            </span>
          )}
          {subtype != null && subtype !== '' && (
            <span
              className="planning-mono inline-flex items-center rounded px-2 py-0.5 text-[10.5px]"
              style={{
                background: 'color-mix(in oklab, var(--ink-3) 15%, transparent)',
                color: 'var(--ink-2)',
              }}
              title="subagent type"
            >
              {subtype}
            </span>
          )}
          {session.agentId && (
            <span
              className="planning-mono truncate text-[10.5px]"
              style={{ color: 'var(--ink-3)' }}
              title={session.agentId}
            >
              {session.agentId}
            </span>
          )}
        </div>
      </section>

      {/* ── Session link ──────────────────────────────────────────────── */}
      <section>
        <SectionLabel>Session</SectionLabel>
        <Link
          to={sessionHref(session.id)}
          className="planning-mono group inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11.5px] transition-colors"
          style={{
            color: 'var(--info, #60a5fa)',
            background: 'color-mix(in oklab, var(--info, #60a5fa) 8%, transparent)',
            border: '1px solid color-mix(in oklab, var(--info, #60a5fa) 20%, transparent)',
          }}
          data-testid="session-link"
        >
          <Activity size={11} aria-hidden="true" />
          <span className="truncate font-medium">{session.id}</span>
          <ExternalLink size={10} className="shrink-0 opacity-60 group-hover:opacity-100" aria-hidden="true" />
        </Link>
      </section>

      {/* ── Parent / root relationship ─────────────────────────────────── */}
      {(session.parentSessionId || session.rootSessionId) && !isRoot && (
        <section>
          <SectionLabel>Lineage</SectionLabel>
          <div className="space-y-1">
            {session.parentSessionId && session.parentSessionId !== session.id && (
              <div className="flex items-center gap-2">
                <span
                  className="planning-mono text-[10px]"
                  style={{ color: 'var(--ink-4)' }}
                >
                  parent
                </span>
                <Link
                  to={sessionHref(session.parentSessionId)}
                  className="planning-mono inline-flex items-center gap-1 text-[11px] transition-opacity hover:opacity-80"
                  style={{ color: 'var(--info, #60a5fa)' }}
                  data-testid="parent-session-link"
                >
                  <GitBranch size={10} aria-hidden="true" />
                  <span className="truncate">{session.parentSessionId}</span>
                </Link>
              </div>
            )}
            {session.rootSessionId && session.rootSessionId !== session.parentSessionId && session.rootSessionId !== session.id && (
              <div className="flex items-center gap-2">
                <span
                  className="planning-mono text-[10px]"
                  style={{ color: 'var(--ink-4)' }}
                >
                  root
                </span>
                <Link
                  to={sessionHref(session.rootSessionId)}
                  className="planning-mono inline-flex items-center gap-1 text-[11px] transition-opacity hover:opacity-80"
                  style={{ color: 'var(--info, #60a5fa)' }}
                  data-testid="root-session-link"
                >
                  <GitBranch size={10} aria-hidden="true" />
                  <span className="truncate">{session.rootSessionId}</span>
                </Link>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ── Linked features ────────────────────────────────────────────── */}
      <section>
        <SectionLabel>Features</SectionLabel>
        {linkedFeatures.length === 0 ? (
          <EmptyHint label="—" />
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {linkedFeatures.map((f) => (
              <Link
                key={f.id}
                to={planningRouteFeatureModalHref(f.id)}
                className="planning-mono inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] transition-opacity hover:opacity-80"
                style={{
                  color: 'var(--info, #60a5fa)',
                  background: 'color-mix(in oklab, var(--info, #60a5fa) 10%, transparent)',
                  border: '1px solid color-mix(in oklab, var(--info, #60a5fa) 22%, transparent)',
                }}
                data-testid={`feature-link-${f.id}`}
              >
                <Layers size={9} aria-hidden="true" />
                <span>{f.name}</span>
              </Link>
            ))}
          </div>
        )}
        {/* Also render raw IDs for any feature ID not resolved in features list */}
        {(session.linkedFeatureIds ?? []).length > 0 && linkedFeatures.length === 0 && (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {(session.linkedFeatureIds ?? []).map((fid) => (
              <Link
                key={fid}
                to={planningRouteFeatureModalHref(fid)}
                className="planning-mono inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] transition-opacity hover:opacity-80"
                style={{
                  color: 'var(--info, #60a5fa)',
                  background: 'color-mix(in oklab, var(--info, #60a5fa) 10%, transparent)',
                }}
                data-testid={`feature-link-raw-${fid}`}
              >
                <Layers size={9} aria-hidden="true" />
                <span>{fid}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* ── Phase / task context ───────────────────────────────────────── */}
      <section>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <SectionLabel>Phase context</SectionLabel>
            {(session.phaseHints ?? []).length === 0 ? (
              <EmptyHint label="—" />
            ) : (
              <div className="flex flex-wrap gap-1" data-testid="phase-hints">
                {(session.phaseHints ?? []).map((h, i) => (
                  <Chip key={i} tone="phase">{h}</Chip>
                ))}
              </div>
            )}
          </div>
          <div>
            <SectionLabel>Task context</SectionLabel>
            {(session.taskHints ?? []).length === 0 ? (
              <EmptyHint label="—" />
            ) : (
              <div className="flex flex-wrap gap-1" data-testid="task-hints">
                {(session.taskHints ?? []).map((h, i) => (
                  <Chip key={i} tone="task">{h}</Chip>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Model ─────────────────────────────────────────────────────── */}
      <section>
        <SectionLabel>Model</SectionLabel>
        <div className="flex items-center gap-2">
          <Cpu size={11} style={{ color: 'var(--ink-3)' }} aria-hidden="true" />
          <span
            className="planning-mono text-[11.5px]"
            style={{ color: 'var(--ink-1)' }}
            data-testid="model-name"
          >
            {session.modelDisplayName ?? session.model ?? 'unknown'}
          </span>
          {session.modelProvider && (
            <span
              className="planning-mono text-[10px]"
              style={{ color: 'var(--ink-3)' }}
            >
              via {session.modelProvider}
            </span>
          )}
        </div>
      </section>

      {/* ── Token / context usage ──────────────────────────────────────── */}
      <section>
        <SectionLabel>Token usage</SectionLabel>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <p
              className="planning-mono text-[10px]"
              style={{ color: 'var(--ink-4)' }}
            >
              Input
            </p>
            <p
              className="planning-mono text-[12.5px] font-semibold tabular-nums"
              style={{ color: 'var(--ink-1)' }}
              data-testid="tokens-in"
            >
              {formatTokens(totalTokensIn)}
            </p>
          </div>
          <div>
            <p
              className="planning-mono text-[10px]"
              style={{ color: 'var(--ink-4)' }}
            >
              Output
            </p>
            <p
              className="planning-mono text-[12.5px] font-semibold tabular-nums"
              style={{ color: 'var(--ink-1)' }}
              data-testid="tokens-out"
            >
              {formatTokens(totalTokensOut)}
            </p>
          </div>
          {session.currentContextTokens != null && (
            <div>
              <p
                className="planning-mono text-[10px]"
                style={{ color: 'var(--ink-4)' }}
              >
                Context
              </p>
              <p
                className="planning-mono text-[12.5px] font-semibold tabular-nums"
                style={{ color: 'var(--ink-1)' }}
                data-testid="context-tokens"
              >
                {formatTokens(session.currentContextTokens)}
              </p>
            </div>
          )}
          {ctxPct != null && (
            <div>
              <p
                className="planning-mono text-[10px]"
                style={{ color: 'var(--ink-4)' }}
              >
                Ctx used
              </p>
              <p
                className="planning-mono text-[12.5px] font-semibold tabular-nums"
                style={{ color: 'var(--ink-1)' }}
                data-testid="context-pct"
              >
                {ctxPct}
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

// ── AgentDetailModal (stateful shell with focus trap) ─────────────────────────

export interface AgentDetailModalProps {
  session: AgentSession;
  features: Feature[];
  onClose: () => void;
}

export function AgentDetailModal({
  session,
  features,
  onClose,
}: AgentDetailModalProps): JSX.Element {
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const displayName =
    (session.displayAgentType != null && session.displayAgentType !== '')
      ? humanizeAgentType(session.displayAgentType)
      : (session.agentId ?? session.title?.split(' ')[0] ?? `Agent ${session.id.slice(0, 6)}`);

  // Initial focus on close button
  useEffect(() => {
    closeBtnRef.current?.focus();
  }, []);

  // ESC to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // Focus trap: keep Tab/Shift+Tab within the dialog
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
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
    };

    dialog.addEventListener('keydown', handler);
    return () => dialog.removeEventListener('keydown', handler);
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/55"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="presentation"
      data-testid="agent-detail-modal-backdrop"
    >
      <div
        ref={dialogRef}
        className="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-xl shadow-2xl"
        style={{
          background: 'var(--surface-overlay, #1a1f2e)',
          border: '1px solid var(--line-1, #2d3347)',
        }}
        role="dialog"
        aria-modal="true"
        aria-label={`Agent details: ${displayName}`}
        data-testid="agent-detail-modal"
      >
        {/* ── Header ────────────────────────────────────────────────── */}
        <div
          className="flex items-start justify-between gap-3 px-5 py-4"
          style={{ borderBottom: '1px solid var(--line-1, #2d3347)' }}
        >
          <div className="flex-1 min-w-0">
            <p
              className="planning-serif text-[14px] font-semibold leading-snug truncate"
              style={{ color: 'var(--ink-0)' }}
              data-testid="modal-display-name"
            >
              {displayName}
            </p>
            <p
              className="planning-mono mt-0.5 text-[10.5px] truncate"
              style={{ color: 'var(--ink-3)' }}
            >
              {session.id}
            </p>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            className="shrink-0 rounded p-1 transition-colors"
            style={{
              color: 'var(--ink-3)',
              border: '1px solid var(--line-1, #2d3347)',
            }}
            aria-label="Close agent details"
            data-testid="modal-close-btn"
          >
            <X size={14} />
          </button>
        </div>

        {/* ── Content ───────────────────────────────────────────────── */}
        <AgentDetailModalContent session={session} features={features} />
      </div>
    </div>
  );
}
