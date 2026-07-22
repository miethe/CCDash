import { describe, expect, it } from 'vitest';

import type {
  AgentSession,
  FeaturePlanningContext,
  PlanningAgentSessionBoard,
  PlanningAgentSessionCard,
  PlanningCommandCenterItem,
} from '@/types';

import {
  buildFeatureAnalyticsSummary,
  buildSessionAnalyticsSummary,
  flattenPlanningSessionCards,
  type PlannedObservedAnalyticsGroup,
} from '../sessionAnalytics';

const sessionFixture = (overrides: Partial<AgentSession> = {}): AgentSession => ({
  id: 'session-1',
  taskId: 'TASK-1',
  status: 'completed',
  model: 'claude-sonnet',
  durationSeconds: 120,
  tokensIn: 100,
  tokensOut: 50,
  cacheInputTokens: 25,
  totalCost: 1.25,
  startedAt: '2026-07-07T10:00:00.000Z',
  agentsUsed: ['planner'],
  skillsUsed: ['planning'],
  toolsUsed: [
    { name: 'Read', count: 2, successRate: 1, category: 'search' },
    { name: 'Bash', count: 1, successRate: 1, category: 'system' },
  ],
  logs: [
    {
      id: 'log-1',
      timestamp: '2026-07-07T10:01:00.000Z',
      speaker: 'agent',
      type: 'message',
      agentName: 'planner',
      content: 'Working.',
    },
    {
      id: 'log-2',
      timestamp: '2026-07-07T10:02:00.000Z',
      speaker: 'agent',
      type: 'skill',
      content: 'Planning skill used.',
      skillDetails: {
        name: 'planning',
        version: '1.0.0',
        description: 'Planning workflow',
      },
    },
  ],
  updatedFiles: [
    {
      filePath: 'src/feature.ts',
      commits: ['abc123'],
      additions: 10,
      deletions: 2,
      agentName: 'planner',
      action: 'update',
      fileType: 'ts',
      timestamp: '2026-07-07T10:03:00.000Z',
    },
  ],
  linkedArtifacts: [
    {
      id: 'artifact-1',
      type: 'implementation_plan',
      title: 'Implementation Plan',
      source: 'planning',
    },
  ],
  phaseHints: ['Phase 1'],
  taskHints: ['TASK-1'],
  ...overrides,
});

const cardFixture = (
  overrides: Partial<PlanningAgentSessionCard> = {},
): PlanningAgentSessionCard => ({
  sessionId: 'session-card-1',
  agentName: 'planner',
  agentType: 'implementation',
  state: 'completed',
  model: 'claude-sonnet',
  correlation: {
    featureId: 'feature-1',
    featureName: 'Feature One',
    phaseNumber: 1,
    phaseTitle: 'Build',
    taskId: 'TASK-1',
    taskTitle: 'Build helper',
    confidence: 'high',
    evidence: [],
  },
  durationSeconds: 90,
  tokenSummary: {
    tokensIn: 100,
    tokensOut: 50,
    totalTokens: 150,
    model: 'claude-sonnet',
  },
  relationships: [],
  activityMarkers: [],
  ...overrides,
});

const featureContextFixture = (): FeaturePlanningContext => ({
  status: 'ok',
  dataFreshness: '2026-07-07T10:00:00.000Z',
  generatedAt: '2026-07-07T10:05:00.000Z',
  sourceRefs: [],
  featureId: 'feature-1',
  featureName: 'Feature One',
  rawStatus: 'active',
  effectiveStatus: 'active',
  mismatchState: 'none',
  planningStatus: {},
  graph: {
    nodes: [],
    edges: [],
    phaseBatches: [
      {
        featureSlug: 'feature-one',
        phase: '1',
        batchId: 'batch-1',
        taskIds: ['TASK-1', 'TASK-2'],
        assignedAgents: ['planner', 'reviewer'],
        fileScopeHints: ['src/feature.ts'],
        readinessState: 'ready',
        readiness: {
          state: 'ready',
          reason: 'Ready',
          blockingNodeIds: [],
          blockingTaskIds: [],
          evidence: [],
          isReady: true,
        },
      },
    ],
  },
  phases: [],
  blockedBatchIds: [],
  linkedArtifactRefs: [],
});

