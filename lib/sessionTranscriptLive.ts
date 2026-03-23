import type { SessionLog, SessionTranscriptAppendPayload } from '@/types';

export type SessionTranscriptAppendDecision =
  | { action: 'append'; nextLogs: SessionLog[]; appendedLog: SessionLog }
  | { action: 'skip'; nextLogs: SessionLog[]; reason: 'duplicate' }
  | { action: 'refetch'; nextLogs: SessionLog[]; reason: 'missing_identifier' | 'sequence_mismatch' | 'rewrite_detected' };

const normalizeText = (value: unknown): string => String(value ?? '').trim();

export const getSessionTranscriptEntryId = (log: Pick<SessionLog, 'id'> | Pick<SessionTranscriptAppendPayload, 'entryId'> | null | undefined): string =>
  normalizeText((log as { id?: unknown } | { entryId?: unknown } | null | undefined)?.id ?? (log as { entryId?: unknown } | null | undefined)?.entryId);

export const toSessionTranscriptLog = (payload: SessionTranscriptAppendPayload): SessionLog => {
  const data = payload.payload;
  return {
    id: normalizeText(data.id || payload.entryId),
    timestamp: normalizeText(data.timestamp || payload.createdAt),
    speaker: data.speaker,
    type: data.type,
    agentName: data.agentName,
    content: data.content,
    linkedSessionId: data.linkedSessionId,
    relatedToolCallId: data.relatedToolCallId,
    metadata: data.metadata,
    toolCall: data.toolCall,
  };
};

const hasSequenceMismatch = (logs: SessionLog[], sequenceNo: number): boolean => sequenceNo !== logs.length + 1;

const isEquivalentTranscriptLog = (current: SessionLog, next: SessionLog): boolean => (
  normalizeText(current.id) === normalizeText(next.id)
  && normalizeText(current.timestamp) === normalizeText(next.timestamp)
  && normalizeText(current.type) === normalizeText(next.type)
  && normalizeText(current.content) === normalizeText(next.content)
);

export const mergeSessionTranscriptAppend = (
  currentLogs: SessionLog[],
  payload: SessionTranscriptAppendPayload,
): SessionTranscriptAppendDecision => {
  const sessionId = normalizeText(payload.sessionId);
  const entryId = normalizeText(payload.entryId);
  if (!sessionId || !entryId) {
    return { action: 'refetch', nextLogs: currentLogs, reason: 'missing_identifier' };
  }

  const nextLog = toSessionTranscriptLog(payload);
  if (!nextLog.id || !nextLog.timestamp) {
    return { action: 'refetch', nextLogs: currentLogs, reason: 'missing_identifier' };
  }

  const existingLog = currentLogs.find(log => normalizeText(log.id) === nextLog.id);
  if (existingLog) {
    if (isEquivalentTranscriptLog(existingLog, nextLog)) {
      return { action: 'skip', nextLogs: currentLogs, reason: 'duplicate' };
    }
    return { action: 'refetch', nextLogs: currentLogs, reason: 'rewrite_detected' };
  }

  if (hasSequenceMismatch(currentLogs, payload.sequenceNo)) {
    return { action: 'refetch', nextLogs: currentLogs, reason: 'sequence_mismatch' };
  }

  return {
    action: 'append',
    nextLogs: [...currentLogs, nextLog],
    appendedLog: nextLog,
  };
};
