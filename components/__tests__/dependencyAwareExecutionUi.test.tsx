import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { Feature, FeatureExecutionContext, LinkedDocument, PlanDocument } from '../../types';

const navigateSpy = vi.fn();
let searchParams = new URLSearchParams();

const createMockData = () => ({
  activeProject: { id: 'project-1' },
  features: [] as Feature[],
  documents: [] as PlanDocument[],
  sessions: [],
  tasks: [],
  alerts: [],
  notifications: [],
  projects: [],
  loading: false,
  error: null as string | null,
  runtimeStatus: null,
  refreshAll: vi.fn(),
  refreshSessions: vi.fn(),
  loadMoreSessions: vi.fn(),
  refreshDocuments: vi.fn(),
  refreshTasks: vi.fn(),
  refreshFeatures: vi.fn(),
  refreshProjects: vi.fn(),
  addProject: vi.fn(),
  updateProject: vi.fn(),
  switchProject: vi.fn(),
  updateFeatureStatus: vi.fn(),
  updatePhaseStatus: vi.fn(),
  updateTaskStatus: vi.fn(),
  getSessionById: vi.fn(),
});

let mockData = createMockData();

const stateOverrides = new Map<number, unknown>();
let stateCallIndex = 0;

const setStateOverride = (index: number, value: unknown) => {
  stateOverrides.set(index, value);
};

const resetStateOverrides = () => {
  stateOverrides.clear();
  stateCallIndex = 0;
};

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  const actualDefault = (actual as { default?: Record<string, unknown> }).default ?? {};
  const mockedUseState = <T,>(initialValue: T): [T, React.Dispatch<React.SetStateAction<T>>] => {
    const overrideIndex = stateCallIndex++;
    if (stateOverrides.has(overrideIndex)) {
      return [stateOverrides.get(overrideIndex) as T, vi.fn()] as [T, React.Dispatch<React.SetStateAction<T>>];
    }
    return actual.useState(initialValue);
  };
  return {
    ...actual,
    default: {
      ...actualDefault,
      useState: mockedUseState,
    },
    useState: mockedUseState,
  };
});

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    Link: ({ to, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string | { pathname?: string } }) => (
      <a
        href={typeof to === 'string' ? to : to.pathname || '#'}
        {...props}
      >
        {children}
      </a>
    ),
    useNavigate: () => navigateSpy,
    useSearchParams: () => [searchParams, vi.fn()] as const,
  };
});

vi.mock('../../contexts/DataContext', () => ({
  useData: () => mockData,
}));

// P5-005: AppRuntimeContext is now used by ProjectBoard for the v2 flag.
// Return a minimal stub so tests that omit AppRuntimeProvider still work.
vi.mock('../../contexts/AppRuntimeContext', () => ({
  useAppRuntime: () => ({ runtimeStatus: null, loading: false, error: null, refreshAll: vi.fn() }),
}));

vi.mock('../../services/live', () => ({
  executionRunTopic: vi.fn(),
  featureTopic: vi.fn(),
  isExecutionLiveUpdatesEnabled: () => false,
  isFeatureLiveUpdatesEnabled: () => false,
  isStackRecommendationsEnabled: () => true,
  isWorkflowAnalyticsEnabled: () => true,
  projectFeaturesTopic: vi.fn(),
  sharedLiveConnectionManager: {},
  useLiveInvalidation: () => 'idle',
}));

vi.mock('../../services/execution', () => ({
  trackExecutionEvent: vi.fn(),
  approveExecutionRun: vi.fn(),
  cancelExecutionRun: vi.fn(),
  checkExecutionPolicy: vi.fn(),
  createExecutionRun: vi.fn(),
  getExecutionRun: vi.fn(),
  getFeatureExecutionContext: vi.fn(),
  listExecutionRunEvents: vi.fn(),
  listExecutionRuns: vi.fn(),
  retryExecutionRun: vi.fn(),
}));

vi.mock('../../services/testVisualizer', () => ({
  getFeatureHealth: vi.fn(),
  listTestRuns: vi.fn(),
}));

vi.mock('../SessionCard', () => ({
  SessionCard: ({ children }: { children?: React.ReactNode }) => <div data-mock="session-card">{children}</div>,
  SessionCardDetailSection: () => null,
  deriveSessionCardTitle: (sessionId: string) => sessionId,
}));

