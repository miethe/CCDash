import { describe, expect, it } from 'vitest';

import { getSkillMeatFeatureFlags, isStackRecommendationsEnabled, isWorkflowAnalyticsEnabled } from '../agenticIntelligence';

describe('agentic intelligence feature flags', () => {
  it('defaults both intelligence surfaces to enabled', () => {
    expect(getSkillMeatFeatureFlags(null)).toEqual({
      stackRecommendationsEnabled: true,
      workflowAnalyticsEnabled: true,
    });
  });

  it('respects project-level overrides', () => {
    const project = {
      skillMeat: {
        featureFlags: {
          stackRecommendationsEnabled: false,
          workflowAnalyticsEnabled: true,
        },
      },
    };

    expect(isStackRecommendationsEnabled(project as any)).toBe(false);
    expect(isWorkflowAnalyticsEnabled(project as any)).toBe(true);
  });
});
