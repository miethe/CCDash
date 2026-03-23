import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildLiveStreamUrl } from '../live/client';
import { LiveConnectionManager } from '../live/connectionManager';
import {
  featureTopic,
  projectFeaturesTopic,
  projectOpsTopic,
  projectTestsTopic,
  sessionTranscriptTopic,
} from '../live/topics';
import type { EventSourceLike } from '../live/types';

class FakeEventSource implements EventSourceLike {
  readonly url: string;
  private readonly listeners = new Map<string, Set<EventListener>>();
  closed = false;

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    const normalized = listener as EventListener;
    const bucket = this.listeners.get(type) ?? new Set<EventListener>();
    bucket.add(normalized);
    this.listeners.set(type, bucket);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.get(type)?.delete(listener as EventListener);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data?: unknown): void {
    const message = { data: JSON.stringify(data ?? {}) } as MessageEvent<string>;
    this.listeners.get(type)?.forEach(listener => listener(message as unknown as Event));
  }
}

const createVisibilityDocument = () => {
  const listeners = new Set<() => void>();
  return {
    hidden: false,
    addEventListener: vi.fn((type: string, listener: EventListenerOrEventListenerObject) => {
      if (type === 'visibilitychange') listeners.add(listener as () => void);
    }),
    removeEventListener: vi.fn((type: string, listener: EventListenerOrEventListenerObject) => {
      if (type === 'visibilitychange') listeners.delete(listener as () => void);
    }),
    emitVisibility() {
      listeners.forEach(listener => listener());
    },
  };
};

describe('buildLiveStreamUrl', () => {
  it('serializes topics and known cursors', () => {
    const url = buildLiveStreamUrl(
      ['execution.run.run-1', 'session.session-1'],
      new Map([
        ['execution.run.run-1', 'cursor-1'],
        ['unused.topic', 'cursor-x'],
      ]),
    );

    expect(url).toBe('/api/live/stream?topic=execution.run.run-1&topic=session.session-1&cursor=cursor-1');
  });
});

describe('live topic helpers', () => {
  it('builds normalized feature, test, and ops topics', () => {
    expect(featureTopic('Feature-1')).toBe('feature.feature-1');
    expect(projectFeaturesTopic('Project-1')).toBe('project.project-1.features');
    expect(projectTestsTopic('Project-1')).toBe('project.project-1.tests');
    expect(projectOpsTopic('Project-1')).toBe('project.project-1.ops');
    expect(sessionTranscriptTopic('Session-1')).toBe('session.session-1.transcript');
  });
});

