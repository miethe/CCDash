/**
 * T3-003: Live Agent Roster Panel
 *
 * Displays running/thinking/queued/idle agent sessions alongside the triage inbox.
 * Derives state from sessions already in DataContext — no new API or SSE calls.
 *
 * State derivation (matches PlanningTopBar LiveAgentPill):
 *   active + thinkingLevel != null && != 'low'  → thinking
 *   active + not thinking                        → running
 *   status === 'queued' (future-proof)           → queued
 *   completed / everything else                  → idle
 *
 * Columns: state dot | agent name + model | current task | since
 */

import { useMemo } from 'react';

import { cn } from '@/lib/utils';
import { useData } from '@/contexts/DataContext';
import type { AgentSession } from '@/types';
import { Panel, Dot } from './primitives';

// ── Types ─────────────────────────────────────────────────────────────────────

type AgentState = 'running' | 'thinking' | 'queued' | 'idle';

interface RosterEntry {
  id: string;
  name: string;
  model: string;
  state: AgentState;
  currentTask: string;
  since: string; // ISO string or raw
  sinceLabel: string;
}

// ── State derivation ──────────────────────────────────────────────────────────

function deriveState(session: AgentSession): AgentState {
  if (session.status === 'active') {
    const tl = session.thinkingLevel;
    if (tl != null && tl !== 'low') return 'thinking';
    return 'running';
  }
  // Future-proof: if the backend ever surfaces a queued status
  if ((session.status as string) === 'queued') return 'queued';
  return 'idle';
}

