/**
 * T3-003: Branch/commit provenance dialog on CommandCenterFeatureCard.
 *
 * Strategy: renderToStaticMarkup — same pattern as T3-001 test. Tests exercise:
 *   (a) BranchProvenancePanel directly (entries + provenance kind labels)
 *   (b) Full card render to verify trigger visibility vs empty-state handling
 *
 * Coverage:
 *   1.  Panel renders entries with visible provenance kind labels (fixture test).
 *   2.  Panel shows all four provenance kinds (worktree, session-git-branch, commit-ref, pr-ref).
 *   3.  Panel renders each entry's value.
 *   4.  Empty-state: when commit_refs and pr_refs both absent and no worktree/gitState,
 *       the disabled trigger renders (not the clickable trigger).
 *   5.  Empty-state: disabled trigger carries aria-disabled="true".
 *   6.  Empty-state tooltip text is "No branch or commit data linked."
 *   7.  Clickable trigger renders when worktree branch is present.
 *   8.  Clickable trigger renders when commitRefs is non-empty.
 *   9.  Clickable trigger renders when prRefs is non-empty.
 *  10.  buildProvenanceEntries — worktree entry produced when worktree.branch present.
 *  11.  buildProvenanceEntries — session-git-branch entry from gitState.head.
 *  12.  buildProvenanceEntries — commit-ref entries from commitRefs array.
 *  13.  buildProvenanceEntries — pr-ref entries from prRefs array.
 *  14.  buildProvenanceEntries — empty when all sources absent.
 *  15.  AC-WORKTREE-EMPTY: "No worktree registered" label when worktree is null.
 *  16.  AC-WORKTREE-EMPTY: "No worktree registered" label when worktree is absent.
 *  17.  AC-CWD-EXCLUSION: no access to session_forensics_json / workingDirectories.
 *  18.  Panel close button renders.
 *  19.  Entry list test-id present in panel.
 *  20.  Multiple commit refs each get their own entry.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { PlanningCommandCenterItem } from '@/types';
import {
  BranchProvenancePanel,
  CommandCenterFeatureCard,
  buildProvenanceEntries,
} from '../CommandCenterFeatureCard';

// ── Fixture factory ───────────────────────────────────────────────────────────

function makeItem(
  overrides: Partial<Pick<
    PlanningCommandCenterItem,
    'worktree' | 'gitState' | 'commitRefs' | 'prRefs'
  >> = {},
): PlanningCommandCenterItem {
  return {
    feature: {
      featureId: 'FEAT-003',
      featureSlug: 'feat-003',
      name: 'Branch Provenance Feature',
      category: 'enhancement',
      tags: [],
      priority: 'high',
      summary: 'Test feature for branch provenance dialog.',
    },
    status: {
      effectiveStatus: 'active',
      rawStatus: 'active',
      planningSignal: 'on_track',
      mismatchState: 'none',
      isMismatch: false,
    },
    storyPoints: { total: 5, remaining: 2, completed: 3 },
    phase: { currentPhase: 3, totalPhases: 5, completedPhases: 2 },
    artifacts: [],
    relatedFiles: [],
    phaseRows: [],
    blockers: [],
    lastActivity: {},
    capabilities: {
      copyCommand: true,
      launch: true,
      review: false,
      merge: false,
      cleanup: false,
      openPr: false,
      editCommand: false,
    },
    ...overrides,
  } as unknown as PlanningCommandCenterItem;
}

// ── Helper: render card to HTML string ───────────────────────────────────────

function renderCard(
  overrides: Partial<Pick<
    PlanningCommandCenterItem,
    'worktree' | 'gitState' | 'commitRefs' | 'prRefs'
  >> = {},
): string {
  const item = makeItem(overrides);
  return renderToStaticMarkup(
    createElement(CommandCenterFeatureCard, {
      item,
      commandValue: '/dev:execute-phase',
    }),
  );
}

// ── 1–3: BranchProvenancePanel renders entries with kind labels ───────────────

describe('BranchProvenancePanel — entry rendering', () => {
  it('renders the panel with a worktree entry and visible provenance label', () => {
    const html = renderToStaticMarkup(
      createElement(BranchProvenancePanel, {
        entries: [{ kind: 'worktree', label: 'worktree', value: 'feat/my-branch' }],
        onClose: () => {},
      }),
    );
    expect(html).toContain('data-testid="branch-provenance-panel"');
    expect(html).toContain('data-testid="branch-provenance-entry"');
    expect(html).toContain('data-testid="branch-provenance-kind-label"');
    expect(html).toContain('worktree');
    expect(html).toContain('feat/my-branch');
  });

  it('renders all four provenance kinds', () => {
    const entries = [
      { kind: 'worktree' as const, label: 'worktree', value: 'main' },
      { kind: 'session-git-branch' as const, label: 'session-git-branch', value: 'abc1234' },
      { kind: 'commit-ref' as const, label: 'commit-ref', value: 'deadbeef' },
      { kind: 'pr-ref' as const, label: 'pr-ref', value: '#42' },
    ];
    const html = renderToStaticMarkup(
      createElement(BranchProvenancePanel, { entries, onClose: () => {} }),
    );
    expect(html).toContain('worktree');
    expect(html).toContain('session-git-branch');
    expect(html).toContain('commit-ref');
    expect(html).toContain('pr-ref');
  });

  it('renders each entry value in the panel', () => {
    const html = renderToStaticMarkup(
      createElement(BranchProvenancePanel, {
        entries: [
          { kind: 'commit-ref' as const, label: 'commit-ref', value: 'abc123def456' },
        ],
        onClose: () => {},
      }),
    );
    expect(html).toContain('abc123def456');
    expect(html).toContain('data-testid="branch-provenance-value"');
  });
});

// ── 4–6: Empty-state trigger (no provenance data) ─────────────────────────────

describe('Empty-state — trigger hidden/disabled', () => {
  it('renders the disabled trigger when no provenance data exists', () => {
    const html = renderCard({
      worktree: null,
      gitState: undefined,
      commitRefs: [],
      prRefs: [],
    });
    expect(html).toContain('data-testid="branch-provenance-trigger-disabled"');
    expect(html).not.toContain('data-testid="branch-provenance-trigger"');
  });

  it('disabled trigger carries aria-disabled="true"', () => {
    const html = renderCard({
      worktree: null,
      gitState: undefined,
      commitRefs: [],
      prRefs: [],
    });
    expect(html).toContain('aria-disabled="true"');
  });

  it('empty-state trigger carries tooltip text "No branch or commit data linked."', () => {
    const html = renderCard({
      worktree: null,
      gitState: undefined,
      commitRefs: [],
      prRefs: [],
    });
    // data-tooltip and title attributes carry the message; Radix TooltipContent
    // renders in a Portal (not serialized by renderToStaticMarkup), so we check
    // the attributes on the trigger element itself.
    expect(html).toContain('No branch or commit data linked.');
  });

  it('does not render the disabled trigger when worktree branch is present', () => {
    const html = renderCard({
      worktree: { branch: 'feat/some-branch', contextId: 'ctx-1', path: '/tmp', status: 'clean', batchId: 'b1' },
    });
    expect(html).not.toContain('data-testid="branch-provenance-trigger-disabled"');
  });
});

// ── 7–9: Clickable trigger renders when data is available ─────────────────────

describe('Clickable trigger — rendered when provenance data present', () => {
  it('renders clickable trigger when worktree.branch is populated', () => {
    const html = renderCard({
      worktree: { branch: 'feat/active-branch', contextId: 'ctx-1', path: '/tmp', status: 'clean', batchId: 'b1' },
    });
    expect(html).toContain('data-testid="branch-provenance-trigger"');
    expect(html).not.toContain('data-testid="branch-provenance-trigger-disabled"');
  });

  it('renders clickable trigger when commitRefs is non-empty', () => {
    const html = renderCard({
      worktree: null,
      gitState: undefined,
      commitRefs: ['abc123'],
      prRefs: [],
    });
    expect(html).toContain('data-testid="branch-provenance-trigger"');
  });

  it('renders clickable trigger when prRefs is non-empty', () => {
    const html = renderCard({
      worktree: null,
      gitState: undefined,
      commitRefs: [],
      prRefs: ['#99'],
    });
    expect(html).toContain('data-testid="branch-provenance-trigger"');
  });
});

// ── 10–14: buildProvenanceEntries utility ────────────────────────────────────

describe('buildProvenanceEntries — entry construction', () => {
  it('produces a worktree entry when worktree.branch is present', () => {
    const item = makeItem({
      worktree: { branch: 'main', contextId: 'c1', path: '/repo', status: 'clean', batchId: 'b1' },
    });
    const entries = buildProvenanceEntries(item);
    const worktree = entries.find((e) => e.kind === 'worktree');
    expect(worktree).toBeDefined();
    expect(worktree?.value).toBe('main');
    expect(worktree?.label).toBe('worktree');
  });

  it('produces a session-git-branch entry from gitState.head', () => {
    const item = makeItem({
      gitState: { head: 'abc1234', upstream: '', probedAt: '', warnings: [], pathExists: true },
    });
    const entries = buildProvenanceEntries(item);
    const gitEntry = entries.find((e) => e.kind === 'session-git-branch');
    expect(gitEntry).toBeDefined();
    expect(gitEntry?.value).toBe('abc1234');
  });

  it('produces commit-ref entries from commitRefs array', () => {
    const item = makeItem({ commitRefs: ['sha-aaa', 'sha-bbb'] });
    const entries = buildProvenanceEntries(item);
    const commitEntries = entries.filter((e) => e.kind === 'commit-ref');
    expect(commitEntries).toHaveLength(2);
    expect(commitEntries[0].value).toBe('sha-aaa');
    expect(commitEntries[1].value).toBe('sha-bbb');
  });

  it('produces pr-ref entries from prRefs array', () => {
    const item = makeItem({ prRefs: ['#10', '#11'] });
    const entries = buildProvenanceEntries(item);
    const prEntries = entries.filter((e) => e.kind === 'pr-ref');
    expect(prEntries).toHaveLength(2);
    expect(prEntries[0].value).toBe('#10');
    expect(prEntries[1].value).toBe('#11');
  });

  it('returns empty array when all sources are absent', () => {
    const item = makeItem({
      worktree: null,
      gitState: undefined,
      commitRefs: [],
      prRefs: [],
    });
    const entries = buildProvenanceEntries(item);
    expect(entries).toHaveLength(0);
  });

  it('returns empty array when all sources are undefined', () => {
    const item = makeItem({});
    const entries = buildProvenanceEntries(item);
    expect(entries).toHaveLength(0);
  });
});

// ── 15–16: AC-WORKTREE-EMPTY ─────────────────────────────────────────────────

describe('AC-WORKTREE-EMPTY — "No worktree registered" label', () => {
  it('shows "No worktree registered" when worktree is null', () => {
    const html = renderCard({
      worktree: null,
      commitRefs: ['sha-abc'],
    });
    expect(html).toContain('No worktree registered');
    expect(html).not.toContain('branch TBD');
  });

  it('shows "No worktree registered" when worktree is absent (undefined)', () => {
    const html = renderCard({ commitRefs: ['sha-xyz'] });
    expect(html).toContain('No worktree registered');
    expect(html).not.toContain('branch TBD');
  });

  it('does not render an error state when worktree is absent', () => {
    expect(() => renderCard({ worktree: null })).not.toThrow();
  });
});

// ── 17: AC-CWD-EXCLUSION ─────────────────────────────────────────────────────

describe('AC-CWD-EXCLUSION', () => {
  it('provenance panel does not reference workingDirectories or session_forensics_json', () => {
    const html = renderToStaticMarkup(
      createElement(BranchProvenancePanel, {
        entries: [
          { kind: 'worktree' as const, label: 'worktree', value: 'feat/test' },
          { kind: 'commit-ref' as const, label: 'commit-ref', value: 'abc123' },
        ],
        onClose: () => {},
      }),
    );
    expect(html).not.toContain('workingDirectories');
    expect(html).not.toContain('session_forensics_json');
  });

  it('card render does not reference workingDirectories or session_forensics_json', () => {
    const html = renderCard({
      worktree: { branch: 'feat/test', contextId: 'c1', path: '/tmp', status: 'clean', batchId: 'b1' },
      commitRefs: ['sha-123'],
    });
    expect(html).not.toContain('workingDirectories');
    expect(html).not.toContain('session_forensics_json');
  });
});

// ── 18: Panel close button ────────────────────────────────────────────────────

describe('BranchProvenancePanel — close button', () => {
  it('renders the close button', () => {
    const html = renderToStaticMarkup(
      createElement(BranchProvenancePanel, {
        entries: [{ kind: 'worktree' as const, label: 'worktree', value: 'main' }],
        onClose: () => {},
      }),
    );
    expect(html).toContain('data-testid="branch-provenance-close-btn"');
  });
});

// ── 19: Panel entry list test-id ─────────────────────────────────────────────

describe('BranchProvenancePanel — structural test-ids', () => {
  it('panel list carries data-testid="branch-provenance-list"', () => {
    const html = renderToStaticMarkup(
      createElement(BranchProvenancePanel, {
        entries: [{ kind: 'pr-ref' as const, label: 'pr-ref', value: '#42' }],
        onClose: () => {},
      }),
    );
    expect(html).toContain('data-testid="branch-provenance-list"');
  });
});

// ── 20: Multiple commit refs each get their own entry ────────────────────────

describe('BranchProvenancePanel — multiple entries', () => {
  it('each commit ref gets its own list entry', () => {
    const entries = [
      { kind: 'commit-ref' as const, label: 'commit-ref', value: 'sha-001' },
      { kind: 'commit-ref' as const, label: 'commit-ref', value: 'sha-002' },
      { kind: 'commit-ref' as const, label: 'commit-ref', value: 'sha-003' },
    ];
    const html = renderToStaticMarkup(
      createElement(BranchProvenancePanel, { entries, onClose: () => {} }),
    );
    const entryCount = (html.match(/data-testid="branch-provenance-entry"/g) ?? []).length;
    expect(entryCount).toBe(3);
    expect(html).toContain('sha-001');
    expect(html).toContain('sha-002');
    expect(html).toContain('sha-003');
  });
});
