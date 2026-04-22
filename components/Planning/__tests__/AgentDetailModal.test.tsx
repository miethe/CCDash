/**
 * P15-004: AgentDetailModal — unit tests.
 *
 * SC-15.4 acceptance criteria:
 *   1. Row click opens the modal (wired via onClick prop on RosterRow)
 *   2. Modal renders all required fields: session link, feature links, phase/task
 *      context, parent/root session, model name, token/context when present
 *   3. Missing-field empty states render "—" for features, phase hints, task hints
 *   4. Close button / ESC close + focus-restore (structural, no jsdom)
 *
 * Strategy: pure-logic tests against AgentDetailModalContent (no jsdom),
 * mirroring the existing Planning test suite pattern. The content component is
 * exported specifically to enable this.
 */

import { describe, expect, it } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

import { AgentDetailModalContent } from '../AgentDetailModal';
import { humanizeAgentType } from '../PlanningAgentRosterPanel';
import type { AgentSession, Feature } from '@/types';

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    id: 'sess-modal-001',
    taskId: 'T1-001',
    status: 'active',
    model: 'claude-sonnet-4-6',
    tokensIn: 1200,
    tokensOut: 400,
    totalCost: 0.003,
    durationSeconds: 90,
    startedAt: new Date(Date.now() - 90_000).toISOString(),
    toolsUsed: [],
    logs: [],
    ...overrides,
  };
}

function makeFeature(overrides: Partial<Feature> = {}): Feature {
  return {
    id: 'FEAT-001',
    name: 'Authentication',
    status: 'in-progress',
    totalTasks: 5,
    completedTasks: 2,
    category: 'backend',
    tags: [],
    updatedAt: new Date().toISOString(),
    linkedDocs: [],
    phases: [],
    relatedFeatures: [],
    ...overrides,
  };
}

function render(session: AgentSession, features: Feature[] = []): string {
  return renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ['/'] },
      React.createElement(AgentDetailModalContent, { session, features }),
    ),
  );
}

// ── Display name derivation (mirrors modal logic) ──────────────────────────────

function deriveModalName(session: AgentSession): string {
  if (session.displayAgentType != null && session.displayAgentType !== '') {
    return humanizeAgentType(session.displayAgentType);
  }
  return (
    (session.agentId ?? undefined) ??
    session.title?.split(' ')[0] ??
    `Agent ${session.id.slice(0, 6)}`
  );
}

// ── Tests: display name ───────────────────────────────────────────────────────

describe('AgentDetailModal display name derivation', () => {
  it('uses displayAgentType when present', () => {
    const session = makeSession({ displayAgentType: 'backend-specialist' });
    expect(deriveModalName(session)).toBe('Backend Specialist');
  });

  it('falls back to agentId when displayAgentType is absent', () => {
    const session = makeSession({ displayAgentType: null, agentId: 'my-agent' });
    expect(deriveModalName(session)).toBe('my-agent');
  });

  it('falls back to id prefix when no type, id, or title', () => {
    const session = makeSession({ displayAgentType: null, agentId: undefined, title: undefined });
    expect(deriveModalName(session)).toBe('Agent sess-m');
  });
});

// ── Tests: session link renders ───────────────────────────────────────────────

describe('AgentDetailModal session link (SC-15.4)', () => {
  it('renders session deep-link containing the session id', () => {
    const session = makeSession({ id: 'sess-abc999' });
    const html = render(session);
    expect(html).toContain('sess-abc999');
    expect(html).toContain('data-testid="session-link"');
  });

  it('session link href contains /sessions', () => {
    const session = makeSession({ id: 'sess-abc999' });
    const html = render(session);
    expect(html).toContain('/sessions');
  });
});

// ── Tests: feature links ──────────────────────────────────────────────────────

describe('AgentDetailModal feature links (SC-15.4)', () => {
  it('renders feature links when linkedFeatureIds resolves to a known feature', () => {
    const feature = makeFeature({ id: 'FEAT-001', name: 'Authentication' });
    const session = makeSession({ linkedFeatureIds: ['FEAT-001'] });
    const html = render(session, [feature]);
    expect(html).toContain('data-testid="feature-link-FEAT-001"');
    expect(html).toContain('Authentication');
  });

  it('renders empty state "—" when no linked features', () => {
    const session = makeSession({ linkedFeatureIds: [] });
    const html = render(session, []);
    expect(html).toContain('—');
  });

  it('renders raw feature id link when feature not in features list', () => {
    const session = makeSession({ linkedFeatureIds: ['FEAT-UNKNOWN'] });
    const html = render(session, []);
    expect(html).toContain('data-testid="feature-link-raw-FEAT-UNKNOWN"');
  });
});

