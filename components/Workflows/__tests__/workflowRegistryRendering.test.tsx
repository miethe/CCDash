import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { WorkflowCatalog } from '../catalog/WorkflowCatalog';
import { WorkflowDetailPanel } from '../detail/WorkflowDetailPanel';
import type {
  WorkflowRegistryAction,
  WorkflowRegistryDetail,
  WorkflowRegistryItem,
} from '../../../types';

const sampleItem: WorkflowRegistryItem = {
  id: 'workflow:phase-execution',
  identity: {
    registryId: 'workflow:phase-execution',
    observedWorkflowFamilyRef: '/dev:execute-phase',
    observedAliases: ['/dev:execute-phase', 'dev:execute-phase'],
    displayLabel: 'Phase Execution',
    resolvedWorkflowId: 'phase-execution',
    resolvedWorkflowLabel: 'Phase Execution',
    resolvedWorkflowSourceUrl: 'https://example.com/workflows/phase-execution',
    resolvedCommandArtifactId: 'command:execute-phase',
    resolvedCommandArtifactLabel: '/dev:execute-phase',
    resolvedCommandArtifactSourceUrl: 'https://example.com/collection?artifact=command%3Aexecute-phase',
    resolutionKind: 'dual_backed',
    correlationState: 'hybrid',
  },
  correlationState: 'hybrid',
  issueCount: 1,
  issues: [
    {
      code: 'weak_resolution',
      severity: 'warning',
      title: 'Workflow is only partially resolved',
      message: 'The registry still relies on a command-backed match for some evidence.',
      metadata: {},
    },
  ],
  effectiveness: {
    scopeType: 'workflow',
    scopeId: 'phase-execution',
    scopeLabel: 'Phase Execution',
    sampleSize: 4,
    successScore: 0.9,
    efficiencyScore: 0.82,
    qualityScore: 0.88,
    riskScore: 0.18,
    attributionCoverage: 0.76,
    averageAttributionConfidence: 0.84,
    evidenceSummary: { representativeSessionIds: ['session-1'] },
  },
  observedCommandCount: 3,
  representativeCommands: ['/dev:execute-phase docs/plan.md'],
  sampleSize: 4,
  lastObservedAt: '2026-03-14T12:00:00Z',
};

const sampleActions: WorkflowRegistryAction[] = [
  {
    id: 'open-workflow',
    label: 'Open SkillMeat workflow',
    target: 'external',
    href: 'https://example.com/workflows/phase-execution',
    disabled: false,
    reason: '',
    metadata: {},
  },
  {
    id: 'open-session',
    label: 'Open representative session',
    target: 'internal',
    href: '/sessions?session=session-1',
    disabled: false,
    reason: '',
    metadata: { sessionId: 'session-1' },
  },
];

const sampleDetail: WorkflowRegistryDetail = {
  ...sampleItem,
  composition: {
    artifactRefs: ['skill:symbols', 'agent:backend-architect'],
    contextRefs: ['ctx:planning'],
    resolvedContextModules: [
      {
        contextRef: 'ctx:planning',
        moduleId: 'planning-module',
        moduleName: 'Planning Memory',
        status: 'resolved',
        sourceUrl: 'https://example.com/projects/project-1/memory',
        previewTokens: 120,
      },
    ],
    planSummary: {
      steps: 3,
      lastReviewedAt: '2026-03-14T10:00:00Z',
    },
    stageOrder: ['plan', 'implement', 'validate'],
    gateCount: 2,
    fanOutCount: 1,
    bundleAlignment: {
      bundleId: 'bundle-python',
      bundleName: 'Python Essentials',
      matchScore: 0.91,
      matchedRefs: ['skill:symbols'],
      sourceUrl: 'https://example.com/collection?collection=default',
    },
  },
  representativeSessions: [
    {
      sessionId: 'session-1',
      featureId: 'feature-1',
      title: 'Workflow registry follow-up',
      status: 'completed',
      workflowRef: '/dev:execute-phase',
      startedAt: '2026-03-14T09:00:00Z',
      endedAt: '2026-03-14T09:20:00Z',
      href: '/sessions?session=session-1',
    },
  ],
  recentExecutions: [
    {
      executionId: 'exec-1',
      status: 'completed',
      startedAt: '2026-03-14T08:00:00Z',
      sourceUrl: 'https://example.com/workflows/executions?workflow_id=phase-execution',
      parameters: { feature_name: 'Workflow Registry' },
    },
  ],
  actions: sampleActions,
};

describe('workflow registry rendering smoke tests', () => {
  it('renders catalog items with badges and command evidence', () => {
    const html = renderToStaticMarkup(
      <WorkflowCatalog
        searchQuery="phase"
        activeFilter="hybrid"
        items={[sampleItem]}
        total={1}
        loading={false}
        error=""
        selectedId="workflow:phase-execution"
        searchInputRef={{ current: null }}
        onSearchQueryChange={() => undefined}
        onActiveFilterChange={() => undefined}
        onSelect={() => undefined}
        onRetry={() => undefined}
        onClearFilters={() => undefined}
      />,
    );

    expect(html).toContain('Workflow Registry');
    expect(html).toContain('Phase Execution');
    expect(html).toContain('Hybrid');
    expect(html).toContain('/dev:execute-phase docs/plan.md');
  });

  it('renders detail sections and workflow actions', () => {
    const html = renderToStaticMarkup(
      <WorkflowDetailPanel
        detail={sampleDetail}
        loading={false}
        error=""
        showBackButton
        onBack={() => undefined}
        onRetry={() => undefined}
        onOpenAction={() => undefined}
      />,
    );

    expect(html).toContain('Workflow shape and dependency surface');
    expect(html).toContain('Outcome signals and quality evidence');
    expect(html).toContain('Correlation gaps and tuning friction');
    expect(html).toContain('Open SkillMeat workflow');
    expect(html).toContain('Open representative session');
    expect(html).toContain('Workflow registry follow-up');
  });

  it('renders empty-state messaging when no detail is selected', () => {
    const html = renderToStaticMarkup(
      <WorkflowDetailPanel
        detail={null}
        loading={false}
        error=""
        showBackButton={false}
        onBack={vi.fn()}
        onRetry={vi.fn()}
        onOpenAction={vi.fn()}
      />,
    );

    expect(html).toContain('Select a workflow');
    expect(html).toContain('identity, composition, effectiveness, and unresolved workflow-correlation gaps');
  });
});
