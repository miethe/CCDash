import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  FeatureSurfaceApiError,
  getFeatureLinkedSessionPage,
  getFeatureModalOverview,
  getFeatureModalSection,
  getFeatureRollups,
  listFeatureCards,
} from '../featureSurface';

// ── Helpers ───────────────────────────────────────────────────────────────────

function envelope<T>(data: T, status: 'ok' | 'partial' | 'error' = 'ok') {
  return { status, data, meta: { generated_at: '2026-04-23T00:00:00Z', instance_id: 'test' } };
}

function okJson(body: unknown, httpStatus = 200): Response {
  return new Response(JSON.stringify(body), {
    status: httpStatus,
    headers: { 'content-type': 'application/json' },
  });
}

function wireCard(overrides: Record<string, unknown> = {}) {
  return {
    id: 'FEAT-1',
    name: 'Test Feature',
    status: 'active',
    effective_status: 'in_progress',
    category: 'core',
    tags: ['tag-a'],
    summary: 'A summary',
    description_preview: 'preview text',
    priority: 'high',
    risk_level: 'medium',
    complexity: 'moderate',
    total_tasks: 10,
    completed_tasks: 4,
    deferred_tasks: 1,
    phase_count: 3,
    planned_at: '2026-01-01',
    started_at: '2026-02-01',
    completed_at: '',
    updated_at: '2026-04-01',
    document_coverage: { present: ['prd'], missing: ['plan'], counts_by_type: { prd: 1 } },
    quality_signals: {
      blocker_count: 0,
      at_risk_task_count: 1,
      has_blocking_signals: false,
      test_impact: 'low',
      integrity_signal_refs: [],
    },
    dependency_state: {
      state: 'ready',
      blocking_reason: '',
      blocked_by_count: 0,
      ready_dependency_count: 2,
    },
    primary_documents: [],
    family_position: null,
    related_feature_count: 0,
    precision: 'exact',
    freshness: null,
    ...overrides,
  };
}