vi.mock('../execution/RecommendedStackCard', () => ({
  RecommendedStackCard: () => <div data-mock="recommended-stack-card" />,
}));

vi.mock('../execution/RecommendedStackPreviewCard', () => ({
  RecommendedStackPreviewCard: () => <div data-mock="recommended-stack-preview-card" />,
}));

vi.mock('../execution/ExecutionRunHistory', () => ({
  ExecutionRunHistory: () => <div data-mock="execution-run-history" />,
}));

vi.mock('../execution/ExecutionRunPanel', () => ({
  ExecutionRunPanel: () => <div data-mock="execution-run-panel" />,
}));

vi.mock('../execution/WorkflowEffectivenessSurface', () => ({
  WorkflowEffectivenessSurface: () => <div data-mock="workflow-effectiveness-surface" />,
}));

vi.mock('../TestVisualizer/FeatureModalTestStatus', () => ({
  FeatureModalTestStatus: () => <div data-mock="feature-modal-test-status" />,
}));

vi.mock('../TestVisualizer/TestStatusView', () => ({
  TestStatusView: () => <div data-mock="test-status-view" />,
}));

import { DocumentModal } from '../DocumentModal';
import { PlanCatalog } from '../PlanCatalog';
import { ProjectBoard } from '../ProjectBoard';

