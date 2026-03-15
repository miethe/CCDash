const normalizeSegment = (value: string): string => value.trim().toLowerCase();

export const joinLiveTopic = (...segments: string[]): string => (
  segments.map(normalizeSegment).filter(Boolean).join('.')
);

export const executionRunTopic = (runId: string): string => joinLiveTopic('execution', 'run', runId);

export const sessionTopic = (sessionId: string): string => joinLiveTopic('session', sessionId);

