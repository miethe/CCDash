import { describe, expect, it, vi } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

import { mergeSessionTranscriptAppend } from '../../lib/sessionTranscriptLive';
import { LiveConnectionManager } from '../../services/live/connectionManager';
import { sessionTopic, sessionTranscriptTopic } from '../../services/live/topics';
import type { EventSourceLike, LiveEventEnvelope } from '../../services/live/types';
import type { AgentSession, SessionTranscriptAppendPayload } from '../../types';

class FakeEventSource implements EventSourceLike {
  readonly url: string;
  private readonly listeners = new Map<string, Set<EventListener>>();
  closed = false;

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    const bucket = this.listeners.get(type) ?? new Set<EventListener>();
    bucket.add(listener as EventListener);
    this.listeners.set(type, bucket);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.get(type)?.delete(listener as EventListener);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data?: LiveEventEnvelope): void {
    const event = data
      ? ({ data: JSON.stringify(data) } as MessageEvent<string>)
      : ({} as Event);
    this.listeners.get(type)?.forEach(listener => listener(event as Event));
  }
}

const sessionInspectorSource = fs.readFileSync(
  path.resolve(__dirname, '../SessionInspector.tsx'),
  'utf-8',
);

const activeSession = (): AgentSession => ({
  id: 'session-test-003',
  title: 'TEST-003 active session',
  taskId: 'task-test-003',
  agentId: 'agent-1',
  status: 'active',
  model: 'claude-sonnet-4.5',
  startedAt: '2026-04-01T12:00:00Z',
  endedAt: null,
  updatedAt: '2026-04-01T12:00:00Z',
  durationSeconds: 0,
  tokensIn: 0,
  tokensOut: 0,
  totalCost: 0,
  toolsUsed: [],
  logs: [
    {
      id: 'log-1',
      timestamp: '2026-04-01T12:00:00Z',
      speaker: 'user',
      type: 'message',
      content: 'start',
    },
  ],
});

const transcriptAppendPayload = (): SessionTranscriptAppendPayload => ({
  sessionId: 'session-test-003',
  entryId: 'log-2',
  sequenceNo: 2,
  kind: 'message',
  createdAt: '2026-04-01T12:01:00Z',
  payload: {
    id: 'log-2',
    timestamp: '2026-04-01T12:01:00Z',
    speaker: 'agent',
    type: 'message',
    content: 'worker-watch append reached the inspector',
  },
});

describe('TEST-003 Session Inspector live SSE smoke', () => {
  it('keeps active Session Inspector wired to session and transcript SSE topics', () => {
    expect(sessionInspectorSource).toContain("selectedSessionStatus !== 'active'");
    expect(sessionInspectorSource).toContain('sharedLiveConnectionManager.subscribe({\n            topic: sessionTopic(sessionId)');
    expect(sessionInspectorSource).toContain('sharedLiveConnectionManager.subscribe({\n                topic: sessionTranscriptTopic(sessionId)');
    expect(sessionInspectorSource).toContain("event.kind !== 'invalidate' || event.payload.resource !== 'session'");
    expect(sessionInspectorSource).toContain('mergeSessionTranscriptAppend(current.logs, payload)');
    expect(sessionInspectorSource).toContain('logs: decision.nextLogs');
    expect(sessionInspectorSource).toContain('void refreshSelectedSessionDetail(sessionId)');
  });

  it('delivers worker-watch session changes through EventSource and applies the inspector update rules', () => {
    const sources: FakeEventSource[] = [];
    const statuses: string[] = [];
    const refreshSelectedSessionDetail = vi.fn();
    let selectedSession: AgentSession = activeSession();
    const sessionId = selectedSession.id;

    const manager = new LiveConnectionManager({
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
    });

    manager.subscribe({
      topic: sessionTopic(sessionId),
      pauseWhenHidden: true,
      onStatusChange: status => statuses.push(status),
      onEvent: event => {
        if (event.kind !== 'invalidate' || event.payload.resource !== 'session') return;
        const logCount = typeof event.payload.logCount === 'number' ? event.payload.logCount : selectedSession.logs.length;
        const nextStatus = event.payload.status === 'active' || event.payload.status === 'completed'
          ? event.payload.status
          : selectedSession.status;
        const nextUpdatedAt = typeof event.payload.updatedAt === 'string'
          ? event.payload.updatedAt
          : selectedSession.updatedAt;
        const shouldRefetch = nextStatus !== selectedSession.status || logCount < selectedSession.logs.length;
        if (shouldRefetch) {
          refreshSelectedSessionDetail(sessionId);
          return;
        }
        if (nextUpdatedAt !== selectedSession.updatedAt) {
          selectedSession = {
            ...selectedSession,
            status: nextStatus,
            updatedAt: nextUpdatedAt,
          };
        }
      },
      onSnapshotRequired: () => refreshSelectedSessionDetail(sessionId),
    });

    manager.subscribe({
      topic: sessionTranscriptTopic(sessionId),
      pauseWhenHidden: true,
      onStatusChange: status => statuses.push(status),
      onEvent: event => {
        if (event.kind !== 'append') return;
        const payload = event.payload as unknown as SessionTranscriptAppendPayload;
        if (payload.sessionId !== sessionId || event.topic !== sessionTranscriptTopic(sessionId)) {
          refreshSelectedSessionDetail(sessionId);
          return;
        }
        const decision = mergeSessionTranscriptAppend(selectedSession.logs, payload);
        if (decision.action === 'refetch') {
          refreshSelectedSessionDetail(sessionId);
          return;
        }
        if (decision.action === 'append') {
          selectedSession = {
            ...selectedSession,
            logs: decision.nextLogs,
            updatedAt: payload.createdAt || selectedSession.updatedAt,
          };
        }
      },
      onSnapshotRequired: () => refreshSelectedSessionDetail(sessionId),
    });

    expect(sources).toHaveLength(2);
    expect(sources[0]?.closed).toBe(true);
    expect(sources[1]?.url).toContain(`topic=${sessionTopic(sessionId)}`);
    expect(sources[1]?.url).toContain(`topic=${sessionTranscriptTopic(sessionId)}`);

    sources[1]?.emit('open');
    sources[1]?.emit('invalidate', {
      topic: sessionTopic(sessionId),
      kind: 'invalidate',
      cursor: 'worker-watch-session-cursor-1',
      sequence: 1,
      occurredAt: '2026-04-01T12:01:00Z',
      payload: {
        resource: 'session',
        runtimeProfile: 'worker-watch',
        sessionId,
        status: 'active',
        updatedAt: '2026-04-01T12:01:00Z',
        logCount: 1,
      },
      delivery: { replayable: true, recoveryHint: null },
    });

    sources[1]?.emit('append', {
      topic: sessionTranscriptTopic(sessionId),
      kind: 'append',
      cursor: 'worker-watch-transcript-cursor-1',
      sequence: 2,
      occurredAt: '2026-04-01T12:01:00Z',
      payload: transcriptAppendPayload() as unknown as Record<string, unknown>,
      delivery: { replayable: true, recoveryHint: null },
    });

    expect(statuses).toContain('open');
    expect(selectedSession.updatedAt).toBe('2026-04-01T12:01:00Z');
    expect(selectedSession.logs).toHaveLength(2);
    expect(selectedSession.logs[1]?.content).toBe('worker-watch append reached the inspector');
    expect(refreshSelectedSessionDetail).not.toHaveBeenCalled();
  });
});
