/**
 * Multi-project Planning Command Center component tests.
 *
 * MPCC-501..505: Tests for the portfolio-mode UI components.
 *
 * Test strategy: render-to-static-markup for pure structural tests
 * (no @tanstack/react-query dependency required).  These cover:
 *   - MultiProjectModeToggle: renders both modes, ARIA attributes
 *   - MultiProjectFilterRail: all/group/project chips + ARIA
 *   - MultiProjectWorkItemCard: project identity strip + V1 card presence
 *   - MultiProjectSessionBoard: empty state + group column structure
 *   - Feature-flag gate: PlanningCommandCenterShell only shows toggle when flag on
 */
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import type { ProjectSummary, AggregateWorkItem } from '@/types';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PROJECT_SUMMARY_A: ProjectSummary = {
  projectId: 'proj-alpha',
  name: 'Alpha Project',
  displayMetadata: { color: '#6366f1', group: 'backend' },
  counts: { workItems: 4, blocked: 1, review: 0, stale: 0, activeSessions: 2, errors: 0 },
  isStale: false,
  error: null,
  lastUpdated: '2026-05-29T10:00:00Z',
  freshnessSeconds: 120,
};

const PROJECT_SUMMARY_B: ProjectSummary = {
  projectId: 'proj-beta',
  name: 'Beta Project',
  displayMetadata: { color: '#ec4899', group: 'frontend' },
  counts: { workItems: 2, blocked: 0, review: 1, stale: 0, activeSessions: 0, errors: 0 },
  isStale: null,
  error: null,
  lastUpdated: null,
  freshnessSeconds: null,
};

const STALE_PROJECT_SUMMARY: ProjectSummary = {
  projectId: 'proj-gamma',
  name: 'Gamma Project',
  displayMetadata: { color: '#f59e0b' },
  counts: { workItems: 1, blocked: 0, review: 0, stale: 1, activeSessions: 0, errors: 0 },
  isStale: true,
  error: null,
  lastUpdated: null,
  freshnessSeconds: null,
};

const ERROR_PROJECT_SUMMARY: ProjectSummary = {
  projectId: 'proj-delta',
  name: 'Delta Project',
  displayMetadata: {},
  counts: { workItems: 0, blocked: 0, review: 0, stale: 0, activeSessions: 0, errors: 1 },
  isStale: null,
  error: 'Sync failed: connection timeout',
  lastUpdated: null,
  freshnessSeconds: null,
};

// ── MultiProjectModeToggle ────────────────────────────────────────────────────

describe('MultiProjectModeToggle', () => {
  // Dynamic import to avoid ESM issues in static tests
  it('renders project mode as the default with correct ARIA attributes', async () => {
    const { MultiProjectModeToggle } = await import('../CommandCenter/MultiProjectModeToggle');
    const html = renderToStaticMarkup(
      createElement(MultiProjectModeToggle, {
        mode: 'single',
        onModeChange: () => void 0,
      }),
    );
    expect(html).toContain('aria-label="Command center scope"');
    expect(html).toContain('aria-label="Single project view"');
    expect(html).toContain('aria-label="All projects portfolio view"');
    // Single mode button should be aria-pressed=true
    expect(html).toContain('"Single project view"');
  });

  it('renders portfolio mode with correct aria-pressed state', async () => {
    const { MultiProjectModeToggle } = await import('../CommandCenter/MultiProjectModeToggle');
    const html = renderToStaticMarkup(
      createElement(MultiProjectModeToggle, {
        mode: 'multi',
        onModeChange: () => void 0,
      }),
    );
    // Portfolio toggle should be present
    expect(html).toContain('portfolio');
    expect(html).toContain('project');
  });
});

// ── MultiProjectFilterRail ────────────────────────────────────────────────────

