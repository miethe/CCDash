const normalizeSegment = (value: string): string => value.trim().toLowerCase();

export const joinLiveTopic = (...segments: string[]): string => (
  segments.map(normalizeSegment).filter(Boolean).join('.')
);

export const executionRunTopic = (runId: string): string => joinLiveTopic('execution', 'run', runId);

export const sessionTopic = (sessionId: string): string => joinLiveTopic('session', sessionId);

export const featureTopic = (featureId: string): string => joinLiveTopic('feature', featureId);

export const projectFeaturesTopic = (projectId: string): string => joinLiveTopic('project', projectId, 'features');

export const projectTestsTopic = (projectId: string): string => joinLiveTopic('project', projectId, 'tests');

export const projectOpsTopic = (projectId: string): string => joinLiveTopic('project', projectId, 'ops');
