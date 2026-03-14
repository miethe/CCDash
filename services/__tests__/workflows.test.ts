import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  WorkflowRegistryApiError,
  buildWorkflowRegistryPath,
  decodeWorkflowRegistryRouteParam,
  encodeWorkflowRegistryRouteParam,
  workflowRegistryService,
} from '../workflows';
import { runWorkflowRegistryAction } from '../../components/Workflows/workflowRegistryUtils';
import type { WorkflowRegistryAction } from '../../types';

describe('workflow registry service helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('round-trips registry ids through the route encoder', () => {
    const registryId = 'observed:/dev:execute-phase';
    const encoded = encodeWorkflowRegistryRouteParam(registryId);

    expect(encoded).not.toContain('/');
    expect(buildWorkflowRegistryPath(registryId)).toBe(`/workflows/${encoded}`);
    expect(decodeWorkflowRegistryRouteParam(encoded)).toBe(registryId);
  });

  it('passes through non-hex route tokens unchanged', () => {
    expect(decodeWorkflowRegistryRouteParam('workflow:phase-execution')).toBe('workflow:phase-execution');
  });

  it('builds list requests with search and correlation filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          projectId: 'project-1',
          items: [],
          total: 0,
          offset: 0,
          limit: 25,
          generatedAt: '2026-03-14T00:00:00Z',
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await workflowRegistryService.list({
      search: 'phase',
      correlationState: 'strong',
      offset: 0,
      limit: 25,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/analytics/workflow-registry?search=phase&correlationState=strong&offset=0&limit=25',
    );
  });

  it('loads detail by registry id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          projectId: 'project-1',
          item: {
            id: 'workflow:phase-execution',
            identity: {
              registryId: 'workflow:phase-execution',
              observedWorkflowFamilyRef: '/dev:execute-phase',
              observedAliases: [],
              displayLabel: 'Phase Execution',
              resolvedWorkflowId: 'phase-execution',
              resolvedWorkflowLabel: 'Phase Execution',
              resolvedWorkflowSourceUrl: 'https://example.com/workflows/phase-execution',
              resolvedCommandArtifactId: '',
              resolvedCommandArtifactLabel: '',
              resolvedCommandArtifactSourceUrl: '',
              resolutionKind: 'workflow_definition',
              correlationState: 'strong',
            },
            correlationState: 'strong',
            issueCount: 0,
            issues: [],
            effectiveness: null,
            observedCommandCount: 1,
            representativeCommands: ['/dev:execute-phase'],
            sampleSize: 1,
            lastObservedAt: '2026-03-14T00:00:00Z',
            composition: {
              artifactRefs: [],
              contextRefs: [],
              resolvedContextModules: [],
              planSummary: {},
              stageOrder: [],
              gateCount: 0,
              fanOutCount: 0,
              bundleAlignment: null,
            },
            representativeSessions: [],
            recentExecutions: [],
            actions: [],
          },
          generatedAt: '2026-03-14T00:00:00Z',
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await workflowRegistryService.getDetail('workflow:phase-execution');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/analytics/workflow-registry/detail?registryId=workflow%3Aphase-execution',
    );
  });

  it('surfaces disabled-state hints from API failures', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { message: 'Workflow analytics disabled', error: 'feature_disabled' } }),
        { status: 503, headers: { 'content-type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(workflowRegistryService.list()).rejects.toMatchObject({
      name: 'WorkflowRegistryApiError',
      status: 503,
      message: 'Workflow analytics disabled',
      hint: 'Workflow analytics may be disabled for the active project.',
      code: 'feature_disabled',
    });
  });
});

describe('workflow registry action dispatch', () => {
  it('navigates internal actions and opens external ones', () => {
    const navigate = vi.fn();
    const openExternal = vi.fn();
    const internalAction: WorkflowRegistryAction = {
      id: 'open-session',
      label: 'Open representative session',
      target: 'internal',
      href: '/sessions?session=session-1',
      disabled: false,
      reason: '',
      metadata: {},
    };
    const externalAction: WorkflowRegistryAction = {
      id: 'open-workflow',
      label: 'Open SkillMeat workflow',
      target: 'external',
      href: 'https://example.com/workflows/phase-execution',
      disabled: false,
      reason: '',
      metadata: {},
    };

    runWorkflowRegistryAction(internalAction, { navigate, openExternal });
    runWorkflowRegistryAction(externalAction, { navigate, openExternal });

    expect(navigate).toHaveBeenCalledWith('/sessions?session=session-1');
    expect(openExternal).toHaveBeenCalledWith('https://example.com/workflows/phase-execution');
  });

  it('ignores disabled actions', () => {
    const navigate = vi.fn();
    const openExternal = vi.fn();

    runWorkflowRegistryAction(
      {
        id: 'disabled',
        label: 'Disabled',
        target: 'external',
        href: 'https://example.com',
        disabled: true,
        reason: 'Missing URL',
        metadata: {},
      },
      { navigate, openExternal },
    );

    expect(navigate).not.toHaveBeenCalled();
    expect(openExternal).not.toHaveBeenCalled();
  });
});
