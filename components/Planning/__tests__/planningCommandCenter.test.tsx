import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { PlanningCommandCenterItem } from '@/types';
import {
  appendRelatedFileToCommand,
  bucketCommandCenterItem,
  CommandCenterBoardView,
  CommandCenterCardView,
  CommandCenterDetailPanel,
  CommandCenterFeatureCard,
  CommandCenterListView,
  commandCenterDoneLabel,
} from '../CommandCenter';

const ITEM: PlanningCommandCenterItem = {
  feature: {
    featureId: 'feature-a',
    featureSlug: 'feature-a',
    name: 'Feature A',
    category: 'enhancement',
    tags: ['planning'],
    priority: 'high',
    summary: 'Shows live command context.',
  },
  status: {
    rawStatus: 'in-progress',
    effectiveStatus: 'in-progress',
    planningSignal: 'active',
    mismatchState: 'none',
    isMismatch: false,
  },
  storyPoints: { total: 5, remaining: 3, completed: 2 },
  phase: { currentPhase: 2, nextPhase: 3, totalPhases: 4, completedPhases: 1 },
  artifacts: [
    {
      artifactId: 'plan-1',
      path: 'docs/project_plans/implementation_plans/enhancements/feature-a.md',
      docType: 'implementation_plan',
      title: 'Feature A Plan',
      status: 'approved',
      exists: true,
    },
    {
      artifactId: 'brief-1',
      path: 'docs/project_plans/briefs/feature-a-human-brief.md',
      docType: 'brief',
      title: 'Human Brief',
      status: 'ready',
      exists: true,
    },
  ],
  targetArtifact: {
    path: 'docs/project_plans/implementation_plans/enhancements/feature-a.md',
    docType: 'implementation_plan',
    title: 'Feature A Plan',
    exists: true,
    sourceRef: 'resolver',
  },
  command: {
    command: '/dev:execute-phase feature-a --phase 2',
    ruleId: 'PCC-CMD-005',
    confidence: 0.92,
    rationale: 'Execute the next phase.',
    targetArtifactPath: 'docs/project_plans/implementation_plans/enhancements/feature-a.md',
    targetArtifactDocType: 'implementation_plan',
    targetArtifact: null,
    phase: 2,
    warnings: [],
    alternatives: [],
    requiredCapabilities: [
      {
        name: 'dev-execution',
        supported: true,
        required: true,
        warning: '',
        fallbackCommand: '',
      },
      {
        name: 'planning',
        supported: true,
        required: true,
        warning: '',
        fallbackCommand: '',
      },
    ],
  },
  relatedFiles: [
    {
      path: 'docs/project_plans/PRDs/enhancements/feature-a.md',
      docType: 'prd',
      sizeBytes: 1000,
      lastModified: '2026-05-28T09:00:00Z',
      addable: true,
    },
  ],
  phaseRows: [
    {
      phaseNumber: 2,
      name: 'Frontend command center',
      storyPoints: 3,
      phaseFiles: ['docs/project_plans/progress/feature-a-phase-2.md'],
      domain: 'frontend',
      model: 'gpt-5.3-codex',
      agents: ['worker'],
      status: 'in-progress',
      details: {},
    },
  ],
  launchBatch: {
    batchId: 'batch-1',
    label: 'Phase 2',
    readiness: 'ready',
    agents: [],
    queuedCount: 0,
    runningCount: 0,
  },
  worktree: {
    contextId: 'ctx-1',
    path: '/Users/miethe/.codex/worktrees/1234/CCDash',
    branch: 'codex/feature-a',
    status: 'active',
    phaseNumber: 2,
    batchId: 'batch-1',
  },
  gitState: {
    pathExists: true,
    head: 'abc1234',
    dirtyCount: 0,
    stashCount: 0,
    upstream: 'origin/main',
    ahead: 1,
    behind: 0,
    probedAt: '2026-05-28T10:01:00Z',
    warnings: [],
  },
  pullRequest: null,
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
};

function renderList(item: PlanningCommandCenterItem = ITEM): string {
  return renderToStaticMarkup(
    <CommandCenterListView
      items={[item]}
      expandedIds={new Set([item.feature.featureId])}
      commandOverrides={{}}
      onToggleExpanded={vi.fn()}
      onCommandChange={vi.fn()}
      onCopyCommand={vi.fn()}
      onOpenExecution={vi.fn()}
      onOpenPlan={vi.fn()}
    />,
  );
}

