import { Project, SkillMeatFeatureFlags } from '../types';

export const DEFAULT_SKILLMEAT_FEATURE_FLAGS: SkillMeatFeatureFlags = {
  stackRecommendationsEnabled: true,
  workflowAnalyticsEnabled: true,
};

export const getSkillMeatFeatureFlags = (project?: Pick<Project, 'skillMeat'> | null): SkillMeatFeatureFlags => ({
  ...DEFAULT_SKILLMEAT_FEATURE_FLAGS,
  ...(project?.skillMeat?.featureFlags || {}),
});

export const isStackRecommendationsEnabled = (project?: Pick<Project, 'skillMeat'> | null): boolean => (
  getSkillMeatFeatureFlags(project).stackRecommendationsEnabled
);

export const isWorkflowAnalyticsEnabled = (project?: Pick<Project, 'skillMeat'> | null): boolean => (
  getSkillMeatFeatureFlags(project).workflowAnalyticsEnabled
);
