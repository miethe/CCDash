/**
 * P4-004: Feature Modal Sessions Pagination UI
 *
 * Verifies the load-more sessions pagination UI. After the P4 boundary
 * extraction refactor:
 *   - Load-more button and partial-tree indicator live in
 *     components/FeatureModal/SessionsTab.tsx
 *   - Accumulator merge effect and tab-label expression remain in
 *     ProjectBoard.tsx (ProjectBoardFeatureModal)
 *
 * Testing strategy (no @testing-library/react):
 *   1. Source-level proofs — assert production source contains the load-more
 *      button, pagination state reads, and partial-tree indicators.
 *   2. Pagination state machine — simulate the sessionPagination state
 *      transitions to confirm button visibility/disabled logic matches source.
 *   3. Tab-label count proof — assert source uses serverTotal when available.
 *
 * What is NOT tested here:
 *   - Full React effect lifecycle (no jsdom / @testing-library/react configured)
 *   - Actual HTTP fetch (covered by useFeatureModalDataSessionsPagination.test.ts)
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

// ── Source files under test ───────────────────────────────────────────────────
// Load-more UI and partial-tree indicator were extracted to SessionsTab.tsx
// during the P4 planning/forensics boundary refactor.
const SESSIONS_TAB_PATH = path.resolve(
  __dirname,
  '../FeatureModal/SessionsTab.tsx',
);
const SESSIONS_TAB_SOURCE = fs.readFileSync(SESSIONS_TAB_PATH, 'utf-8');

// Accumulator merge effect and tab-label expression remain in ProjectBoard.tsx.
const SOURCE_PATH = path.resolve(__dirname, '../ProjectBoard.tsx');
const SOURCE = fs.readFileSync(SOURCE_PATH, 'utf-8');

// ── Source extraction helpers ─────────────────────────────────────────────────

/**
 * Returns the load-more UI block from SessionsTab.tsx.
 * Anchored on the section comment that wraps the pagination control.
 */
function getLoadMoreBlock(): string {
  const marker = '{/* ── Load-more pagination control';
  const idx = SESSIONS_TAB_SOURCE.indexOf(marker);
  if (idx === -1) return '';
  // Capture roughly 2000 chars after the marker — enough for the full button block.
  return SESSIONS_TAB_SOURCE.slice(idx, idx + 2000);
}

/**
 * Returns the partial-tree indicator block inside coreSessionGroups.map
 * from SessionsTab.tsx.
 */
function getPartialTreeBlock(): string {
  const marker = '{/* Partial-tree indicator when more pages are available */}';
  const idx = SESSIONS_TAB_SOURCE.indexOf(marker);
  if (idx === -1) return '';
  return SESSIONS_TAB_SOURCE.slice(idx, idx + 400);
}

/**
 * Returns the sessions tab-label expression from ProjectBoard.tsx.
 */
function getTabLabelBlock(): string {
  const marker = '// P4-004: prefer server-reported total';
  const idx = SOURCE.indexOf(marker);
  if (idx === -1) return '';
  return SOURCE.slice(idx, idx + 500);
}

/**
 * Returns the P4-004 accumulator merge effect block from ProjectBoard.tsx.
 */
function getAccumulatorEffectBlock(): string {
  const marker = '// P4-004: Adapt LinkedFeatureSessionDTO items from the paginated accumulator';
  const idx = SOURCE.indexOf(marker);
  if (idx === -1) return '';
  return SOURCE.slice(idx, idx + 2500);
}

// ── Load-more button source proofs ───────────────────────────────────────────

