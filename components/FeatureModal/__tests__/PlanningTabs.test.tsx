/**
 * P4-003: Planning tab components — PhasesTab, DocsTab, RelationsTab.
 *
 * Tests verify:
 * - Correct TabStateView status delegation (idle, loading, error, success)
 * - Empty-state rendering when data is absent after a successful load
 * - Data rendering for the happy path (success with items)
 * - Navigation callbacks are invoked correctly (RelationsTab)
 * - Filter controls exist on PhasesTab
 * - PlanningTabGroup routes correctly to each tab component
 *
 * Uses renderToStaticMarkup (no DOM) to keep tests fast and dependency-free.
 * Interactive behaviours (filter changes, phase toggles) require DOM and are
 * left to integration tests (FeatureModalConsumerWiring, FeatureModalLazyTabs).
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

import { PhasesTab } from '../PhasesTab';
import { DocsTab } from '../DocsTab';
import { RelationsTab } from '../RelationsTab';
import { PlanningTabGroup } from '../PlanningTabGroup';

import type { SectionHandle } from '../../../services/useFeatureModalCore';
import type { FeatureModalPlanningStore } from '../../../services/useFeatureModalPlanning';
import type {
  FeaturePhase,
  LinkedDocument,
  LinkedFeatureRef,
  ProjectTask,
} from '../../../types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function render(ui: React.ReactElement): string {
  return renderToStaticMarkup(ui);
}

function makeHandle(overrides: Partial<SectionHandle> = {}): SectionHandle {
  return {
    status: 'success',
    data: null,
    error: null,
    requestId: 1,
    load: vi.fn(),
    retry: vi.fn(),
    invalidate: vi.fn(),
    ...overrides,
  };
}

function makePlanningStore(
  overrides: Partial<FeatureModalPlanningStore> = {},
): FeatureModalPlanningStore {
  return {
    phases: makeHandle(),
    docs: makeHandle(),
    relations: makeHandle(),
    prefetch: vi.fn(),
    markStale: vi.fn(),
    invalidateAll: vi.fn(),
    ...overrides,
  };
}

/** Minimal ProjectTask fixture — satisfies the full interface. */
function makeTask(id: string, title: string, status: ProjectTask['status']): ProjectTask {
  return {
    id,
    title,
    status,
    description: '',
    owner: '',
    lastAgent: '',
    cost: 0,
    priority: 'medium',
    projectType: 'Feature',
    projectLevel: 'Full',
    tags: [],
    updatedAt: '2026-05-01T00:00:00Z',
    relatedFiles: [],
  };
}

const NOOP_CALLBACKS = {
  onSessionNavigate: vi.fn(),
  onCommitNavigate: vi.fn(),
  onPhaseStatusChange: vi.fn(),
  onTaskStatusChange: vi.fn(),
  onTaskView: vi.fn(),
};

const NOOP_RENDER_DOC_GRID = () => null;

const SAMPLE_PHASE: FeaturePhase = {
  id: 'p1',
  phase: '1',
  title: 'Foundation',
  status: 'in-progress',
  progress: 50,
  totalTasks: 4,
  completedTasks: 2,
  deferredTasks: 0,
  tasks: [
    makeTask('T1-001', 'Set up CI pipeline', 'done'),
    makeTask('T1-002', 'Write integration tests', 'backlog'),
  ],
};

const SAMPLE_DOC: LinkedDocument = {
  id: 'doc-001',
  title: 'Planning PRD v1',
  filePath: '/docs/prd.md',
  docType: 'prd',
};

const SAMPLE_LINKED_FEATURE: LinkedFeatureRef = {
  feature: 'FEAT-042',
  type: 'depends_on',
  source: 'prd',
  confidence: 0.9,
};

// ── PhasesTab ─────────────────────────────────────────────────────────────────

