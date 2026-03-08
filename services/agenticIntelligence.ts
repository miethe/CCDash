import { Project, SkillMeatFeatureFlags } from '../types';

export const DEFAULT_SKILLMEAT_FEATURE_FLAGS: SkillMeatFeatureFlags = {
  stackRecommendationsEnabled: true,
  workflowAnalyticsEnabled: true,
};

export const defaultSkillMeatConfig = () => ({
  enabled: false,
  baseUrl: '',
  projectId: '',
  collectionId: '',
  aaaEnabled: false,
  apiKey: '',
  requestTimeoutSeconds: 5,
  featureFlags: { ...DEFAULT_SKILLMEAT_FEATURE_FLAGS },
});

export const normalizeSkillMeatConfig = (project?: Pick<Project, 'skillMeat'> | null): Project['skillMeat'] => {
  const legacyConfig = (project?.skillMeat || {}) as Project['skillMeat'] & { workspaceId?: string };
  const collectionId = legacyConfig.collectionId || legacyConfig.workspaceId || '';
  return {
    ...defaultSkillMeatConfig(),
    ...legacyConfig,
    collectionId,
    featureFlags: {
      ...DEFAULT_SKILLMEAT_FEATURE_FLAGS,
      ...(legacyConfig.featureFlags || {}),
    },
  };
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
