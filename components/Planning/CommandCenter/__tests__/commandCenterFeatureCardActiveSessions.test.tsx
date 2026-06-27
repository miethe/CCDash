/**
 * T3-001: Active-session chip row on CommandCenterFeatureCard.
 *
 * Strategy: renderToStaticMarkup — no DOM/jsdom required, matches established
 * test pattern in __tests__/multiProjectPerformanceA11y.test.tsx.
 *
 * Coverage:
 *   1. Chip row renders when activeSessions is non-empty.
 *   2. Chip row is absent when activeSessions is undefined (resilience).
 *   3. Chip row is absent when activeSessions is null (resilience).
 *   4. Chip row is absent when activeSessions is empty array (resilience).
 *   5. Each chip links to #/sessions/{sessionId} (transcript link).
 *   6. Agent name displayed in chip (falls back to "agent" when absent).
 *   7. "+N" overflow fires at MAX_CHIPS threshold (3 visible, overflow shown).
 *   8. No overflow indicator when session count ≤ MAX_CHIPS.
 *   9. Pulsing green dot present on each chip (motion-safe:animate-pulse).
 *  10. AC-CWD-EXCLUSION — no access to session_forensics_json / workingDirectories.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { AggregateWorkItemSession, PlanningCommandCenterItem } from '@/types';
import { CommandCenterFeatureCard } from '../CommandCenterFeatureCard';

// ── Minimal fixture factory ───────────────────────────────────────────────────

function makeItem(
  activeSessions?: AggregateWorkItemSession[] | null,
): PlanningCommandCenterItem {
  // Cast through unknown: the fixture only needs the fields that
  // CommandCenterFeatureCard actually reads.  Required-field completeness
  // is a runtime concern for the backend; the component reads each field
  // with optional chaining / fallbacks.
  return {
    feature: {
      featureId: 'FEAT-001',
      featureSlug: 'feat-001',
      name: 'Test Feature',
      category: 'enhancement',
      tags: [],
      priority: 'medium',
      summary: 'A test feature summary.',
    },
    status: {
      effectiveStatus: 'in_progress',
      rawStatus: 'in_progress',
      planningSignal: 'on_track',
      mismatchState: 'none',
      isMismatch: false,
    },
    storyPoints: { total: 5, remaining: 3, completed: 2 },
    phase: { currentPhase: 2, totalPhases: 5, completedPhases: 1 },
    artifacts: [],
    relatedFiles: [],
    phaseRows: [],
    blockers: [],
    lastActivity: {},
    capabilities: {
      copyCommand: true,
      launch: true,
      review: false,
      merge: false,
      cleanup: false,
      openPr: false,
      editCommand: false,
    },
    // activeSessions is optional; null must also be handled (resilience AC).
    activeSessions: activeSessions ?? undefined,
  } as unknown as PlanningCommandCenterItem;
}

function makeSession(
  sessionId: string,
  agentName?: string,
): AggregateWorkItemSession {
  return { sessionId, agentName };
}

// ── Helper: render card to HTML string ───────────────────────────────────────

function renderCard(
  activeSessions?: AggregateWorkItemSession[] | null,
): string {
  const item = makeItem(activeSessions);
  return renderToStaticMarkup(
    createElement(CommandCenterFeatureCard, {
      item,
      commandValue: '/dev:execute-phase',
    }),
  );
}

// ── 1. Chip row renders when activeSessions is non-empty ──────────────────────

describe('Active-session chip row — rendering', () => {
  it('renders the chip row when activeSessions has one session', () => {
    const html = renderCard([makeSession('sess-abc', 'Sonnet')]);
    expect(html).toContain('data-testid="command-center-active-sessions"');
    expect(html).toContain('data-testid="command-center-session-chip"');
  });

  it('renders the chip row when activeSessions has multiple sessions', () => {
    const html = renderCard([
      makeSession('sess-001', 'Sonnet'),
      makeSession('sess-002', 'Haiku'),
    ]);
    expect(html).toContain('data-testid="command-center-active-sessions"');
    const chips = html.match(/data-testid="command-center-session-chip"/g) ?? [];
    expect(chips.length).toBe(2);
  });
});

// ── 2–4. Resilience — absent or empty activeSessions ─────────────────────────

describe('Active-session chip row — resilience (AC-ACTIVE-SESSION-CHIP, §resilience)', () => {
  it('does NOT render chip row when activeSessions is undefined', () => {
    const html = renderCard(undefined);
    expect(html).not.toContain('data-testid="command-center-active-sessions"');
    expect(html).not.toContain('data-testid="command-center-session-chip"');
  });

  it('does NOT throw when activeSessions is undefined', () => {
    expect(() => renderCard(undefined)).not.toThrow();
  });

  it('does NOT render chip row when activeSessions is null', () => {
    const html = renderCard(null);
    expect(html).not.toContain('data-testid="command-center-active-sessions"');
    expect(html).not.toContain('data-testid="command-center-session-chip"');
  });

  it('does NOT throw when activeSessions is null', () => {
    expect(() => renderCard(null)).not.toThrow();
  });

  it('does NOT render chip row when activeSessions is empty array', () => {
    const html = renderCard([]);
    expect(html).not.toContain('data-testid="command-center-active-sessions"');
    expect(html).not.toContain('data-testid="command-center-session-chip"');
  });

  it('does NOT throw when activeSessions is empty array', () => {
    expect(() => renderCard([])).not.toThrow();
  });
});

// ── 5. Transcript link navigates to #/sessions/{sessionId} ───────────────────

describe('Active-session chip row — transcript link', () => {
  it('chip href points to #/sessions/{sessionId}', () => {
    const html = renderCard([makeSession('sess-xyz', 'Opus')]);
    expect(html).toContain('href="#/sessions/sess-xyz"');
  });

  it('each chip carries data-session-id attribute', () => {
    const html = renderCard([makeSession('sess-t1', 'Sonnet')]);
    expect(html).toContain('data-session-id="sess-t1"');
  });

  it('multiple chips each link to their own session', () => {
    const html = renderCard([
      makeSession('sess-a', 'Alpha'),
      makeSession('sess-b', 'Beta'),
    ]);
    expect(html).toContain('href="#/sessions/sess-a"');
    expect(html).toContain('href="#/sessions/sess-b"');
  });
});

// ── 6. Agent name display ─────────────────────────────────────────────────────

describe('Active-session chip row — agent name', () => {
  it('shows agentName when present', () => {
    const html = renderCard([makeSession('sess-1', 'Sonnet')]);
    expect(html).toContain('Sonnet');
  });

  it('falls back to "agent" when agentName is absent', () => {
    const html = renderCard([makeSession('sess-2')]);
    expect(html).toContain('agent');
  });
});

// ── 7. "+N" overflow fires at MAX_CHIPS threshold ─────────────────────────────

describe('Active-session chip row — overflow (+N)', () => {
  it('shows all chips when session count equals MAX_CHIPS (3)', () => {
    const sessions = [
      makeSession('sess-1', 'A1'),
      makeSession('sess-2', 'A2'),
      makeSession('sess-3', 'A3'),
    ];
    const html = renderCard(sessions);
    const chips = html.match(/data-testid="command-center-session-chip"/g) ?? [];
    expect(chips.length).toBe(3);
    expect(html).not.toContain('data-testid="command-center-session-overflow"');
  });

  it('shows MAX_CHIPS chips and overflow indicator when session count exceeds 3', () => {
    const sessions = [
      makeSession('sess-1', 'A1'),
      makeSession('sess-2', 'A2'),
      makeSession('sess-3', 'A3'),
      makeSession('sess-4', 'A4'),
      makeSession('sess-5', 'A5'),
    ];
    const html = renderCard(sessions);

    const chips = html.match(/data-testid="command-center-session-chip"/g) ?? [];
    expect(chips.length).toBe(3);

    expect(html).toContain('data-testid="command-center-session-overflow"');
    // overflow = 5 - 3 = 2
    expect(html).toContain('+2');
  });

  it('overflow count is correct for exactly 4 sessions', () => {
    const sessions = [
      makeSession('s1'),
      makeSession('s2'),
      makeSession('s3'),
      makeSession('s4'),
    ];
    const html = renderCard(sessions);
    expect(html).toContain('+1');
  });
});

// ── 8. No overflow when count ≤ MAX_CHIPS ────────────────────────────────────

describe('Active-session chip row — no overflow for small counts', () => {
  it('no overflow element when there is exactly 1 session', () => {
    const html = renderCard([makeSession('s1', 'Solo')]);
    expect(html).not.toContain('data-testid="command-center-session-overflow"');
  });

  it('no overflow element when there are 2 sessions', () => {
    const html = renderCard([makeSession('s1'), makeSession('s2')]);
    expect(html).not.toContain('data-testid="command-center-session-overflow"');
  });
});

// ── 9. Pulsing green dot (reduced-motion safe) ────────────────────────────────

describe('Active-session chip row — pulse animation (motion-safe)', () => {
  it('each chip has a pulsing dot using motion-safe:animate-pulse', () => {
    const html = renderCard([makeSession('sess-p1', 'Opus')]);
    expect(html).toContain('motion-safe:animate-pulse');
  });

  it('bare animate-pulse (without motion-safe prefix) does NOT appear', () => {
    const html = renderCard([makeSession('sess-p2', 'Haiku')]);
    // Negative lookahead: ensure no "animate-pulse" that isn't preceded by "motion-safe:"
    expect(html).not.toMatch(/(?<!motion-safe:)animate-pulse/);
  });
});

// ── 10. AC-CWD-EXCLUSION — no workingDirectories / session_forensics_json ─────

describe('AC-CWD-EXCLUSION', () => {
  it('chip row renders without accessing workingDirectories or session_forensics_json', () => {
    // Provide an activeSessions entry with NO forensics fields.
    // If the component tried to access forensics, TypeScript would flag it
    // at compile-time. This runtime test confirms no string leakage.
    const html = renderCard([makeSession('sess-fw', 'Sonnet')]);
    expect(html).not.toContain('workingDirectories');
    expect(html).not.toContain('session_forensics_json');
    expect(html).toContain('data-testid="command-center-session-chip"');
  });
});