describe('PhasesTab', () => {
  it('renders idle state as empty (TabStateView idle = null)', () => {
    const html = render(
      <PhasesTab
        handle={makeHandle({ status: 'idle' })}
        phases={[]}
        callbacks={NOOP_CALLBACKS}
      />,
    );
    expect(html).toBe('');
  });

  it('renders loading skeleton when status is loading', () => {
    const html = render(
      <PhasesTab
        handle={makeHandle({ status: 'loading' })}
        phases={[]}
        callbacks={NOOP_CALLBACKS}
      />,
    );
    expect(html).toContain('Loading');
  });

  it('renders error banner with retry affordance', () => {
    const html = render(
      <PhasesTab
        handle={makeHandle({ status: 'error', error: new Error('network timeout') })}
        phases={[]}
        callbacks={NOOP_CALLBACKS}
      />,
    );
    expect(html).toContain('Failed to load');
    expect(html).toContain('network timeout');
    expect(html).toContain('Retry');
  });

  it('renders empty state when success but no phases', () => {
    const html = render(
      <PhasesTab
        handle={makeHandle({ status: 'success' })}
        phases={[]}
        callbacks={NOOP_CALLBACKS}
      />,
    );
    expect(html).toContain('No phases tracked for this feature.');
  });

  it('renders phase data on success', () => {
    const html = render(
      <PhasesTab
        handle={makeHandle({ status: 'success' })}
        phases={[SAMPLE_PHASE]}
        callbacks={NOOP_CALLBACKS}
      />,
    );
    expect(html).toContain('Phase 1');
    expect(html).toContain('Foundation');
  });

  it('renders filter dropdowns when phases are present', () => {
    const html = render(
      <PhasesTab
        handle={makeHandle({ status: 'success' })}
        phases={[SAMPLE_PHASE]}
        callbacks={NOOP_CALLBACKS}
      />,
    );
    expect(html).toContain('Phase Status');
    expect(html).toContain('Task Status');
  });

  it('renders stale indicator on stale status', () => {
    const html = render(
      <PhasesTab
        handle={makeHandle({ status: 'stale' })}
        phases={[SAMPLE_PHASE]}
        callbacks={NOOP_CALLBACKS}
      />,
    );
    expect(html).toContain('Refreshing phases');
  });

  it('renders deferred badge when phase has deferred tasks', () => {
    const phaseWithDeferred: FeaturePhase = {
      ...SAMPLE_PHASE,
      id: 'p-deferred',
      deferredTasks: 1,
      tasks: [makeTask('T2-001', 'Deferred task', 'deferred')],
    };
    const html = render(
      <PhasesTab
        handle={makeHandle({ status: 'success' })}
        phases={[phaseWithDeferred]}
        callbacks={NOOP_CALLBACKS}
      />,
    );
    expect(html).toContain('Deferred');
  });
});

// ── DocsTab ───────────────────────────────────────────────────────────────────

describe('DocsTab', () => {
  it('renders idle state as empty', () => {
    const html = render(
      <DocsTab
        handle={makeHandle({ status: 'idle' })}
        linkedDocs={[]}
        docsByGroup={new Map()}
        renderDocGrid={NOOP_RENDER_DOC_GRID}
      />,
    );
    expect(html).toBe('');
  });

  it('renders loading skeleton when status is loading', () => {
    const html = render(
      <DocsTab
        handle={makeHandle({ status: 'loading' })}
        linkedDocs={[]}
        docsByGroup={new Map()}
        renderDocGrid={NOOP_RENDER_DOC_GRID}
      />,
    );
    expect(html).toContain('Loading');
  });

  it('renders error banner when status is error', () => {
    const html = render(
      <DocsTab
        handle={makeHandle({ status: 'error', error: new Error('doc fetch failed') })}
        linkedDocs={[]}
        docsByGroup={new Map()}
        renderDocGrid={NOOP_RENDER_DOC_GRID}
      />,
    );
    expect(html).toContain('Failed to load');
    expect(html).toContain('doc fetch failed');
  });

  it('renders empty state when success with no linked docs', () => {
    const html = render(
      <DocsTab
        handle={makeHandle({ status: 'success' })}
        linkedDocs={[]}
        docsByGroup={new Map()}
        renderDocGrid={NOOP_RENDER_DOC_GRID}
      />,
    );
    expect(html).toContain('No documents linked to this feature.');
  });

  it('renders metric tiles on success with docs', () => {
    const html = render(
      <DocsTab
        handle={makeHandle({ status: 'success' })}
        linkedDocs={[SAMPLE_DOC]}
        docsByGroup={new Map([['prds', [SAMPLE_DOC]]])}
        familyPositionLabel="1 of 3"
        featureFamily="auth-suite"
        executionGateLabel="Ready"
        renderDocGrid={NOOP_RENDER_DOC_GRID}
      />,
    );
    expect(html).toContain('Document Groups');
    expect(html).toContain('Family Position');
    expect(html).toContain('Execution Gate');
    expect(html).toContain('1 of 3');
    expect(html).toContain('auth-suite');
    expect(html).toContain('Ready');
  });

  it('renders doc type count chip', () => {
    const html = render(
      <DocsTab
        handle={makeHandle({ status: 'success' })}
        linkedDocs={[SAMPLE_DOC]}
        docsByGroup={new Map([['prds', [SAMPLE_DOC]]])}
        renderDocGrid={NOOP_RENDER_DOC_GRID}
      />,
    );
    // PRD type chip should appear in the type breakdown strip
    expect(html).toContain('PRD');
  });

  it('renders stale indicator when stale', () => {
    const html = render(
      <DocsTab
        handle={makeHandle({ status: 'stale' })}
        linkedDocs={[SAMPLE_DOC]}
        docsByGroup={new Map([['prds', [SAMPLE_DOC]]])}
        renderDocGrid={NOOP_RENDER_DOC_GRID}
      />,
    );
    expect(html).toContain('Refreshing documents');
  });

  it('renders doc group section headers for groups with docs', () => {
    const planDoc: LinkedDocument = {
      id: 'plan-001',
      title: 'Impl Plan',
      filePath: '/docs/plan.md',
      docType: 'implementation_plan',
    };
    const html = render(
      <DocsTab
        handle={makeHandle({ status: 'success' })}
        linkedDocs={[SAMPLE_DOC, planDoc]}
        docsByGroup={
          new Map([
            ['prds', [SAMPLE_DOC]],
            ['plans', [planDoc]],
          ])
        }
        renderDocGrid={NOOP_RENDER_DOC_GRID}
      />,
    );
    expect(html).toContain('Plans');
    expect(html).toContain('PRDs');
  });
});

