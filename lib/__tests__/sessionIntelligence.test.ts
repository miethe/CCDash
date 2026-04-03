import { describe, expect, it } from 'vitest';

import type { RuntimeStatus } from '../../services/runtimeProfile';
import type { SessionIntelligenceCapability, SessionIntelligenceSessionRollup } from '../../types';
import {
  aggregateSessionIntelligence,
  describeIntelligenceAvailability,
  formatConcernLabel,
  formatConcernScore,
} from '../sessionIntelligence';

const makeRuntimeStatus = (overrides: Partial<RuntimeStatus> = {}): RuntimeStatus => ({
  health: 'ok',
  database: 'ok',
  watcher: 'ok',
  profile: 'local',
  startupSync: 'idle',
  analyticsSnapshots: 'idle',
  telemetryExports: 'not_applicable',
  jobsEnabled: true,
  storageMode: 'filesystem',
  storageProfile: 'local',
  storageBackend: 'sqlite',
  recommendedStorageProfile: 'local',
  supportedStorageProfiles: ['local'],
  filesystemSourceOfTruth: true,
  sharedPostgresEnabled: false,
  storageIsolationMode: 'project',
  supportedStorageIsolationModes: ['project'],
  storageCanonicalStore: 'sqlite',
  storageSchema: 'main',
  canonicalSessionStore: 'sqlite',
  ...overrides,
});

const makeCapability = (overrides: Partial<SessionIntelligenceCapability> = {}): SessionIntelligenceCapability => ({
  supported: true,
  authoritative: true,
  storageProfile: 'enterprise',
  searchMode: 'semantic',
  detail: 'Canonical transcript intelligence is available.',
  ...overrides,
});

const makeRollup = (overrides: Partial<SessionIntelligenceSessionRollup> = {}): SessionIntelligenceSessionRollup => ({
  sessionId: 'session-1',
  featureId: 'feature-1',
  rootSessionId: 'root-1',
  startedAt: '2026-04-03T00:00:00Z',
  endedAt: '2026-04-03T00:05:00Z',
  sentiment: { label: 'negative', score: -0.7, confidence: 0.8, factCount: 2, flaggedCount: 1 },
  churn: { label: 'looping', score: 0.6, confidence: 0.75, factCount: 3, flaggedCount: 1 },
  scopeDrift: { label: 'drifting', score: 0.4, confidence: 0.7, factCount: 1, flaggedCount: 1 },
  ...overrides,
});

describe('sessionIntelligence helpers', () => {
  it('aggregates rollups into feature-level summaries', () => {
    const aggregate = aggregateSessionIntelligence([
      makeRollup(),
      makeRollup({
        sessionId: 'session-2',
        sentiment: { label: 'mixed', score: -0.2, confidence: 0.5, factCount: 1, flaggedCount: 0 },
        churn: { label: 'stable', score: 0.1, confidence: 0.6, factCount: 1, flaggedCount: 0 },
        scopeDrift: { label: 'in_scope', score: 0, confidence: 0.4, factCount: 0, flaggedCount: 0 },
      }),
    ]);

    expect(aggregate.sessionCount).toBe(2);
    expect(aggregate.sentiment.flaggedSessions).toBe(1);
    expect(aggregate.churn.factCount).toBe(4);
    expect(aggregate.representativeSessionIds[0]).toBe('session-1');
  });

  it('treats local mode as unsupported without capability support', () => {
    const availability = describeIntelligenceAvailability(makeRuntimeStatus(), null);

    expect(availability.kind).toBe('unsupported');
    expect(availability.message).toContain('local storage mode');
  });

  it('treats authoritative capability as available', () => {
    const availability = describeIntelligenceAvailability(
      makeRuntimeStatus({ storageProfile: 'enterprise', storageBackend: 'postgres' }),
      makeCapability(),
    );

    expect(availability.kind).toBe('available');
    expect(availability.title).toContain('Enterprise');
  });

  it('formats concern labels and scores for UI chips', () => {
    expect(formatConcernLabel('scope_drift')).toBe('Scope drift');
    expect(formatConcernScore(0.42)).toBe('+0.42');
    expect(formatConcernScore(-0.3)).toBe('-0.30');
  });
});
