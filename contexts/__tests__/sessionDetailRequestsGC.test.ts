import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/**
 * Unit tests for the in-flight request GC on sessionDetailRequestsRef (FE-105).
 *
 * We test the core Map-management logic in isolation without mounting the full
 * React context tree.  The helpers below mirror the exact patterns used in
 * AppEntityDataContext.tsx so they stay structurally in sync.
 */

const TTL_MS = 30_000;

type InFlightMap = Map<string, Promise<unknown>>;
type TimestampMap = Map<string, number>;

/** Sweep expired entries — mirrors gcSessionDetailRequests in the context. */
function gcExpired(requests: InFlightMap, timestamps: TimestampMap, ttl: number): void {
  const now = Date.now();
  for (const [key, ts] of timestamps) {
    if (now - ts > ttl) {
      requests.delete(key);
      timestamps.delete(key);
    }
  }
}

/**
 * Simulated getSessionById insert path.
 * Returns a controller so tests can resolve/reject the promise externally.
 */
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

describe('sessionDetailRequestsRef GC (FE-105)', () => {
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

  it('removes entry on rejection via finally block', async () => {
    const rejectedFetch = () =>
      new Promise<null>((_resolve, reject) => {
        setTimeout(() => reject(new Error('network failure')), 100);
      });

    const promise = insertRequest('sess-1', requests, timestamps, TTL_MS, rejectedFetch);
    expect(requests.size).toBe(1);

    // Advance time so the rejection fires, then await (suppressed)
    vi.advanceTimersByTime(200);
    await promise.catch(() => null);

    expect(requests.size).toBe(0);
    expect(timestamps.size).toBe(0);
  });

  it('removes entry on successful resolution via finally block', async () => {
    const successFetch = () =>
      new Promise<string>(resolve => {
        setTimeout(() => resolve('session-data'), 50);
      });

    const promise = insertRequest('sess-2', requests, timestamps, TTL_MS, successFetch);
    expect(requests.size).toBe(1);

    vi.advanceTimersByTime(100);
    await promise;

    expect(requests.size).toBe(0);
    expect(timestamps.size).toBe(0);
  });

  it('entry is expired and removed by GC sweep after TTL', () => {
    // Manually plant an "old" entry without going through the promise lifecycle
    const stalePromise = new Promise<null>(() => {}); // never resolves
    requests.set('sess-stale', stalePromise);
    timestamps.set('sess-stale', Date.now());

    // Advance past the 30s TTL
    vi.advanceTimersByTime(TTL_MS + 1);

    gcExpired(requests, timestamps, TTL_MS);

    expect(requests.has('sess-stale')).toBe(false);
    expect(timestamps.has('sess-stale')).toBe(false);
  });

  it('GC on insert sweeps expired entries before adding new one', () => {
    // Plant two stale entries
    const staleA = new Promise<null>(() => {});
    const staleB = new Promise<null>(() => {});
    requests.set('sess-old-a', staleA);
    timestamps.set('sess-old-a', Date.now());
    requests.set('sess-old-b', staleB);
    timestamps.set('sess-old-b', Date.now());

    // Advance past TTL
    vi.advanceTimersByTime(TTL_MS + 1);

    // Insert a fresh request — GC runs first inside insertRequest
    const freshFetch = () => new Promise<string>(() => {}); // never resolves
    insertRequest('sess-new', requests, timestamps, TTL_MS, freshFetch);

    // Old entries swept; only the new one remains
    expect(requests.has('sess-old-a')).toBe(false);
    expect(requests.has('sess-old-b')).toBe(false);
    expect(requests.has('sess-new')).toBe(true);
    expect(requests.size).toBe(1);
  });

  it('Map size stays bounded after repeated network failures', async () => {
    for (let i = 0; i < 5; i++) {
      const id = `sess-fail-${i}`;
      const failFetch = () =>
        new Promise<null>((_resolve, reject) => {
          // Synchronously reject to keep the test fast
          reject(new Error('fail'));
        });

      const p = insertRequest(id, requests, timestamps, TTL_MS, failFetch);
      await p.catch(() => null);
    }

    expect(requests.size).toBe(0);
    expect(timestamps.size).toBe(0);
  });
});
