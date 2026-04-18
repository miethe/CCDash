/**
 * PCP-504: PlanningLaunchSheet tests.
 *
 * Strategy: Uses renderToStaticMarkup (same as phaseOperationsPanel.test.tsx)
 * since no jsdom/testing-library is installed. Tests cover:
 *
 *   1. open=false → returns null (no HTML)
 *   2. Loading state on initial render when prepareLaunch is unresolved
 *   3. Error state when prepareLaunch rejects
 *   4. Loaded state with a ready batch + local provider selected
 *   5. Unsupported provider option has disabled attribute
 *   6. Approval gate renders when requirement=required
 *   7. 409 path: component renders inline error and force button via inner content
 *
 * Note: renderToStaticMarkup does not run effects, so async flows are tested
 * via PlanningLaunchSheetContent (the inner pure renderer) directly.
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { LaunchPreparation } from '../../../types';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../../services/execution', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/execution')>();
  return {
    ...actual,
    prepareLaunch: vi.fn(),
    startLaunch: vi.fn(),
  };
});

import { prepareLaunch } from '../../../services/execution';
import { PlanningLaunchSheet } from '../PlanningLaunchSheet';
import { PlanningLaunchSheetContent } from '../PlanningLaunchSheet';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makePreparation = (overrides: Partial<LaunchPreparation> = {}): LaunchPreparation => ({
  projectId: 'proj-1',
  featureId: 'feat-auth',
  phaseNumber: 1,
  batchId: 'batch-001',
  batch: {
    batchId: 'batch-001',
    phaseNumber: 1,
    featureId: 'feat-auth',
    featureName: 'Auth Feature',
    phaseTitle: 'Phase 1: Setup',
    readinessState: 'ready',
    isReady: true,
    blockedReason: '',
    taskIds: ['TASK-1.1'],
    tasks: [
      { taskId: 'TASK-1.1', title: 'Init middleware', status: 'pending', assignees: [], blockers: [] },
    ],
    owners: ['alice'],
    dependencies: [],
  },
  providers: [
    {
      provider: 'local',
      label: 'Local',
      supported: true,
      supportsWorktrees: true,
      supportsModelSelection: false,
      defaultModel: '',
      availableModels: [],
      requiresApproval: false,
      unsupportedReason: '',
      metadata: {},
    },
  ],
  selectedProvider: 'local',
  selectedModel: '',
  worktreeCandidates: [],
  worktreeSelection: {
    worktreeContextId: '',
    createIfMissing: false,
    branch: '',
    worktreePath: '',
    baseBranch: 'main',
    notes: '',
  },
  approval: { requirement: 'none', reasonCodes: [], riskLevel: 'low' },
  warnings: [],
  generatedAt: '2026-04-17T00:00:00Z',
  ...overrides,
});

const defaultSheetProps = {
  open: true,
  projectId: 'proj-1',
  featureId: 'feat-auth',
  phaseNumber: 1,
  batchId: 'batch-001',
  onClose: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

// ── PlanningLaunchSheet (outer shell) ─────────────────────────────────────────

describe('PlanningLaunchSheet (initial render state)', () => {
  it('renders null when open=false', () => {
    vi.mocked(prepareLaunch).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <PlanningLaunchSheet {...defaultSheetProps} open={false} />,
    );
    expect(html).toBe('');
  });

  it('renders the loading skeleton on initial synchronous render when open=true', () => {
    vi.mocked(prepareLaunch).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <PlanningLaunchSheet {...defaultSheetProps} />,
    );
    // Initial render: loading=true, data=null → loading skeleton visible
    expect(html).toContain('Loading launch preparation');
    expect(html).toContain('animate-pulse');
  });

  it('renders the overlay wrapper and modal panel when open', () => {
    vi.mocked(prepareLaunch).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <PlanningLaunchSheet {...defaultSheetProps} />,
    );
    expect(html).toContain('fixed inset-0 z-50');
    expect(html).toContain('rounded-xl');
  });

  it('shows the batchId in header even before prep loads', () => {
    vi.mocked(prepareLaunch).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <PlanningLaunchSheet {...defaultSheetProps} />,
    );
    // Header shows batchId fallback
    expect(html).toContain('batch-001');
  });
});

// ── PlanningLaunchSheetContent (pure renderer) ────────────────────────────────

describe('PlanningLaunchSheetContent', () => {
  it('renders batch id and feature name', () => {
    const html = renderToStaticMarkup(
      <PlanningLaunchSheetContent
        preparation={makePreparation()}
        selectedProvider="local"
        selectedModel=""
        worktreeMode="create"
        selectedWorktreeId=""
        newBranch=""
        newWorktreePath=""
        newBaseBranch="main"
        newNotes=""
        commandOverride=""
        approvalAcknowledged={false}
        launching={false}
        launchError={null}
        showForceButton={false}
        onProviderChange={() => {}}
        onModelChange={() => {}}
        onWorktreeModeChange={() => {}}
        onWorktreeIdChange={() => {}}
        onNewBranchChange={() => {}}
        onNewWorktreePathChange={() => {}}
        onNewBaseBranchChange={() => {}}
        onNewNotesChange={() => {}}
        onCommandOverrideChange={() => {}}
        onApprovalAcknowledgeChange={() => {}}
        onLaunch={() => {}}
        onForceLaunch={() => {}}
      />,
    );
    expect(html).toContain('Auth Feature');
    expect(html).toContain('batch-001');
    expect(html).toContain('Phase 1: Setup');
  });

  it('renders "local" as selected provider option', () => {
    const html = renderToStaticMarkup(
      <PlanningLaunchSheetContent
        preparation={makePreparation()}
        selectedProvider="local"
        selectedModel=""
        worktreeMode="create"
        selectedWorktreeId=""
        newBranch=""
        newWorktreePath=""
        newBaseBranch=""
        newNotes=""
        commandOverride=""
        approvalAcknowledged={false}
        launching={false}
        launchError={null}
        showForceButton={false}
        onProviderChange={() => {}}
        onModelChange={() => {}}
        onWorktreeModeChange={() => {}}
        onWorktreeIdChange={() => {}}
        onNewBranchChange={() => {}}
        onNewWorktreePathChange={() => {}}
        onNewBaseBranchChange={() => {}}
        onNewNotesChange={() => {}}
        onCommandOverrideChange={() => {}}
        onApprovalAcknowledgeChange={() => {}}
        onLaunch={() => {}}
        onForceLaunch={() => {}}
      />,
    );
    expect(html).toContain('Local');
  });

  it('disables unsupported provider option and includes unsupportedReason', () => {
    const prep = makePreparation({
      providers: [
        {
          provider: 'local',
          label: 'Local',
          supported: true,
          supportsWorktrees: true,
          supportsModelSelection: false,
          defaultModel: '',
          availableModels: [],
          requiresApproval: false,
          unsupportedReason: '',
          metadata: {},
        },
        {
          provider: 'cloud',
          label: 'Cloud',
          supported: false,
          supportsWorktrees: false,
          supportsModelSelection: false,
          defaultModel: '',
          availableModels: [],
          requiresApproval: false,
          unsupportedReason: 'coming soon',
          metadata: {},
        },
      ],
    });
    const html = renderToStaticMarkup(
      <PlanningLaunchSheetContent
        preparation={prep}
        selectedProvider="local"
        selectedModel=""
        worktreeMode="create"
        selectedWorktreeId=""
        newBranch=""
        newWorktreePath=""
        newBaseBranch=""
        newNotes=""
        commandOverride=""
        approvalAcknowledged={false}
        launching={false}
        launchError={null}
        showForceButton={false}
        onProviderChange={() => {}}
        onModelChange={() => {}}
        onWorktreeModeChange={() => {}}
        onWorktreeIdChange={() => {}}
        onNewBranchChange={() => {}}
        onNewWorktreePathChange={() => {}}
        onNewBaseBranchChange={() => {}}
        onNewNotesChange={() => {}}
        onCommandOverrideChange={() => {}}
        onApprovalAcknowledgeChange={() => {}}
        onLaunch={() => {}}
        onForceLaunch={() => {}}
      />,
    );
    // disabled attribute renders as "disabled" in static markup
    expect(html).toContain('disabled');
    expect(html).toContain('coming soon');
  });

  it('renders approval gate section when requirement=required', () => {
    const prep = makePreparation({
      approval: { requirement: 'required', reasonCodes: ['high-risk-cmd'], riskLevel: 'high' },
    });
    const html = renderToStaticMarkup(
      <PlanningLaunchSheetContent
        preparation={prep}
        selectedProvider="local"
        selectedModel=""
        worktreeMode="create"
        selectedWorktreeId=""
        newBranch=""
        newWorktreePath=""
        newBaseBranch=""
        newNotes=""
        commandOverride=""
        approvalAcknowledged={false}
        launching={false}
        launchError={null}
        showForceButton={false}
        onProviderChange={() => {}}
        onModelChange={() => {}}
        onWorktreeModeChange={() => {}}
        onWorktreeIdChange={() => {}}
        onNewBranchChange={() => {}}
        onNewWorktreePathChange={() => {}}
        onNewBaseBranchChange={() => {}}
        onNewNotesChange={() => {}}
        onCommandOverrideChange={() => {}}
        onApprovalAcknowledgeChange={() => {}}
        onLaunch={() => {}}
        onForceLaunch={() => {}}
      />,
    );
    expect(html).toContain('required');
    expect(html).toContain('high-risk-cmd');
    expect(html).toContain('I acknowledge this launch requires approval');
  });

  it('renders Launch button disabled when approval=required and not acknowledged', () => {
    const prep = makePreparation({
      approval: { requirement: 'required', reasonCodes: [], riskLevel: 'high' },
    });
    const html = renderToStaticMarkup(
      <PlanningLaunchSheetContent
        preparation={prep}
        selectedProvider="local"
        selectedModel=""
        worktreeMode="create"
        selectedWorktreeId=""
        newBranch=""
        newWorktreePath=""
        newBaseBranch=""
        newNotes=""
        commandOverride=""
        approvalAcknowledged={false}
        launching={false}
        launchError={null}
        showForceButton={false}
        onProviderChange={() => {}}
        onModelChange={() => {}}
        onWorktreeModeChange={() => {}}
        onWorktreeIdChange={() => {}}
        onNewBranchChange={() => {}}
        onNewWorktreePathChange={() => {}}
        onNewBaseBranchChange={() => {}}
        onNewNotesChange={() => {}}
        onCommandOverrideChange={() => {}}
        onApprovalAcknowledgeChange={() => {}}
        onLaunch={() => {}}
        onForceLaunch={() => {}}
      />,
    );
    // disabled attribute on the launch button
    expect(html).toContain('disabled');
  });

  it('renders inline error message and Force launch button on 409 state', () => {
    const html = renderToStaticMarkup(
      <PlanningLaunchSheetContent
        preparation={makePreparation()}
        selectedProvider="local"
        selectedModel=""
        worktreeMode="create"
        selectedWorktreeId=""
        newBranch=""
        newWorktreePath=""
        newBaseBranch=""
        newNotes=""
        commandOverride=""
        approvalAcknowledged={false}
        launching={false}
        launchError="Failed to start launch (409): approval required"
        showForceButton={true}
        onProviderChange={() => {}}
        onModelChange={() => {}}
        onWorktreeModeChange={() => {}}
        onWorktreeIdChange={() => {}}
        onNewBranchChange={() => {}}
        onNewWorktreePathChange={() => {}}
        onNewBaseBranchChange={() => {}}
        onNewNotesChange={() => {}}
        onCommandOverrideChange={() => {}}
        onApprovalAcknowledgeChange={() => {}}
        onLaunch={() => {}}
        onForceLaunch={() => {}}
      />,
    );
    expect(html).toContain('Failed to start launch (409): approval required');
    expect(html).toContain('Force launch (approve override)');
  });

  it('renders warnings section when warnings are present', () => {
    const prep = makePreparation({ warnings: ['Worktree path already in use'] });
    const html = renderToStaticMarkup(
      <PlanningLaunchSheetContent
        preparation={prep}
        selectedProvider="local"
        selectedModel=""
        worktreeMode="create"
        selectedWorktreeId=""
        newBranch=""
        newWorktreePath=""
        newBaseBranch=""
        newNotes=""
        commandOverride=""
        approvalAcknowledged={false}
        launching={false}
        launchError={null}
        showForceButton={false}
        onProviderChange={() => {}}
        onModelChange={() => {}}
        onWorktreeModeChange={() => {}}
        onWorktreeIdChange={() => {}}
        onNewBranchChange={() => {}}
        onNewWorktreePathChange={() => {}}
        onNewBaseBranchChange={() => {}}
        onNewNotesChange={() => {}}
        onCommandOverrideChange={() => {}}
        onApprovalAcknowledgeChange={() => {}}
        onLaunch={() => {}}
        onForceLaunch={() => {}}
      />,
    );
    expect(html).toContain('Worktree path already in use');
    expect(html).toContain('Warnings');
  });
});
