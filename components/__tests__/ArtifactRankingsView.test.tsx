import { describe, expect, it } from 'vitest';

import type { ArtifactRankingRow } from '../../types';
import {
  formatNullableScore,
  resolveArtifactLabel,
  resolveRecommendationTypes,
} from '../Analytics/ArtifactRankingsView';

describe('ArtifactRankingsView helpers', () => {
  it('renders null or invalid scores as placeholders', () => {
    expect(formatNullableScore(null)).toBe('—');
    expect(formatNullableScore(undefined)).toBe('—');
    expect(formatNullableScore(Number.NaN)).toBe('—');
    expect(formatNullableScore(0.82)).toBe('82%');
  });

  it('resolves artifact labels from optional identifiers', () => {
    expect(resolveArtifactLabel({ displayName: 'Primary Skill' })).toBe('Primary Skill');
    expect(resolveArtifactLabel({ artifactName: 'Fallback Agent' })).toBe('Fallback Agent');
    expect(resolveArtifactLabel({ artifactUuid: 'artifact-uuid-1' })).toBe('artifact-uuid-1');
    expect(resolveArtifactLabel({})).toBe('Unknown artifact');
  });

  it('collects recommendation types from all supported response shapes', () => {
    const row = {
      recommendation: { type: 'optimization_target' },
      recommendations: [{ type: 'load_on_demand' }, { type: 'optimization_target' }],
      recommendationTypes: ['disable_candidate'],
    } as ArtifactRankingRow & { recommendationTypes: string[] };

    expect(resolveRecommendationTypes(row)).toEqual([
      'optimization_target',
      'load_on_demand',
      'disable_candidate',
    ]);
  });
});
