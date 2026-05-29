import { describe, expect, it } from 'vitest';
import { createProjectQueryClient } from '../queryClient';

// Helper: get the retry function from a fresh QueryClient.
// The TQ generic defaults TError to `Error`, but our implementation treats the
// error as `unknown` and uses a runtime status-field check. We cast through
// `unknown` so TypeScript accepts the test-specific error shapes.
function getRetry(projectId = 'proj-1') {
  const client = createProjectQueryClient(projectId);
  const retry = client.getDefaultOptions().queries?.retry;
  if (typeof retry !== 'function') {
    throw new Error('Expected retry to be a function');
  }
  // Cast: we test with plain objects that have a status field; the runtime
  // implementation uses `(err as any)?.status` so the cast is safe.
  return (count: number, err: unknown) => (retry as (count: number, err: unknown) => boolean)(count, err);
}

describe('createProjectQueryClient', () => {
  it('returns a QueryClient with staleTime 30_000', () => {
    const client = createProjectQueryClient('proj-1');
    const defaults = client.getDefaultOptions();
    expect(defaults.queries?.staleTime).toBe(30_000);
  });

  it('returns a QueryClient with gcTime 300_000', () => {
    const client = createProjectQueryClient('proj-1');
    const defaults = client.getDefaultOptions();
    expect(defaults.queries?.gcTime).toBe(300_000);
  });

  it('returns a QueryClient with refetchOnWindowFocus false', () => {
    const client = createProjectQueryClient('proj-1');
    const defaults = client.getDefaultOptions();
    expect(defaults.queries?.refetchOnWindowFocus).toBe(false);
  });

  describe('retry function', () => {
    it('retries on the first three failures for a 500 error', () => {
      const retry = getRetry();
      expect(retry(0, { status: 500 })).toBe(true);
      expect(retry(1, { status: 500 })).toBe(true);
      expect(retry(2, { status: 500 })).toBe(true);
    });

    it('does not retry a 4th time for a 500 error', () => {
      const retry = getRetry();
      expect(retry(3, { status: 500 })).toBe(false);
    });

    it('does not retry on a 400 error', () => {
      expect(getRetry()(0, { status: 400 })).toBe(false);
    });

    it('does not retry on a 401 error', () => {
      expect(getRetry()(0, { status: 401 })).toBe(false);
    });

    it('does not retry on a 403 error', () => {
      expect(getRetry()(0, { status: 403 })).toBe(false);
    });

    it('does not retry on a 404 error', () => {
      expect(getRetry()(0, { status: 404 })).toBe(false);
    });

    it('retries on a network-level error (no status field)', () => {
      const retry = getRetry();
      expect(retry(0, new Error('Network failure'))).toBe(true);
      expect(retry(2, new Error('Network failure'))).toBe(true);
      expect(retry(3, new Error('Network failure'))).toBe(false);
    });
  });

  it('creates separate instances per project id', () => {
    const a = createProjectQueryClient('proj-a');
    const b = createProjectQueryClient('proj-b');
    expect(a).not.toBe(b);
  });

  it('exposes a clear() method for project-switch teardown', () => {
    const client = createProjectQueryClient('proj-1');
    expect(typeof client.clear).toBe('function');
  });
});
