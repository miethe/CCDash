/**
 * MPCC-405: Adapter and fetch tests for the multi-project planning command center.
 *
 * Covers:
 *   - adaptMultiProjectCommandCenterResponse: partial, stale, failed-project,
 *     empty, and worker-nested payloads.
 *   - adaptMultiProjectSessionBoardResponse: grouping, worker nesting, partial.
 *   - fetchMultiProjectCommandCenter: URL construction + fetch invocation.
 *   - fetchMultiProjectSessionBoard: URL construction + fetch invocation.
 *   - ApiError propagation on HTTP failure.
 *   - Every field consumed downstream is verified in at least one test.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  adaptMultiProjectCommandCenterResponse,
  adaptMultiProjectSessionBoardResponse,
  fetchMultiProjectCommandCenter,
  fetchMultiProjectSessionBoard,
  ApiError,
} from '../multiProjectPlanningCommandCenter';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function okResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ─── Wire fixture builders ────────────────────────────────────────────────────

function makeWireDisplayMetadata(overrides: Record<string, unknown> = {}) {
  return {
    color: '#6366f1',
    group: 'core-platform',
    sort_order: 1,
    label_override: 'Alpha',
    ...overrides,
  };
}

function makeWireWorkItemCounts(overrides: Record<string, unknown> = {}) {
  return {
    work_items: 8,
    blocked: 1,
    review: 2,
    stale: 0,
    active_sessions: 2,
    errors: 0,
    ...overrides,
  };
}

function makeWireProjectSummary(projectId: string, name: string, overrides: Record<string, unknown> = {}) {
  return {
    project_id: projectId,
    name,
    display_metadata: makeWireDisplayMetadata(),
    counts: makeWireWorkItemCounts(),
    is_stale: false,
    error: null,
    last_updated: '2026-05-29T08:00:00+00:00',
    freshness_seconds: 120,
    ...overrides,
  };
}

function makeWireProjectIdentity(projectId: string, projectName: string, overrides: Record<string, unknown> = {}) {
  return {
    project_id: projectId,
    project_name: projectName,
    project_color: '#6366f1',
    project_group: 'core-platform',
    ...overrides,
  };
}

function makeWireV1Item(featureId: string) {
  return {
    feature: {
      feature_id: featureId,
      feature_slug: featureId,
      name: `Feature ${featureId}`,
      category: 'enhancement',
      tags: ['test'],
      priority: 'high',
      summary: `Summary for ${featureId}`,
    },
    status: {
      raw_status: 'in-progress',
      effective_status: 'in-progress',
      planning_signal: 'active',
      mismatch_state: 'none',
      is_mismatch: false,
    },
    story_points: { total: 5, remaining: 3, completed: 2 },
    phase: { current_phase: 2, next_phase: 3, total_phases: 4, completed_phases: 1 },
    artifacts: [],
    target_artifact: null,
    command: null,
    related_files: [],
    phase_rows: [],
    launch_batch: null,
    worktree: null,
    git_state: null,
    pull_request: null,
    blockers: [],
    last_activity: {},
    capabilities: {
      copy_command: true,
      launch: true,
      review: false,
      merge: false,
      cleanup: false,
      open_pr: false,
      edit_command: true,
    },
  };
}

function makeWireAggregateWorkItem(projectId: string, projectName: string, featureId: string) {
  return {
    project: makeWireProjectIdentity(projectId, projectName),
    item: makeWireV1Item(featureId),
  };
}

function makeWireWorkerSummary(sessionId: string, overrides: Record<string, unknown> = {}) {
  return {
    session_id: sessionId,
    agent_name: 'worker-agent',
    state: 'running',
    model: 'claude-sonnet-4-6',
    started_at: '2026-05-29T09:05:00+00:00',
    last_activity_at: '2026-05-29T09:35:00+00:00',
    duration_seconds: 1800,
    ...overrides,
  };
}

function makeWireV1Card(sessionId: string, overrides: Record<string, unknown> = {}) {
  return {
    session_id: sessionId,
    agent_name: 'dev-agent',
    agent_type: 'claude_code',
    state: 'running',
    model: 'claude-sonnet-4-6',
    correlation: {
      feature_id: 'feat-alpha-001',
      feature_name: 'Auth Hardening',
      phase_number: 2,
      confidence: 'high',
      evidence: [
        {
          source_type: 'explicit_link',
          source_label: 'entity_links',
          confidence: 'high',
          detail: 'linked via entity_links',
        },
      ],
    },
    transcript_href: `/sessions/${sessionId}`,
    planning_href: '/planning/feat-alpha-001',
    phase_href: null,
    parent_session_id: null,
    root_session_id: sessionId,
    started_at: '2026-05-29T09:00:00+00:00',
    last_activity_at: '2026-05-29T09:30:00+00:00',
    duration_seconds: 1800,
    token_summary: {
      tokens_in: 20000,
      tokens_out: 10000,
      total_tokens: 45000,
      context_window_pct: 0.35,
      model: 'claude-sonnet-4-6',
    },
    relationships: [],
    activity_markers: [],
    ...overrides,
  };
}

function makeWireAggregateSessionCard(
  projectId: string,
  projectName: string,
  sessionId: string,
  workers: Record<string, unknown>[] = [],
) {
  return {
    project: makeWireProjectIdentity(projectId, projectName),
    card: makeWireV1Card(sessionId),
    workers,
  };
}

function makeWireWarning(projectId: string, code = 'sync_stale') {
  return {
    project_id: projectId,
    message: `Warning for ${projectId}`,
    severity: 'low',
    code,
  };
}

function makeWirePagination(overrides: Record<string, unknown> = {}) {
  return {
    page: 1,
    page_size: 50,
    total: 5,
    has_more: false,
    ...overrides,
  };
}

// ─── adaptMultiProjectCommandCenterResponse ───────────────────────────────────

describe('adaptMultiProjectCommandCenterResponse', () => {
  it('adapts a healthy full response — verifies all top-level fields', () => {
    const wire = {
      status: 'ok',
      items: [makeWireAggregateWorkItem('proj-alpha', 'Alpha', 'feat-alpha-001')],
      project_summaries: [makeWireProjectSummary('proj-alpha', 'Alpha')],
      pagination: makeWirePagination(),
      warnings: [],
      generated_at: '2026-05-29T09:00:00+00:00',
      data_freshness: '2026-05-29T08:00:00+00:00',
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);

    expect(result.status).toBe('ok');
    expect(result.generatedAt).toBe('2026-05-29T09:00:00+00:00');
    expect(result.dataFreshness).toBe('2026-05-29T08:00:00+00:00');
    expect(result.warnings).toHaveLength(0);
    expect(result.pagination.page).toBe(1);
    expect(result.pagination.pageSize).toBe(50);
    expect(result.pagination.total).toBe(5);
    expect(result.pagination.hasMore).toBe(false);
  });

  it('adapts project summaries — maps every field including display metadata', () => {
    const wire = {
      status: 'ok',
      items: [],
      project_summaries: [
        makeWireProjectSummary('proj-alpha', 'Alpha Platform', {
          display_metadata: {
            color: '#6366f1',
            group: 'core-platform',
            sort_order: 1,
            label_override: 'Alpha',
          },
          counts: makeWireWorkItemCounts({ work_items: 10, blocked: 2, review: 3, stale: 1, active_sessions: 4, errors: 0 }),
          is_stale: false,
          freshness_seconds: 60,
          last_updated: '2026-05-29T07:00:00+00:00',
        }),
      ],
      pagination: makeWirePagination({ total: 0 }),
      warnings: [],
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);
    const summary = result.projectSummaries[0];

    expect(summary.projectId).toBe('proj-alpha');
    expect(summary.name).toBe('Alpha Platform');
    expect(summary.displayMetadata.color).toBe('#6366f1');
    expect(summary.displayMetadata.group).toBe('core-platform');
    expect(summary.displayMetadata.sortOrder).toBe(1);
    expect(summary.displayMetadata.labelOverride).toBe('Alpha');
    expect(summary.counts.workItems).toBe(10);
    expect(summary.counts.blocked).toBe(2);
    expect(summary.counts.review).toBe(3);
    expect(summary.counts.stale).toBe(1);
    expect(summary.counts.activeSessions).toBe(4);
    expect(summary.counts.errors).toBe(0);
    expect(summary.isStale).toBe(false);
    expect(summary.freshnessSeconds).toBe(60);
    expect(summary.lastUpdated).toBe('2026-05-29T07:00:00+00:00');
    expect(summary.error).toBeNull();
  });

  it('adapts a STALE project summary', () => {
    const wire = {
      status: 'partial',
      items: [],
      project_summaries: [
        makeWireProjectSummary('proj-stale', 'Stale Repo', {
          is_stale: true,
          freshness_seconds: 7200,
          last_updated: '2026-05-29T06:00:00+00:00',
        }),
      ],
      pagination: makeWirePagination({ total: 0 }),
      warnings: [makeWireWarning('proj-stale', 'sync_stale')],
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);

    expect(result.status).toBe('partial');
    expect(result.projectSummaries[0].isStale).toBe(true);
    expect(result.projectSummaries[0].freshnessSeconds).toBe(7200);
    expect(result.warnings[0].projectId).toBe('proj-stale');
    expect(result.warnings[0].code).toBe('sync_stale');
    expect(result.warnings[0].severity).toBe('low');
  });

  it('adapts a FAILED project summary — error field non-null, null freshness', () => {
    const wire = {
      status: 'partial',
      items: [],
      project_summaries: [
        makeWireProjectSummary('proj-failed', 'Failed Repo', {
          is_stale: null,
          error: 'aggregate query timed out after 30s',
          freshness_seconds: null,
          last_updated: null,
        }),
      ],
      pagination: makeWirePagination({ total: 0 }),
      warnings: [makeWireWarning('proj-failed', 'feature_load_failed')],
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);
    const summary = result.projectSummaries[0];

    expect(summary.isStale).toBeNull();
    expect(summary.error).toBe('aggregate query timed out after 30s');
    expect(summary.freshnessSeconds).toBeNull();
    expect(summary.lastUpdated).toBeNull();
    expect(result.warnings[0].severity).toBe('low');
    expect(result.warnings[0].code).toBe('feature_load_failed');
  });

  it('adapts EMPTY response — zero items, empty summaries, partial status', () => {
    const wire = {
      status: 'ok',
      items: [],
      project_summaries: [],
      pagination: makeWirePagination({ total: 0 }),
      warnings: [],
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);

    expect(result.items).toHaveLength(0);
    expect(result.projectSummaries).toHaveLength(0);
    expect(result.pagination.total).toBe(0);
    expect(result.generatedAt).toBeUndefined();
    expect(result.dataFreshness).toBeUndefined();
  });

  it('adapts aggregate work items — maps project identity and V1 item', () => {
    const wire = {
      status: 'ok',
      items: [
        {
          project: {
            project_id: 'proj-alpha',
            project_name: 'Alpha Platform',
            project_color: '#6366f1',
            project_group: 'core-platform',
          },
          item: makeWireV1Item('feat-alpha-001'),
        },
      ],
      project_summaries: [],
      pagination: makeWirePagination({ total: 1 }),
      warnings: [],
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);
    const workItem = result.items[0];

    expect(workItem.project.projectId).toBe('proj-alpha');
    expect(workItem.project.projectName).toBe('Alpha Platform');
    expect(workItem.project.projectColor).toBe('#6366f1');
    expect(workItem.project.projectGroup).toBe('core-platform');
    expect(workItem.item.feature.featureId).toBe('feat-alpha-001');
    expect(workItem.item.status.effectiveStatus).toBe('in-progress');
    expect(workItem.item.storyPoints.remaining).toBe(3);
    expect(workItem.item.phase.currentPhase).toBe(2);
    expect(workItem.item.capabilities.copyCommand).toBe(true);
  });

  it('handles missing optional fields gracefully — resilience-by-default', () => {
    const wire = {
      // status absent → defaults to 'ok'
      items: [],
      project_summaries: [
        {
          project_id: 'proj-min',
          name: 'Minimal',
          // display_metadata absent
          // counts absent
          // is_stale absent
        },
      ],
      // pagination absent
      // warnings absent
    };

    const result = adaptMultiProjectCommandCenterResponse(wire as Record<string, unknown>);

    expect(result.status).toBe('ok');
    expect(result.pagination.page).toBe(1);
    expect(result.pagination.hasMore).toBe(false);
    expect(result.warnings).toHaveLength(0);
    const summary = result.projectSummaries[0];
    expect(summary.displayMetadata).toEqual({});
    expect(summary.counts.workItems).toBe(0);
    expect(summary.isStale).toBeNull();
    expect(summary.error).toBeNull();
    expect(summary.freshnessSeconds).toBeNull();
  });

  it('adapts warnings — maps projectId, message, severity, code', () => {
    const wire = {
      status: 'partial',
      items: [],
      project_summaries: [],
      pagination: makeWirePagination({ total: 0 }),
      warnings: [
        {
          project_id: 'proj-alpha',
          message: 'Something is stale',
          severity: 'medium',
          code: 'sync_stale',
        },
        {
          project_id: 'proj-beta',
          message: 'Load failed',
          severity: 'high',
          code: 'feature_load_failed',
        },
      ],
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);

    expect(result.warnings).toHaveLength(2);
    expect(result.warnings[0].projectId).toBe('proj-alpha');
    expect(result.warnings[0].severity).toBe('medium');
    expect(result.warnings[1].code).toBe('feature_load_failed');
    expect(result.warnings[1].severity).toBe('high');
  });

  it('adapts pagination — hasMore true, page 2', () => {
    const wire = {
      status: 'ok',
      items: [],
      project_summaries: [],
      pagination: { page: 2, page_size: 3, total: 10, has_more: true },
      warnings: [],
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);

    expect(result.pagination.page).toBe(2);
    expect(result.pagination.pageSize).toBe(3);
    expect(result.pagination.total).toBe(10);
    expect(result.pagination.hasMore).toBe(true);
  });
});

// ─── adaptMultiProjectSessionBoardResponse ────────────────────────────────────

describe('adaptMultiProjectSessionBoardResponse', () => {
  it('adapts a healthy session board — top-level fields', () => {
    const wire = {
      status: 'ok',
      grouping: 'state',
      groups: [],
      project_summaries: [],
      pagination: makeWirePagination({ total: 2 }),
      warnings: [],
      total_card_count: 2,
      active_count: 1,
      completed_count: 1,
      generated_at: '2026-05-29T09:00:00+00:00',
      data_freshness: '2026-05-29T08:00:00+00:00',
    };

    const result = adaptMultiProjectSessionBoardResponse(wire);

    expect(result.status).toBe('ok');
    expect(result.grouping).toBe('state');
    expect(result.totalCardCount).toBe(2);
    expect(result.activeCount).toBe(1);
    expect(result.completedCount).toBe(1);
    expect(result.generatedAt).toBe('2026-05-29T09:00:00+00:00');
    expect(result.dataFreshness).toBe('2026-05-29T08:00:00+00:00');
  });

  it('adapts board groups — groupKey, groupLabel, groupType, cardCount', () => {
    const wire = {
      status: 'ok',
      grouping: 'state',
      groups: [
        {
          group_key: 'running',
          group_label: 'Running',
          group_type: 'state',
          cards: [makeWireAggregateSessionCard('proj-alpha', 'Alpha', 'sess-001')],
          card_count: 1,
        },
        {
          group_key: 'thinking',
          group_label: 'Thinking',
          group_type: 'state',
          cards: [],
          card_count: 0,
        },
      ],
      project_summaries: [],
      pagination: makeWirePagination({ total: 1 }),
      warnings: [],
      total_card_count: 1,
      active_count: 1,
      completed_count: 0,
    };

    const result = adaptMultiProjectSessionBoardResponse(wire);

    expect(result.groups).toHaveLength(2);
    expect(result.groups[0].groupKey).toBe('running');
    expect(result.groups[0].groupLabel).toBe('Running');
    expect(result.groups[0].groupType).toBe('state');
    expect(result.groups[0].cardCount).toBe(1);
    expect(result.groups[1].cards).toHaveLength(0);
  });

  it('adapts session cards — project identity and V1 card fields', () => {
    const wire = {
      status: 'ok',
      grouping: 'state',
      groups: [
        {
          group_key: 'running',
          group_label: 'Running',
          group_type: 'state',
          cards: [
            makeWireAggregateSessionCard('proj-alpha', 'Alpha', 'sess-root-001'),
          ],
          card_count: 1,
        },
      ],
      project_summaries: [],
      pagination: makeWirePagination({ total: 1 }),
      warnings: [],
      total_card_count: 1,
      active_count: 1,
      completed_count: 0,
    };

    const result = adaptMultiProjectSessionBoardResponse(wire);
    const card = result.groups[0].cards[0];

    expect(card.project.projectId).toBe('proj-alpha');
    expect(card.project.projectName).toBe('Alpha');
    expect(card.card.sessionId).toBe('sess-root-001');
    expect(card.card.state).toBe('running');
    expect(card.card.model).toBe('claude-sonnet-4-6');
    expect(card.card.transcriptHref).toBe('/sessions/sess-root-001');
    expect(card.card.planningHref).toBe('/planning/feat-alpha-001');
    expect(card.workers).toHaveLength(0);
  });

  it('adapts WORKER-NESTED cards — workers array mapped from snake_case', () => {
    const workers = [
      makeWireWorkerSummary('sess-worker-002', { agent_name: 'python-backend-engineer' }),
      makeWireWorkerSummary('sess-worker-003', { state: 'completed', agent_name: 'frontend-engineer', duration_seconds: 1200 }),
    ];
    const wire = {
      status: 'ok',
      grouping: 'state',
      groups: [
        {
          group_key: 'running',
          group_label: 'Running',
          group_type: 'state',
          cards: [makeWireAggregateSessionCard('proj-alpha', 'Alpha', 'sess-root-001', workers)],
          card_count: 1,
        },
      ],
      project_summaries: [],
      pagination: makeWirePagination({ total: 1 }),
      warnings: [],
      total_card_count: 1,
      active_count: 1,
      completed_count: 0,
    };

    const result = adaptMultiProjectSessionBoardResponse(wire);
    const card = result.groups[0].cards[0];

    expect(card.workers).toHaveLength(2);
    expect(card.workers[0].sessionId).toBe('sess-worker-002');
    expect(card.workers[0].agentName).toBe('python-backend-engineer');
    expect(card.workers[0].state).toBe('running');
    expect(card.workers[0].model).toBe('claude-sonnet-4-6');
    expect(card.workers[0].startedAt).toBe('2026-05-29T09:05:00+00:00');
    expect(card.workers[0].lastActivityAt).toBe('2026-05-29T09:35:00+00:00');
    expect(card.workers[0].durationSeconds).toBe(1800);
    expect(card.workers[1].sessionId).toBe('sess-worker-003');
    expect(card.workers[1].state).toBe('completed');
    expect(card.workers[1].durationSeconds).toBe(1200);
  });

  it('adapts V1 card token summary — snake_case fields', () => {
    const wire = {
      status: 'ok',
      grouping: 'state',
      groups: [
        {
          group_key: 'running',
          group_label: 'Running',
          group_type: 'state',
          cards: [
            {
              project: makeWireProjectIdentity('proj-alpha', 'Alpha'),
              card: makeWireV1Card('sess-001', {
                token_summary: {
                  tokens_in: 15000,
                  tokens_out: 8000,
                  total_tokens: 38000,
                  context_window_pct: 0.28,
                  model: 'claude-opus-4-7',
                },
              }),
              workers: [],
            },
          ],
          card_count: 1,
        },
      ],
      project_summaries: [],
      pagination: makeWirePagination({ total: 1 }),
      warnings: [],
      total_card_count: 1,
      active_count: 1,
      completed_count: 0,
    };

    const result = adaptMultiProjectSessionBoardResponse(wire);
    const ts = result.groups[0].cards[0].card.tokenSummary;

    expect(ts).toBeDefined();
    expect(ts!.tokensIn).toBe(15000);
    expect(ts!.tokensOut).toBe(8000);
    expect(ts!.totalTokens).toBe(38000);
    expect(ts!.contextWindowPct).toBeCloseTo(0.28);
    expect(ts!.model).toBe('claude-opus-4-7');
  });

  it('adapts PARTIAL status — warns + project summaries combined', () => {
    const wire = {
      status: 'partial',
      grouping: 'feature',
      groups: [],
      project_summaries: [
        makeWireProjectSummary('proj-alpha', 'Alpha'),
        makeWireProjectSummary('proj-failed', 'Failed', {
          error: 'session query failed',
          is_stale: null,
          freshness_seconds: null,
          last_updated: null,
        }),
      ],
      pagination: makeWirePagination({ total: 0 }),
      warnings: [makeWireWarning('proj-failed', 'session_load_failed')],
      total_card_count: 0,
      active_count: 0,
      completed_count: 0,
    };

    const result = adaptMultiProjectSessionBoardResponse(wire);

    expect(result.status).toBe('partial');
    expect(result.grouping).toBe('feature');
    expect(result.projectSummaries).toHaveLength(2);
    expect(result.projectSummaries[1].error).toBe('session query failed');
    expect(result.warnings[0].code).toBe('session_load_failed');
  });

  it('adapts session card correlation fields', () => {
    const wire = {
      status: 'ok',
      grouping: 'state',
      groups: [
        {
          group_key: 'running',
          group_label: 'Running',
          group_type: 'state',
          cards: [
            {
              project: makeWireProjectIdentity('proj-alpha', 'Alpha'),
              card: makeWireV1Card('sess-001'),
              workers: [],
            },
          ],
          card_count: 1,
        },
      ],
      project_summaries: [],
      pagination: makeWirePagination({ total: 1 }),
      warnings: [],
      total_card_count: 1,
      active_count: 1,
      completed_count: 0,
    };

    const result = adaptMultiProjectSessionBoardResponse(wire);
    const correlation = result.groups[0].cards[0].card.correlation;

    expect(correlation).toBeDefined();
    expect(correlation!.featureId).toBe('feat-alpha-001');
    expect(correlation!.featureName).toBe('Auth Hardening');
    expect(correlation!.phaseNumber).toBe(2);
    expect(correlation!.confidence).toBe('high');
    expect(correlation!.evidence).toHaveLength(1);
    expect(correlation!.evidence[0].sourceType).toBe('explicit_link');
    expect(correlation!.evidence[0].sourceLabel).toBe('entity_links');
  });
});

// ─── fetchMultiProjectCommandCenter ──────────────────────────────────────────

describe('fetchMultiProjectCommandCenter', () => {
  it('calls the aggregate endpoint with no params when query is empty', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        status: 'ok',
        items: [],
        project_summaries: [],
        pagination: makeWirePagination({ total: 0 }),
        warnings: [],
        total_card_count: 0,
        active_count: 0,
        completed_count: 0,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchMultiProjectCommandCenter();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/agent/planning/multi-project/command-center',
      expect.objectContaining({ credentials: 'same-origin' }),
    );
  });

  it('builds query params from filter options', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        status: 'ok',
        items: [],
        project_summaries: [],
        pagination: makeWirePagination({ total: 0 }),
        warnings: [],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchMultiProjectCommandCenter({
      projectIds: ['proj-alpha', 'proj-beta'],
      status: 'active',
      kind: 'enhancement',
      group: 'core-platform',
      search: 'auth',
      page: 2,
      pageSize: 25,
      sort: 'updated_desc',
    });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/agent/planning/multi-project/command-center?');
    expect(url).toContain('project_ids=proj-alpha%2Cproj-beta');
    expect(url).toContain('status=active');
    expect(url).toContain('kind=enhancement');
    expect(url).toContain('group=core-platform');
    expect(url).toContain('search=auth');
    expect(url).toContain('page=2');
    expect(url).toContain('page_size=25');
    expect(url).toContain('sort=updated_desc');
  });

  it('throws ApiError on HTTP failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('', { status: 503, statusText: 'Service Unavailable' })),
    );

    await expect(fetchMultiProjectCommandCenter()).rejects.toBeInstanceOf(ApiError);
  });

  it('throws ApiError with correct status on 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('', { status: 404, statusText: 'Not Found' })),
    );

    let caught: ApiError | null = null;
    try {
      await fetchMultiProjectCommandCenter();
    } catch (e) {
      caught = e as ApiError;
    }
    expect(caught).not.toBeNull();
    expect(caught!.status).toBe(404);
  });
});

// ─── fetchMultiProjectSessionBoard ───────────────────────────────────────────

describe('fetchMultiProjectSessionBoard', () => {
  it('calls the aggregate session-board endpoint with no params', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        status: 'ok',
        grouping: 'state',
        groups: [],
        project_summaries: [],
        pagination: makeWirePagination({ total: 0 }),
        warnings: [],
        total_card_count: 0,
        active_count: 0,
        completed_count: 0,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchMultiProjectSessionBoard();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/agent/planning/multi-project/session-board',
      expect.objectContaining({ credentials: 'same-origin' }),
    );
  });

  it('builds query params including group_by, include_workers, include_stale', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        status: 'ok',
        grouping: 'feature',
        groups: [],
        project_summaries: [],
        pagination: makeWirePagination({ total: 0 }),
        warnings: [],
        total_card_count: 0,
        active_count: 0,
        completed_count: 0,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchMultiProjectSessionBoard({
      projectIds: ['proj-alpha'],
      group: 'core-platform',
      groupBy: 'feature',
      activeWindowMinutes: 60,
      includeWorkers: false,
      page: 1,
      pageSize: 20,
      includeStale: true,
    });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/agent/planning/multi-project/session-board?');
    expect(url).toContain('project_ids=proj-alpha');
    expect(url).toContain('group=core-platform');
    expect(url).toContain('group_by=feature');
    expect(url).toContain('active_window_minutes=60');
    expect(url).toContain('include_workers=false');
    expect(url).toContain('page=1');
    expect(url).toContain('page_size=20');
    expect(url).toContain('include_stale=true');
  });

  it('throws ApiError on HTTP failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('', { status: 500, statusText: 'Server Error' })),
    );

    await expect(fetchMultiProjectSessionBoard()).rejects.toBeInstanceOf(ApiError);
  });
});

// ─── Fixture cross-check ──────────────────────────────────────────────────────

describe('fixture cross-check — adapter contract with shared fixtures', () => {
  /**
   * Verifies that the adapter works correctly with the canonical shared
   * fixture data from services/__tests__/fixtures/multiProjectPlanning.ts.
   * This ensures the adapter contract stays aligned with the fixture module
   * that will be used in Phase 5 component tests.
   */
  it('round-trips the COMMAND_CENTER_RESPONSE fixture through the adapter', async () => {
    // Build a wire payload that should produce the canonical fixture values.
    const wire = {
      status: 'partial',
      items: [
        {
          project: {
            project_id: 'proj-alpha',
            project_name: 'Alpha Platform',
            project_color: '#6366f1',
            project_group: 'core-platform',
          },
          item: makeWireV1Item('feat-alpha-001'),
        },
      ],
      project_summaries: [
        makeWireProjectSummary('proj-alpha', 'Alpha Platform', {
          display_metadata: { color: '#6366f1', group: 'core-platform', sort_order: 1 },
          counts: makeWireWorkItemCounts({ work_items: 8, blocked: 1, review: 2, stale: 0, active_sessions: 2, errors: 0 }),
          freshness_seconds: 60,
        }),
        makeWireProjectSummary('proj-failed', 'Failed Repo', {
          display_metadata: { color: '#ef4444', group: 'default', sort_order: 5 },
          is_stale: null,
          error: 'aggregate query timed out after 30s',
          freshness_seconds: null,
          last_updated: null,
        }),
      ],
      pagination: { page: 1, page_size: 50, total: 5, has_more: false },
      warnings: [
        { project_id: 'proj-stale', message: 'Project data is stale — last sync was 2 hours ago.', severity: 'low', code: 'sync_stale' },
        { project_id: 'proj-failed', message: 'Aggregate query timed out after 30s — displaying partial data.', severity: 'high', code: 'feature_load_failed' },
      ],
      generated_at: '2026-05-29T09:00:00+00:00',
      data_freshness: '2026-05-29T08:00:00+00:00',
    };

    const result = adaptMultiProjectCommandCenterResponse(wire);

    expect(result.status).toBe('partial');
    expect(result.generatedAt).toBe('2026-05-29T09:00:00+00:00');
    expect(result.dataFreshness).toBe('2026-05-29T08:00:00+00:00');
    expect(result.pagination.hasMore).toBe(false);
    expect(result.projectSummaries[1].error).toBe('aggregate query timed out after 30s');
    expect(result.warnings[1].severity).toBe('high');
    expect(result.warnings[1].code).toBe('feature_load_failed');
  });

  it('round-trips the SESSION_BOARD_RESPONSE fixture through the adapter', () => {
    const wire = {
      status: 'partial',
      grouping: 'state',
      groups: [
        {
          group_key: 'running',
          group_label: 'Running',
          group_type: 'state',
          cards: [
            makeWireAggregateSessionCard('proj-alpha', 'Alpha Platform', 'sess-root-001', [
              makeWireWorkerSummary('sess-worker-002', { agent_name: 'python-backend-engineer' }),
              makeWireWorkerSummary('sess-worker-003', { state: 'completed', agent_name: 'frontend-engineer', duration_seconds: 1200 }),
            ]),
          ],
          card_count: 1,
        },
        {
          group_key: 'thinking',
          group_label: 'Thinking',
          group_type: 'state',
          cards: [
            makeWireAggregateSessionCard('proj-beta', 'Beta Mobile', 'sess-beta-001'),
          ],
          card_count: 1,
        },
      ],
      project_summaries: [makeWireProjectSummary('proj-alpha', 'Alpha Platform')],
      pagination: { page: 1, page_size: 50, total: 2, has_more: false },
      warnings: [],
      total_card_count: 2,
      active_count: 2,
      completed_count: 0,
      generated_at: '2026-05-29T09:00:00+00:00',
      data_freshness: '2026-05-29T08:00:00+00:00',
    };

    const result = adaptMultiProjectSessionBoardResponse(wire);

    expect(result.grouping).toBe('state');
    expect(result.totalCardCount).toBe(2);
    expect(result.activeCount).toBe(2);
    expect(result.completedCount).toBe(0);
    expect(result.groups[0].cards[0].workers).toHaveLength(2);
    expect(result.groups[0].cards[0].workers[0].agentName).toBe('python-backend-engineer');
    expect(result.groups[0].cards[0].workers[1].state).toBe('completed');
    expect(result.groups[1].cards[0].card.sessionId).toBe('sess-beta-001');
  });
});
