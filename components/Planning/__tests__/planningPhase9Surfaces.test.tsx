import { readFileSync } from 'node:fs';

import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import type { AgentSession, ProjectPlanningSummary } from '../../../types';

const mocks = vi.hoisted(() => ({
  sessions: [] as AgentSession[],
  navigate: vi.fn(),
}));

vi.mock('../../../contexts/DataContext', () => ({
  useData: () => ({
    activeProject: { id: 'proj-1', name: 'Project One' },
    documents: [],
    sessions: mocks.sessions,
  }),
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

import { PlanningAgentRosterPanel } from '../PlanningAgentRosterPanel';
import { PlanningArtifactChipRow } from '../PlanningArtifactChipRow';
import { PlanningTriagePanel } from '../PlanningTriagePanel';

function makeSummary(overrides: Partial<ProjectPlanningSummary> = {}): ProjectPlanningSummary {
  return {
    status: 'ok',
    dataFreshness: '2026-04-21T12:00:00Z',
    generatedAt: '2026-04-21T12:00:00Z',
    sourceRefs: [],
    projectId: 'proj-1',
    projectName: 'Project One',
    totalFeatureCount: 4,
    activeFeatureCount: 2,
    staleFeatureCount: 1,
    blockedFeatureCount: 1,
    mismatchCount: 1,
    reversalCount: 0,
    staleFeatureIds: ['feature-stale'],
    reversalFeatureIds: [],
    blockedFeatureIds: ['feature-blocked'],
    nodeCountsByType: {
      designSpec: 1,
      prd: 2,
      implementationPlan: 3,
      progress: 4,
      context: 5,
      tracker: 6,
      report: 7,
    },
    featureSummaries: [
      {
        featureId: 'feature-blocked',
        featureName: 'Blocked Work',
        rawStatus: 'in-progress',
        effectiveStatus: 'blocked',
        isMismatch: false,
        mismatchState: 'aligned',
        hasBlockedPhases: true,
        phaseCount: 2,
        blockedPhaseCount: 1,
        nodeCount: 4,
      },
      {
        featureId: 'feature-mismatch',
        featureName: 'Mismatched Docs',
        rawStatus: 'draft',
        effectiveStatus: 'ready',
        isMismatch: true,
        mismatchState: 'raw-draft-effective-ready',
        hasBlockedPhases: false,
        phaseCount: 1,
        blockedPhaseCount: 0,
        nodeCount: 3,
      },
      {
        featureId: 'feature-stale',
        featureName: 'Stale Shaping',
        rawStatus: 'shaping',
        effectiveStatus: 'shaping',
        isMismatch: false,
        mismatchState: 'aligned',
        hasBlockedPhases: false,
        phaseCount: 1,
        blockedPhaseCount: 0,
        nodeCount: 2,
      },
    ],
    ...overrides,
  };
}

function makeSession(overrides: Partial<AgentSession>): AgentSession {
  return {
    id: 'session-1',
    title: 'Agent task',
    taskId: 'task-1',
    status: 'active',
    model: 'claude-sonnet',
    durationSeconds: 120,
    tokensIn: 100,
    tokensOut: 50,
    totalCost: 0.02,
    startedAt: '2026-04-21T11:55:00Z',
    toolsUsed: [],
    logs: [],
    ...overrides,
  };
}

describe('PlanningTriagePanel — tabs and rows', () => {
  it('renders filter tabs, counts, derived rows, and action labels', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PlanningTriagePanel summary={makeSummary()} />
      </MemoryRouter>,
    );

    expect(html).toContain('role="tablist"');
    expect(html).toContain('aria-label="Triage filter tabs"');
    expect(html).toContain('role="tab"');
    expect(html).toContain('All');
    expect(html).toContain('Blocked');
    expect(html).toContain('Mismatches');
    expect(html).toContain('Stale');
    expect(html).toContain('Ready to promote');
    expect(html).toContain('data-testid="triage-row-feature-blocked:blocked"');
    expect(html).toContain('data-testid="triage-row-feature-mismatch:mismatch"');
    expect(html).toContain('data-testid="triage-row-feature-stale:stale"');
    expect(html).toContain('Blocked Work');
    expect(html).toContain('Mismatched Docs');
    expect(html).toContain('Stale Shaping');
    expect(html).toContain('Remediate');
    expect(html).toContain('Reconcile');
    expect(html).toContain('Resume shaping');
    expect(html).toContain('Promote');
  });

  it('renders the empty state when no feature needs triage', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PlanningTriagePanel summary={makeSummary({
          staleFeatureIds: [],
          blockedFeatureIds: [],
          featureSummaries: [],
        })} />
      </MemoryRouter>,
    );

    expect(html).toContain('data-testid="triage-empty-state"');
    expect(html).toContain('Nothing to triage.');
    expect(html).toContain('0 items');
  });
});

