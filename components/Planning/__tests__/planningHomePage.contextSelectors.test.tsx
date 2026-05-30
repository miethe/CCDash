/**
 * PlanningHomePage context selector / pure-logic tests.
 *
 * Strategy: Pure TypeScript unit tests — no rendering, no jsdom required.
 * Tests cover the exported helper functions from PlanningHomePage that can be
 * tested in isolation from React, such as resolvePlanningModalFeature.
 *
 * These are deliberately separate from the rendering tests in
 * planningHomePage.behavior.test.tsx so the pure logic can be validated
 * without any rendering overhead.
 */
import { describe, expect, it, vi } from 'vitest';

import type { Feature, ProjectPlanningSummary, FeatureSummaryItem } from '../../../types';

// ── Mocks (minimal — only what the module requires at load time) ──────────────

vi.mock('../../../services/live/useLiveInvalidation', () => ({
  useLiveInvalidation: () => 'idle',
}));

vi.mock('../../../services/planning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/planning')>();
  return {
    ...actual,
    getProjectPlanningSummary: vi.fn(),
    prefetchFeaturePlanningContext: vi.fn(),
  };
});

vi.mock('../../../contexts/DataContext', () => ({
  useData: () => ({ activeProject: null }),
}));

// Mock TanStack Query hooks used by PlanningHomePage so import doesn't fail.
vi.mock('../../../services/queries/planning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/queries/planning')>();
  return {
    ...actual,
    usePlanningViewQuery: vi.fn().mockReturnValue({ data: undefined, isFetching: false, error: null }),
    usePlanningFeatureContextQuery: vi.fn().mockReturnValue({ data: undefined, isFetching: false, error: null }),
  };
});

import { resolvePlanningModalFeature } from '../PlanningHomePage';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makeFeatureSummary = (overrides: Partial<FeatureSummaryItem> = {}): FeatureSummaryItem => ({
  featureId: 'feat-1',
  featureName: 'Auth Revamp',
  rawStatus: 'in-progress',
  effectiveStatus: 'in_progress',
  isMismatch: false,
  mismatchState: 'aligned',
  hasBlockedPhases: false,
  phaseCount: 3,
  blockedPhaseCount: 0,
  nodeCount: 5,
  ...overrides,
});

const makeSummary = (overrides: Partial<ProjectPlanningSummary> = {}): ProjectPlanningSummary => ({
  status: 'ok',
  dataFreshness: '2026-04-17T00:00:00Z',
  generatedAt: '2026-04-17T00:00:00Z',
  sourceRefs: [],
  projectId: 'proj-1',
  projectName: 'My Project',
  totalFeatureCount: 3,
  activeFeatureCount: 2,
  staleFeatureCount: 1,
  blockedFeatureCount: 1,
  mismatchCount: 1,
  reversalCount: 0,
  staleFeatureIds: ['feat-stale'],
  reversalFeatureIds: [],
  blockedFeatureIds: ['feat-blocked'],
  nodeCountsByType: {
    prd: 2,
    designSpec: 1,
    implementationPlan: 3,
    progress: 2,
    context: 0,
    tracker: 1,
    report: 0,
  },
  featureSummaries: [
    makeFeatureSummary({ featureId: 'feat-1', featureName: 'Auth Revamp', rawStatus: 'in-progress', effectiveStatus: 'in_progress' }),
  ],
  ...overrides,
});

const makeFeature = (overrides: Partial<Feature> = {}): Feature => ({
  id: 'feat-1',
  name: 'Auth Revamp',
  status: 'in-progress',
  totalTasks: 0,
  completedTasks: 0,
  category: '',
  tags: [],
  updatedAt: '2026-04-17T00:00:00Z',
  linkedDocs: [],
  phases: [],
  relatedFeatures: [],
  ...overrides,
});

// ── resolvePlanningModalFeature ───────────────────────────────────────────────

describe('resolvePlanningModalFeature', () => {
  it('uses the full Feature from app data when the featureId matches', () => {
    const feature = makeFeature({ id: 'enhancements/feat-1', name: 'Full Feature' });
    const resolved = resolvePlanningModalFeature('feat-1', [feature], makeSummary());
    expect(resolved).toBe(feature);
  });

  it('falls back to a summary-backed feature shell when no full feature found', () => {
    const resolved = resolvePlanningModalFeature('feat-1', [], makeSummary());
    expect(resolved).toMatchObject({
      id: 'feat-1',
      name: 'Auth Revamp',
      status: 'in-progress',
      linkedDocs: [],
      phases: [],
    });
  });

  it('returns null when featureId is not in features or summary', () => {
    const resolved = resolvePlanningModalFeature('unknown-feat', [], makeSummary({
      featureSummaries: [],
    }));
    expect(resolved).toBeNull();
  });

  it('prefers full Feature over summary shell when both match', () => {
    const fullFeature = makeFeature({ id: 'feat-1', name: 'Full Feature (authoritative)' });
    const resolved = resolvePlanningModalFeature('feat-1', [fullFeature], makeSummary());
    expect(resolved?.name).toBe('Full Feature (authoritative)');
  });

  it('matches by featureId suffix when full Feature.id has category prefix', () => {
    // Feature IDs in the app often have format: 'category/feat-id'
    const feature = makeFeature({ id: 'enhancements/feat-1', name: 'Prefixed Feature' });
    const resolved = resolvePlanningModalFeature('feat-1', [feature], makeSummary());
    expect(resolved).toBe(feature);
  });

  it('summary-backed shell has expected required fields', () => {
    const resolved = resolvePlanningModalFeature('feat-1', [], makeSummary());
    // Shape check: all required Feature fields are present
    expect(resolved).not.toBeNull();
    expect(typeof resolved!.id).toBe('string');
    expect(typeof resolved!.name).toBe('string');
    expect(Array.isArray(resolved!.linkedDocs)).toBe(true);
    expect(Array.isArray(resolved!.phases)).toBe(true);
    expect(Array.isArray(resolved!.tags)).toBe(true);
  });

  it('handles empty features array without throwing', () => {
    expect(() => {
      resolvePlanningModalFeature('feat-1', [], makeSummary());
    }).not.toThrow();
  });

  it('handles empty featureSummaries without throwing', () => {
    expect(() => {
      resolvePlanningModalFeature('unknown', [], makeSummary({ featureSummaries: [] }));
    }).not.toThrow();
  });

  it('returns null for an empty-string featureId when not in summary', () => {
    const resolved = resolvePlanningModalFeature('', [], makeSummary({ featureSummaries: [] }));
    expect(resolved).toBeNull();
  });
});
