import { describe, expect, it } from 'vitest';

import { mergeSessionTranscriptAppend, toSessionTranscriptLog } from '../sessionTranscriptLive';
import type { SessionLog } from '@/types';
import type { SessionTranscriptAppendPayload } from '@/types';

const basePayload = (): SessionTranscriptAppendPayload => ({
  sessionId: 'session-1',
  entryId: 'log-3',
  sequenceNo: 3,
  kind: 'message',
  createdAt: '2026-03-23T12:00:00Z',
  payload: {
    id: 'log-3',
    timestamp: '2026-03-23T12:00:00Z',
    speaker: 'agent',
    type: 'message',
    content: 'hello',
    agentName: 'Claude',
    linkedSessionId: 'session-child',
    relatedToolCallId: 'tool-1',
    metadata: { foo: 'bar' },
    toolCall: { name: 'write_file', args: '{}', status: 'success' },
  },
});

describe('toSessionTranscriptLog', () => {
  it('normalizes transcript append payloads into SessionLog entries', () => {
    const log = toSessionTranscriptLog(basePayload());
    expect(log.id).toBe('log-3');
    expect(log.timestamp).toBe('2026-03-23T12:00:00Z');
    expect(log.content).toBe('hello');
    expect(log.toolCall?.name).toBe('write_file');
  });
});

describe('mergeSessionTranscriptAppend', () => {
  it('appends a new transcript entry when sequence and identity are aligned', () => {
    const currentLogs: SessionLog[] = [
      { id: 'log-1', timestamp: '2026-03-23T11:58:00Z', speaker: 'user', type: 'message', content: 'start' },
      { id: 'log-2', timestamp: '2026-03-23T11:59:00Z', speaker: 'agent', type: 'message', content: 'reply' },
    ];

    const result = mergeSessionTranscriptAppend(currentLogs, basePayload());
    expect(result.action).toBe('append');
    if (result.action === 'append') {
      expect(result.nextLogs).toHaveLength(3);
      expect(result.appendedLog.id).toBe('log-3');
    }
  });

  it('skips duplicate transcript entries instead of appending them twice', () => {
    const currentLogs: SessionLog[] = [
      { id: 'log-1', timestamp: '2026-03-23T11:58:00Z', speaker: 'user', type: 'message', content: 'start' },
      { id: 'log-2', timestamp: '2026-03-23T11:59:00Z', speaker: 'agent', type: 'message', content: 'reply' },
      { id: 'log-3', timestamp: '2026-03-23T12:00:00Z', speaker: 'agent', type: 'message', content: 'hello' },
    ];

    const result = mergeSessionTranscriptAppend(currentLogs, basePayload());
    expect(result.action).toBe('skip');
    if (result.action === 'skip') {
      expect(result.reason).toBe('duplicate');
      expect(result.nextLogs).toHaveLength(3);
    }
  });

  it('refetches when the append sequence does not match the current transcript length', () => {
    const currentLogs: SessionLog[] = [
      { id: 'log-1', timestamp: '2026-03-23T11:58:00Z', speaker: 'user', type: 'message', content: 'start' },
    ];

    const result = mergeSessionTranscriptAppend(currentLogs, {
      ...basePayload(),
      sequenceNo: 7,
    });

    expect(result.action).toBe('refetch');
    if (result.action === 'refetch') {
      expect(result.reason).toBe('sequence_mismatch');
    }
  });

  it('refetches when required identifiers are missing', () => {
    const result = mergeSessionTranscriptAppend([], {
      ...basePayload(),
      sessionId: '',
    });

    expect(result.action).toBe('refetch');
    if (result.action === 'refetch') {
      expect(result.reason).toBe('missing_identifier');
    }
  });

  it('refetches when a rewrite-like append conflicts with existing ids', () => {
    const currentLogs: SessionLog[] = [
      { id: 'log-1', timestamp: '2026-03-23T11:58:00Z', speaker: 'user', type: 'message', content: 'start' },
      { id: 'log-2', timestamp: '2026-03-23T11:59:00Z', speaker: 'agent', type: 'message', content: 'reply' },
    ];

    const result = mergeSessionTranscriptAppend(currentLogs, {
      ...basePayload(),
      entryId: 'log-1',
      payload: {
        ...basePayload().payload,
        id: 'log-1',
        content: 'rewritten',
      },
    });

    expect(result.action).toBe('refetch');
    if (result.action === 'refetch') {
      expect(result.reason).toBe('rewrite_detected');
    }
  });
});
