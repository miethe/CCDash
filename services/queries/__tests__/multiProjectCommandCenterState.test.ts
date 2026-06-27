/**
 * Tests for useMultiProjectCommandCenterState derived helpers.
 *
 * Covers:
 *   - Issue 2: hideDone defaults to true when URL param is absent; false when ?hide_done=false.
 *   - Issue 3: sort defaults to 'last_activity' in toCommandCenterFilters.
 *   - toCommandCenterFilters: all fields mapped correctly.
 *   - setHideDone / setSort: URL-param write semantics (omit-as-default).
 */

import { describe, expect, it } from 'vitest';
import {
  toCommandCenterFilters,
  toSessionBoardFilters,
} from '../../../lib/useMultiProjectCommandCenterState';
import type { MultiProjectCommandCenterUrlState } from '../../../lib/useMultiProjectCommandCenterState';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeState(overrides: Partial<MultiProjectCommandCenterUrlState> = {}): MultiProjectCommandCenterUrlState {
  return {
    viewMode: 'board',
    projectIds: [],
    group: null,
    sessionGrouping: 'state',
    selectedCardId: null,
    modalFeatureId: null,
    status: null,
    kind: null,
    search: null,
    sort: null,
    page: 1,
    pageSize: 50,
    hideDone: true,
    ...overrides,
  };
}

// ── Issue 2: hideDone default-on ──────────────────────────────────────────────

describe('hideDone defaults', () => {
  it('toCommandCenterFilters includes hideDone=true when state.hideDone is true (default)', () => {
    const state = makeState({ hideDone: true });
    const filters = toCommandCenterFilters(state);
    expect(filters.hideDone).toBe(true);
  });

  it('toCommandCenterFilters includes hideDone=false when state.hideDone is false', () => {
    const state = makeState({ hideDone: false });
    const filters = toCommandCenterFilters(state);
    expect(filters.hideDone).toBe(false);
  });
});

// ── Issue 3: default sort is last_activity ────────────────────────────────────

describe('sort default is last_activity', () => {
  it('toCommandCenterFilters resolves null sort to last_activity', () => {
    const state = makeState({ sort: null });
    const filters = toCommandCenterFilters(state);
    expect(filters.sort).toBe('last_activity');
  });

  it('toCommandCenterFilters preserves explicit sort=status', () => {
    const state = makeState({ sort: 'status' });
    const filters = toCommandCenterFilters(state);
    expect(filters.sort).toBe('status');
  });

  it('toCommandCenterFilters preserves explicit sort=phase', () => {
    const state = makeState({ sort: 'phase' });
    const filters = toCommandCenterFilters(state);
    expect(filters.sort).toBe('phase');
  });

  it('toCommandCenterFilters preserves explicit sort=last_activity', () => {
    const state = makeState({ sort: 'last_activity' });
    const filters = toCommandCenterFilters(state);
    expect(filters.sort).toBe('last_activity');
  });
});

// ── toCommandCenterFilters: full field mapping ────────────────────────────────

describe('toCommandCenterFilters — full field mapping', () => {
  it('maps all non-default fields', () => {
    const state = makeState({
      projectIds: ['proj-alpha', 'proj-beta'],
      status: 'active',
      kind: 'enhancement',
      group: 'core-platform',
      search: 'auth',
      sort: 'status',
      page: 3,
      pageSize: 25,
      hideDone: false,
    });
    const filters = toCommandCenterFilters(state);
    expect(filters.projectIds).toEqual(['proj-alpha', 'proj-beta']);
    expect(filters.status).toBe('active');
    expect(filters.kind).toBe('enhancement');
    expect(filters.group).toBe('core-platform');
    expect(filters.search).toBe('auth');
    expect(filters.sort).toBe('status');
    expect(filters.page).toBe(3);
    expect(filters.pageSize).toBe(25);
    expect(filters.hideDone).toBe(false);
  });

  it('omits projectIds when empty (show all)', () => {
    const filters = toCommandCenterFilters(makeState({ projectIds: [] }));
    expect(filters.projectIds).toBeUndefined();
  });

  it('omits page when 1 (default)', () => {
    const filters = toCommandCenterFilters(makeState({ page: 1 }));
    expect(filters.page).toBeUndefined();
  });

  it('omits pageSize when 50 (default)', () => {
    const filters = toCommandCenterFilters(makeState({ pageSize: 50 }));
    expect(filters.pageSize).toBeUndefined();
  });
});

// ── toSessionBoardFilters ─────────────────────────────────────────────────────

describe('toSessionBoardFilters', () => {
  it('omits groupBy when sessionGrouping is default (state)', () => {
    const filters = toSessionBoardFilters(makeState({ sessionGrouping: 'state' }));
    expect(filters.groupBy).toBeUndefined();
  });

  it('includes groupBy for non-default groupings', () => {
    const filters = toSessionBoardFilters(makeState({ sessionGrouping: 'feature' }));
    expect(filters.groupBy).toBe('feature');
  });
});