const commandCenterItemFixture = (): PlanningCommandCenterItem => ({
  feature: {
    featureId: 'feature-1',
    featureSlug: 'feature-one',
    name: 'Feature One',
    category: 'enhancement',
    tags: [],
    priority: 'high',
    summary: 'Build analytics helper',
  },
  status: {
    rawStatus: 'active',
    effectiveStatus: 'active',
    planningSignal: 'active',
    mismatchState: 'none',
    isMismatch: false,
  },
  storyPoints: {
    total: 2,
    remaining: 1,
    completed: 1,
  },
  phase: {
    currentPhase: 1,
    nextPhase: 2,
    totalPhases: 2,
    completedPhases: 0,
  },
  artifacts: [
    {
      artifactId: 'plan-1',
      path: 'docs/plan.md',
      docType: 'implementation_plan',
      title: 'Plan',
      status: 'active',
      exists: true,
    },
  ],
  relatedFiles: [
    {
      path: 'src/feature.ts',
      docType: 'source',
      sizeBytes: 200,
      lastModified: '2026-07-07T10:00:00.000Z',
      addable: false,
    },
  ],
  phaseRows: [
    {
      phaseNumber: 1,
      name: 'Build',
      storyPoints: 2,
      phaseFiles: ['src/feature.ts'],
      domain: 'frontend',
      model: 'claude-sonnet',
      agents: ['planner'],
      status: 'active',
      details: {},
    },
  ],
  launchBatch: {
    batchId: 'batch-1',
    label: 'Batch 1',
    readiness: 'ready',
    agents: [
      {
        agentId: 'planner',
        label: 'planner',
        skills: ['planning'],
        tools: ['Read'],
        state: 'queued',
      },
    ],
    queuedCount: 1,
    runningCount: 0,
  },
  blockers: [],
  lastActivity: {},
  capabilities: {
    copyCommand: true,
    launch: true,
    review: false,
    merge: false,
    cleanup: false,
    openPr: false,
    editCommand: true,
  },
});

const row = (group: PlannedObservedAnalyticsGroup, label: string) => {
  const match = group.items.find(item => item.label === label || item.key === label.toLowerCase());
  expect(match).toBeTruthy();
  return match!;
};

describe('buildSessionAnalyticsSummary', () => {
  it('aggregates session totals and dimensions through existing token and cost helpers', () => {
    const summary = buildSessionAnalyticsSummary([
      sessionFixture(),
      sessionFixture({
        id: 'session-2',
        taskId: 'TASK-2',
        status: 'active',
        model: 'gpt-5',
        agentsUsed: ['implementer'],
        skillsUsed: [],
        skillName: 'debugging',
        toolsUsed: [],
        logs: [
          {
            id: 'log-3',
            timestamp: '2026-07-07T10:04:00.000Z',
            speaker: 'agent',
            type: 'tool',
            content: 'Edit',
            toolCall: {
              name: 'Edit',
              args: '{}',
              status: 'success',
            },
          },
        ],
        updatedFiles: [],
        linkedArtifacts: [],
        phaseHints: ['Phase 2'],
        taskHints: ['TASK-2'],
        tokensIn: 5,
        tokensOut: 10,
        cacheInputTokens: 0,
        observedTokens: 40,
        totalCost: 2,
      }),
    ]);

    expect(summary.totals.sessionCount).toBe(2);
    expect(summary.totals.activeSessionCount).toBe(1);
    expect(summary.totals.logCount).toBe(3);
    expect(summary.totals.costUsd).toBe(3.25);
    expect(summary.totals.tokens.workloadTokens).toBe(215);
    expect(summary.totals.tokens.workloadBySource.derived).toBe(175);
    expect(summary.totals.tokens.workloadBySource.observed).toBe(40);
    expect(summary.totals.toolUseCount).toBe(4);
    expect(summary.totals.artifactCount).toBe(1);
    expect(summary.totals.fileTouchCount).toBe(1);

    expect(summary.models.find(item => item.label === 'claude-sonnet')?.sessionCount).toBe(1);
    expect(summary.agents.find(item => item.label === 'planner')?.sessionCount).toBe(1);
    expect(summary.skills.find(item => item.label === 'planning')?.sessionCount).toBe(1);
    expect(summary.skills.find(item => item.label === 'debugging')?.sessionCount).toBe(1);
    expect(summary.tools.find(item => item.label === 'Read')?.count).toBe(2);
    expect(summary.tools.find(item => item.label === 'Edit')?.count).toBe(1);
    expect(summary.files.find(item => item.label === 'src/feature.ts')?.metadata?.additions).toBe(10);
    expect(summary.phases.find(item => item.label === 'Phase 1')?.sessionCount).toBe(1);
    expect(summary.tasks.find(item => item.label === 'TASK-2')?.sessionCount).toBe(1);
  });
});

