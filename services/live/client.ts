import type { EventSourceLike, LiveEventEnvelope } from './types';

const LIVE_EVENT_TYPES = ['append', 'invalidate', 'heartbeat', 'snapshot_required'] as const;

export type LiveEventType = (typeof LIVE_EVENT_TYPES)[number];

export interface LiveStreamConnection {
  source: EventSourceLike;
  dispose: () => void;
}

export interface LiveStreamClientOptions {
  basePath?: string;
  createEventSource?: (url: string) => EventSourceLike;
}

export const buildLiveStreamUrl = (
  topics: readonly string[],
  cursors: ReadonlyMap<string, string>,
  basePath = '/api/live/stream',
): string => {
  const params = new URLSearchParams();
  topics.forEach(topic => params.append('topic', topic));
  topics.forEach(topic => {
    const cursor = cursors.get(topic);
    if (cursor) params.append('cursor', cursor);
  });
  const query = params.toString();
  return query ? `${basePath}?${query}` : basePath;
};

export const parseLiveEvent = (raw: string): LiveEventEnvelope | null => {
  if (!raw.trim()) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<LiveEventEnvelope>;
    if (!parsed || typeof parsed !== 'object') return null;
    if (typeof parsed.topic !== 'string' || typeof parsed.kind !== 'string') return null;
    return {
      topic: parsed.topic,
      kind: parsed.kind as LiveEventEnvelope['kind'],
      cursor: typeof parsed.cursor === 'string' ? parsed.cursor : null,
      sequence: typeof parsed.sequence === 'number' ? parsed.sequence : null,
      occurredAt: typeof parsed.occurredAt === 'string' ? parsed.occurredAt : '',
      payload: parsed.payload && typeof parsed.payload === 'object' ? parsed.payload as Record<string, unknown> : {},
      delivery: parsed.delivery && typeof parsed.delivery === 'object'
        ? {
            replayable: Boolean(parsed.delivery.replayable),
            recoveryHint: typeof parsed.delivery.recoveryHint === 'string' ? parsed.delivery.recoveryHint : null,
          }
        : { replayable: false, recoveryHint: null },
    };
  } catch {
    return null;
  }
};

export const connectLiveStream = (
  topics: readonly string[],
  cursors: ReadonlyMap<string, string>,
  handlers: Partial<Record<LiveEventType, (event: LiveEventEnvelope) => void>> & {
    onOpen?: () => void;
    onError?: () => void;
  },
  options: LiveStreamClientOptions = {},
): LiveStreamConnection => {
  const createEventSource = options.createEventSource ?? ((url: string) => new EventSource(url, { withCredentials: true }));
  const url = buildLiveStreamUrl(topics, cursors, options.basePath);
  const source = createEventSource(url);
  const listeners: Array<[string, EventListener]> = [];

  const add = (type: string, listener: EventListener) => {
    listeners.push([type, listener]);
    source.addEventListener(type, listener);
  };

  add('open', () => {
    handlers.onOpen?.();
  });
  add('error', () => {
    handlers.onError?.();
  });

  LIVE_EVENT_TYPES.forEach(type => {
    add(type, ((event: Event) => {
      const message = event as MessageEvent<string>;
      const parsed = parseLiveEvent(String(message.data ?? ''));
      if (!parsed) return;
      handlers[type]?.(parsed);
    }) as EventListener);
  });

  return {
    source,
    dispose: () => {
      listeners.forEach(([type, listener]) => source.removeEventListener(type, listener));
      source.close();
    },
  };
};