function wireRollup(featureId = 'FEAT-1'): Record<string, unknown> {
  return {
    feature_id: featureId,
    session_count: 5,
    primary_session_count: 3,
    subthread_count: 2,
    unresolved_subthread_count: 0,
    total_cost: 1.23,
    display_cost: 1.23,
    observed_tokens: 50000,
    model_io_tokens: 48000,
    cache_input_tokens: 2000,
    latest_session_at: '2026-04-20T10:00:00Z',
    latest_activity_at: '2026-04-20T11:00:00Z',
    model_families: [{ key: 'claude', label: 'Claude', count: 5, share: 1.0 }],
    providers: [],
    workflow_types: [],
    linked_doc_count: 3,
    linked_doc_counts_by_type: [],
    linked_task_count: 10,
    linked_commit_count: null,
    linked_pr_count: null,
    test_count: null,
    failing_test_count: null,
    precision: 'eventually_consistent',
    freshness: null,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('featureSurface service', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── listFeatureCards ──────────────────────────────────────────────────────

  describe('listFeatureCards', () => {
    it('calls GET /api/v1/features with view=cards', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        okJson(envelope({ items: [wireCard()], total: 1, offset: 0, limit: 50, has_more: false, query_hash: 'abc', precision: 'exact', freshness: null })),
      );
      vi.stubGlobal('fetch', mockFetch);

      const result = await listFeatureCards({ q: 'auth' });

      const [url] = mockFetch.mock.calls[0] as [string];
      expect(url).toContain('/api/v1/features');
      expect(url).toContain('view=cards');
      expect(url).toContain('q=auth');
      expect(result.items).toHaveLength(1);
      expect(result.items[0].id).toBe('FEAT-1');
    });

    it('adapts snake_case fields to camelCase', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          okJson(envelope({ items: [wireCard()], total: 1, offset: 0, limit: 50, has_more: true, query_hash: 'qh', precision: 'exact', freshness: null })),
        ),
      );

      const result = await listFeatureCards();
      const card = result.items[0];

      expect(card.effectiveStatus).toBe('in_progress');
      expect(card.descriptionPreview).toBe('preview text');
      expect(card.totalTasks).toBe(10);
      expect(card.completedTasks).toBe(4);
      expect(card.deferredTasks).toBe(1);
      expect(card.documentCoverage.countsByType).toEqual({ prd: 1 });
      expect(card.qualitySignals.atRiskTaskCount).toBe(1);
      expect(card.dependencyState.readyDependencyCount).toBe(2);
      expect(result.hasMore).toBe(true);
      expect(result.queryHash).toBe('qh');
    });

    it('sends multi-value status, stage, and tags params', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        okJson(envelope({ items: [], total: 0, offset: 0, limit: 50, has_more: false, query_hash: '', precision: 'exact', freshness: null })),
      );
      vi.stubGlobal('fetch', mockFetch);

      await listFeatureCards({ status: ['active', 'planned'], stage: ['board'], tags: ['alpha'] });

      const [url] = mockFetch.mock.calls[0] as [string];
      expect(url).toContain('status=active');
      expect(url).toContain('status=planned');
      expect(url).toContain('stage=board');
      expect(url).toContain('tags=alpha');
    });

    it('computes offset from page + pageSize', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        okJson(envelope({ items: [], total: 0, offset: 100, limit: 25, has_more: false, query_hash: '', precision: 'exact', freshness: null })),
      );
      vi.stubGlobal('fetch', mockFetch);

      await listFeatureCards({ page: 5, pageSize: 25 });

      const [url] = mockFetch.mock.calls[0] as [string];
      expect(url).toContain('offset=100');
      expect(url).toContain('limit=25');
    });

    it('throws FeatureSurfaceApiError on HTTP error', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 500, statusText: 'Internal Server Error' })));

      await expect(listFeatureCards()).rejects.toBeInstanceOf(FeatureSurfaceApiError);
    });
  });

  // ── getFeatureRollups ─────────────────────────────────────────────────────

  describe('getFeatureRollups', () => {
    it('POSTs to /api/v1/features/rollups with snake_case body', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        okJson(envelope({
          rollups: { 'FEAT-1': wireRollup('FEAT-1') },
          missing: [],
          errors: {},
          generated_at: '2026-04-23T00:00:00Z',
          cache_version: 'v1',
        })),
      );
      vi.stubGlobal('fetch', mockFetch);

      const result = await getFeatureRollups({ featureIds: ['FEAT-1'], fields: ['session_counts'] });

      const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/features/rollups');
      expect(init.method).toBe('POST');
      const body = JSON.parse(init.body as string) as Record<string, unknown>;
      expect(body.feature_ids).toEqual(['FEAT-1']);
      expect(body.fields).toEqual(['session_counts']);

      expect(result.rollups['FEAT-1'].featureId).toBe('FEAT-1');
      expect(result.rollups['FEAT-1'].sessionCount).toBe(5);
      expect(result.rollups['FEAT-1'].modelFamilies[0].key).toBe('claude');
    });

    it('adapts rollup snake_case to camelCase', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          okJson(envelope({
            rollups: { 'FEAT-2': wireRollup('FEAT-2') },
            missing: [],
            errors: {},
            generated_at: '',
            cache_version: '',
          })),
        ),
      );

      const result = await getFeatureRollups({ featureIds: ['FEAT-2'] });
      const r = result.rollups['FEAT-2'];

      expect(r.primarySessionCount).toBe(3);
      expect(r.subthreadCount).toBe(2);
      expect(r.unresolvedSubthreadCount).toBe(0);
      expect(r.observedTokens).toBe(50000);
      expect(r.modelIoTokens).toBe(48000);
      expect(r.cacheInputTokens).toBe(2000);
      expect(r.latestSessionAt).toBe('2026-04-20T10:00:00Z');
      expect(r.latestActivityAt).toBe('2026-04-20T11:00:00Z');
      expect(r.linkedDocCount).toBe(3);
      expect(r.linkedTaskCount).toBe(10);
    });
  });

  // ── getFeatureModalOverview ───────────────────────────────────────────────

  describe('getFeatureModalOverview', () => {
    it('encodes the featureId in the path', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        okJson(envelope({
          feature_id: 'FEAT/1',
          card: wireCard({ id: 'FEAT/1' }),
          rollup: null,
          description: 'desc',
          precision: 'exact',
          freshness: null,
        })),
      );
      vi.stubGlobal('fetch', mockFetch);

      await getFeatureModalOverview('FEAT/1');

      const [url] = mockFetch.mock.calls[0] as [string];
      expect(url).toContain('FEAT%2F1');
      expect(url).toContain('/modal');
    });

    it('adapts overview including nested card and null rollup', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          okJson(envelope({
            feature_id: 'FEAT-1',
            card: wireCard(),
            rollup: wireRollup('FEAT-1'),
            description: 'Full description',
            precision: 'exact',
            freshness: null,
          })),
        ),
      );

      const result = await getFeatureModalOverview('FEAT-1');

      expect(result.featureId).toBe('FEAT-1');
      expect(result.card.name).toBe('Test Feature');
      expect(result.rollup?.featureId).toBe('FEAT-1');
      expect(result.description).toBe('Full description');
    });
  });

  // ── getFeatureModalSection ────────────────────────────────────────────────

  describe('getFeatureModalSection', () => {
    it('encodes both featureId and section in path', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        okJson(envelope({
          feature_id: 'FEAT-1',
          section: 'phases',
          title: 'Phases',
          items: [],
          total: 0,
          offset: 0,
          limit: 20,
          has_more: false,
          includes: [],
          precision: 'exact',
          freshness: null,
        })),
      );
      vi.stubGlobal('fetch', mockFetch);

      await getFeatureModalSection('FEAT/1', 'phases', { limit: 10, include: ['tasks'] });

      const [url] = mockFetch.mock.calls[0] as [string];
      expect(url).toContain('FEAT%2F1');
      expect(url).toContain('phases');
      expect(url).toContain('limit=10');
      expect(url).toContain('include=tasks');
    });

    it('adapts section items from snake_case', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          okJson(envelope({
            feature_id: 'FEAT-1',
            section: 'documents',
            title: 'Documents',
            items: [{ item_id: 'doc-1', label: 'PRD', kind: 'prd', status: 'active', description: 'desc', href: '/docs/prd', badges: ['draft'], metadata: {} }],
            total: 1,
            offset: 0,
            limit: 20,
            has_more: false,
            includes: [],
            precision: 'exact',
            freshness: null,
          })),
        ),
      );

      const result = await getFeatureModalSection('FEAT-1', 'documents');

      expect(result.items[0].itemId).toBe('doc-1');
      expect(result.hasMore).toBe(false);
    });
  });

  // ── getFeatureLinkedSessionPage ───────────────────────────────────────────

  describe('getFeatureLinkedSessionPage', () => {
    it('calls /sessions/page with encoded featureId', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        okJson(envelope({
          items: [],
          total: 0,
          offset: 0,
          limit: 20,
          has_more: false,
          next_cursor: null,
          enrichment: { includes: [], logs_read: false, command_count_included: false, task_refs_included: false, thread_children_included: false },
          precision: 'eventually_consistent',
          freshness: null,
        })),
      );
      vi.stubGlobal('fetch', mockFetch);

      await getFeatureLinkedSessionPage('FEAT/2', { limit: 20, offset: 0 });

      const [url] = mockFetch.mock.calls[0] as [string];
      expect(url).toContain('FEAT%2F2');
      expect(url).toContain('/sessions/page');
      expect(url).toContain('limit=20');
    });

    it('adapts linked session items from snake_case', async () => {
      const wireSession = {
        session_id: 'sess-1',
        title: 'Session 1',
        status: 'completed',
        model: 'claude-3-sonnet',
        model_provider: 'anthropic',
        model_family: 'claude',
        started_at: '2026-04-20T09:00:00Z',
        ended_at: '2026-04-20T10:00:00Z',
        updated_at: '2026-04-20T10:00:00Z',
        total_cost: 0.50,
        observed_tokens: 20000,
        root_session_id: 'root-1',
        parent_session_id: null,
        workflow_type: 'code',
        is_primary_link: true,
        is_subthread: false,
        thread_child_count: 0,
        reasons: ['slug_match'],
        commands: ['Bash'],
        related_tasks: [
          { task_id: 't-1', task_title: 'Task 1', phase_id: 'p-1', phase: 'Phase 1', matched_by: 'title' },
        ],
      };

      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          okJson(envelope({
            items: [wireSession],
            total: 1,
            offset: 0,
            limit: 20,
            has_more: false,
            next_cursor: null,
            enrichment: {
              includes: ['commands', 'tasks'],
              logs_read: true,
              command_count_included: true,
              task_refs_included: true,
              thread_children_included: false,
            },
            precision: 'eventually_consistent',
            freshness: null,
          })),
        ),
      );

      const result = await getFeatureLinkedSessionPage('FEAT-1');
      const s = result.items[0];

      expect(s.sessionId).toBe('sess-1');
      expect(s.modelProvider).toBe('anthropic');
      expect(s.modelFamily).toBe('claude');
      expect(s.isPrimaryLink).toBe(true);
      expect(s.isSubthread).toBe(false);
      expect(s.relatedTasks[0].taskId).toBe('t-1');
      expect(s.relatedTasks[0].matchedBy).toBe('title');
      expect(result.enrichment.logsRead).toBe(true);
      expect(result.enrichment.commandCountIncluded).toBe(true);
      expect(result.enrichment.taskRefsIncluded).toBe(true);
    });

    it('surfaces nextCursor when present', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          okJson(envelope({
            items: [],
            total: 42,
            offset: 20,
            limit: 20,
            has_more: true,
            next_cursor: 'cursor-abc',
            enrichment: {},
            precision: 'eventually_consistent',
            freshness: null,
          })),
        ),
      );

      const result = await getFeatureLinkedSessionPage('FEAT-1');
      expect(result.nextCursor).toBe('cursor-abc');
      expect(result.hasMore).toBe(true);
    });
  });

  // ── Error handling ────────────────────────────────────────────────────────

  describe('error handling', () => {
    it('throws FeatureSurfaceApiError when envelope status=error', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(okJson(envelope({}, 'error'))),
      );

      await expect(listFeatureCards()).rejects.toBeInstanceOf(FeatureSurfaceApiError);
    });

    it('FeatureSurfaceApiError carries http status', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404, statusText: 'Not Found' })));

      const err = await getFeatureModalOverview('FEAT-MISSING').catch((e: unknown) => e);
      expect(err).toBeInstanceOf(FeatureSurfaceApiError);
      expect((err as FeatureSurfaceApiError).status).toBe(404);
    });
  });
});