const sampleFeature: Feature = {
  id: 'feature-1',
  name: 'Dependency aware execution',
  status: 'in-progress',
  totalTasks: 8,
  completedTasks: 3,
  deferredTasks: 1,
  category: 'Enhancement',
  tags: ['execution', 'family'],
  description: 'Feature work that is blocked on a predecessor and sequenced in a family.',
  summary: 'Tracks dependency-aware execution gates and family ordering.',
  priority: 'high',
  riskLevel: 'medium',
  complexity: 'high',
  track: 'delivery',
  timelineEstimate: '2 weeks',
  targetRelease: 'R1',
  milestone: 'Beta',
  owners: ['ops'],
  contributors: ['docs'],
  requestLogIds: ['REQ-1'],
  commitRefs: ['abc1234'],
  prRefs: ['PR-17'],
  executionReadiness: 'blocked',
  testImpact: 'moderate',
  featureFamily: 'family-alpha',
  updatedAt: '2026-03-23T09:00:00Z',
  plannedAt: '2026-03-20T09:00:00Z',
  startedAt: '2026-03-21T09:00:00Z',
  linkedDocs: [
    {
      id: 'doc-1',
      title: 'Dependency-aware execution plan',
      filePath: 'docs/project_plans/implementation_plans/enhancements/dependency-aware-execution-and-family-views-v1.md',
      docType: 'implementation_plan',
      sequenceOrder: 1,
      featureFamily: 'family-alpha',
      blockedBy: ['feature-0'],
    } as LinkedDocument,
    {
      id: 'doc-2',
      title: 'Family phase tracker',
      filePath: 'docs/project_plans/progress/family-phase-tracker.md',
      docType: 'progress',
      sequenceOrder: 2,
      featureFamily: 'family-alpha',
      blockedBy: ['feature-0'],
    } as LinkedDocument,
  ],
  linkedFeatures: [
    {
      feature: 'feature-0',
      type: 'blocked_by',
      source: 'frontmatter',
      confidence: 1,
    },
    {
      feature: 'feature-next',
      type: 'related',
      source: 'family',
      confidence: 0.85,
    },
  ],
  primaryDocuments: {
    prd: null,
    implementationPlan: null,
    phasePlans: [],
    progressDocs: [],
    supportingDocs: [],
  },
  documentCoverage: {
    present: ['implementation_plan', 'progress'],
    missing: ['prd'],
    countsByType: { implementation_plan: 1, progress: 1 },
    coverageScore: 0.67,
  },
  qualitySignals: {
    blockerCount: 1,
    atRiskTaskCount: 2,
    integritySignalRefs: ['SIG-1'],
    reportFindingsBySeverity: {},
    testImpact: 'moderate',
    hasBlockingSignals: true,
  },
  dependencyState: {
    state: 'blocked',
    dependencyCount: 1,
    resolvedDependencyCount: 0,
    blockedDependencyCount: 1,
    unknownDependencyCount: 0,
    blockingFeatureIds: ['feature-0'],
    blockingDocumentIds: ['doc-0'],
    firstBlockingDependencyId: 'feature-0',
    blockingReason: 'Waiting on feature-0 to complete',
    completionEvidence: ['phase:1'],
    dependencies: [
      {
        dependencyFeatureId: 'feature-0',
        dependencyFeatureName: 'Predecessor feature',
        dependencyStatus: 'in-progress',
        dependencyCompletionEvidence: ['phase:1'],
        blockingDocumentIds: ['doc-0'],
        blockingReason: 'Predecessor still open',
        resolved: false,
        state: 'blocked',
      },
    ],
  },
  blockingFeatures: [
    {
      dependencyFeatureId: 'feature-0',
      dependencyFeatureName: 'Predecessor feature',
      dependencyStatus: 'in-progress',
      dependencyCompletionEvidence: ['phase:1'],
      blockingDocumentIds: ['doc-0'],
      blockingReason: 'Predecessor still open',
      resolved: false,
      state: 'blocked',
    },
  ],
  familySummary: {
    featureFamily: 'family-alpha',
    totalItems: 3,
    sequencedItems: 2,
    unsequencedItems: 1,
    currentFeatureId: 'feature-1',
    currentFeatureName: 'Dependency aware execution',
    currentPosition: 2,
    currentSequencedPosition: 2,
    nextRecommendedFeatureId: 'feature-next',
    nextRecommendedFamilyItem: null,
    items: [],
  },
  familyPosition: {
    familyKey: 'family-alpha',
    currentIndex: 2,
    sequencedIndex: 2,
    totalItems: 3,
    sequencedItems: 2,
    unsequencedItems: 1,
    display: '2 of 3',
    currentItemId: 'feature-1',
    nextItemId: 'feature-next',
    nextItemLabel: 'Next family item',
  },
  executionGate: {
    state: 'blocked_dependency',
    blockingDependencyId: 'feature-0',
    firstExecutableFamilyItemId: 'feature-next',
    recommendedFamilyItemId: 'feature-next',
    familyPosition: null,
    dependencyState: {
      state: 'blocked',
      dependencyCount: 1,
      resolvedDependencyCount: 0,
      blockedDependencyCount: 1,
      unknownDependencyCount: 0,
      blockingFeatureIds: ['feature-0'],
      blockingDocumentIds: ['doc-0'],
      firstBlockingDependencyId: 'feature-0',
      blockingReason: 'Waiting on feature-0 to complete',
      completionEvidence: ['phase:1'],
      dependencies: [],
    },
    familySummary: {
      featureFamily: 'family-alpha',
      totalItems: 3,
      sequencedItems: 2,
      unsequencedItems: 1,
      currentFeatureId: 'feature-1',
      currentFeatureName: 'Dependency aware execution',
      currentPosition: 2,
      currentSequencedPosition: 2,
      nextRecommendedFeatureId: 'feature-next',
      items: [],
    },
    reason: 'Blocked by dependency-feature',
    waitingOnFamilyPredecessor: true,
    isReady: false,
  },
  nextRecommendedFamilyItem: null,
  phases: [
    {
      phase: '1',
      title: 'Prep',
      status: 'done',
      progress: 100,
      totalTasks: 3,
      completedTasks: 3,
      tasks: [],
    },
  ],
  relatedFeatures: ['feature-0', 'feature-next'],
  dates: undefined,
  timeline: [],
};

