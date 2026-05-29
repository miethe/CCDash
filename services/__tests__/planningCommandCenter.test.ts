import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  adaptPlanningCommandCenterPage,
  getPlanningCommandCenter,
  getPlanningCommandCenterItem,
  PlanningCommandCenterApiError,
} from '../planningCommandCenter';

function okResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function commandCenterPayload(overrides: Record<string, unknown> = {}) {
  return {
    status: 'ok',
    data_freshness: '2026-05-28T10:00:00Z',
    generated_at: '2026-05-28T10:01:00Z',
    source_refs: ['planning-index'],
    project_id: 'proj-1',
    items: [
      {
        feature: {
          feature_id: 'feature-a',
          feature_slug: 'feature-a',
          name: 'Feature A',
          category: 'enhancement',
          tags: ['planning'],
          priority: 'high',
          summary: 'Command center fixture',
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
        artifacts: [
          {
            artifact_id: 'plan-1',
            path: 'docs/project_plans/implementation_plans/enhancements/feature-a.md',
            doc_type: 'implementation_plan',
            title: 'Feature A Plan',
            status: 'approved',
            exists: true,
          },
        ],
        target_artifact: {
          path: 'docs/project_plans/implementation_plans/enhancements/feature-a.md',
          doc_type: 'implementation_plan',
          title: 'Feature A Plan',
          exists: true,
          source_ref: 'planner',
        },
        command: {
          command: '/dev:execute-phase feature-a --phase 2',
          rule_id: 'PCC-CMD-005',
          confidence: 0.92,
          rationale: 'Execute the next open phase.',
          target_artifact_path: 'docs/project_plans/implementation_plans/enhancements/feature-a.md',
          target_artifact_doc_type: 'implementation_plan',
          target_artifact: null,
          phase: 2,
          warnings: [],
          alternatives: [],
          required_capabilities: [
            {
              name: 'dev-execution',
              supported: true,
              required: true,
              warning: '',
              fallback_command: '',
            },
          ],
        },
        related_files: [
          {
            path: 'docs/project_plans/PRDs/enhancements/feature-a.md',
            doc_type: 'prd',
            size_bytes: 1200,
            last_modified: '2026-05-28T09:00:00Z',
            addable: true,
          },
        ],
        phase_rows: [],
        launch_batch: {
          batch_id: 'batch-1',
          label: 'Phase 2',
          readiness: 'ready',
          agents: [],
          queued_count: 0,
          running_count: 0,
        },
        worktree: {
          context_id: 'ctx-1',
          path: '/tmp/feature-a',
          branch: 'codex/feature-a',
          status: 'active',
          phase_number: 2,
          batch_id: 'batch-1',
        },
        git_state: {
          path_exists: true,
          head: 'abc1234',
          dirty_count: 0,
          stash_count: 0,
          upstream: 'origin/main',
          ahead: 1,
          behind: 0,
          probed_at: '2026-05-28T10:01:00Z',
          warnings: [],
        },
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
      },
    ],
    total: 1,
    page: 1,
    page_size: 50,
    sort_by: 'priority',
    sort_direction: 'desc',
    warnings: [],
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('planningCommandCenter service', () => {
  it('adapts aggregate payloads to camelCase command-center models', () => {
    const page = adaptPlanningCommandCenterPage(commandCenterPayload());

    expect(page.projectId).toBe('proj-1');
    expect(page.items).toHaveLength(1);
    expect(page.items[0].feature.featureId).toBe('feature-a');
    expect(page.items[0].storyPoints.remaining).toBe(3);
    expect(page.items[0].command?.ruleId).toBe('PCC-CMD-005');
    expect(page.items[0].worktree?.branch).toBe('codex/feature-a');
    expect(page.items[0].gitState?.head).toBe('abc1234');
  });

  it('calls the aggregate endpoint with planning filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(commandCenterPayload()));
    vi.stubGlobal('fetch', fetchMock);

    await getPlanningCommandCenter({
      projectId: 'proj-1',
      q: 'feature',
      status: 'active',
      phase: 2,
      sortBy: 'phase',
      sortDirection: 'asc',
      pageSize: 25,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/agent/planning/command-center?project_id=proj-1&q=feature&status=active&phase=2&sort_by=phase&sort_direction=asc&page_size=25',
      { credentials: 'same-origin', headers: expect.any(Headers) },
    );
  });

  it('loads a single command-center item', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(commandCenterPayload().items[0]));
    vi.stubGlobal('fetch', fetchMock);

    const item = await getPlanningCommandCenterItem('feature-a', { projectId: 'proj-1' });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/agent/planning/command-center/feature-a?project_id=proj-1',
      { credentials: 'same-origin', headers: expect.any(Headers) },
    );
    expect(item.feature.featureId).toBe('feature-a');
  });

  it('throws a typed API error on HTTP failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 500, statusText: 'Server Error' })));

    await expect(getPlanningCommandCenter()).rejects.toBeInstanceOf(PlanningCommandCenterApiError);
  });
});
