/**
 * Quality-gate tests for PlanningAgentSessionDetailPanel (PASB-302/305).
 *
 * Coverage:
 *   1. Renders agent name, model, state, and session ID from the card.
 *   2. Renders all sections: lineage, feature correlation, evidence, token context,
 *      activity timeline, quick actions including AddToPromptContextButton.
 *   3. Close button renders with aria-label and data-testid.
 *   4. Weak/unknown correlation cards render appropriate confidence labels.
 *   5. Lineage section: parent relationship link is rendered.
 *   6. Evidence section: evidence items are rendered when present.
 *   7. Token context section: tokensIn/tokensOut displayed.
 *   8. Activity timeline renders markers.
 *   9. Empty states: renders graceful fallback text when sections lack data.
 *  10. Detail panel has role="complementary" and aria-label.
 *  11. data-testid="session-detail-panel" is present.
 *
 * Strategy: renderToStaticMarkup — consistent with the Planning test suite.
 * No jsdom, no @testing-library required.
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { PlanningAgentSessionDetailPanel } from '../PlanningAgentSessionDetailPanel';
import type {
  PlanningAgentSessionCard,
  SessionCorrelation,
  SessionActivityMarker,
  BoardSessionRelationship,
  SessionCorrelationEvidence,
} from '@/types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeCard(overrides: Partial<PlanningAgentSessionCard> = {}): PlanningAgentSessionCard {
  return {
    sessionId: 'sess-detail-001',
    agentName: 'Frontend Specialist',
    state: 'running',
    model: 'claude-sonnet-4-6',
    relationships: [],
    activityMarkers: [],
    ...overrides,
  };
}

function makeCorrelation(overrides: Partial<SessionCorrelation> = {}): SessionCorrelation {
  return {
    featureId: 'FEAT-001',
    featureName: 'Auth Revamp',
    confidence: 'high',
    evidence: [],
    ...overrides,
  };
}

function makeEvidence(overrides: Partial<SessionCorrelationEvidence> = {}): SessionCorrelationEvidence {
  return {
    sourceType: 'explicit_link',
    sourceLabel: 'Linked via task T3-001',
    confidence: 'high',
    ...overrides,
  };
}

function makeMarker(overrides: Partial<SessionActivityMarker> = {}): SessionActivityMarker {
  return {
    markerType: 'tool_call',
    label: 'Read file: main.ts',
    timestamp: new Date(Date.now() - 10_000).toISOString(),
    ...overrides,
  };
}

function makeRelationship(overrides: Partial<BoardSessionRelationship> = {}): BoardSessionRelationship {
  return {
    relatedSessionId: 'sess-parent-001',
    relationType: 'parent',
    agentName: 'Orchestrator',
    ...overrides,
  };
}

function render(card: PlanningAgentSessionCard): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <PlanningAgentSessionDetailPanel card={card} onClose={vi.fn()} />
    </MemoryRouter>,
  );
}

// ── Tests: panel identity / ARIA ──────────────────────────────────────────────

describe('PlanningAgentSessionDetailPanel — panel identity', () => {
  it('has role="complementary"', () => {
    const html = render(makeCard());
    expect(html).toContain('role="complementary"');
  });

  it('has data-testid="session-detail-panel"', () => {
    const html = render(makeCard());
    expect(html).toContain('data-testid="session-detail-panel"');
  });

  it('aria-label includes agent name', () => {
    const card = makeCard({ agentName: 'Backend Specialist' });
    const html = render(card);
    expect(html).toContain('Backend Specialist');
    expect(html).toContain('aria-label=');
  });
});

// ── Tests: header section ─────────────────────────────────────────────────────

describe('PlanningAgentSessionDetailPanel — header', () => {
  it('renders agent name in detail-panel-agent-name', () => {
    const html = render(makeCard({ agentName: 'Frontend Specialist' }));
    expect(html).toContain('data-testid="detail-panel-agent-name"');
    expect(html).toContain('Frontend Specialist');
  });

  it('falls back to id-derived name when agentName is absent', () => {
    const card = makeCard({ agentName: undefined, sessionId: 'sess-abc123456' });
    const html = render(card);
    // Fallback: "Agent " + last 8 chars
    expect(html).toContain('Agent ');
  });

  it('renders session ID in detail-panel-session-id', () => {
    const html = render(makeCard({ sessionId: 'sess-detail-001' }));
    expect(html).toContain('data-testid="detail-panel-session-id"');
    expect(html).toContain('sess-detail-001');
  });

  it('renders model when present', () => {
    const html = render(makeCard({ model: 'claude-opus-4-7' }));
    expect(html).toContain('claude-opus-4-7');
  });

  it('renders close button with aria-label and data-testid', () => {
    const html = render(makeCard());
    expect(html).toContain('data-testid="detail-panel-close-btn"');
    expect(html).toContain('aria-label="Close session detail panel"');
  });

  it('renders freshness badge', () => {
    const html = render(makeCard({ lastActivityAt: new Date().toISOString() }));
    expect(html).toContain('data-testid="detail-panel-freshness-badge"');
  });
});

// ── Tests: lineage section ────────────────────────────────────────────────────

describe('PlanningAgentSessionDetailPanel — lineage', () => {
  it('renders "No relationships" empty hint when relationships is empty', () => {
    const html = render(makeCard({ relationships: [] }));
    expect(html).toContain('No relationships');
  });

  it('renders parent relationship link with data-testid', () => {
    const card = makeCard({
      relationships: [makeRelationship({ relationType: 'parent', relatedSessionId: 'sess-parent-001' })],
    });
    const html = render(card);
    expect(html).toContain('data-testid="lineage-parent-sess-parent-001"');
  });

  it('renders root relationship link with data-testid', () => {
    const card = makeCard({
      relationships: [makeRelationship({ relationType: 'root', relatedSessionId: 'sess-root-000' })],
    });
    const html = render(card);
    expect(html).toContain('data-testid="lineage-root-sess-root-000"');
  });

  it('renders sibling relationship link with data-testid', () => {
    const card = makeCard({
      relationships: [makeRelationship({ relationType: 'sibling', relatedSessionId: 'sess-sib-001' })],
    });
    const html = render(card);
    expect(html).toContain('data-testid="lineage-sibling-sess-sib-001"');
  });

  it('renders current session marker with aria-current="true"', () => {
    const card = makeCard({ relationships: [makeRelationship()] });
    const html = render(card);
    expect(html).toContain('aria-current="true"');
  });
});

// ── Tests: feature correlation ────────────────────────────────────────────────

describe('PlanningAgentSessionDetailPanel — feature correlation', () => {
  it('renders "No correlation data" when correlation is absent', () => {
    const html = render(makeCard({ correlation: undefined }));
    expect(html).toContain('No correlation data');
  });

  it('renders feature name link when correlation present', () => {
    const card = makeCard({
      correlation: makeCorrelation({ featureId: 'FEAT-001', featureName: 'Auth Revamp' }),
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-feature-link"');
    expect(html).toContain('Auth Revamp');
  });

  it('renders phase when phaseNumber present', () => {
    const card = makeCard({
      correlation: makeCorrelation({ phaseNumber: 3, phaseTitle: 'Integration' }),
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-phase"');
    expect(html).toContain('P3: Integration');
  });

  it('renders task when taskId present', () => {
    const card = makeCard({
      correlation: makeCorrelation({ taskId: 'T3-001', taskTitle: 'Wire auth hook' }),
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-task"');
    expect(html).toContain('Wire auth hook');
  });
});

// ── Tests: weak/unknown correlation confidence ────────────────────────────────

describe('PlanningAgentSessionDetailPanel — confidence badges', () => {
  it('low confidence correlation renders "low" confidence pill', () => {
    const card = makeCard({
      correlation: makeCorrelation({
        confidence: 'low',
        evidence: [makeEvidence({ confidence: 'low' })],
      }),
    });
    const html = render(card);
    // ConfidencePill renders the EVIDENCE_CONFIDENCE_LABEL value
    expect(html).toContain('low');
  });

  it('unknown confidence correlation renders "?" confidence pill', () => {
    const card = makeCard({
      correlation: makeCorrelation({
        confidence: 'unknown',
        evidence: [makeEvidence({ confidence: 'unknown' })],
      }),
    });
    const html = render(card);
    expect(html).toContain('?');
  });

  it('high confidence correlation renders "high" confidence label', () => {
    const card = makeCard({
      correlation: makeCorrelation({
        confidence: 'high',
        evidence: [makeEvidence({ confidence: 'high' })],
      }),
    });
    const html = render(card);
    expect(html).toContain('high');
  });
});

// ── Tests: evidence section ───────────────────────────────────────────────────

describe('PlanningAgentSessionDetailPanel — evidence', () => {
  it('renders "No evidence items" empty hint when evidence is empty', () => {
    const card = makeCard({
      correlation: makeCorrelation({ evidence: [] }),
    });
    const html = render(card);
    expect(html).toContain('No evidence items');
  });

  it('renders evidence list with data-testid when evidence items present', () => {
    const card = makeCard({
      correlation: makeCorrelation({
        evidence: [
          makeEvidence({ sourceLabel: 'Linked via task T3-001', confidence: 'high' }),
        ],
      }),
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-evidence"');
    expect(html).toContain('Linked via task T3-001');
  });
});

// ── Tests: token context ─────────────────────────────────────────────────────

describe('PlanningAgentSessionDetailPanel — token context', () => {
  it('renders "No token data" when tokenSummary absent', () => {
    const html = render(makeCard({ tokenSummary: undefined }));
    expect(html).toContain('No token data');
  });

  it('renders tokensIn when tokenSummary present', () => {
    const card = makeCard({
      tokenSummary: { tokensIn: 1500, tokensOut: 300, totalTokens: 1800 },
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-tokens-in"');
    expect(html).toContain('1.5k');
  });

  it('renders tokensOut when tokenSummary present', () => {
    const card = makeCard({
      tokenSummary: { tokensIn: 1500, tokensOut: 300, totalTokens: 1800 },
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-tokens-out"');
    expect(html).toContain('300');
  });

  it('renders context window bar when contextWindowPct present', () => {
    const card = makeCard({
      tokenSummary: {
        tokensIn: 10000,
        tokensOut: 2000,
        totalTokens: 12000,
        contextWindowPct: 0.65,
      },
    });
    const html = render(card);
    expect(html).toContain('role="meter"');
    expect(html).toContain('Context window');
  });
});

// ── Tests: activity timeline ──────────────────────────────────────────────────

describe('PlanningAgentSessionDetailPanel — activity timeline', () => {
  it('renders "No activity markers" empty hint when activityMarkers is empty', () => {
    const html = render(makeCard({ activityMarkers: [] }));
    expect(html).toContain('No activity markers');
  });

  it('renders timeline with data-testid when markers present', () => {
    const card = makeCard({
      activityMarkers: [
        makeMarker({ markerType: 'tool_call', label: 'Read file: app.tsx' }),
      ],
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-activity"');
    expect(html).toContain('Read file: app.tsx');
  });

  it('renders activity summary pill row when markers present', () => {
    const card = makeCard({
      activityMarkers: [
        makeMarker({ markerType: 'tool_call', label: 'Tool A' }),
        makeMarker({ markerType: 'file_edit', label: 'Edit B' }),
      ],
    });
    const html = render(card);
    expect(html).toContain('aria-label="Activity summary"');
  });
});

// ── Tests: quick actions ──────────────────────────────────────────────────────

describe('PlanningAgentSessionDetailPanel — quick actions', () => {
  it('renders the AddToPromptContextButton', () => {
    const html = render(makeCard());
    expect(html).toContain('data-testid="detail-panel-add-context-btn"');
    expect(html).toContain('Add to prompt context');
  });

  it('renders transcript link when sessionId present', () => {
    const card = makeCard({ sessionId: 'sess-tx-001' });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-transcript-link"');
    expect(html).toContain('Transcript');
  });

  it('renders feature plan link when correlation.featureId present', () => {
    const card = makeCard({
      correlation: makeCorrelation({ featureId: 'FEAT-002' }),
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-feature-plan-link"');
    expect(html).toContain('Feature Plan');
  });

  it('renders phase ops link when correlation has featureId and phaseNumber', () => {
    const card = makeCard({
      correlation: makeCorrelation({ featureId: 'FEAT-002', phaseNumber: 5 }),
    });
    const html = render(card);
    expect(html).toContain('data-testid="detail-panel-phase-ops-link"');
    expect(html).toContain('Phase Ops');
  });

  it('renders "No actions available" hint when sessionId is empty and no feature', () => {
    const card = makeCard({ sessionId: '', correlation: undefined });
    const html = render(card);
    expect(html).toContain('No actions available');
  });
});