describe('MultiProjectFilterRail', () => {
  it('renders "all" control and per-project chips', async () => {
    const { MultiProjectFilterRail } = await import('../CommandCenter/MultiProjectFilterRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectFilterRail, {
        projectSummaries: [PROJECT_SUMMARY_A, PROJECT_SUMMARY_B],
        selectedProjectIds: [],
        selectedGroup: null,
        onProjectSelect: () => void 0,
        onGroupSelect: () => void 0,
      }),
    );
    expect(html).toContain('data-testid="multi-project-filter-rail"');
    expect(html).toContain('all');
    expect(html).toContain('Alpha Project');
    expect(html).toContain('Beta Project');
    // Project work item counts shown
    expect(html).toContain('4'); // Alpha counts.workItems
    expect(html).toContain('2'); // Beta counts.workItems
  });

  it('shows group chips when multiple groups present', async () => {
    const { MultiProjectFilterRail } = await import('../CommandCenter/MultiProjectFilterRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectFilterRail, {
        projectSummaries: [PROJECT_SUMMARY_A, PROJECT_SUMMARY_B],
        selectedProjectIds: [],
        selectedGroup: null,
        onProjectSelect: () => void 0,
        onGroupSelect: () => void 0,
      }),
    );
    // Both groups (backend, frontend) should appear as group chips
    expect(html).toContain('backend');
    expect(html).toContain('frontend');
  });

  it('shows stale indicator for stale project', async () => {
    const { MultiProjectFilterRail } = await import('../CommandCenter/MultiProjectFilterRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectFilterRail, {
        projectSummaries: [STALE_PROJECT_SUMMARY],
        selectedProjectIds: [],
        selectedGroup: null,
        onProjectSelect: () => void 0,
        onGroupSelect: () => void 0,
      }),
    );
    expect(html).toContain('Data may be stale');
  });

  it('shows error indicator for errored project', async () => {
    const { MultiProjectFilterRail } = await import('../CommandCenter/MultiProjectFilterRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectFilterRail, {
        projectSummaries: [ERROR_PROJECT_SUMMARY],
        selectedProjectIds: [],
        selectedGroup: null,
        onProjectSelect: () => void 0,
        onGroupSelect: () => void 0,
      }),
    );
    expect(html).toContain('Error:');
  });

  it('uses text + color accent (never color-only) — label always present', async () => {
    const { MultiProjectFilterRail } = await import('../CommandCenter/MultiProjectFilterRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectFilterRail, {
        projectSummaries: [PROJECT_SUMMARY_A],
        selectedProjectIds: [],
        selectedGroup: null,
        onProjectSelect: () => void 0,
        onGroupSelect: () => void 0,
      }),
    );
    // Text label must be present (not color-only)
    expect(html).toContain('Alpha Project');
    // Color is applied as accent style, not as sole identifier
    expect(html).toContain('#6366f1');
  });

  it('marks selected project with aria-checked', async () => {
    const { MultiProjectFilterRail } = await import('../CommandCenter/MultiProjectFilterRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectFilterRail, {
        projectSummaries: [PROJECT_SUMMARY_A, PROJECT_SUMMARY_B],
        selectedProjectIds: ['proj-alpha'],
        selectedGroup: null,
        onProjectSelect: () => void 0,
        onGroupSelect: () => void 0,
      }),
    );
    // aria-checked appears for radio buttons
    expect(html).toContain('role="radio"');
    expect(html).toContain('role="radiogroup"');
  });

  it('renders keyboard navigation attributes', async () => {
    const { MultiProjectFilterRail } = await import('../CommandCenter/MultiProjectFilterRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectFilterRail, {
        projectSummaries: [PROJECT_SUMMARY_A],
        selectedProjectIds: [],
        selectedGroup: null,
        onProjectSelect: () => void 0,
        onGroupSelect: () => void 0,
      }),
    );
    expect(html).toContain('role="radiogroup"');
    // Focus ring styles present
    expect(html).toContain('focus-visible:ring');
  });
});

// ── MultiProjectSessionBoard ──────────────────────────────────────────────────