const sampleDocument: PlanDocument = {
  id: 'doc-1',
  title: 'Dependency-aware execution plan',
  filePath: 'docs/project_plans/implementation_plans/enhancements/dependency-aware-execution-and-family-views-v1.md',
  canonicalPath: 'docs/project_plans/implementation_plans/enhancements/dependency-aware-execution-and-family-views-v1.md',
  status: 'active',
  statusNormalized: 'in_progress',
  createdAt: '2026-03-20T09:00:00Z',
  updatedAt: '2026-03-23T09:00:00Z',
  completedAt: '',
  lastModified: '2026-03-23T09:00:00Z',
  author: 'CCDash',
  content: '# Dependency-aware execution plan',
  docType: 'implementation_plan',
  docSubtype: 'implementation_plan',
  rootKind: 'project_plans',
  hasFrontmatter: true,
  frontmatterType: 'yaml',
  featureSlugHint: 'feature-1',
  featureSlugCanonical: 'feature-1',
  prdRef: 'PRD-1',
  phaseToken: '1',
  phaseNumber: 1,
  overallProgress: 55,
  completionEstimate: '2026-03-24',
  description: 'Implementation plan with dependency-aware execution and family views.',
  summary: 'Tracks blocked-by state, family ordering, and navigation affordances.',
  priority: 'high',
  riskLevel: 'medium',
  complexity: 'high',
  track: 'delivery',
  timelineEstimate: '2 weeks',
  targetRelease: 'R1',
  milestone: 'Beta',
  decisionStatus: 'approved',
  executionReadiness: 'ready',
  testImpact: 'moderate',
  primaryDocRole: 'plan',
  featureSlug: 'feature-1',
  featureFamily: 'family-alpha',
  blockedBy: ['feature-0'],
  sequenceOrder: 1,
  featureVersion: 'v1',
  planRef: 'PLAN-1',
  implementationPlanRef: 'PLAN-1',
  totalTasks: 12,
  completedTasks: 7,
  inProgressTasks: 2,
  blockedTasks: 1,
  category: 'enhancement',
  pathSegments: ['docs', 'project_plans'],
  featureCandidates: [],
  metadata: {
    phase: '1',
    phaseNumber: 1,
    overallProgress: 55,
    taskCounts: { total: 12, completed: 7, inProgress: 2, blocked: 1 },
    owners: ['ccdash'],
    contributors: ['docs'],
    reviewers: [],
    approvers: [],
    audience: ['users'],
    labels: ['dependency-aware'],
    description: 'Implementation plan with dependency-aware execution and family views.',
    summary: 'Tracks blocked-by state, family ordering, and navigation affordances.',
    priority: 'high',
    riskLevel: 'medium',
    complexity: 'high',
    track: 'delivery',
    timelineEstimate: '2 weeks',
    targetRelease: 'R1',
    milestone: 'Beta',
    decisionStatus: 'approved',
    executionReadiness: 'ready',
    testImpact: 'moderate',
    primaryDocRole: 'plan',
    featureSlug: 'feature-1',
    featureFamily: 'family-alpha',
    featureVersion: 'v1',
    planRef: 'PLAN-1',
    implementationPlanRef: 'PLAN-1',
    blockedBy: ['feature-0'],
    sequenceOrder: 1,
    requestLogIds: ['REQ-1'],
    commitRefs: ['abc1234'],
    prRefs: ['PR-17'],
    sourceDocuments: [],
    filesAffected: [],
    filesModified: [],
    contextFiles: [],
    integritySignalRefs: ['SIG-1'],
    linkedTasks: [],
    executionEntrypoints: [],
    linkedFeatureRefs: [],
    docTypeFields: {},
    featureSlugHint: 'feature-1',
    canonicalPath: 'docs/project_plans/implementation_plans/enhancements/dependency-aware-execution-and-family-views-v1.md',
  },
  linkCounts: { features: 2, tasks: 1, sessions: 0, documents: 1 },
  dates: undefined,
  timeline: [],
  frontmatter: {
    tags: ['dependency-aware', 'family'],
    linkedFeatures: ['feature-1'],
    linkedFeatureRefs: [{ feature: 'feature-1', type: 'implements', source: 'frontmatter', confidence: 1 }],
    blockedBy: ['feature-0'],
    sequenceOrder: 1,
    linkedSessions: [],
    linkedTasks: [],
    lineageFamily: 'family-alpha',
    lineageParent: 'feature-0',
    lineageChildren: ['feature-next'],
    lineageType: 'implementation',
    relatedFiles: [],
    version: 'v1',
    commits: ['abc1234'],
    prs: ['PR-17'],
    requestLogIds: ['REQ-1'],
    commitRefs: ['abc1234'],
    prRefs: ['PR-17'],
    relatedRefs: ['feature-0'],
    pathRefs: ['docs/project_plans/progress/family-phase-tracker.md'],
    slugRefs: ['feature-1'],
    prd: 'PRD-1',
    prdRefs: ['PRD-1'],
    sourceDocuments: [],
    filesAffected: [],
    filesModified: [],
    contextFiles: [],
    integritySignalRefs: ['SIG-1'],
    fieldKeys: ['lineageFamily', 'blockedBy', 'sequenceOrder'],
    raw: null,
  },
};