describe('feature session analytics', () => {
  it('flattens board groups and maps planned signals against observed session cards', () => {
    const plannerCard = cardFixture();
    const implementerCard = cardFixture({
      sessionId: 'session-card-2',
      agentName: 'implementer',
      model: 'gpt-5',
      state: 'running',
      correlation: {
        featureId: 'feature-1',
        featureName: 'Feature One',
        phaseNumber: 1,
        phaseTitle: 'Build',
        taskId: 'TASK-3',
        taskTitle: 'Follow-up task',
        confidence: 'medium',
        evidence: [],
      },
      tokenSummary: {
        tokensIn: 40,
        tokensOut: 10,
        totalTokens: 50,
        model: 'gpt-5',
      },
    });
    const board: PlanningAgentSessionBoard = {
      projectId: 'project-1',
      grouping: 'state',
      groups: [
        {
          groupKey: 'completed',
          groupLabel: 'Completed',
          groupType: 'state',
          cards: [plannerCard],
          cardCount: 1,
        },
        {
          groupKey: 'running',
          groupLabel: 'Running',
          groupType: 'state',
          cards: [implementerCard, plannerCard],
          cardCount: 2,
        },
      ],
      totalCardCount: 3,
      activeCount: 1,
      completedCount: 1,
    };

    const cards = flattenPlanningSessionCards(board);
    const summary = buildFeatureAnalyticsSummary({
      featureContext: featureContextFixture(),
      sessionCards: cards,
      commandCenterItem: commandCenterItemFixture(),
    });

    expect(cards).toHaveLength(2);
    expect(summary.totals.sessionCount).toBe(2);
    expect(summary.totals.activeSessionCount).toBe(1);
    expect(summary.totals.totalTokens).toBe(200);

    expect(row(summary.plannedVsObserved.agents, 'planner')).toMatchObject({ planned: true, observed: true });
    expect(row(summary.plannedVsObserved.agents, 'reviewer')).toMatchObject({ planned: true, observed: false });
    expect(row(summary.plannedVsObserved.agents, 'implementer')).toMatchObject({ planned: false, observed: true });
    expect(row(summary.plannedVsObserved.skills, 'planning')).toMatchObject({ planned: true, observed: false });
    expect(row(summary.plannedVsObserved.models, 'claude-sonnet')).toMatchObject({ planned: true, observed: true });
    expect(row(summary.plannedVsObserved.models, 'gpt-5')).toMatchObject({ planned: false, observed: true });
    expect(row(summary.plannedVsObserved.tasks, 'TASK-1')).toMatchObject({ planned: true, observed: true });
    expect(row(summary.plannedVsObserved.tasks, 'TASK-2')).toMatchObject({ planned: true, observed: false });
    expect(row(summary.plannedVsObserved.tasks, 'TASK-3')).toMatchObject({ planned: false, observed: true });
    expect(summary.files.find(item => item.label === 'src/feature.ts')).toBeTruthy();
    expect(summary.artifacts.find(item => item.label === 'Plan')).toBeTruthy();
  });
});
