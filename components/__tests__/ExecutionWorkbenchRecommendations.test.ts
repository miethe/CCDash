import { describe, expect, it } from 'vitest';

import {
  formatConfidence,
  formatRecommendationLabel,
  hasStaleSnapshotWarning,
  normalizeEvidenceEntries,
  resolveAffectedArtifactLabel,
} from '../execution/ExecutionWorkbenchRecommendations';
import type { ArtifactRecommendationItem } from '../../services/analytics';

describe('ExecutionWorkbenchRecommendations helpers', () => {
  it('formats recommendation labels and confidence values', () => {
    expect(formatRecommendationLabel('workflow_specific_swap')).toBe('Workflow Specific Swap');
    expect(formatRecommendationLabel(null)).toBe('Recommendation');
    expect(formatConfidence(0.734)).toBe('73%');
    expect(formatConfidence(null)).toBe('n/a');
  });

  it('normalizes object evidence and stale snapshot signals', () => {
    const recommendation: ArtifactRecommendationItem = {
      type: 'insufficient_data',
      rationaleCode: 'stale_snapshot',
      evidence: {
        snapshotFetchedAt: '2026-04-01T00:00:00Z',
        suppressedType: 'optimization_target',
      },
    };

    expect(normalizeEvidenceEntries(recommendation.evidence)).toEqual([
      { key: 'Snapshot Fetched At', value: '2026-04-01T00:00:00Z' },
      { key: 'Suppressed Type', value: 'optimization_target' },
    ]);
    expect(hasStaleSnapshotWarning(recommendation)).toBe(true);
  });

  it('falls back from affected artifacts to scope', () => {
    expect(resolveAffectedArtifactLabel({ affectedArtifactIds: ['skill:planner'] })).toBe('skill:planner');
    expect(resolveAffectedArtifactLabel({ scope: 'project' })).toBe('project');
    expect(resolveAffectedArtifactLabel({})).toBe('Project artifact set');
  });
});