const sampleExecutionContext: FeatureExecutionContext = {
  feature: sampleFeature,
  documents: sampleFeature.linkedDocs,
  sessions: [],
  analytics: {
    sessionCount: 3,
    primarySessionCount: 2,
    totalSessionCost: 12.5,
    artifactEventCount: 4,
    commandEventCount: 3,
    lastEventAt: '2026-03-23T09:30:00Z',
    modelCount: 1,
  },
  recommendations: {
    ruleId: 'family-aware',
    confidence: 0.92,
    explanation: 'The feature is blocked, but the family sequence is still visible and ready for review.',
    primary: {
      command: '/dev:execute-phase docs/project_plans/implementation_plans/enhancements/dependency-aware-execution-and-family-views-v1.md',
      ruleId: 'family-aware',
      confidence: 0.92,
      explanation: 'Review the family lane before starting implementation work.',
      evidenceRefs: [],
    },
    alternatives: [],
    evidenceRefs: [],
    evidence: [],
  },
  dependencyState: sampleFeature.dependencyState,
  familySummary: sampleFeature.familySummary,
  familyPosition: sampleFeature.familyPosition,
  executionGate: sampleFeature.executionGate,
  recommendedFamilyItem: null,
  warnings: [
    {
      section: 'dependency',
      message: 'Predecessor feature is still blocking execution.',
      recoverable: true,
    },
  ],
  recommendedStack: null,
  stackAlternatives: [],
  stackEvidence: [],
  definitionResolutionWarnings: [],
  generatedAt: '2026-03-23T09:30:00Z',
};

const renderMarkup = (node: React.ReactElement, overrides: Record<number, unknown> = {}) => {
  resetStateOverrides();
  Object.entries(overrides).forEach(([key, value]) => {
    setStateOverride(Number(key), value);
  });
  return renderToStaticMarkup(node);
};

describe('dependency-aware execution UI', () => {
  beforeEach(() => {
    navigateSpy.mockReset();
    searchParams = new URLSearchParams();
    mockData = createMockData();
    resetStateOverrides();
  });

  it('renders the project board blocked summary and family sequence text', () => {
    mockData = {
      ...mockData,
      features: [sampleFeature],
      documents: [sampleDocument],
    };
    searchParams = new URLSearchParams('feature=feature-1&tab=overview');

    const html = renderMarkup(<ProjectBoard />, {
      1: sampleFeature,
      2: 'overview',
    });

    expect(html).toContain('Hard Dependencies');
    expect(html).toContain('Family Sequence');
    expect(html).toContain('feature-0');
    expect(html).toContain('feature-next');
  });

  it('renders the project board execution gate and family metadata', () => {
    mockData = {
      ...mockData,
      features: [sampleFeature],
      documents: [sampleDocument],
    };
    searchParams = new URLSearchParams('feature=feature-1&tab=overview');

    const html = renderMarkup(<ProjectBoard />, {
      1: sampleFeature,
      2: 'overview',
    });

    expect(html).toContain('Execution Gate');
    expect(html).toContain('Family Position');
    expect(html).toContain('family-alpha');
    expect(html).toContain('Blocked by dependency');
    expect(html).toContain('feature-next');
  });

  it('renders plan catalog dependency metadata and feature navigation affordances', () => {
    mockData = {
      ...mockData,
      documents: [sampleDocument],
      features: [sampleFeature],
    };

    const html = renderMarkup(<PlanCatalog />);

    expect(html).toContain('Dependency-aware execution plan');
    expect(html).toContain('seq 1');
    expect(html).toContain('1 blocked by');
    expect(html).toContain('title="Open Feature feature-1');
  });

  it('renders document modal relationships and lineage details', () => {
    mockData = {
      ...mockData,
      features: [sampleFeature],
      documents: [sampleDocument],
    };

    const html = renderMarkup(
      <DocumentModal doc={sampleDocument} onClose={() => undefined} />,
      { 0: 'relationships' },
    );

    expect(html).toContain('Hard Dependencies');
    expect(html).toContain('feature-0');
    expect(html).toContain('Family');
    expect(html).toContain('feature-next');
    expect(html).toContain('docs/project_plans/progress/family-phase-tracker.md');
  });
});
