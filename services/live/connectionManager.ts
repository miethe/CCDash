import { connectLiveStream } from './client';
import { resolveLiveStreamBaseUrl } from '../runtimeBase';
import type {
  EventSourceLike,
  LiveConnectionSnapshot,
  LiveConnectionStatus,
  LiveEventEnvelope,
  LiveSubscriptionOptions,
} from './types';

interface LiveConnectionManagerOptions {
  basePath?: string;
  createEventSource?: (url: string) => EventSourceLike;
  reconnectBaseMs?: number;
  reconnectMaxMs?: number;
  documentRef?: Pick<Document, 'hidden' | 'addEventListener' | 'removeEventListener'> | null;
}

interface InternalSubscription extends LiveSubscriptionOptions {
  id: number;
  topic: string;
}

export class LiveConnectionManager {
  private readonly basePath: string;
  private readonly createEventSource?: (url: string) => EventSourceLike;
  private readonly reconnectBaseMs: number;
  private readonly reconnectMaxMs: number;
  private readonly documentRef: Pick<Document, 'hidden' | 'addEventListener' | 'removeEventListener'> | null;
  private readonly subscriptions = new Map<number, InternalSubscription>();
  private readonly cursorByTopic = new Map<string, string>();
  private readonly activeTopics = new Set<string>();
  private nextSubscriptionId = 1;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private status: LiveConnectionStatus = 'idle';
  private connectedTopicsKey = '';
  private connection: ReturnType<typeof connectLiveStream> | null = null;
  private listeningForVisibility = false;

  constructor(options: LiveConnectionManagerOptions = {}) {
    this.basePath = options.basePath ?? resolveLiveStreamBaseUrl();
    this.createEventSource = options.createEventSource;
    this.reconnectBaseMs = options.reconnectBaseMs ?? 1000;
    this.reconnectMaxMs = options.reconnectMaxMs ?? 15000;
    this.documentRef = options.documentRef ?? (typeof document !== 'undefined' ? document : null);
  }

  subscribe(options: LiveSubscriptionOptions): () => void {
    const topic = String(options.topic || '').trim().toLowerCase();
    if (!topic) {
      throw new Error('Live subscription topic is required.');
    }
    const id = this.nextSubscriptionId++;
    this.subscriptions.set(id, { ...options, id, topic });
    options.onStatusChange?.(this.status);
    this.refreshConnection();
    return () => {
      this.subscriptions.delete(id);
      this.refreshConnection();
    };
  }

  getSnapshot(): LiveConnectionSnapshot {
    return {
      status: this.status,
      topics: Array.from(this.activeTopics),
    };
  }

  disconnect(): void {
    this.clearReconnectTimer();
    this.teardownConnection();
    this.setStatus(this.subscriptions.size > 0 ? 'closed' : 'idle');
  }

  private refreshConnection(): void {
    this.syncVisibilityListener();
    const topics = Array.from(new Set(Array.from(this.subscriptions.values()).map(sub => sub.topic))).sort();
    if (topics.length === 0) {
      this.activeTopics.clear();
      this.connectedTopicsKey = '';
      this.disconnect();
      return;
    }
    if (this.shouldPauseForVisibility()) {
      this.activeTopics.clear();
      this.teardownConnection();
      this.setStatus('paused');
      return;
    }

    const nextKey = topics.join('|');
    if (nextKey === this.connectedTopicsKey && this.connection) {
      return;
    }

    this.clearReconnectTimer();
    this.teardownConnection();
    this.connectedTopicsKey = nextKey;
    this.activeTopics.clear();
    topics.forEach(topic => this.activeTopics.add(topic));
    this.openConnection(topics);
  }

  private openConnection(topics: string[]): void {
    this.setStatus('connecting');
    this.connection = connectLiveStream(
      topics,
      this.cursorByTopic,
      {
        onOpen: () => {
          this.reconnectAttempt = 0;
          this.setStatus('open');
        },
        onError: () => {
          this.teardownConnection();
          if (this.subscriptions.size === 0) {
            this.setStatus('idle');
            return;
          }
          if (this.shouldPauseForVisibility()) {
            this.setStatus('paused');
            return;
          }
          this.setStatus('backoff');
          this.scheduleReconnect();
        },
        append: event => {
          this.handleEvent(event);
        },
        invalidate: event => {
          this.handleEvent(event);
        },
        heartbeat: event => {
          this.handleEvent(event);
        },
        snapshot_required: event => {
          this.cursorByTopic.delete(event.topic);
          this.handleEvent(event);
        },
      },
      {
        basePath: this.basePath,
        createEventSource: this.createEventSource,
      },
    );
  }

  private handleEvent(event: LiveEventEnvelope): void {
    if (event.cursor) {
      this.cursorByTopic.set(event.topic, event.cursor);
    }
    const subscribers = Array.from(this.subscriptions.values()).filter(sub => sub.topic === event.topic);
    subscribers.forEach(sub => {
      if (event.kind === 'snapshot_required') {
        void sub.onSnapshotRequired?.(event);
        return;
      }
      sub.onEvent?.(event);
    });
  }

  private scheduleReconnect(): void {
    this.clearReconnectTimer();
    const delay = Math.min(this.reconnectMaxMs, this.reconnectBaseMs * (2 ** this.reconnectAttempt));
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.refreshConnection();
    }, delay);
  }

  private setStatus(next: LiveConnectionStatus): void {
    if (this.status === next) return;
    this.status = next;
    this.subscriptions.forEach(sub => sub.onStatusChange?.(next));
  }

  private teardownConnection(): void {
    this.connection?.dispose();
    this.connection = null;
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private shouldPauseForVisibility(): boolean {
    if (!this.documentRef || !this.documentRef.hidden) return false;
    return Array.from(this.subscriptions.values()).some(sub => sub.pauseWhenHidden !== false);
  }

  private syncVisibilityListener(): void {
    if (!this.documentRef) return;
    const needsListener = this.subscriptions.size > 0;
    if (needsListener && !this.listeningForVisibility) {
      this.documentRef.addEventListener('visibilitychange', this.handleVisibilityChange);
      this.listeningForVisibility = true;
      return;
    }
    if (!needsListener && this.listeningForVisibility) {
      this.documentRef.removeEventListener('visibilitychange', this.handleVisibilityChange);
      this.listeningForVisibility = false;
    }
  }

  private readonly handleVisibilityChange = () => {
    this.refreshConnection();
  };
}

export const sharedLiveConnectionManager = new LiveConnectionManager();