describe('LiveConnectionManager', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('multiplexes subscriptions over one connection and rebuilds when topics change', () => {
    const sources: FakeEventSource[] = [];
    const manager = new LiveConnectionManager({
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
    });

    const disposeRun = manager.subscribe({ topic: 'execution.run.run-1' });
    expect(sources).toHaveLength(1);
    expect(sources[0]?.url).toContain('topic=execution.run.run-1');

    const disposeSession = manager.subscribe({ topic: 'session.session-1' });
    expect(sources).toHaveLength(2);
    expect(sources[0]?.closed).toBe(true);
    expect(sources[1]?.url).toContain('topic=execution.run.run-1');
    expect(sources[1]?.url).toContain('topic=session.session-1');

    disposeRun();
    expect(sources).toHaveLength(3);
    expect(sources[1]?.closed).toBe(true);
    expect(sources[2]?.url).toContain('topic=session.session-1');

    disposeSession();
    expect(manager.getSnapshot().status).toBe('idle');
    expect(sources[2]?.closed).toBe(true);
  });

  it('persists cursors and clears them when snapshot recovery is required', () => {
    vi.useFakeTimers();
    const sources: FakeEventSource[] = [];
    const recover = vi.fn();
    const manager = new LiveConnectionManager({
      reconnectBaseMs: 5,
      reconnectMaxMs: 5,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
    });

    manager.subscribe({
      topic: 'execution.run.run-9',
      onSnapshotRequired: recover,
    });

    sources[0]?.emit('append', {
      topic: 'execution.run.run-9',
      kind: 'append',
      cursor: 'cursor-9',
      sequence: 1,
      occurredAt: '2026-03-15T10:00:00Z',
      payload: { sequenceNo: 1 },
      delivery: { replayable: true, recoveryHint: null },
    });

    sources[0]?.emit('error');
    vi.advanceTimersByTime(5);
    expect(sources).toHaveLength(2);
    expect(sources[1]?.url).toContain('cursor=cursor-9');

    sources[1]?.emit('snapshot_required', {
      topic: 'execution.run.run-9',
      kind: 'snapshot_required',
      cursor: null,
      sequence: null,
      occurredAt: '2026-03-15T10:00:01Z',
      payload: { latestSequence: 10 },
      delivery: { replayable: false, recoveryHint: 'rest_snapshot' },
    });
    expect(recover).toHaveBeenCalledTimes(1);

    sources[1]?.emit('error');
    vi.advanceTimersByTime(5);
    expect(sources).toHaveLength(3);
    expect(sources[2]?.url).not.toContain('cursor=cursor-9');
  });

  it('keeps transcript-topic cursors for append replay and clears them on transcript snapshot recovery', () => {
    vi.useFakeTimers();
    const sources: FakeEventSource[] = [];
    const recover = vi.fn();
    const manager = new LiveConnectionManager({
      reconnectBaseMs: 5,
      reconnectMaxMs: 5,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
    });

    manager.subscribe({
      topic: sessionTranscriptTopic('session-42'),
      onSnapshotRequired: recover,
    });

    sources[0]?.emit('append', {
      topic: sessionTranscriptTopic('session-42'),
      kind: 'append',
      cursor: 'transcript-cursor-1',
      sequence: 1,
      occurredAt: '2026-03-15T10:00:00Z',
      payload: {
        sessionId: 'session-42',
        entryId: 'log-1',
        sequenceNo: 1,
      },
      delivery: { replayable: true, recoveryHint: null },
    });

    sources[0]?.emit('error');
    vi.advanceTimersByTime(5);
    expect(sources).toHaveLength(2);
    expect(sources[1]?.url).toContain('topic=session.session-42.transcript');
    expect(sources[1]?.url).toContain('cursor=transcript-cursor-1');

    sources[1]?.emit('snapshot_required', {
      topic: sessionTranscriptTopic('session-42'),
      kind: 'snapshot_required',
      cursor: null,
      sequence: null,
      occurredAt: '2026-03-15T10:00:01Z',
      payload: { latestSequence: 12 },
      delivery: { replayable: false, recoveryHint: 'rest_snapshot' },
    });
    expect(recover).toHaveBeenCalledTimes(1);

    sources[1]?.emit('error');
    vi.advanceTimersByTime(5);
    expect(sources).toHaveLength(3);
    expect(sources[2]?.url).not.toContain('cursor=transcript-cursor-1');
  });

  it('pauses when the document is hidden and resumes when visible again', () => {
    const doc = createVisibilityDocument();
    const sources: FakeEventSource[] = [];
    const manager = new LiveConnectionManager({
      documentRef: doc,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
    });

    manager.subscribe({ topic: 'session.session-7' });
    expect(manager.getSnapshot().status).toBe('connecting');

    doc.hidden = true;
    doc.emitVisibility();
    expect(manager.getSnapshot().status).toBe('paused');
    expect(sources[0]?.closed).toBe(true);

    doc.hidden = false;
    doc.emitVisibility();
    expect(sources).toHaveLength(2);
    expect(manager.getSnapshot().status).toBe('connecting');
  });

  it('resubscribes to transcript topics after hidden-tab resume with cursor retention intact', () => {
    const doc = createVisibilityDocument();
    const sources: FakeEventSource[] = [];
    const manager = new LiveConnectionManager({
      documentRef: doc,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
    });

    manager.subscribe({ topic: sessionTranscriptTopic('session-88') });
    sources[0]?.emit('append', {
      topic: sessionTranscriptTopic('session-88'),
      kind: 'append',
      cursor: 'transcript-cursor-88',
      sequence: 1,
      occurredAt: '2026-03-15T10:00:00Z',
      payload: { sessionId: 'session-88', entryId: 'log-88', sequenceNo: 1 },
      delivery: { replayable: true, recoveryHint: null },
    });

    doc.hidden = true;
    doc.emitVisibility();
    expect(manager.getSnapshot().status).toBe('paused');

    doc.hidden = false;
    doc.emitVisibility();
    expect(sources).toHaveLength(2);
    expect(sources[1]?.url).toContain('topic=session.session-88.transcript');
    expect(sources[1]?.url).toContain('cursor=transcript-cursor-88');
    expect(manager.getSnapshot().status).toBe('connecting');
  });
});
