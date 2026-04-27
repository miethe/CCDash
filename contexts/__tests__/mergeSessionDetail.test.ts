import { describe, it, expect } from 'vitest';
import { mergeSessionDetail } from '../dataContextShared';
import { MAX_SESSION_LOG_ROWS } from '../../constants';
import type { AgentSession, SessionLog } from '../../types';

function makeLog(id: string, timestamp: string): SessionLog {
  return {
    id,
    timestamp,
    speaker: 'agent',
    type: 'message',
    content: `log ${id}`,
  };
}

function makeSession(id: string, logCount: number): AgentSession {
  const logs = Array.from({ length: logCount }, (_, i) =>
    makeLog(`log-${i}`, `2026-01-01T00:${String(i).padStart(2, '0')}:00Z`)
  );
  return {
    id,
    taskId: 'T-001',
    status: 'completed',
    model: 'claude-test',
    durationSeconds: 10,
    tokensIn: 0,
    tokensOut: 0,
    totalCost: 0,
    startedAt: '2026-01-01T00:00:00Z',
    toolsUsed: [],
    logs,
  };
}

describe('mergeSessionDetail ring-buffer cap', () => {
  it('does not truncate when logs are below the cap', () => {
    const session = makeSession('s1', 100);
    const sessions = [{ ...session, logs: [] }];
    const result = mergeSessionDetail(sessions, session);
    expect(result[0].logs).toHaveLength(100);
    expect(result[0].transcriptTruncated).toBeUndefined();
  });

  it('does not truncate when logs equal the cap exactly', () => {
    const session = makeSession('s1', MAX_SESSION_LOG_ROWS);
    const sessions = [{ ...session, logs: [] }];
    const result = mergeSessionDetail(sessions, session);
    expect(result[0].logs).toHaveLength(MAX_SESSION_LOG_ROWS);
    expect(result[0].transcriptTruncated).toBeUndefined();
  });

  it('caps logs to MAX_SESSION_LOG_ROWS and sets correct droppedCount', () => {
    const overLimit = MAX_SESSION_LOG_ROWS + 300;
    const session = makeSession('s1', overLimit);
    const sessions = [{ ...session, logs: [] }];
    const result = mergeSessionDetail(sessions, session);
    expect(result[0].logs).toHaveLength(MAX_SESSION_LOG_ROWS);
    expect(result[0].transcriptTruncated).toBeDefined();
    expect(result[0].transcriptTruncated!.droppedCount).toBe(300);
  });

  it('retains the newest (tail) rows when dropping oldest', () => {
    const overLimit = MAX_SESSION_LOG_ROWS + 1;
    const session = makeSession('s1', overLimit);
    const sessions = [{ ...session, logs: [] }];
    const result = mergeSessionDetail(sessions, session);
    // The first retained log should be index 1 (second log), not index 0
    expect(result[0].logs[0].id).toBe('log-1');
    expect(result[0].logs[MAX_SESSION_LOG_ROWS - 1].id).toBe(`log-${overLimit - 1}`);
  });

  it('sets firstRetainedTimestamp to the first retained log timestamp', () => {
    const overLimit = MAX_SESSION_LOG_ROWS + 50;
    const session = makeSession('s1', overLimit);
    const sessions = [{ ...session, logs: [] }];
    const result = mergeSessionDetail(sessions, session);
    const expectedTimestamp = session.logs[50].timestamp;
    expect(result[0].transcriptTruncated!.firstRetainedTimestamp).toBe(expectedTimestamp);
  });

  it('returns original sessions array when session id is not found', () => {
    const session = makeSession('s1', 10);
    const fetched = makeSession('s-unknown', 10);
    const result = mergeSessionDetail([session], fetched);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('s1');
  });
});
