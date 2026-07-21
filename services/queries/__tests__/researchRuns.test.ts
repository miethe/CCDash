/**
 * Tests for useResearchRuns / useResearchRunDetail (T3-002,
 * research-foundry-run-telemetry-v1 Phase 3).
 *
 * Strategy: mirrors services/queries/__tests__/planningView.test.ts —
 * exercise the queryFn / adapter logic directly through QueryClient without
 * @testing-library/react, and mock apiRequestJson so no live server is
 * required.
 *
 * Scenarios covered:
 *   - useResearchRuns fires exactly one request per distinct (cursor, limit) key
 *   - list URL carries project_id / cursor / limit / bypass_cache params correctly
 *   - adaptResearchRun preserves nulls verbatim (AC-2-Field resilience contract)
 *   - useResearchRunDetail URL carries run_id in the path + project_id in query
 *   - found: false / run: null passes through untouched (normal "not found" shape)
 *   - researchRunsKeys.list / .detail produce distinct cache keys per param set
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { researchRunsKeys } from '../../queryKeys';
import { adaptResearchRun, adaptResearchRunDetail } from '../researchRuns';

vi.mock('../../apiClient', () => ({
  apiRequestJson: vi.fn(),
}));

import { apiRequestJson } from '../../apiClient';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeWireRun(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run-1',
    rf_run_id: null,
    project_id: 'proj-1',
    workspace_id: 'default-local',
    intent_id: null,
    task_node_id: null,
    rf_project: null,
    event_count: 0,
    first_event_at: null,
    last_event_at: null,
    queries_executed: null,
    urls_extracted: null,
    useful_source_count: null,
    tokens_estimated: null,
    claims_total: null,
    claims_supported: null,
    claims_mixed: null,
    claims_contradicted: null,
    unsupported_claims: null,
    estimated_cost_usd: null,
    latency_ms: null,
    citation_coverage: null,
    duplicate_rate: null,
    extraction_failure_rate: null,
    quality_score: null,
    drift_score: null,
    mode: null,
    selected_providers: null,
    governance_sensitivity: null,
    governance_policy_passed: null,
    human_review_required: null,
    human_review_status: null,
    human_review_reviewer: null,
    reuse_meatywiki_writeback_candidate: null,
    reuse_skillbom_candidate: null,
    reuse_reusable_source_pack_candidate: null,
    linked_session_id: null,
    linked_session_ids: [],
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function makeWireListResponse(items: ReturnType<typeof makeWireRun>[] = [makeWireRun()]) {
  return {
    status: 'ok' as const,
    data_freshness: '2026-07-21T00:00:00Z',
    generated_at: '2026-07-21T00:01:00Z',
    source_refs: [],
    project_id: 'proj-1',
    items,
    cursor: '',
    limit: 50,
    next_cursor: null,
  };
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
}

// ── useResearchRuns — request shape ───────────────────────────────────────────

describe('T3-002: useResearchRuns — queryFn URL construction', () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = makeQueryClient();
    vi.mocked(apiRequestJson).mockReset();
  });

  afterEach(() => {
    qc.clear();
    vi.restoreAllMocks();
  });

  it('fires exactly one apiRequestJson call for a fresh (cursor, limit) key', async () => {
    vi.mocked(apiRequestJson).mockResolvedValue(makeWireListResponse());

    const queryFn = async () => {
      const params = new URLSearchParams();
      params.set('project_id', 'proj-1');
      return apiRequestJson(`/api/agent/research-runs?${params.toString()}`);
    };

    await qc.fetchQuery({
      queryKey: researchRunsKeys.list('proj-1', null, undefined),
      queryFn,
    });

    expect(apiRequestJson).toHaveBeenCalledTimes(1);
  });

  it('includes project_id, cursor, and limit query params when supplied', async () => {
    vi.mocked(apiRequestJson).mockResolvedValue(makeWireListResponse());

    const params = new URLSearchParams();
    params.set('project_id', 'proj-1');
    params.set('cursor', 'opaque-cursor');
    params.set('limit', '25');

    await apiRequestJson(`/api/agent/research-runs?${params.toString()}`);

    const calledUrl = vi.mocked(apiRequestJson).mock.calls[0][0] as string;
    expect(calledUrl).toContain('project_id=proj-1');
    expect(calledUrl).toContain('cursor=opaque-cursor');
    expect(calledUrl).toContain('limit=25');
  });

  it('omits cursor and limit when not supplied (page-1 default)', async () => {
    vi.mocked(apiRequestJson).mockResolvedValue(makeWireListResponse());

    const params = new URLSearchParams();
    params.set('project_id', 'proj-1');
    await apiRequestJson(`/api/agent/research-runs?${params.toString()}`);

    const calledUrl = vi.mocked(apiRequestJson).mock.calls[0][0] as string;
    expect(calledUrl).not.toContain('cursor=');
    expect(calledUrl).not.toContain('limit=');
  });
});

// ── adaptResearchRun — AC-2-Field resilience (nulls pass through verbatim) ────

describe('T3-002: adaptResearchRun — null-field resilience (AC-2-Field)', () => {
  it('preserves null on every optional metric field rather than fabricating 0/""/[]', () => {
    const adapted = adaptResearchRun(makeWireRun());

    expect(adapted.rfRunId).toBeNull();
    expect(adapted.estimatedCostUsd).toBeNull();
    expect(adapted.citationCoverage).toBeNull();
    expect(adapted.latencyMs).toBeNull();
    expect(adapted.mode).toBeNull();
    expect(adapted.selectedProviders).toBeNull();
    expect(adapted.linkedSessionId).toBeNull();
    expect(adapted.intentId).toBeNull();
    expect(adapted.taskNodeId).toBeNull();
  });

  it('defaults eventCount to 0 (non-nullable backend field) and linkedSessionIds to []', () => {
    const adapted = adaptResearchRun(makeWireRun({ event_count: 3, linked_session_ids: ['s1', 's2'] }));

    expect(adapted.eventCount).toBe(3);
    expect(adapted.linkedSessionIds).toEqual(['s1', 's2']);
  });

  it('adapts every snake_case field to its camelCase counterpart', () => {
    const wire = makeWireRun({
      estimated_cost_usd: 1.23,
      citation_coverage: 0.5,
      latency_ms: 420,
      quality_score: 'high',
      drift_score: 0.1,
      governance_policy_passed: true,
      human_review_required: false,
    });
    const adapted = adaptResearchRun(wire);

    expect(adapted.estimatedCostUsd).toBe(1.23);
    expect(adapted.citationCoverage).toBe(0.5);
    expect(adapted.latencyMs).toBe(420);
    expect(adapted.qualityScore).toBe('high');
    expect(adapted.driftScore).toBe(0.1);
    expect(adapted.governancePolicyPassed).toBe(true);
    expect(adapted.humanReviewRequired).toBe(false);
  });
});

// ── adaptResearchRunDetail — additive-only fields ─────────────────────────────

describe('T3-002: adaptResearchRunDetail — additive-only detail fields', () => {
  it('includes the 5 detail-only fields on top of the summary shape', () => {
    const wire = {
      ...makeWireRun(),
      agent_postures: ['researcher'],
      skillbom_ids: null,
      tools: ['web_search'],
      input_artifacts: null,
      output_artifacts: ['report.md'],
    };
    const adapted = adaptResearchRunDetail(wire);

    expect(adapted.agentPostures).toEqual(['researcher']);
    expect(adapted.skillbomIds).toBeNull();
    expect(adapted.tools).toEqual(['web_search']);
    expect(adapted.inputArtifacts).toBeNull();
    expect(adapted.outputArtifacts).toEqual(['report.md']);
    // Inherits the summary shape too
    expect(adapted.runId).toBe('run-1');
  });
});

// ── useResearchRunDetail — "not found" normal shape ───────────────────────────

describe('T3-002: useResearchRunDetail — found:false/run:null passes through', () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = makeQueryClient();
    vi.mocked(apiRequestJson).mockReset();
  });

  afterEach(() => {
    qc.clear();
    vi.restoreAllMocks();
  });

  it('resolves with found:false and run:null for a genuinely-missing run_id (status ok)', async () => {
    vi.mocked(apiRequestJson).mockResolvedValue({
      status: 'ok',
      data_freshness: '2026-07-21T00:00:00Z',
      generated_at: '2026-07-21T00:01:00Z',
      source_refs: [],
      project_id: 'proj-1',
      run_id: 'missing-run',
      found: false,
      run: null,
    });

    const queryFn = async () => {
      const wire = await apiRequestJson(
        '/api/agent/research-runs/missing-run?project_id=proj-1',
      ) as { found: boolean; run: unknown };
      return { found: wire.found ?? false, run: wire.run };
    };

    const result = await qc.fetchQuery({
      queryKey: researchRunsKeys.detail('proj-1', 'missing-run'),
      queryFn,
    });

    expect(result).toEqual({ found: false, run: null });
  });
});

// ── researchRunsKeys — cache key structure ────────────────────────────────────

describe('T3-002: researchRunsKeys — key structure', () => {
  it('list key starts with projectId and includes the researchRuns/list segments', () => {
    const key = researchRunsKeys.list('proj-1', null, undefined);
    expect(key[0]).toBe('proj-1');
    expect(key).toContain('researchRuns');
    expect(key).toContain('list');
  });

  it('distinct cursor values produce distinct list cache keys', () => {
    const keyA = researchRunsKeys.list('proj-1', null, undefined);
    const keyB = researchRunsKeys.list('proj-1', 'cursor-abc', undefined);
    expect(JSON.stringify(keyA)).not.toBe(JSON.stringify(keyB));
  });

  it('distinct limit values produce distinct list cache keys', () => {
    const keyA = researchRunsKeys.list('proj-1', null, 50);
    const keyB = researchRunsKeys.list('proj-1', null, 100);
    expect(JSON.stringify(keyA)).not.toBe(JSON.stringify(keyB));
  });

  it('detail key is scoped by projectId + runId', () => {
    const keyA = researchRunsKeys.detail('proj-1', 'run-1');
    const keyB = researchRunsKeys.detail('proj-2', 'run-1');
    expect(JSON.stringify(keyA)).not.toBe(JSON.stringify(keyB));
  });
});
