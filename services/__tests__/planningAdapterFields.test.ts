/**
 * Adapter-path unit tests for the four new wire fields added in phase 3–4:
 *
 *   1. WirePlanningAgentSessionCard.git_branch / git_commit_hash  (Fix 1 — CRITICAL)
 *   2. WirePhaseContextItem.linked_sessions_by_phase               (Fix 4 — HIGH)
 *   3. adaptPlanningCommandCenterItem.active_sessions              (Fix 2 — CRITICAL)
 *   4. adaptPlanningCommandCenterItem.commit_refs / pr_refs        (Fix 2 — CRITICAL)
 *   5. phaseRow.linked_sessions                                    (Fix 3 — HIGH)
 *
 * Strategy: test via the public adapters (adaptPlanningAgentSessionBoard,
 * getFeaturePlanningContext mock, adaptPlanningCommandCenterPage) so the
 * tests exercise the full adapter pipeline, not just type assertions.
 *
 * Each test group has:
 *   (a) Populated-field test: assert camelCase mapped output matches wire input.
 *   (b) Absent-field test: assert undefined/empty fallback when field missing.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  adaptPlanningAgentSessionBoard,
  getFeaturePlanningContext,
} from '../planning';
import { adaptPlanningCommandCenterPage } from '../planningCommandCenter';

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── 1. WirePlanningAgentSessionCard: git_branch / git_commit_hash ─────────────

describe('adaptPlanningAgentSessionBoard — git_branch / git_commit_hash adapter path', () => {
  function makeBoardWire(cardOverrides: Record<string, unknown> = {}) {
    return {
      project_id: 'proj-1',
      grouping: 'state',
      groups: [
        {
          group_key: 'running',
          group_label: 'Running',
          group_type: 'state',
          card_count: 1,
          cards: [
            {
              session_id: 'sess-1',
              state: 'running',
              relationships: [],
              activity_markers: [],
              ...cardOverrides,
            },
          ],
        },
      ],
      total_card_count: 1,
      active_count: 1,
      completed_count: 0,
    };
  }

  it('maps git_branch from wire to gitBranch on the card', () => {
    const board = adaptPlanningAgentSessionBoard(
      makeBoardWire({ git_branch: 'feat/my-feature' }) as Parameters<typeof adaptPlanningAgentSessionBoard>[0],
    );
    const card = board.groups[0].cards[0];
    expect(card.gitBranch).toBe('feat/my-feature');
  });

  it('maps git_commit_hash from wire to gitCommitHash on the card', () => {
    const board = adaptPlanningAgentSessionBoard(
      makeBoardWire({ git_commit_hash: 'abc1234def5678' }) as Parameters<typeof adaptPlanningAgentSessionBoard>[0],
    );
    const card = board.groups[0].cards[0];
    expect(card.gitCommitHash).toBe('abc1234def5678');
  });

  it('sets gitBranch to null when git_branch is absent', () => {
    const board = adaptPlanningAgentSessionBoard(
      makeBoardWire() as Parameters<typeof adaptPlanningAgentSessionBoard>[0],
    );
    const card = board.groups[0].cards[0];
    expect(card.gitBranch).toBeNull();
  });

  it('sets gitCommitHash to null when git_commit_hash is absent', () => {
    const board = adaptPlanningAgentSessionBoard(
      makeBoardWire() as Parameters<typeof adaptPlanningAgentSessionBoard>[0],
    );
    const card = board.groups[0].cards[0];
    expect(card.gitCommitHash).toBeNull();
  });

  it('maps git_branch=null wire value to gitBranch=null', () => {
    const board = adaptPlanningAgentSessionBoard(
      makeBoardWire({ git_branch: null }) as Parameters<typeof adaptPlanningAgentSessionBoard>[0],
    );
    expect(board.groups[0].cards[0].gitBranch).toBeNull();
  });
});

// ── 2. WirePhaseContextItem: linked_sessions_by_phase ────────────────────────

describe('getFeaturePlanningContext — linked_sessions_by_phase adapter path', () => {
  function makeContextPayload(phaseOverrides: Record<string, unknown> = {}) {
    return {
      status: 'ok',
      data_freshness: '2026-06-01T00:00:00Z',
      generated_at: '2026-06-01T00:01:00Z',
      source_refs: [],
      feature_id: 'feat-1',
      feature_name: 'Feature One',
      raw_status: 'active',
      effective_status: 'active',
      mismatch_state: 'none',
      planning_status: {},
      graph: { nodes: [], edges: [], phase_batches: [] },
      blocked_batch_ids: [],
      linked_artifact_refs: [],
      specs: [],
      prds: [],
      plans: [],
      ctxs: [],
      reports: [],
      spikes: [],
      open_questions: [],
      ready_to_promote: false,
      phases: [
        {
          phase_id: 'phase-2',
          phase_token: 'phase-2',
          phase_title: 'Phase 2',
          raw_status: 'in_progress',
          effective_status: 'in_progress',
          is_mismatch: false,
          mismatch_state: 'none',
          planning_status: {},
          batches: [],
          blocked_batch_ids: [],
          total_tasks: 3,
          completed_tasks: 1,
          deferred_tasks: 0,
          ...phaseOverrides,
        },
      ],
    };
  }

  it('maps linked_sessions_by_phase from wire to linkedSessionsByPhase on PhaseContextItem', async () => {
    const payload = makeContextPayload({
      linked_sessions_by_phase: {
        2: [
          {
            session_id: 'sess-abc',
            agent_name: 'Sonnet',
            start_time: '2026-06-01T10:00:00Z',
            transcript_href: '#/sessions/sess-abc',
          },
        ],
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(payload)));

    const ctx = await getFeaturePlanningContext('feat-1');
    const phase = ctx.phases[0];

    expect(phase.linkedSessionsByPhase).toBeDefined();
    expect(phase.linkedSessionsByPhase?.[2]).toHaveLength(1);
    expect(phase.linkedSessionsByPhase?.[2][0].sessionId).toBe('sess-abc');
    expect(phase.linkedSessionsByPhase?.[2][0].agentName).toBe('Sonnet');
    expect(phase.linkedSessionsByPhase?.[2][0].transcriptHref).toBe('#/sessions/sess-abc');
  });

  it('sets linkedSessionsByPhase to undefined when wire field is absent', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(makeContextPayload())));

    const ctx = await getFeaturePlanningContext('feat-1');
    expect(ctx.phases[0].linkedSessionsByPhase).toBeUndefined();
  });

  it('sets linkedSessionsByPhase to undefined when wire field is null', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(makeContextPayload({ linked_sessions_by_phase: null })),
    ));

    const ctx = await getFeaturePlanningContext('feat-1');
    expect(ctx.phases[0].linkedSessionsByPhase).toBeUndefined();
  });
});

// ── 3–4. adaptPlanningCommandCenterItem: active_sessions / commit_refs / pr_refs ──

describe('adaptPlanningCommandCenterPage — active_sessions / commit_refs / pr_refs adapter path', () => {
  function makePagePayload(itemOverrides: Record<string, unknown> = {}) {
    return {
      status: 'ok',
      data_freshness: '2026-06-01T00:00:00Z',
      generated_at: '2026-06-01T00:01:00Z',
      source_refs: [],
      project_id: 'proj-1',
      total: 1,
      page: 1,
      page_size: 50,
      sort_by: 'priority',
      sort_direction: 'desc',
      warnings: [],
      items: [
        {
          feature: {
            feature_id: 'feat-a',
            feature_slug: 'feat-a',
            name: 'Feature A',
            category: 'enhancement',
            tags: [],
            priority: 'high',
            summary: 'Summary',
          },
          status: { raw_status: 'active', effective_status: 'active', planning_signal: 'active', mismatch_state: 'none', is_mismatch: false },
          story_points: {},
          phase: {},
          artifacts: [],
          related_files: [],
          phase_rows: [],
          blockers: [],
          last_activity: {},
          capabilities: {},
          ...itemOverrides,
        },
      ],
    };
  }

  it('maps active_sessions from wire to activeSessions on the item', () => {
    const page = adaptPlanningCommandCenterPage(
      makePagePayload({
        active_sessions: [
          { session_id: 'sess-x', state: 'running', agent_name: 'Opus' },
        ],
      }) as Record<string, unknown>,
    );
    const item = page.items[0];
    expect(item.activeSessions).toHaveLength(1);
    expect(item.activeSessions?.[0].sessionId).toBe('sess-x');
    expect(item.activeSessions?.[0].agentName).toBe('Opus');
  });

  it('sets activeSessions to empty array when wire field is absent', () => {
    const page = adaptPlanningCommandCenterPage(makePagePayload() as Record<string, unknown>);
    expect(page.items[0].activeSessions).toEqual([]);
  });

  it('maps commit_refs from wire to commitRefs on the item', () => {
    const page = adaptPlanningCommandCenterPage(
      makePagePayload({ commit_refs: ['sha-001', 'sha-002'] }) as Record<string, unknown>,
    );
    expect(page.items[0].commitRefs).toEqual(['sha-001', 'sha-002']);
  });

  it('sets commitRefs to empty array when wire field is absent', () => {
    const page = adaptPlanningCommandCenterPage(makePagePayload() as Record<string, unknown>);
    expect(page.items[0].commitRefs).toEqual([]);
  });

  it('maps pr_refs from wire to prRefs on the item', () => {
    const page = adaptPlanningCommandCenterPage(
      makePagePayload({ pr_refs: ['#42', '#99'] }) as Record<string, unknown>,
    );
    expect(page.items[0].prRefs).toEqual(['#42', '#99']);
  });

  it('sets prRefs to empty array when wire field is absent', () => {
    const page = adaptPlanningCommandCenterPage(makePagePayload() as Record<string, unknown>);
    expect(page.items[0].prRefs).toEqual([]);
  });
});

// ── 5. phaseRow linked_sessions ──────────────────────────────────────────────

describe('adaptPlanningCommandCenterPage — phase_row.linked_sessions adapter path', () => {
  function makePageWithPhaseRows(phaseRowOverrides: Record<string, unknown> = {}) {
    return {
      status: 'ok',
      data_freshness: '2026-06-01T00:00:00Z',
      generated_at: '2026-06-01T00:01:00Z',
      source_refs: [],
      project_id: 'proj-1',
      total: 1,
      page: 1,
      page_size: 50,
      sort_by: 'priority',
      sort_direction: 'desc',
      warnings: [],
      items: [
        {
          feature: { feature_id: 'feat-b', feature_slug: 'feat-b', name: 'B', category: '', tags: [], priority: '', summary: '' },
          status: { raw_status: 'active', effective_status: 'active', planning_signal: 'active', mismatch_state: 'none', is_mismatch: false },
          story_points: {},
          phase: {},
          artifacts: [],
          related_files: [],
          blockers: [],
          last_activity: {},
          capabilities: {},
          phase_rows: [
            {
              phase_number: 2,
              name: 'Phase 2',
              story_points: 5,
              phase_files: [],
              domain: '',
              model: '',
              agents: [],
              status: 'in_progress',
              details: {},
              ...phaseRowOverrides,
            },
          ],
        },
      ],
    };
  }

  it('maps linked_sessions from wire phaseRow to linkedSessions on PlanningCommandCenterPhaseRow', () => {
    const page = adaptPlanningCommandCenterPage(
      makePageWithPhaseRows({
        linked_sessions: [
          {
            session_id: 'sess-p2',
            agent_name: 'Haiku',
            start_time: '2026-06-01T09:00:00Z',
            transcript_href: '#/sessions/sess-p2',
          },
        ],
      }) as Record<string, unknown>,
    );
    const row = page.items[0].phaseRows[0];
    expect(row.linkedSessions).toHaveLength(1);
    expect(row.linkedSessions?.[0].sessionId).toBe('sess-p2');
    expect(row.linkedSessions?.[0].agentName).toBe('Haiku');
    expect(row.linkedSessions?.[0].transcriptHref).toBe('#/sessions/sess-p2');
  });

  it('sets linkedSessions to undefined when linked_sessions is absent', () => {
    const page = adaptPlanningCommandCenterPage(
      makePageWithPhaseRows() as Record<string, unknown>,
    );
    expect(page.items[0].phaseRows[0].linkedSessions).toBeUndefined();
  });

  it('sets linkedSessions to empty array when linked_sessions is empty array', () => {
    const page = adaptPlanningCommandCenterPage(
      makePageWithPhaseRows({ linked_sessions: [] }) as Record<string, unknown>,
    );
    expect(page.items[0].phaseRows[0].linkedSessions).toEqual([]);
  });
});