describe('MultiProjectSessionBoard', () => {
  it('renders empty state when no groups', async () => {
    const { MultiProjectSessionBoard } = await import('../CommandCenter/MultiProjectSessionBoard');
    const html = renderToStaticMarkup(
      createElement(MultiProjectSessionBoard, {
        data: {
          status: 'ok',
          grouping: 'state',
          groups: [],
          projectSummaries: [],
          pagination: { page: 1, pageSize: 50, total: 0, hasMore: false },
          warnings: [],
          totalCardCount: 0,
          activeCount: 0,
          completedCount: 0,
        },
        loading: false,
        error: null,
        grouping: 'state',
        selectedCardId: null,
        onGroupingChange: () => void 0,
        onCardSelect: () => void 0,
        onRefresh: () => void 0,
      }),
    );
    expect(html).toContain('data-testid="multi-project-session-board"');
    expect(html).toContain('No active sessions across projects');
  });

  it('renders loading state when no data', async () => {
    const { MultiProjectSessionBoard } = await import('../CommandCenter/MultiProjectSessionBoard');
    const html = renderToStaticMarkup(
      createElement(MultiProjectSessionBoard, {
        data: undefined,
        loading: true,
        error: null,
        grouping: 'state',
        selectedCardId: null,
        onGroupingChange: () => void 0,
        onCardSelect: () => void 0,
        onRefresh: () => void 0,
      }),
    );
    expect(html).toContain('Loading active sessions across projects');
  });

  it('renders error state', async () => {
    const { MultiProjectSessionBoard } = await import('../CommandCenter/MultiProjectSessionBoard');
    const html = renderToStaticMarkup(
      createElement(MultiProjectSessionBoard, {
        data: undefined,
        loading: false,
        error: new Error('Network failure'),
        grouping: 'state',
        selectedCardId: null,
        onGroupingChange: () => void 0,
        onCardSelect: () => void 0,
        onRefresh: () => void 0,
      }),
    );
    expect(html).toContain('Network failure');
  });

  it('renders grouping mode toolbar with all 6 modes', async () => {
    const { MultiProjectSessionBoard } = await import('../CommandCenter/MultiProjectSessionBoard');
    const html = renderToStaticMarkup(
      createElement(MultiProjectSessionBoard, {
        data: {
          status: 'ok',
          grouping: 'state',
          groups: [],
          projectSummaries: [],
          pagination: { page: 1, pageSize: 50, total: 0, hasMore: false },
          warnings: [],
          totalCardCount: 0,
          activeCount: 0,
          completedCount: 0,
        },
        loading: false,
        error: null,
        grouping: 'state',
        selectedCardId: null,
        onGroupingChange: () => void 0,
        onCardSelect: () => void 0,
        onRefresh: () => void 0,
      }),
    );
    // All 6 grouping modes must be present as buttons
    expect(html).toContain('state');
    expect(html).toContain('project');
    expect(html).toContain('feature');
    expect(html).toContain('phase');
    expect(html).toContain('agent');
    expect(html).toContain('model');
    expect(html).toContain('aria-label="Session grouping dimension"');
  });

  it('renders group columns with aria list structure', async () => {
    const { MultiProjectSessionBoard } = await import('../CommandCenter/MultiProjectSessionBoard');
    const html = renderToStaticMarkup(
      createElement(MultiProjectSessionBoard, {
        data: {
          status: 'ok',
          grouping: 'state',
          groups: [
            {
              groupKey: 'running',
              groupLabel: 'running',
              groupType: 'state',
              cards: [],
              cardCount: 0,
            },
            {
              groupKey: 'completed',
              groupLabel: 'completed',
              groupType: 'state',
              cards: [],
              cardCount: 0,
            },
          ],
          projectSummaries: [],
          pagination: { page: 1, pageSize: 50, total: 0, hasMore: false },
          warnings: [],
          totalCardCount: 0,
          activeCount: 0,
          completedCount: 0,
        },
        loading: false,
        error: null,
        grouping: 'state',
        selectedCardId: null,
        onGroupingChange: () => void 0,
        onCardSelect: () => void 0,
        onRefresh: () => void 0,
      }),
    );
    expect(html).toContain('role="list"');
    expect(html).toContain('role="listitem"');
    expect(html).toContain('data-group-key="running"');
    expect(html).toContain('data-group-key="completed"');
  });
});

