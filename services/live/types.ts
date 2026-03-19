export type LiveEventKind = 'append' | 'invalidate' | 'heartbeat' | 'snapshot_required';

export type LiveConnectionStatus = 'idle' | 'connecting' | 'open' | 'backoff' | 'paused' | 'closed';

export interface LiveDelivery {
  replayable: boolean;
  recoveryHint?: string | null;
}

export interface LiveEventEnvelope {
  topic: string;
  kind: LiveEventKind;
  cursor: string | null;
  sequence: number | null;
  occurredAt: string;
  payload: Record<string, unknown>;
  delivery: LiveDelivery;
}

export interface LiveSubscriptionCallbacks {
  onEvent?: (event: LiveEventEnvelope) => void;
  onSnapshotRequired?: (event: LiveEventEnvelope) => void | Promise<void>;
  onStatusChange?: (status: LiveConnectionStatus) => void;
}

export interface LiveSubscriptionOptions extends LiveSubscriptionCallbacks {
  topic: string;
  pauseWhenHidden?: boolean;
}

export interface LiveConnectionSnapshot {
  status: LiveConnectionStatus;
  topics: string[];
}

export interface EventSourceLike {
  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void;
  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void;
  close(): void;
}

