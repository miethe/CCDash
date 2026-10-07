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

// Since 265b14e every service request goes through apiClient.apiFetch, which
// normalizes init.headers into a Headers instance (adding the project-scope
// header only when a scope is selected) and defaults credentials to
// 'same-origin'. Assert on the request the wrapper actually sends — URL,
// credentials, and the real header contents — rather than the pre-wrapper
// argument shape.
function fetchCall(fetchMock: ReturnType<typeof vi.fn>, callIndex = 0) {
  const [url, init] = fetchMock.mock.calls[callIndex] as [string, RequestInit | undefined];
  return {
    url,
    init: init ?? {},
    headers: Object.fromEntries(new Headers(init?.headers).entries()),
  };
}

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
          correlationCounts: {
            strong: 0,
            hybrid: 0,
            weak: 0,
            unresolved: 0,
          },
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

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchCall(fetchMock);
    expect(call.url).toBe('/api/analytics/workflow-registry?search=phase&correlationState=strong&offset=0&limit=25');
    expect(call.init.credentials).toBe('same-origin');
    expect(call.headers).toEqual({});
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

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchCall(fetchMock);
    expect(call.url).toBe('/api/analytics/workflow-registry/detail?registryId=workflow%3Aphase-execution');
    expect(call.init.credentials).toBe('same-origin');
    expect(call.headers).toEqual({});
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
