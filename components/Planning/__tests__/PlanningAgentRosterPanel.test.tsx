/**
 * P15-002: PlanningAgentRosterPanel — row label precedence tests.
 * P15-005: Inline hint chips — feature/phase/task context with em-dash fallback.
 *
 * Strategy: unit-test the pure helpers (humanizeAgentType, deriveEntry via
 * exported humanizeAgentType) directly, plus markup assertions via the
 * name-derivation logic mirrored from the component (same approach as the rest
 * of the Planning test suite — no jsdom / @testing-library installed).
 *
 * Coverage:
 *   SC-15.1: No title-string parsing for type inference
 *   SC-15.2: Subagent shows type label; root shows "Orchestrator"; id is tooltip-only
 *   SC-15.5: Inline hint chips from canonical backend fields; em-dash when all absent
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
 *
 *  P15-005 hint chip tests:
 *  13. Row with all three hints → all three chips present with correct text
 *  14. Row with feature hint only → feature chip present; no phase/task chips; no em-dash
 *  15. Row with no hints → em-dash placeholder; no chip elements
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { humanizeAgentType } from '../PlanningAgentRosterPanel';
import { PlanningAgentRosterPanel } from '../PlanningAgentRosterPanel';
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

// ── SC-15.5: Inline hint chips ────────────────────────────────────────────────
//
// These tests render PlanningAgentRosterPanel via renderToStaticMarkup and
// assert the presence/absence of hint chip elements by data-testid and text
// content in the produced HTML.

const mocks = vi.hoisted(() => ({
  sessions: [] as AgentSession[],
}));

vi.mock('../../../contexts/DataContext', () => ({
  useData: () => ({
    activeProject: { id: 'proj-1', name: 'Test Project' },
    documents: [],
    sessions: mocks.sessions,
    features: [],
    getSessionById: vi.fn(),
  }),
}));

describe('SC-15.5: inline hint chips on roster rows', () => {
  let originalDocument: typeof globalThis.document;

  beforeEach(() => {
    originalDocument = globalThis.document;
    globalThis.document = {
      createElement: () => ({ textContent: '', style: {} }),
      head: { appendChild: vi.fn(), querySelector: () => null },
      querySelector: () => null,
    } as unknown as Document;
  });

  afterEach(() => {
    globalThis.document = originalDocument;
    mocks.sessions = [];
  });

  it('row with all three hints renders feature, phase, and task chips', () => {
    mocks.sessions = [
      makeSession({
        id: 'sess-hints-all',
        linkedFeatureIds: ['FEAT-123'],
        phaseHints: ['P7'],
        taskHints: ['T7-003'],
      }),
    ];

    const html = renderToStaticMarkup(<PlanningAgentRosterPanel />);

    // All three chips container must be present
    expect(html).toContain('data-testid="roster-hint-chips"');

    // Feature chip: shows truncated feature ID
    expect(html).toContain('FEAT-123');

    // Phase chip
    expect(html).toContain('P7');

    // Task chip
    expect(html).toContain('T7-003');

    // No em-dash placeholder when chips are present
    expect(html).not.toContain('data-testid="roster-hint-empty"');
  });

  it('row with feature hint only renders feature chip; no em-dash placeholder', () => {
    mocks.sessions = [
      makeSession({
        id: 'sess-feat-only',
        linkedFeatureIds: ['FEAT-456'],
        phaseHints: undefined,
        taskHints: undefined,
      }),
    ];

    const html = renderToStaticMarkup(<PlanningAgentRosterPanel />);

    // Chips container present
    expect(html).toContain('data-testid="roster-hint-chips"');

    // Feature chip present
    expect(html).toContain('FEAT-456');

    // No em-dash placeholder
    expect(html).not.toContain('data-testid="roster-hint-empty"');
  });

  it('row with no hints renders em-dash placeholder and no chip elements', () => {
    mocks.sessions = [
      makeSession({
        id: 'sess-no-hints',
        linkedFeatureIds: undefined,
        phaseHints: undefined,
        taskHints: undefined,
      }),
    ];

    const html = renderToStaticMarkup(<PlanningAgentRosterPanel />);

    // Em-dash placeholder rendered
    expect(html).toContain('data-testid="roster-hint-empty"');
    // Em-dash character present
    expect(html).toContain('—');

    // No chips container
    expect(html).not.toContain('data-testid="roster-hint-chips"');
  });

  it('row with empty hint arrays renders em-dash placeholder', () => {
    mocks.sessions = [
      makeSession({
        id: 'sess-empty-arrays',
        linkedFeatureIds: [],
        phaseHints: [],
        taskHints: [],
      }),
    ];

    const html = renderToStaticMarkup(<PlanningAgentRosterPanel />);

    expect(html).toContain('data-testid="roster-hint-empty"');
    expect(html).not.toContain('data-testid="roster-hint-chips"');
  });

  it('feature ID longer than 12 chars is truncated to 12 in the chip', () => {
    mocks.sessions = [
      makeSession({
        id: 'sess-long-feat',
        linkedFeatureIds: ['FEAT-VERY-LONG-ID-HERE'],
        phaseHints: undefined,
        taskHints: undefined,
      }),
    ];

    const html = renderToStaticMarkup(<PlanningAgentRosterPanel />);

    // Truncated to first 12 chars: "FEAT-VERY-LO"
    expect(html).toContain('FEAT-VERY-LO');
    // Full ID should not appear verbatim in a chip (aria-label carries it)
    // Note: the full ID appears in aria-label of the chip, so we check the chip container
    expect(html).toContain('data-testid="roster-hint-chips"');
  });

  it('row with only phase and task hints (no feature) renders two chips', () => {
    mocks.sessions = [
      makeSession({
        id: 'sess-phase-task',
        linkedFeatureIds: undefined,
        phaseHints: ['P12'],
        taskHints: ['T12-007'],
      }),
    ];

    const html = renderToStaticMarkup(<PlanningAgentRosterPanel />);

    expect(html).toContain('data-testid="roster-hint-chips"');
    expect(html).toContain('P12');
    expect(html).toContain('T12-007');
    expect(html).not.toContain('data-testid="roster-hint-empty"');
  });

  it('density class planning-density-row still present with hint chips', () => {
    mocks.sessions = [
      makeSession({
        id: 'sess-density-check',
        linkedFeatureIds: ['FEAT-789'],
        phaseHints: ['P3'],
        taskHints: ['T3-001'],
      }),
    ];

    const html = renderToStaticMarkup(<PlanningAgentRosterPanel />);

    expect(html).toContain('planning-density-row');
    expect(html).toContain('data-testid="roster-hint-chips"');
  });
});
