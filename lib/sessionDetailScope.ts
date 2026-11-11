import type { AgentSession } from '../types';

export function sameSessionScope(left: AgentSession | null, right: AgentSession): boolean {
    return Boolean(left && left.id === right.id && left.projectId === right.projectId);
}

export function sessionDetailPollKey(sessionId: string | null, projectId: string | null) {
    return ['session-detail-poll', projectId, sessionId] as const;
}

export function scopedSessionFallback(sessions: AgentSession[], sessionId: string, projectId?: string) {
    return sessions.find(session => session.id === sessionId && (!projectId || session.projectId === projectId));
}
