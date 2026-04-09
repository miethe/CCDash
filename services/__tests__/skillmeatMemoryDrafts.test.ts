import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  generateSessionMemoryDrafts,
  listSessionMemoryDrafts,
  publishSessionMemoryDraft,
  reviewSessionMemoryDraft,
} from '../skillmeat';

describe('skillmeat memory draft helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('lists memory drafts with the assumed project-scoped query contract', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          projectId: 'project-1',
          total: 1,
          offset: 0,
          limit: 8,
          generatedAt: '2026-04-03T12:00:00Z',
          items: [],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await listSessionMemoryDrafts('project-1', { limit: 8, sessionId: 'session-1', status: 'approved' });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/integrations/skillmeat/memory-drafts?projectId=project-1&offset=0&limit=8&sessionId=session-1&status=approved',
      undefined,
    );
  });

  it('serializes generate, review, and publish actions against assumed draft routes', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            projectId: 'project-1',
            generatedAt: '2026-04-03T12:00:00Z',
            sessionsConsidered: 1,
            draftsCreated: 1,
            draftsUpdated: 0,
            draftsSkipped: 0,
            items: [],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 17,
            projectId: 'project-1',
            sessionId: 'session-1',
            featureId: 'feature-1',
            rootSessionId: 'root-1',
            threadSessionId: 'thread-1',
            workflowRef: '/dev:execute-phase',
            title: 'Capture a rule',
            memoryType: 'learning',
            status: 'approved',
            moduleName: 'Captured Rules',
            moduleDescription: 'Notes from a successful session.',
            content: 'Document the important rule.',
            confidence: 0.82,
            sourceMessageId: 'msg-1',
            sourceLogId: 'log-1',
            sourceMessageIndex: 3,
            contentHash: 'abc123',
            evidence: {},
            publishAttempts: 0,
            publishedModuleId: '',
            publishedMemoryId: '',
            reviewedBy: 'ops-panel',
            reviewNotes: 'Looks good',
            reviewedAt: '2026-04-03T12:00:01Z',
            publishedAt: '',
            lastPublishError: '',
            createdAt: '2026-04-03T12:00:00Z',
            updatedAt: '2026-04-03T12:00:01Z',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 17,
            projectId: 'project-1',
            sessionId: 'session-1',
            featureId: 'feature-1',
            rootSessionId: 'root-1',
            threadSessionId: 'thread-1',
            workflowRef: '/dev:execute-phase',
            title: 'Capture a rule',
            memoryType: 'learning',
            status: 'published',
            moduleName: 'Captured Rules',
            moduleDescription: 'Notes from a successful session.',
            content: 'Document the important rule.',
            confidence: 0.82,
            sourceMessageId: 'msg-1',
            sourceLogId: 'log-1',
            sourceMessageIndex: 3,
            contentHash: 'abc123',
            evidence: {},
            publishAttempts: 1,
            publishedModuleId: 'module-1',
            publishedMemoryId: 'memory-1',
            reviewedBy: 'ops-panel',
            reviewNotes: 'Looks good',
            reviewedAt: '2026-04-03T12:00:01Z',
            publishedAt: '2026-04-03T12:02:00Z',
            lastPublishError: '',
            createdAt: '2026-04-03T12:00:00Z',
            updatedAt: '2026-04-03T12:02:00Z',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    await generateSessionMemoryDrafts('project-1', { sessionId: 'session-1', limit: 5, actor: 'ops-panel' });
    await reviewSessionMemoryDraft('project-1', 17, { decision: 'approved', actor: 'ops-panel', notes: 'Looks good' });
    await publishSessionMemoryDraft('project-1', 17, { actor: 'ops-panel', notes: 'Publish it' });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/integrations/skillmeat/memory-drafts/generate?projectId=project-1',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: 'session-1', limit: 5, actor: 'ops-panel' }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/integrations/skillmeat/memory-drafts/17/review?projectId=project-1',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'approved', actor: 'ops-panel', notes: 'Looks good' }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/integrations/skillmeat/memory-drafts/17/publish?projectId=project-1',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor: 'ops-panel', notes: 'Publish it' }),
      }),
    );
  });
});