describe('PlanningAgentRosterPanel — rows', () => {
  const originalDocument = globalThis.document;

  beforeEach(() => {
    vi.clearAllMocks();
    const head = { appendChild: vi.fn() };
    globalThis.document = {
      createElement: () => ({ textContent: '' }),
      head,
    } as unknown as Document;
    mocks.sessions = [
      makeSession({
        id: 'running-session',
        agentId: 'runner',
        taskId: 'task-running',
        modelDisplayName: 'Sonnet 4.5',
        thinkingLevel: 'low',
      }),
      makeSession({
        id: 'thinking-session',
        agentId: 'planner',
        taskId: 'task-thinking',
        modelDisplayName: 'Opus 4.1',
        thinkingLevel: 'high',
      }),
      makeSession({
        id: 'queued-session',
        agentId: 'queued-agent',
        taskId: 'task-queued',
        status: 'queued' as AgentSession['status'],
        model: 'claude-haiku',
      }),
      makeSession({
        id: 'idle-session',
        agentId: 'done-agent',
        taskId: 'task-done',
        status: 'completed',
        model: 'claude-sonnet',
      }),
    ];
  });

  afterEach(() => {
    globalThis.document = originalDocument;
    mocks.sessions = [];
  });

  it('renders a table with sorted agent state rows and active count', () => {
    const html = renderToStaticMarkup(<PlanningAgentRosterPanel />);

    expect(html).toContain('data-testid="planning-agent-roster"');
    expect(html).toContain('role="table"');
    expect(html).toContain('aria-label="Live agent roster"');
    expect(html).toContain('2 live');
    expect(html).toContain('aria-label="Agent runner: running');
    expect(html).toContain('aria-label="Agent planner: thinking');
    expect(html).toContain('aria-label="Agent queued-agent: queued');
    expect(html).toContain('aria-label="Agent done-agent: idle');
    expect(html).toContain('task-running');
    expect(html).toContain('task-thinking');
    expect(html).toContain('task-queued');
    expect(html).toContain('task-done');
  });
});

describe('Planning artifact and metric chip surfaces', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders artifact composition chips with list semantics and corpus summary', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PlanningArtifactChipRow
          nodeCountsByType={{
            designSpec: 1,
            prd: 2,
            implementationPlan: 3,
            progress: 4,
            context: 5,
            tracker: 6,
            report: 7,
          }}
          totalRefs={9}
        />
      </MemoryRouter>,
    );

    expect(html).toContain('data-testid="planning-artifact-chip-row"');
    expect(html).toContain('role="list"');
    expect(html).toContain('aria-label="Artifact composition"');
    expect(html).toContain('SPEC');
    expect(html).toContain('SPIKE');
    expect(html).toContain('PRD');
    expect(html).toContain('PLAN');
    expect(html).toContain('PROG');
    expect(html).toContain('CTX');
    expect(html).toContain('TRK');
    expect(html).toContain('REP');
    expect(html).toContain('aria-label="28 docs indexed, 9 refs resolved"');
    expect(html).toContain('28 docs indexed');
    expect(html).toContain('9 refs resolved');
  });
});

describe('PlanningGraphPanel — a11y role contract', () => {
  it('keeps the ready-state graph exposed as a named table with row and gridcell roles', () => {
    const source = readFileSync(new URL('../PlanningGraphPanel.tsx', import.meta.url), 'utf8');

    expect(source).toContain('role="table"');
    expect(source).toContain('aria-label="Planning feature artifact graph"');
    expect(source).toContain('role="row"');
    expect(source).toContain('role="columnheader"');
    expect(source).toContain('role="rowheader"');
    expect(source).toContain('role="gridcell"');
    expect(source).toContain('aria-label="Artifact type legend"');
    expect(source).toContain('aria-label="Filter features by category"');
  });
});