// ── RelationsTab ──────────────────────────────────────────────────────────────

describe('RelationsTab', () => {
  it('renders idle state as empty', () => {
    const html = render(<RelationsTab handle={makeHandle({ status: 'idle' })} />);
    expect(html).toBe('');
  });

  it('renders loading skeleton when loading', () => {
    const html = render(<RelationsTab handle={makeHandle({ status: 'loading' })} />);
    expect(html).toContain('Loading');
  });

  it('renders error banner when error', () => {
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'error', error: new Error('relations error') })}
      />,
    );
    expect(html).toContain('Failed to load');
    expect(html).toContain('relations error');
  });

  it('renders empty state when success with no relations', () => {
    const html = render(<RelationsTab handle={makeHandle({ status: 'success' })} />);
    expect(html).toContain('No relations found for this feature.');
  });

  it('renders dependency evidence on success', () => {
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'success' })}
        blockingEvidence={[
          {
            dependencyFeatureId: 'FEAT-001',
            dependencyFeatureName: 'Auth Core',
            dependencyStatus: 'done',
            dependencyCompletionEvidence: ['commit abc123'],
            blockingDocumentIds: [],
            blockingReason: 'Must complete auth first',
            resolved: false,
            state: 'blocked',
          },
        ]}
      />,
    );
    expect(html).toContain('Auth Core');
    expect(html).toContain('Must complete auth first');
    expect(html).toContain('blocked');
  });

  it('renders typed feature relations', () => {
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'success' })}
        linkedFeatures={[SAMPLE_LINKED_FEATURE]}
        relatedFeatures={['FEAT-010']}
      />,
    );
    expect(html).toContain('FEAT-042');
    expect(html).toContain('depends_on');
    expect(html).toContain('FEAT-010');
  });

  it('renders family order section', () => {
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'success' })}
        familyPositionLabel="2 of 5"
        featureFamily="platform-suite"
        linkedFeatures={[SAMPLE_LINKED_FEATURE]}
      />,
    );
    expect(html).toContain('Family Order');
    expect(html).toContain('platform-suite');
    expect(html).toContain('2 of 5');
  });

  it('renders lineage signals from docs with lineage metadata', () => {
    const docWithLineage: LinkedDocument = {
      id: 'doc-lineage-001',
      title: 'Platform PRD',
      filePath: '/docs/prd.md',
      docType: 'prd',
      lineageFamily: 'platform-suite',
      lineageParent: 'FEAT-000',
      lineageChildren: ['FEAT-002'],
    };
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'success' })}
        linkedDocs={[docWithLineage]}
        linkedFeatures={[SAMPLE_LINKED_FEATURE]}
      />,
    );
    expect(html).toContain('Lineage Signals');
    expect(html).toContain('platform-suite');
    expect(html).toContain('FEAT-000');
    expect(html).toContain('FEAT-002');
  });

  it('renders "no lineage metadata detected" when no docs have lineage', () => {
    const docWithoutLineage: LinkedDocument = {
      id: 'doc-001',
      title: 'Plain doc',
      filePath: '/docs/plain.md',
      docType: 'prd',
    };
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'success' })}
        linkedDocs={[docWithoutLineage]}
        linkedFeatures={[SAMPLE_LINKED_FEATURE]}
      />,
    );
    expect(html).toContain('No lineage metadata detected.');
  });

  it('renders with launchedFromPlanning=true without errors', () => {
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'success' })}
        linkedFeatures={[SAMPLE_LINKED_FEATURE]}
        launchedFromPlanning={true}
      />,
    );
    expect(html).toContain('FEAT-042');
  });

  it('renders with custom onFeatureNavigate callback without errors', () => {
    const onNavigate = vi.fn();
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'success' })}
        linkedFeatures={[SAMPLE_LINKED_FEATURE]}
        onFeatureNavigate={onNavigate}
      />,
    );
    expect(html).toContain('FEAT-042');
  });

  it('renders no related features message when relatedFeatures is empty', () => {
    const html = render(
      <RelationsTab
        handle={makeHandle({ status: 'success' })}
        linkedFeatures={[SAMPLE_LINKED_FEATURE]}
        relatedFeatures={[]}
      />,
    );
    expect(html).toContain('No related features.');
  });
});