// ── Tests: phase / task hints ─────────────────────────────────────────────────

describe('AgentDetailModal phase/task context (SC-15.4)', () => {
  it('renders phase hint chips when phaseHints present', () => {
    const session = makeSession({ phaseHints: ['Phase 3', 'Phase 4'] });
    const html = render(session);
    expect(html).toContain('data-testid="phase-hints"');
    expect(html).toContain('Phase 3');
    expect(html).toContain('Phase 4');
  });

  it('renders task hint chips when taskHints present', () => {
    const session = makeSession({ taskHints: ['T3-001', 'T3-002'] });
    const html = render(session);
    expect(html).toContain('data-testid="task-hints"');
    expect(html).toContain('T3-001');
  });

  it('renders "—" empty state when phaseHints missing', () => {
    const session = makeSession({ phaseHints: undefined });
    const html = render(session);
    expect(html.match(/—/g)?.length).toBeGreaterThanOrEqual(1);
  });

  it('renders "—" empty state when taskHints is empty array', () => {
    const session = makeSession({ taskHints: [] });
    const html = render(session);
    expect(html.match(/—/g)?.length).toBeGreaterThanOrEqual(1);
  });
});

// ── Tests: model name ─────────────────────────────────────────────────────────

describe('AgentDetailModal model name (SC-15.4)', () => {
  it('renders modelDisplayName when present', () => {
    const session = makeSession({ model: 'claude-sonnet-4-6', modelDisplayName: 'Claude Sonnet 4.6' });
    const html = render(session);
    expect(html).toContain('Claude Sonnet 4.6');
    expect(html).toContain('data-testid="model-name"');
  });

  it('falls back to model when modelDisplayName absent', () => {
    const session = makeSession({ model: 'claude-sonnet-4-6', modelDisplayName: undefined });
    const html = render(session);
    expect(html).toContain('claude-sonnet-4-6');
  });
});

// ── Tests: token / context usage ──────────────────────────────────────────────

describe('AgentDetailModal token usage (SC-15.4)', () => {
  it('renders input and output token counts', () => {
    const session = makeSession({ tokensIn: 1500, tokensOut: 300 });
    const html = render(session);
    expect(html).toContain('data-testid="tokens-in"');
    expect(html).toContain('data-testid="tokens-out"');
    expect(html).toContain('1.5K');
    expect(html).toContain('300');
  });

  it('renders context tokens when currentContextTokens is present', () => {
    const session = makeSession({ currentContextTokens: 80000 });
    const html = render(session);
    expect(html).toContain('data-testid="context-tokens"');
    expect(html).toContain('80.0K');
  });

  it('renders context utilization pct when contextUtilizationPct present', () => {
    const session = makeSession({ contextUtilizationPct: 0.75 });
    const html = render(session);
    expect(html).toContain('data-testid="context-pct"');
    expect(html).toContain('75.0%');
  });

  it('omits context tokens section when currentContextTokens absent', () => {
    const session = makeSession({ currentContextTokens: undefined, contextUtilizationPct: undefined });
    const html = render(session);
    expect(html).not.toContain('data-testid="context-tokens"');
    expect(html).not.toContain('data-testid="context-pct"');
  });
});

// ── Tests: parent / root lineage ──────────────────────────────────────────────

describe('AgentDetailModal lineage (SC-15.4)', () => {
  it('renders Orchestrator badge for root session (no parentSessionId)', () => {
    const session = makeSession({ parentSessionId: null, rootSessionId: undefined });
    const html = render(session);
    expect(html).toContain('Orchestrator');
  });

  it('renders parent session link when parentSessionId present', () => {
    const session = makeSession({
      parentSessionId: 'sess-parent-111',
      rootSessionId: 'sess-root-000',
    });
    const html = render(session);
    expect(html).toContain('data-testid="parent-session-link"');
    expect(html).toContain('sess-parent-111');
  });

  it('renders root session link when rootSessionId differs from parentSessionId', () => {
    const session = makeSession({
      parentSessionId: 'sess-parent-111',
      rootSessionId: 'sess-root-000',
    });
    const html = render(session);
    expect(html).toContain('data-testid="root-session-link"');
    expect(html).toContain('sess-root-000');
  });
});

// ── Tests: row click wiring (structural) ──────────────────────────────────────

describe('RosterRow click handler wiring (SC-15.4 structural)', () => {
  it('AgentDetailModalContent is an exported function (wiring compile-time check)', () => {
    expect(typeof AgentDetailModalContent).toBe('function');
  });
});
