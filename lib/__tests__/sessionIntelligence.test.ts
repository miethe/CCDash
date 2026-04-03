import { describe, expect, it } from 'vitest';

import {
  aggregateSessionIntelligence,
  describeIntelligenceAvailability,
  formatConcernLabel,
  formatConcernScore,
} from '../sessionIntelligence';

describe('session intelligence helpers', () => {
  it('aggregates rollups into feature-level summaries', () => {
    const summary = aggregateSessionIntelligence([
      {
        sessionId: 'session-1',
        featureId: 'feature-1',
        rootSessionId: 'root-1',
        startedAt: '2026-04-03T00:00:00Z',
        endedAt: '2026-04-03T01:00:00Z',
        sentiment: { label: 'negative', score: -0.7, confidence: 0.9, factCount: 2, flaggedCount: 1 },
        churn: { label: 'high_churn', score: 0.8, confidence: 0.8, factCount: 3, flaggedCount: 1 },
        scopeDrift: { label: 'drifting', score: 0.6, confidence: 0.7, factCount: 1, flaggedCount: 1 },
      },
      {
        sessionId: 'session-2',
        featureId: 'feature-1',
        rootSessionId: 'root-1',
        startedAt: '2026-04-03T02:00:00Z',
        endedAt: '2026-04-03T03:00:00Z',
        sentiment: { label: 'neutral', score: 0, confidence: 0.5, factCount: 1, flaggedCount: 0 },
        churn: { label: 'stable', score: 0.1, confidence: 0.6, factCount: 1, flaggedCount: 0 },
        scopeDrift: { label: 'in_scope', score: 0.1, confidence: 0.8, factCount: 1, flaggedCount: 0 },
      },
    ]);

    expect(summary.sessionCount).toBe(2);
    expect(summary.featureIds).toEqual(['feature-1']);
    expect(summary.representativeSessionIds[0]).toBe('session-1');
    expect(summary.sentiment.label).toBe('negative');
    expect(summary.churn.flaggedSessions).toBe(1);
    expect(summary.scopeDrift.factCount).toBe(2);
  });

  it('maps local runtime profiles to unsupported intelligence availability', () => {
    const availability = describeIntelligenceAvailability(
      { storageProfile: 'local' } as never,
      null,
    );

    expect(availability.kind).toBe('unsupported');
    expect(availability.title).toBe('Enterprise-only capability');
  });

  it('formats concern labels and signed scores for UI display', () => {
    expect(formatConcernLabel('scope_drift')).toBe('Scope drift');
    expect(formatConcernScore(0.345)).toBe('+0.34');
    expect(formatConcernScore(-0.2)).toBe('-0.20');
  });
});
