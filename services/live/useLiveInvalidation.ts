import { useEffect, useRef, useState } from 'react';

import { sharedLiveConnectionManager } from './connectionManager';
import type { LiveConnectionStatus, LiveEventEnvelope } from './types';

interface UseLiveInvalidationOptions {
  topics: string[];
  enabled?: boolean;
  pauseWhenHidden?: boolean;
  onInvalidate: (event: LiveEventEnvelope) => void | Promise<void>;
  onSnapshotRequired?: (event: LiveEventEnvelope) => void | Promise<void>;
}

export function useLiveInvalidation(options: UseLiveInvalidationOptions): LiveConnectionStatus {
  const {
    topics,
    enabled = true,
    pauseWhenHidden = true,
    onInvalidate,
    onSnapshotRequired,
  } = options;
  const [status, setStatus] = useState<LiveConnectionStatus>('idle');
  const onInvalidateRef = useRef(onInvalidate);
  const onSnapshotRequiredRef = useRef(onSnapshotRequired);
  const topicsKey = Array.from(new Set(topics.map(topic => String(topic || '').trim().toLowerCase()).filter(Boolean)))
    .sort()
    .join('|');

  useEffect(() => {
    onInvalidateRef.current = onInvalidate;
  }, [onInvalidate]);

  useEffect(() => {
    onSnapshotRequiredRef.current = onSnapshotRequired;
  }, [onSnapshotRequired]);

  useEffect(() => {
    if (!enabled || !topicsKey) {
      setStatus(prev => (prev === 'idle' ? prev : 'idle'));
      return undefined;
    }

    const normalizedTopics = topicsKey.split('|').filter(Boolean);
    const disposers = normalizedTopics.map(topic => sharedLiveConnectionManager.subscribe({
      topic,
      pauseWhenHidden,
      onStatusChange: nextStatus => {
        setStatus(nextStatus);
      },
      onEvent: event => {
        if (event.kind !== 'invalidate') return;
        void onInvalidateRef.current(event);
      },
      onSnapshotRequired: event => {
        if (onSnapshotRequiredRef.current) {
          void onSnapshotRequiredRef.current(event);
          return;
        }
        void onInvalidateRef.current(event);
      },
    }));

    return () => {
      disposers.forEach(dispose => dispose());
    };
  }, [enabled, pauseWhenHidden, topicsKey]);

  return status;
}
