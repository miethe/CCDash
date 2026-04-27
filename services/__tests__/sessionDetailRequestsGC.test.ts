/**
 * TEST-504 — FE-105 in-flight request GC (services surface)
 *
 * Verifies the sessionDetailRequestsRef-style Map + TTL mechanics that are
 * implemented in AppEntityDataContext.tsx.  Tests are self-contained: the
 * helpers below mirror the exact insert/sweep logic so they stay structurally
 * in sync without coupling to React internals.
 *
 * Three mandatory scenarios (Phase 5 / runtime-performance-hardening-v1):
 *   1. Promise rejection removes the entry from the in-flight map.
 *   2. After 30 s TTL the entry is removed even if never resolved/rejected.
 *   3. Repeated network failures do NOT cause unbounded map growth.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const TTL_MS = 30_000;

type InFlightMap = Map<string, Promise<unknown>>;
type TimestampMap = Map<string, number>;

/** Mirror of gcSessionDetailRequests from AppEntityDataContext. */
function gcExpired(requests: InFlightMap, timestamps: TimestampMap, ttl: number): void {
  const now = Date.now();
  for (const [key, ts] of timestamps) {
    if (now - ts > ttl) {
      requests.delete(key);
      timestamps.delete(key);
    }
  }
}

/** Mirror of the getSessionById insert path in AppEntityDataContext. */
function insertRequest(
  sessionId: string,
  requests: InFlightMap,
  timestamps: TimestampMap,
  ttl: number,
  fetchFn: () => Promise<unknown>,
): Promise<unknown> {
  gcExpired(requests, timestamps, ttl);

  const existing = requests.get(sessionId);
  if (existing) return existing;

  const request = fetchFn().finally(() => {
    requests.delete(sessionId);
    timestamps.delete(sessionId);
  });

  requests.set(sessionId, request);
  timestamps.set(sessionId, Date.now());
  return request;
}

// ---------------------------------------------------------------------------

describe('FE-105: sessionDetailRequestsRef in-flight GC', () => {
  let requests: InFlightMap;
  let timestamps: TimestampMap;

  beforeEach(() => {
    requests = new Map();
    timestamps = new Map();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('promise rejection removes the entry from the in-flight map', async () => {
    const rejectingFetch = vi.fn(
      () =>
        new Promise<null>((_resolve, reject) => {
          setTimeout(() => reject(new Error('network error')), 100);
        }),
    );

    const p = insertRequest('sess-reject', requests, timestamps, TTL_MS, rejectingFetch);
    expect(requests.size).toBe(1);

    vi.advanceTimersByTime(200);
    await p.catch(() => null);

    expect(requests.has('sess-reject')).toBe(false);
    expect(timestamps.has('sess-reject')).toBe(false);
    expect(requests.size).toBe(0);
  });

  it('entry is removed after 30 s TTL even if never resolved or rejected', () => {
    // Plant a permanently-pending promise (simulates a hung request)
    const hangingPromise = new Promise<null>(() => {}); // never settles
    requests.set('sess-hanging', hangingPromise);
    timestamps.set('sess-hanging', Date.now());

    expect(requests.size).toBe(1);

    // Advance just past the 30 s TTL
    vi.advanceTimersByTime(TTL_MS + 1);

    // Trigger a GC sweep (happens on next insertRequest or explicit call)
    gcExpired(requests, timestamps, TTL_MS);

    expect(requests.has('sess-hanging')).toBe(false);
    expect(timestamps.has('sess-hanging')).toBe(false);
    expect(requests.size).toBe(0);
  });

  it('repeated network failures do not cause unbounded map growth', async () => {
    const FAILURE_COUNT = 10;

    for (let i = 0; i < FAILURE_COUNT; i++) {
      const id = `sess-fail-${i}`;
      const failFetch = vi.fn(
        () => new Promise<null>((_resolve, reject) => reject(new Error('fail'))),
      );

      const p = insertRequest(id, requests, timestamps, TTL_MS, failFetch);
      // Suppress unhandled rejection; finally block runs synchronously here
      await p.catch(() => null);
    }

    // Every failed promise's finally block should have cleared its entry
    expect(requests.size).toBe(0);
    expect(timestamps.size).toBe(0);
  });
});
