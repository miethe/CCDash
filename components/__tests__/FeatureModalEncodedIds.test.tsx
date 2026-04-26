/**
 * P4-001: Feature modal encoded IDs regression suite.
 *
 * Verifies that getLegacyFeatureDetail and getLegacyFeatureLinkedSessions
 * (the typed helpers that replaced raw fetch() calls in ProjectBoard,
 * FeatureExecutionWorkbench, and SessionInspector) correctly percent-encode
 * feature IDs before interpolating them into request URLs.
 *
 * IDs under test:
 *   "feat/slash"    → slash must be encoded as %2F
 *   "feat with space" → space must be encoded as %20 (or +)
 *   "feat#hash"     → hash must be encoded as %23
 *   "feat?query"    → question mark must be encoded as %3F
 *   "feat&amp"      → ampersand must be encoded as %26
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getLegacyFeatureDetail,
  getLegacyFeatureLinkedSessions,
} from '../../services/featureSurface';

// ── Helpers ───────────────────────────────────────────────────────────────────

function okJson(body: unknown, httpStatus = 200): Response {
  return new Response(JSON.stringify(body), {
    status: httpStatus,
    headers: { 'content-type': 'application/json' },
  });
}

/** Minimal Feature-shaped stub so the callers don't choke on the response. */
const stubFeature = { id: 'stub', name: 'Stub Feature', status: 'active' };

/** Minimal linked-sessions array stub. */
const stubLinkedSessions = [{ sessionId: 's1', confidence: 1, reasons: [] }];

// ── Special-character feature IDs under test ──────────────────────────────────

const SPECIAL_IDS = [
  { raw: 'feat/slash',       encoded: 'feat%2Fslash' },
  { raw: 'feat with space',  encoded: 'feat%20with%20space' },
  { raw: 'feat#hash',        encoded: 'feat%23hash' },
  { raw: 'feat?query',       encoded: 'feat%3Fquery' },
  { raw: 'feat&amp',         encoded: 'feat%26amp' },
] as const;

// ── getLegacyFeatureDetail ────────────────────────────────────────────────────

describe('getLegacyFeatureDetail', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each(SPECIAL_IDS)(
    'encodes "$raw" as "$encoded" in the request URL',
    async ({ raw, encoded }) => {
      const mockFetch = vi.fn().mockResolvedValue(okJson(stubFeature));
      vi.stubGlobal('fetch', mockFetch);

      await getLegacyFeatureDetail(raw);

      expect(mockFetch).toHaveBeenCalledOnce();
      const [url] = mockFetch.mock.calls[0] as [string];
      expect(url).toBe(`/api/features/${encoded}`);
    },
  );

  it('returns the parsed JSON body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okJson(stubFeature)));

    const result = await getLegacyFeatureDetail('FEAT-1');

    expect(result).toEqual(stubFeature);
  });

  it('throws FeatureSurfaceApiError on non-ok response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('Not Found', { status: 404, statusText: 'Not Found' }),
      ),
    );

    await expect(getLegacyFeatureDetail('FEAT-missing')).rejects.toThrow(
      /Legacy feature API error/,
    );
  });
});

// ── getLegacyFeatureLinkedSessions ────────────────────────────────────────────

describe('getLegacyFeatureLinkedSessions', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each(SPECIAL_IDS)(
    'encodes "$raw" as "$encoded" in the /linked-sessions URL',
    async ({ raw, encoded }) => {
      const mockFetch = vi.fn().mockResolvedValue(okJson(stubLinkedSessions));
      vi.stubGlobal('fetch', mockFetch);

      await getLegacyFeatureLinkedSessions(raw);

      expect(mockFetch).toHaveBeenCalledOnce();
      const [url] = mockFetch.mock.calls[0] as [string];
      expect(url).toBe(`/api/features/${encoded}/linked-sessions`);
    },
  );

  it('returns the parsed JSON body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okJson(stubLinkedSessions)));

    const result = await getLegacyFeatureLinkedSessions('FEAT-1');

    expect(result).toEqual(stubLinkedSessions);
  });

  it('throws FeatureSurfaceApiError on non-ok response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('Internal Server Error', { status: 500, statusText: 'Internal Server Error' }),
      ),
    );

    await expect(getLegacyFeatureLinkedSessions('FEAT-broken')).rejects.toThrow(
      /Legacy feature API error/,
    );
  });
});