function relativeTime(isoOrRaw: string): string {
  const d = new Date(isoOrRaw);
  if (Number.isNaN(d.getTime())) return isoOrRaw;
  const diffMs = Date.now() - d.getTime();
  const secs = Math.floor(diffMs / 1000);
  if (secs < 5) return 'just now';
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function deriveEntry(session: AgentSession): RosterEntry {
  const state = deriveState(session);
  const name =
    session.agentId ??
    session.title?.split(' ')[0] ??
    `Agent ${session.id.slice(0, 6)}`;
  const model =
    session.modelDisplayName ??
    session.model ??
    'unknown';
  const currentTask = session.taskId || session.title || '—';
  const since = session.startedAt;
  return {
    id: session.id,
    name,
    model,
    state,
    currentTask,
    since,
    sinceLabel: relativeTime(since),
  };
}

// ── State config ──────────────────────────────────────────────────────────────

const STATE_CONFIG: Record<
  AgentState,
  { dotColor: string; rowClass: string; label: string; glow: boolean }
> = {
  running: {
    dotColor: 'var(--ok)',
    rowClass: 'bg-[color:color-mix(in_oklab,var(--ok)_5%,transparent)]',
    label: 'running',
    glow: true,
  },
  thinking: {
    dotColor: 'var(--info, #60a5fa)',
    rowClass: 'bg-[color:color-mix(in_oklab,var(--info,#60a5fa)_5%,transparent)]',
    label: 'thinking',
    glow: true,
  },
  queued: {
    dotColor: 'var(--warn)',
    rowClass: 'bg-[color:color-mix(in_oklab,var(--warn)_5%,transparent)]',
    label: 'queued',
    glow: false,
  },
  idle: {
    dotColor: 'var(--ink-4)',
    rowClass: '',
    label: 'idle',
    glow: false,
  },
};

// Priority order for sorting
const STATE_ORDER: Record<AgentState, number> = {
  running: 0,
  thinking: 1,
  queued: 2,
  idle: 3,
};

// ── Glow keyframe (injected once) ─────────────────────────────────────────────

const GLOW_STYLE = `
@keyframes roster-dot-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 currentColor; }
  50% { opacity: 0.85; box-shadow: 0 0 6px 2px currentColor; }
}
.roster-dot-glow {
  animation: roster-dot-pulse 2s ease-in-out infinite;
}
`;

let _glowInjected = false;
function injectGlowStyle() {
  if (_glowInjected || typeof document === 'undefined') return;
  const tag = document.createElement('style');
  tag.textContent = GLOW_STYLE;
  document.head.appendChild(tag);
  _glowInjected = true;
}

// ── Row ───────────────────────────────────────────────────────────────────────

function RosterRow({
  entry,
  onPrefetchSession,
}: {
  entry: RosterEntry;
  onPrefetchSession?: (sessionId: string) => void;
}) {
  injectGlowStyle();
  const cfg = STATE_CONFIG[entry.state];

  return (
    <div
      className={cn(
        'grid items-center gap-x-3 rounded-md px-3 py-2',
        'border border-transparent',
        'transition-colors hover:border-[color:var(--line-1)]',
        cfg.rowClass,
      )}
      style={{
        gridTemplateColumns: '18px 1fr 1fr max-content',
      }}
      role="row"
      onMouseEnter={() => onPrefetchSession?.(entry.id)}
      onFocus={() => onPrefetchSession?.(entry.id)}
      tabIndex={0}
      aria-label={`Agent ${entry.name}: ${cfg.label}, model ${entry.model}, task ${entry.currentTask}, since ${entry.sinceLabel}`}
    >
      {/* State dot */}
      <div className="flex items-center justify-center">
        <Dot
          tone={cfg.dotColor}
          className={cfg.glow ? 'roster-dot-glow' : undefined}
          style={{
            width: 7,
            height: 7,
            color: cfg.dotColor,
            ...(cfg.glow
              ? { boxShadow: `0 0 5px ${cfg.dotColor}` }
              : {}),
          }}
          aria-hidden="true"
        />
        <span className="sr-only">{cfg.label}</span>
      </div>

      {/* Name + model */}
      <div className="min-w-0">
        <div
          className="truncate text-[12.5px] font-medium leading-tight"
          style={{ color: 'var(--ink-0)' }}
          title={entry.name}
        >
          {entry.name}
        </div>
        <div
          className="planning-mono truncate text-[10px] leading-tight"
          style={{ color: 'var(--ink-3)' }}
          title={entry.model}
        >
          {entry.model}
        </div>
      </div>

      {/* Current task */}
      <div
        className="planning-mono min-w-0 truncate text-[11px]"
        style={{ color: 'var(--ink-2)' }}
        title={entry.currentTask}
      >
        {entry.currentTask}
      </div>

      {/* Since */}
      <div
        className="planning-mono shrink-0 text-right text-[10.5px] tabular-nums"
        style={{ color: 'var(--ink-3)' }}
        title={entry.since}
      >
        {entry.sinceLabel}
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function RosterEmpty() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10">
      <div
        className="planning-dot"
        style={{ width: 7, height: 7, background: 'var(--ink-4)', borderRadius: '50%' }}
      />
      <p className="planning-mono text-[11px]" style={{ color: 'var(--ink-3)' }}>
        No active agents
      </p>
    </div>
  );
}

// ── Column header ─────────────────────────────────────────────────────────────

function RosterHeader() {
  return (
    <div
      className="planning-mono mb-1 grid items-center gap-x-3 px-3 pb-1"
      style={{
        gridTemplateColumns: '18px 1fr 1fr max-content',
        fontSize: 10,
        color: 'var(--ink-4)',
        borderBottom: '1px solid var(--line-1)',
        paddingBottom: 6,
      }}
      role="row"
    >
      <span role="columnheader">State</span>
      <span role="columnheader">Agent / Model</span>
      <span role="columnheader">Task</span>
      <span role="columnheader">Since</span>
    </div>
  );
}

// ── PlanningAgentRosterPanel ──────────────────────────────────────────────────

export interface PlanningAgentRosterPanelProps {
  className?: string;
}

export function PlanningAgentRosterPanel({ className }: PlanningAgentRosterPanelProps) {
  const { sessions, getSessionById } = useData();

  const entries = useMemo<RosterEntry[]>(() => {
    const mapped = sessions.map(deriveEntry);
    // Sort: running → thinking → queued → idle; then by since desc (most recent first)
    return mapped.sort((a, b) => {
      const stateSort = STATE_ORDER[a.state] - STATE_ORDER[b.state];
      if (stateSort !== 0) return stateSort;
      return new Date(b.since).getTime() - new Date(a.since).getTime();
    });
  }, [sessions]);

  const activeCount = entries.filter(
    (e) => e.state === 'running' || e.state === 'thinking',
  ).length;

  return (
    <Panel className={cn('flex flex-col p-5', className)} data-testid="planning-agent-roster">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h2
          className="planning-serif text-sm font-semibold"
          style={{ color: 'var(--ink-0)' }}
        >
          Agent Roster
        </h2>
        <span
          className="planning-mono rounded-full px-2 py-0.5 text-[11px] font-medium"
          style={{
            color: activeCount > 0 ? 'var(--ok)' : 'var(--ink-3)',
            background: activeCount > 0
              ? 'color-mix(in oklab, var(--ok) 14%, transparent)'
              : 'color-mix(in oklab, var(--ink-3) 10%, transparent)',
          }}
          aria-label={`${activeCount} active`}
        >
          {activeCount > 0 ? `${activeCount} live` : `${entries.length} agents`}
        </span>
      </div>

      {/* Table */}
      <div className="flex-1" role="table" aria-label="Live agent roster">
        {entries.length === 0 ? (
          <RosterEmpty />
        ) : (
          <div className="space-y-0.5" role="rowgroup">
            <RosterHeader />
            {entries.map((entry) => (
              <RosterRow
                key={entry.id}
                entry={entry}
                onPrefetchSession={(sessionId) => void getSessionById(sessionId)}
              />
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}