describe('P4-004 — Source-level: load-more button is present', () => {
  it('load-more pagination block exists in Sessions tab', () => {
    const block = getLoadMoreBlock();
    expect(block.length).toBeGreaterThan(0);
  });

  it('button renders only when hasMore is true', () => {
    const block = getLoadMoreBlock();
    // The button is inside a conditional that checks hasMore
    expect(block).toContain('hasMore');
    expect(block).toContain('<button');
    expect(block).toContain('Load more sessions');
  });

  it('button is disabled when isLoadingMore is true', () => {
    const block = getLoadMoreBlock();
    expect(block).toContain('isLoadingMore');
    expect(block).toContain('disabled={isLoadingMore}');
  });

  it('button click calls loadMoreSessions', () => {
    const block = getLoadMoreBlock();
    expect(block).toContain('loadMoreSessions');
  });

  it('spinner renders when isLoadingMore', () => {
    const block = getLoadMoreBlock();
    expect(block).toContain('animate-spin');
    expect(block).toContain('Loading');
  });

  it('"not yet loaded" count badge is rendered when serverTotal > loaded count', () => {
    const block = getLoadMoreBlock();
    expect(block).toContain('notYetLoaded');
    expect(block).toContain('not yet loaded');
  });
});

// ── Partial-tree indicator source proofs ─────────────────────────────────────

describe('P4-004 — Source-level: partial-tree indicator in session groups', () => {
  it('partial-tree indicator block exists inside coreSessionGroups.map', () => {
    const block = getPartialTreeBlock();
    expect(block.length).toBeGreaterThan(0);
  });

  it('partial-tree indicator checks sessionPagination.hasMore', () => {
    // After extraction, SessionsTab.tsx destructures hasMore from sessionPagination
    // at the top of the render scope, so the indicator block references {hasMore && ...}.
    // We verify the invariant in two steps:
    //   1. The file destructures hasMore from sessionPagination.
    //   2. The indicator block is gated on hasMore.
    expect(SESSIONS_TAB_SOURCE).toContain('hasMore, isLoadingMore, serverTotal } = sessionPagination');
    const block = getPartialTreeBlock();
    expect(block).toContain('{hasMore && (');
  });

  it('partial-tree indicator explains more sessions may appear in group', () => {
    const block = getPartialTreeBlock();
    expect(block).toContain('More sessions may appear in this group');
  });
});

// ── Tab-label count source proofs ─────────────────────────────────────────────

describe('P4-004 — Source-level: tab-label uses serverTotal', () => {
  it('sessions tab-label prefers serverTotal from sessionPagination', () => {
    const block = getTabLabelBlock();
    expect(block.length).toBeGreaterThan(0);
    expect(block).toContain('sessionPagination.serverTotal');
    expect(block).toContain('linkedSessions.length');
  });

  it('tab-label falls back to linkedSessions.length when serverTotal is 0', () => {
    const block = getTabLabelBlock();
    // The ternary pattern: serverTotal > 0 ? serverTotal : linkedSessions.length
    expect(block).toContain('serverTotal > 0');
  });
});

// ── Accumulator effect source proofs ─────────────────────────────────────────