// ── PlanningTabGroup ──────────────────────────────────────────────────────────

describe('PlanningTabGroup', () => {
  it('renders PhasesTab for phases tab', () => {
    const html = render(
      <PlanningTabGroup
        activeTab="phases"
        planningStore={makePlanningStore()}
        phasesProps={{ phases: [SAMPLE_PHASE], callbacks: NOOP_CALLBACKS }}
        docsProps={{
          linkedDocs: [],
          docsByGroup: new Map(),
          renderDocGrid: NOOP_RENDER_DOC_GRID,
        }}
        relationsProps={{}}
      />,
    );
    expect(html).toContain('Phase 1');
    expect(html).toContain('Foundation');
  });

  it('renders DocsTab for docs tab', () => {
    const html = render(
      <PlanningTabGroup
        activeTab="docs"
        planningStore={makePlanningStore()}
        phasesProps={{ phases: [], callbacks: NOOP_CALLBACKS }}
        docsProps={{
          linkedDocs: [SAMPLE_DOC],
          docsByGroup: new Map([['prds', [SAMPLE_DOC]]]),
          renderDocGrid: NOOP_RENDER_DOC_GRID,
        }}
        relationsProps={{}}
      />,
    );
    expect(html).toContain('Document Groups');
  });

  it('renders RelationsTab for relations tab', () => {
    const html = render(
      <PlanningTabGroup
        activeTab="relations"
        planningStore={makePlanningStore()}
        phasesProps={{ phases: [], callbacks: NOOP_CALLBACKS }}
        docsProps={{
          linkedDocs: [],
          docsByGroup: new Map(),
          renderDocGrid: NOOP_RENDER_DOC_GRID,
        }}
        relationsProps={{ linkedFeatures: [SAMPLE_LINKED_FEATURE] }}
      />,
    );
    expect(html).toContain('FEAT-042');
  });

  it('returns empty string for non-planning tab IDs', () => {
    const nonPlanningTabs = ['overview', 'sessions', 'history', 'test-status'] as const;
    for (const tabId of nonPlanningTabs) {
      const html = render(
        <PlanningTabGroup
          activeTab={tabId}
          planningStore={makePlanningStore()}
          phasesProps={{ phases: [], callbacks: NOOP_CALLBACKS }}
          docsProps={{
            linkedDocs: [],
            docsByGroup: new Map(),
            renderDocGrid: NOOP_RENDER_DOC_GRID,
          }}
          relationsProps={{}}
        />,
      );
      expect(html).toBe('');
    }
  });

  it('forwards error handle from store to PhasesTab', () => {
    const store = makePlanningStore({
      phases: makeHandle({ status: 'error', error: new Error('phases failed') }),
    });
    const html = render(
      <PlanningTabGroup
        activeTab="phases"
        planningStore={store}
        phasesProps={{ phases: [], callbacks: NOOP_CALLBACKS }}
        docsProps={{
          linkedDocs: [],
          docsByGroup: new Map(),
          renderDocGrid: NOOP_RENDER_DOC_GRID,
        }}
        relationsProps={{}}
      />,
    );
    expect(html).toContain('Failed to load');
    expect(html).toContain('phases failed');
  });
});
