import { describe, expect, it } from 'vitest';

import {
  getSkillMeatFeatureFlags,
  isSessionBlockInsightsEnabled,
  isStackRecommendationsEnabled,
  isUsageAttributionEnabled,
  isWorkflowAnalyticsEnabled,
  normalizeSkillMeatConfig,
} from '../agenticIntelligence';

describe('agentic intelligence feature flags', () => {
  it('defaults both intelligence surfaces to enabled', () => {
    expect(getSkillMeatFeatureFlags(null)).toEqual({
      stackRecommendationsEnabled: true,
      workflowAnalyticsEnabled: true,
      usageAttributionEnabled: true,
      sessionBlockInsightsEnabled: true,
    });
  });

  it('respects project-level overrides', () => {
    const project = {
      skillMeat: {
        featureFlags: {
          stackRecommendationsEnabled: false,
          workflowAnalyticsEnabled: true,
          usageAttributionEnabled: false,
          sessionBlockInsightsEnabled: true,
        },
      },
    };

    expect(isStackRecommendationsEnabled(project as any)).toBe(false);
    expect(isWorkflowAnalyticsEnabled(project as any)).toBe(true);
    expect(isUsageAttributionEnabled(project as any)).toBe(false);
    expect(isSessionBlockInsightsEnabled(project as any)).toBe(true);
  });

  it('defaults the SkillMeat web app URL to empty', () => {
    expect(normalizeSkillMeatConfig(null).webBaseUrl).toBe('');
  });
});
