/**
 * The FE half of the insight lane's PER-PROJECT egress consent contract.
 *
 * The server requires the named project's `llm_egress_consent` before any
 * prompt leaves the box, and REFUSES (returns `disabled: true`) when the
 * request names no project. So the client MUST put the active project's id on
 * the wire — if it silently stopped doing so, every insight call would degrade
 * to "disabled" and look like a server/config problem rather than a client
 * regression. That failure is invisible without this test: the UI shows the
 * same graceful text either way.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { generateDashboardInsight } from '../geminiService';
import type { AnalyticsMetric, ProjectTask } from '../../types';

const METRICS = [] as AnalyticsMetric[];
const TASKS = [] as ProjectTask[];

function mockFetchOk(text = 'ok') {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ text, disabled: false, error: '' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function sentBody(fetchMock: ReturnType<typeof mockFetchOk>) {
  const [, init] = fetchMock.mock.calls[0];
  return JSON.parse((init as RequestInit).body as string);
}

describe('generateDashboardInsight — per-project egress consent wire contract', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends project_id when an active project is supplied', async () => {
    const fetchMock = mockFetchOk('insight text');

    await generateDashboardInsight(METRICS, TASKS, 'proj-42');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/ai/insight');
    expect(sentBody(fetchMock).project_id).toBe('proj-42');
  });

  it('sends an explicit null project_id when no project is active', async () => {
    const fetchMock = mockFetchOk();

    await generateDashboardInsight(METRICS, TASKS, undefined);

    // Explicit null rather than an omitted key: the server treats both as
    // "refuse", but sending the key makes the client's intent legible on the
    // wire (and pins that we are not accidentally omitting it for a real id).
    const body = sentBody(fetchMock);
    expect('project_id' in body).toBe(true);
    expect(body.project_id).toBeNull();
  });

  it('still forwards metrics and tasks alongside project_id', async () => {
    const fetchMock = mockFetchOk();
    const metrics = [{ name: '2026-08-11', value: 1.25, unit: '$' }] as unknown as AnalyticsMetric[];
    const tasks = [{ title: 'Auth', status: 'active', cost: 1.25 }] as unknown as ProjectTask[];

    await generateDashboardInsight(metrics, tasks, 'proj-7');

    const body = sentBody(fetchMock);
    expect(body.project_id).toBe('proj-7');
    expect(body.metrics).toHaveLength(1);
    expect(body.tasks).toHaveLength(1);
  });

  it('surfaces the disabled degrade as a string rather than throwing', async () => {
    // The server's refusal path. The UI must render text, not crash — this is
    // the state a consent-denied project now legitimately produces.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ text: '', disabled: true, error: '' }),
      }),
    );

    const result = await generateDashboardInsight(METRICS, TASKS, 'proj-denied');

    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });
});