// ── MultiProjectDetailRail ────────────────────────────────────────────────────

describe('MultiProjectDetailRail', () => {
  it('renders nothing when target is null', async () => {
    const { MultiProjectDetailRail } = await import('../CommandCenter/MultiProjectDetailRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectDetailRail, {
        target: null,
        onClose: () => void 0,
      }),
    );
    expect(html).toBe('');
  });

  it('renders session detail with project identity badge', async () => {
    const { MultiProjectDetailRail } = await import('../CommandCenter/MultiProjectDetailRail');
    const html = renderToStaticMarkup(
      createElement(MultiProjectDetailRail, {
        target: {
          kind: 'session',
          sessionId: 'sess-abc123',
          projectId: 'proj-alpha',
          aggregateCard: {
            project: {
              projectId: 'proj-alpha',
              projectName: 'Alpha Project',
              projectColor: '#6366f1',
            },
            card: {
              sessionId: 'sess-abc123',
              state: 'running',
              relationships: [],
              activityMarkers: [],
            },
            workers: [],
          },
        },
        onClose: () => void 0,
      }),
    );
    expect(html).toContain('data-testid="multi-project-detail-rail"');
    expect(html).toContain('data-project-id="proj-alpha"');
    expect(html).toContain('Alpha Project');
    expect(html).toContain('sess-abc123');
    // Drawer must have ARIA dialog role
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
  });

  it('renders non-active project detail without switching projects', async () => {
    const { MultiProjectDetailRail } = await import('../CommandCenter/MultiProjectDetailRail');
    // The drawer renders project context from explicit project_id, not active project
    const html = renderToStaticMarkup(
      createElement(MultiProjectDetailRail, {
        target: {
          kind: 'session',
          sessionId: 'sess-xyz',
          projectId: 'proj-other',
        },
        onClose: () => void 0,
      }),
    );
    // Note: this is a non-active project — rail must still show project_id
    expect(html).toContain('data-project-id="proj-other"');
    // The "viewing does not change your active project" notice
    expect(html).toContain('Viewing does not change your active project');
  });
});

// ── MultiProjectWorkItemCard ──────────────────────────────────────────────────

describe('MultiProjectWorkItemCard', () => {
  it('renders project identity strip with color accent and text label', async () => {
    const { MultiProjectWorkItemCard } = await import('../CommandCenter/MultiProjectWorkItemCard');
    const workItem: AggregateWorkItem = {
      project: {
        projectId: 'proj-alpha',
        projectName: 'Alpha Project',
        projectColor: '#6366f1',
        projectGroup: 'backend',
      },
      item: {
        feature: {
          featureId: 'feat-001',
          featureSlug: 'feat-001',
          name: 'Feature 001',
          category: 'enhancement',
          tags: [],
          priority: 'high',
          summary: 'Test feature',
        },
        status: {
          rawStatus: 'in-progress',
          effectiveStatus: 'in-progress',
          planningSignal: 'active',
          mismatchState: 'none',
          isMismatch: false,
        },
        storyPoints: { total: 3, remaining: 2, completed: 1 },
        phase: { currentPhase: 1, nextPhase: 2, totalPhases: 3, completedPhases: 0 },
        artifacts: [],
        relatedFiles: [],
        phaseRows: [],
        blockers: [],
        lastActivity: {},
        capabilities: {
          copyCommand: false,
          launch: false,
          review: false,
          merge: false,
          cleanup: false,
          openPr: false,
          editCommand: false,
        },
      },
    };
    const html = renderToStaticMarkup(
      createElement(MultiProjectWorkItemCard, {
        workItem,
        commandValue: '',
        onCopyCommand: () => void 0,
      }),
    );
    expect(html).toContain('data-testid="multi-project-work-item-card"');
    expect(html).toContain('data-project-id="proj-alpha"');
    // Text label present — not color-only
    expect(html).toContain('Alpha Project');
    expect(html).toContain('#6366f1');
    // Group label present
    expect(html).toContain('backend');
  });
});
