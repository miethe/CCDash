import { describe, expect, it } from 'vitest';

import type { ArtifactRankingRow, SnapshotHealth } from '@/types';

function rankingFallbackSummary(row: ArtifactRankingRow) {
  return {
    title: row.displayName ?? row.artifactName ?? 'Unknown artifact',
    successScore: row.successScore?.toFixed(2) ?? '-',
    efficiencyScore: row.efficiencyScore?.toFixed(2) ?? '-',
    contextPressure: row.contextPressure == null ? 'hidden' : row.contextPressure.toFixed(2),
    identityConfidence: row.identityConfidence?.toFixed(2) ?? 'unavailable',
    recommendationType: row.recommendation?.type ?? row.recommendations?.[0]?.type ?? 'none',
  };
}

function snapshotHealthFallbackSummary(health?: SnapshotHealth | null) {
  return {
    lastFetched: health?.fetchedAt ?? 'Unknown',
    artifactCount: health?.artifactCount ?? 0,
    unresolvedCount: health?.unresolvedCount ?? null,
    stale: health?.isStale ?? false,
  };
}

describe('artifact intelligence type consumers', () => {
  it('imports artifact intelligence types from @/types and handles missing ranking fields', () => {
    const row: ArtifactRankingRow = {
      artifactUuid: 'artifact-uuid',
      recommendation: null,
    };

    expect(rankingFallbackSummary(row)).toEqual({
      title: 'Unknown artifact',
      successScore: '-',
      efficiencyScore: '-',
      contextPressure: 'hidden',
      identityConfidence: 'unavailable',
      recommendationType: 'none',
    });
  });

  it('handles absent snapshot health as a no-data state', () => {
    expect(snapshotHealthFallbackSummary(null)).toEqual({
      lastFetched: 'Unknown',
      artifactCount: 0,
      unresolvedCount: null,
      stale: false,
    });
  });
});