describe('P4-004 — Source-level: accumulator merge effect', () => {
  it('merge effect exists in ProjectBoardFeatureModal', () => {
    const block = getAccumulatorEffectBlock();
    expect(block.length).toBeGreaterThan(0);
  });

  it('merge effect appends only items not already present by sessionId', () => {
    const block = getAccumulatorEffectBlock();
    expect(block).toContain('existingIds');
    expect(block).toContain('sessionId');
    expect(block).toContain('filter(dto => !existingIds.has(dto.sessionId))');
  });

  it('merge effect adapts LinkedFeatureSessionDTO fields to FeatureSessionLink', () => {
    const block = getAccumulatorEffectBlock();
    expect(block).toContain('workflowType');
    expect(block).toContain('isPrimaryLink');
    expect(block).toContain('isSubthread');
    expect(block).toContain('relatedTasks');
    expect(block).toContain('relatedPhases: Array.from');
  });

  it('prevAccumulatedCountRef is reset on feature change', () => {
    const resetMarker = '// P4-004: Reset pagination accumulator pointer on feature change.';
    const idx = SOURCE.indexOf(resetMarker);
    expect(idx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(idx, idx + 150);
    expect(snippet).toContain('prevAccumulatedCountRef.current = 0');
  });
});

describe('Feature modal sessions grouping inputs', () => {
  it('phase grouping considers related task phase metadata', () => {
    expect(SESSIONS_TAB_SOURCE).toContain('session.relatedTasks');
    expect(SESSIONS_TAB_SOURCE).toContain('task.phase || task.phaseId');
  });
});

// ── Button visibility logic (pure state machine) ─────────────────────────────

interface PaginationState {
  hasMore: boolean;
  isLoadingMore: boolean;
  serverTotal: number;
}

/**
 * Pure function mirroring the conditional block guarding the load-more UI:
 *   if (!hasMore && notYetLoaded <= 0) return null;
 */
function shouldShowLoadMoreUI(
  state: PaginationState,
  loadedCount: number,
): { show: boolean; buttonDisabled: boolean; showSpinner: boolean; notYetLoaded: number } {
  const notYetLoaded = state.serverTotal > 0 ? state.serverTotal - loadedCount : 0;
  if (!state.hasMore && notYetLoaded <= 0) {
    return { show: false, buttonDisabled: false, showSpinner: false, notYetLoaded: 0 };
  }
  return {
    show: true,
    buttonDisabled: state.isLoadingMore,
    showSpinner: state.isLoadingMore,
    notYetLoaded,
  };
}

describe('P4-004 — Button visibility state machine', () => {
  it('renders load-more button when hasMore=true', () => {
    const result = shouldShowLoadMoreUI(
      { hasMore: true, isLoadingMore: false, serverTotal: 5 },
      2,
    );
    expect(result.show).toBe(true);
    expect(result.buttonDisabled).toBe(false);
  });

  it('button disappears when hasMore=false and all loaded', () => {
    const result = shouldShowLoadMoreUI(
      { hasMore: false, isLoadingMore: false, serverTotal: 3 },
      3,
    );
    expect(result.show).toBe(false);
  });

  it('button is disabled during loadingMore', () => {
    const result = shouldShowLoadMoreUI(
      { hasMore: true, isLoadingMore: true, serverTotal: 5 },
      2,
    );
    expect(result.show).toBe(true);
    expect(result.buttonDisabled).toBe(true);
    expect(result.showSpinner).toBe(true);
  });

  it('spinner shown only when isLoadingMore=true', () => {
    const idle = shouldShowLoadMoreUI(
      { hasMore: true, isLoadingMore: false, serverTotal: 5 },
      2,
    );
    const loading = shouldShowLoadMoreUI(
      { hasMore: true, isLoadingMore: true, serverTotal: 5 },
      2,
    );
    expect(idle.showSpinner).toBe(false);
    expect(loading.showSpinner).toBe(true);
  });

  it('notYetLoaded count computed correctly', () => {
    const result = shouldShowLoadMoreUI(
      { hasMore: true, isLoadingMore: false, serverTotal: 10 },
      3,
    );
    expect(result.notYetLoaded).toBe(7);
  });

  it('notYetLoaded is 0 when serverTotal is 0 (unknown total)', () => {
    const result = shouldShowLoadMoreUI(
      { hasMore: true, isLoadingMore: false, serverTotal: 0 },
      2,
    );
    expect(result.notYetLoaded).toBe(0);
  });

  it('shows "not yet loaded" info even when hasMore=false but serverTotal > loaded', () => {
    // Edge: serverTotal>0 but hasMore=false means we know there are more but
    // the API says no further pages — surface shows a count info label.
    const result = shouldShowLoadMoreUI(
      { hasMore: false, isLoadingMore: false, serverTotal: 5 },
      3,
    );
    // show=true because notYetLoaded > 0
    expect(result.show).toBe(true);
    expect(result.notYetLoaded).toBe(2);
  });
});

// ── Tab-label count logic (pure) ──────────────────────────────────────────────

describe('P4-004 — Tab-label count logic', () => {
  function sessionTabLabel(serverTotal: number, loadedCount: number): string {
    return `Sessions (${serverTotal > 0 ? serverTotal : loadedCount})`;
  }

  it('uses serverTotal when > 0', () => {
    expect(sessionTabLabel(12, 4)).toBe('Sessions (12)');
  });

  it('falls back to loadedCount when serverTotal is 0', () => {
    expect(sessionTabLabel(0, 3)).toBe('Sessions (3)');
  });

  it('shows 0 when both are 0', () => {
    expect(sessionTabLabel(0, 0)).toBe('Sessions (0)');
  });
});
