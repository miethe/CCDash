/**
 * P15-002: PlanningAgentRosterPanel — row label precedence tests.
 *
 * Strategy: unit-test the pure helpers (humanizeAgentType, deriveEntry via
 * exported humanizeAgentType) directly, plus markup assertions via the
 * name-derivation logic mirrored from the component (same approach as the rest
 * of the Planning test suite — no jsdom / @testing-library installed).
 *
 * Coverage:
 *   SC-15.1: No title-string parsing for type inference
 *   SC-15.2: Subagent shows type label; root shows "Orchestrator"; id is tooltip-only
 *
 *   1. humanizeAgentType: kebab-case → title-case words (simple, no acronym detection)
 *   2. humanizeAgentType: single-segment slug capitalises first letter
 *   3. humanizeAgentType: already-title-case "Orchestrator" passes through unchanged
 *   4. humanizeAgentType: underscore-separated slug is also handled
 *   5. humanizeAgentType: mixed separators are collapsed to single spaces
 *   6. deriveEntry: displayAgentType="backend-specialist" → name="Backend Specialist"
 *   7. deriveEntry: displayAgentType="Orchestrator" (root session) → name="Orchestrator"
 *   8. deriveEntry: displayAgentType=null → falls back to legacy logic (no crash)
 *   9. deriveEntry: displayAgentType present → agentId surfaces only as tooltip, not name
 *  10. deriveEntry: displayAgentType="" (empty string) → falls back to legacy logic
 *  11. deriveEntry: displayAgentType=null, no agentId → falls back to title word-one
 *  12. deriveEntry: displayAgentType=null, no agentId, no title → falls back to id prefix
 */

import { describe, expect, it } from 'vitest';

import { humanizeAgentType } from '../PlanningAgentRosterPanel';
import type { AgentSession } from '@/types';

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Minimal valid AgentSession for deriveEntry testing. */
function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    id: 'sess-abc123',
    taskId: 'T1-001',
    status: 'active',
    model: 'claude-sonnet-4-6',
    tokensIn: 0,
    tokensOut: 0,
    totalCost: 0,
    durationSeconds: 60,
    startedAt: new Date(Date.now() - 60_000).toISOString(),
    toolsUsed: [],
    logs: [],
    ...overrides,
  };
}

/**
 * Mirror of the name-derivation logic from deriveEntry in the component.
 * Kept in sync manually; tests validate the component's actual exported helper
 * (humanizeAgentType) plus this mirror for branch coverage.
 */
function deriveName(session: AgentSession): string {
  if (session.displayAgentType != null && session.displayAgentType !== '') {
    return humanizeAgentType(session.displayAgentType);
  }
  // legacy fallback
  return (
    (session.agentId ?? undefined) ??
    session.title?.split(' ')[0] ??
    `Agent ${session.id.slice(0, 6)}`
  );
}

function deriveTooltip(session: AgentSession): string | undefined {
  return session.agentId ?? undefined;
}

// ── humanizeAgentType ─────────────────────────────────────────────────────────

describe('humanizeAgentType', () => {
  it('converts kebab-case slug to title-case words (simple, no acronym detection)', () => {
    // "backend-specialist" → "Backend Specialist"
    expect(humanizeAgentType('backend-specialist')).toBe('Backend Specialist');
  });

  it('multi-segment slug produces title-case for each word', () => {
    expect(humanizeAgentType('frontend-design-engineer')).toBe('Frontend Design Engineer');
  });

  it('single-segment slug capitalises first letter', () => {
    expect(humanizeAgentType('orchestrator')).toBe('Orchestrator');
  });

  it('already-title-case "Orchestrator" passes through unchanged', () => {
    expect(humanizeAgentType('Orchestrator')).toBe('Orchestrator');
  });

  it('underscore-separated slug is also handled', () => {
    expect(humanizeAgentType('backend_api_specialist')).toBe('Backend Api Specialist');
  });

  it('mixed separators are all collapsed to spaces', () => {
    expect(humanizeAgentType('frontend--design__engineer')).toBe('Frontend Design Engineer');
  });
});

// ── SC-15.1 / SC-15.2: name precedence ───────────────────────────────────────

describe('roster row name precedence (SC-15.1, SC-15.2)', () => {
  it('subagent: displayAgentType slug → humanized type label', () => {
    const session = makeSession({ displayAgentType: 'backend-specialist', agentId: 'agent-xyz' });
    expect(deriveName(session)).toBe('Backend Specialist');
  });

  it('root session: displayAgentType="Orchestrator" → "Orchestrator"', () => {
    const session = makeSession({ displayAgentType: 'Orchestrator', agentId: 'agent-root' });
    expect(deriveName(session)).toBe('Orchestrator');
  });

  it('displayAgentType present → agentId is tooltip only, not primary name', () => {
    const session = makeSession({ displayAgentType: 'backend-specialist', agentId: 'agent-abc' });
    const name = deriveName(session);
    const tooltip = deriveTooltip(session);
    expect(name).toBe('Backend Specialist');
    expect(tooltip).toBe('agent-abc');
    // The primary name must not equal the raw agentId
    expect(name).not.toBe(session.agentId);
  });

  it('displayAgentType=null → falls back to agentId without crashing', () => {
    const session = makeSession({ displayAgentType: null, agentId: 'agent-fallback' });
    expect(deriveName(session)).toBe('agent-fallback');
  });

  it('displayAgentType=null and no agentId → falls back to title word-one', () => {
    const session = makeSession({ displayAgentType: null, agentId: undefined, title: 'Debug Session' });
    expect(deriveName(session)).toBe('Debug');
  });

  it('displayAgentType=null, no agentId, no title → falls back to id prefix', () => {
    const session = makeSession({ displayAgentType: null, agentId: undefined, title: undefined });
    expect(deriveName(session)).toBe('Agent sess-a');
  });

  it('displayAgentType="" (empty string) → treated as absent, falls back to legacy', () => {
    const session = makeSession({ displayAgentType: '', agentId: 'agent-legacy' });
    expect(deriveName(session)).toBe('agent-legacy');
  });
});