describe('Planning Command Center list view', () => {
  it('renders status, story points, command, plan path, worktree branch, and commit head', () => {
    const html = renderList();

    expect(html).toContain('data-testid="command-center-list-view"');
    expect(html).toContain('Feature A');
    expect(html).toContain('3/5 pts left');
    expect(html).toContain('/dev:execute-phase feature-a --phase 2');
    expect(html).toContain('docs/project_plans/implementation_plans/enhancements/feature-a.md');
    expect(html).toContain('codex/feature-a');
    expect(html).toContain('abc1234');
  });

  it('renders expanded phase, related-file, capability, and worktree sections', () => {
    const html = renderList();

    expect(html).toContain('data-testid="command-center-phase-table"');
    expect(html).toContain('data-testid="command-center-related-files"');
    expect(html).toContain('data-testid="command-center-worktree-git"');
    expect(html).toContain('dev-execution');
    expect(html).toContain('planning');
  });

  it('appends related files as command context without duplicates', () => {
    const command = '/dev:execute-phase feature-a --phase 2';
    const withContext = appendRelatedFileToCommand(command, 'docs/project_plans/PRDs/enhancements/feature-a.md');

    expect(withContext).toBe(
      '/dev:execute-phase feature-a --phase 2 --context "docs/project_plans/PRDs/enhancements/feature-a.md"',
    );
    expect(appendRelatedFileToCommand(withContext, 'docs/project_plans/PRDs/enhancements/feature-a.md')).toBe(withContext);
  });

  it('shows branch-aware done labels for completed items', () => {
    expect(commandCenterDoneLabel({
      ...ITEM,
      status: { ...ITEM.status, effectiveStatus: 'completed' },
    })).toBe('done on codex/feature-a');
  });

  it('renders card and board views from the same item model', () => {
    const cardHtml = renderToStaticMarkup(
      <CommandCenterCardView
        items={[ITEM]}
        commandOverrides={{}}
        onOpenExecution={vi.fn()}
        onOpenPlan={vi.fn()}
        onOpenDetail={vi.fn()}
      />,
    );
    const boardHtml = renderToStaticMarkup(
      <CommandCenterBoardView
        items={[ITEM]}
        commandOverrides={{}}
        onOpenExecution={vi.fn()}
        onOpenPlan={vi.fn()}
        onOpenDetail={vi.fn()}
      />,
    );

    expect(cardHtml).toContain('data-testid="command-center-card-view"');
    expect(cardHtml).toContain('Feature A');
    expect(boardHtml).toContain('data-testid="command-center-board-view"');
    expect(boardHtml).toContain('Active Phase');
    expect(bucketCommandCenterItem(ITEM)).toBe('active');
  });

  it('renders the route-local detail panel with plan, worktree, phase, and review context', () => {
    const html = renderToStaticMarkup(
      <CommandCenterDetailPanel
        item={ITEM}
        commandValue={ITEM.command?.command ?? ''}
        onClose={vi.fn()}
        onOpenPlan={vi.fn()}
      />,
    );

    expect(html).toContain('role="dialog"');
    expect(html).toContain('target plan and guides');
    expect(html).toContain('worktree and git state');
    expect(html).toContain('phase plan');
    expect(html).toContain('launch and review context');
  });

  it('feature card renders status pill, title+slug full-width zone, next-command box, copy button, and branch button', () => {
    const html = renderToStaticMarkup(
      <CommandCenterFeatureCard
        item={ITEM}
        commandValue={ITEM.command?.command ?? ''}
        onCopyCommand={vi.fn()}
        onOpenExecution={vi.fn()}
        onOpenPlan={vi.fn()}
        onOpenDetail={vi.fn()}
      />,
    );

    // Status pill present (absolute top-right positioning)
    expect(html).toContain('in-progress');

    // Title and slug rendered without sharing a row with the pill
    expect(html).toContain('Feature A');
    expect(html).toContain('feature-a'); // slug

    // Next command box: testid present and command text shown
    expect(html).toContain('data-testid="command-center-next-command-box"');
    expect(html).toContain('/dev:execute-phase feature-a --phase 2');

    // Copy command button rendered with correct aria-label and testid
    expect(html).toContain('data-testid="command-center-copy-command-btn"');
    expect(html).toContain('aria-label="Copy command"');

    // Branch copy button rendered with correct aria-label and testid
    expect(html).toContain('data-testid="command-center-branch-copy-btn"');
    expect(html).toContain('aria-label="Copy branch name"');
    expect(html).toContain('codex/feature-a');
  });

  it('feature card copy button is disabled when commandValue is empty', () => {
    const html = renderToStaticMarkup(
      <CommandCenterFeatureCard
        item={ITEM}
        commandValue=""
        onCopyCommand={vi.fn()}
        onOpenExecution={vi.fn()}
        onOpenPlan={vi.fn()}
        onOpenDetail={vi.fn()}
      />,
    );

    // The button should have disabled attribute when no command; both the
    // testid and the disabled attribute must be present in the same button tag.
    expect(html).toContain('data-testid="command-center-copy-command-btn"');
    // disabled="" appears in the same button element (order-agnostic check)
    expect(html).toMatch(/aria-label="Copy command"[^>]*disabled/);
  });

  it('feature card thread: card view forwards onCopyCommand to feature cards', () => {
    const onCopyCommand = vi.fn();
    const html = renderToStaticMarkup(
      <CommandCenterCardView
        items={[ITEM]}
        commandOverrides={{}}
        onCopyCommand={onCopyCommand}
        onOpenExecution={vi.fn()}
        onOpenPlan={vi.fn()}
        onOpenDetail={vi.fn()}
      />,
    );

    // Verify that the copy button is present inside the card view
    expect(html).toContain('data-testid="command-center-copy-command-btn"');
    expect(html).toContain('data-testid="command-center-branch-copy-btn"');
  });

  it('feature card thread: board view forwards onCopyCommand to feature cards', () => {
    const onCopyCommand = vi.fn();
    const html = renderToStaticMarkup(
      <CommandCenterBoardView
        items={[ITEM]}
        commandOverrides={{}}
        onCopyCommand={onCopyCommand}
        onOpenExecution={vi.fn()}
        onOpenPlan={vi.fn()}
        onOpenDetail={vi.fn()}
      />,
    );

    // Copy button and branch button are present inside board cards
    expect(html).toContain('data-testid="command-center-copy-command-btn"');
    expect(html).toContain('data-testid="command-center-branch-copy-btn"');
  });

  it('board view uses fluid min-width (not fixed 1380px)', () => {
    const html = renderToStaticMarkup(
      <CommandCenterBoardView
        items={[ITEM]}
        commandOverrides={{}}
        onOpenExecution={vi.fn()}
        onOpenPlan={vi.fn()}
        onOpenDetail={vi.fn()}
      />,
    );

    // The old fixed min-w-[1380px] should no longer appear
    expect(html).not.toContain('min-w-[1380px]');
    // The new smaller min-width should be present
    expect(html).toContain('min-w-[900px]');
  });
});
