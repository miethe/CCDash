import type { AgentSession, Feature } from '../types';
import { MAX_SESSION_LOG_ROWS } from '../constants';

export interface SessionFilters {
  status?: string;
  thread_kind?: string;
  conversation_family_id?: string;
  model?: string;
  model_provider?: string;
  model_family?: string;
  model_version?: string;
  platform_type?: string;
  platform_version?: string;
  include_subagents?: boolean;
  root_session_id?: string;
  start_date?: string;
  end_date?: string;
  created_start?: string;
  created_end?: string;
  completed_start?: string;
  completed_end?: string;
  updated_start?: string;
  updated_end?: string;
  min_duration?: number;
  max_duration?: number;
}

export interface SessionFetchOptions {
  force?: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export const TERMINAL_PHASE_STATUSES = new Set(['done', 'deferred']);

export const hasSessionDetail = (session: AgentSession | null | undefined): boolean => (
  Boolean(session && Array.isArray(session.logs) && session.logs.length > 0)
);

export const mergeSessionDetail = (sessions: AgentSession[], fetched: AgentSession): AgentSession[] => {
  const idx = sessions.findIndex(session => session.id === fetched.id);
  if (idx === -1) return sessions;
  const next = [...sessions];
  const logs = fetched.logs ?? [];
  let merged: AgentSession;
  if (logs.length > MAX_SESSION_LOG_ROWS) {
    const droppedCount = logs.length - MAX_SESSION_LOG_ROWS;
    const retained = logs.slice(droppedCount);
    merged = {
      ...fetched,
      logs: retained,
      transcriptTruncated: {
        droppedCount,
        firstRetainedTimestamp: retained[0]?.timestamp,
      },
    };
  } else {
    merged = fetched;
  }
  next[idx] = merged;
  return next;
};

export const matchesPhase = (phase: Feature['phases'][number], phaseId: string): boolean =>
  phase.id === phaseId || phase.phase === phaseId;

export const aggregateFeatureFromPhases = (feature: Feature, phases: Feature['phases']): Feature => {
  const totalTasks = phases.reduce((sum, phase) => sum + Math.max(phase.totalTasks || 0, 0), 0);
  const completedTasks = phases.reduce((sum, phase) => {
    const completed = Math.max(phase.completedTasks || 0, 0);
    const deferred = Math.max(phase.deferredTasks || 0, 0);
    return sum + Math.max(completed, deferred);
  }, 0);
  const deferredTasks = phases.reduce((sum, phase) => sum + Math.max(phase.deferredTasks || 0, 0), 0);
  const allTerminal = phases.length > 0 && phases.every(phase => TERMINAL_PHASE_STATUSES.has(phase.status));
  const anyInProgress = phases.some(phase => phase.status === 'in-progress');
  const anyReview = phases.some(phase => phase.status === 'review');

  const status = totalTasks > 0 && completedTasks >= totalTasks
    ? 'done'
    : allTerminal
      ? 'done'
      : anyInProgress
        ? 'in-progress'
        : anyReview
          ? 'review'
          : 'backlog';

  return {
    ...feature,
    status,
    totalTasks,
    completedTasks,
    deferredTasks,
    phases,
  };
};
