/**
 * P4-006: Feature Modal Live Refresh Policy
 *
 * Verifies that the live-refresh policy implemented in ProjectBoardFeatureModal
 * correctly handles invalidation events and polling ticks according to the
 * rules defined by P4-006:
 *
 *   ACTIVE tab     → refresh immediately (call the legacy refresh fn).
 *   INACTIVE tab, status 'success'|'stale' → markStale(section) only — no fetch.
 *   INACTIVE tab, status 'idle'|'loading'|'error' → no-op (do not pre-fetch).
 *
 * Testing strategy (mirrors the P4-003 test approach):
 *  1. Source-level proofs — assert the production source contains the P4-006
 *     comment block and the applyLiveRefreshPolicy helper, and that the old
 *     unconditional refresh calls are replaced by the new policy calls.
 *  2. Pure applyLiveRefreshPolicy logic — the policy function is simulated
 *     inline to cover all (activeTab × sectionStatus) combinations without
 *     needing a DOM environment.
 *  3. Invalidation event orchestration — simulates the full onInvalidate
 *     call tree and asserts call counts for refresh functions and markStale.
 *  4. Polling loop orchestration — mirrors the setInterval body assertions.
 *
 * What is NOT tested here:
 *  - Full React effect lifecycle (no jsdom / @testing-library/react configured)
 *  - Live WebSocket/SSE transport (covered by live.test.ts and E2E)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

import type { SectionStatus, ModalTabId } from '../../services/useFeatureModalData';

// ── Source file under test ─────────────────────────────────────────────────────
const SOURCE_PATH = path.resolve(__dirname, '../ProjectBoard.tsx');
const SOURCE = fs.readFileSync(SOURCE_PATH, 'utf-8');

// ────────────────────────────────────────────────────────────────────────────────
// 1. SOURCE-LEVEL PROOFS
// ────────────────────────────────────────────────────────────────────────────────

describe('P4-006 — Source-level: policy comment block is present', () => {
  it('contains the P4-006 policy heading comment', () => {
    expect(SOURCE).toContain('// ── P4-006: Live-refresh policy');
  });

  it('documents the three policy branches (ACTIVE, INACTIVE loaded, INACTIVE idle)', () => {
    expect(SOURCE).toContain('ACTIVE tab');
    expect(SOURCE).toContain("INACTIVE tab, section.status === 'success' | 'stale'");
    expect(SOURCE).toContain("INACTIVE tab, section.status === 'idle' | 'loading' | 'error'");
  });

  it('documents that overview shell always refreshes', () => {
    expect(SOURCE).toContain('Overview shell always refreshes');
  });
});

describe('P4-006 — Source-level: applyLiveRefreshPolicy helper is defined', () => {
  it('defines the applyLiveRefreshPolicy useCallback', () => {
    expect(SOURCE).toContain('const applyLiveRefreshPolicy = useCallback(');
  });

  it('checks isActive via activeTab === section', () => {
    const idx = SOURCE.indexOf('const applyLiveRefreshPolicy = useCallback(');
    expect(idx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(idx, idx + 800);
    expect(snippet).toContain('const isActive = activeTab === section');
  });

  it("marks stale for 'success' or 'stale' status on inactive tab", () => {
    const idx = SOURCE.indexOf('const applyLiveRefreshPolicy = useCallback(');
    const snippet = SOURCE.slice(idx, idx + 800);
    expect(snippet).toContain("sectionStatus === 'success' || sectionStatus === 'stale'");
    expect(snippet).toContain('modalSections.markStale(section)');
  });

  it('returns Promise.resolve() for idle/loading/error inactive tabs (no-op)', () => {
    const idx = SOURCE.indexOf('const applyLiveRefreshPolicy = useCallback(');
    const snippet = SOURCE.slice(idx, idx + 800);
    // The no-op path falls through to the final Promise.resolve()
    expect(snippet).toContain("// 'idle' | 'loading' | 'error' → no-op");
    expect(snippet).toContain('return Promise.resolve()');
  });

  it('includes [activeTab, modalSections] in useCallback dependency array', () => {
    const idx = SOURCE.indexOf('const applyLiveRefreshPolicy = useCallback(');
    const snippet = SOURCE.slice(idx, idx + 900);
    expect(snippet).toContain('[activeTab, modalSections]');
  });
});

describe('P4-006 — Source-level: onInvalidate uses applyLiveRefreshPolicy', () => {
  it('onInvalidate calls applyLiveRefreshPolicy for sessions', () => {
    const idx = SOURCE.indexOf('onInvalidate: async () => {');
    expect(idx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(idx, idx + 1200);
    expect(snippet).toContain("applyLiveRefreshPolicy(");
    expect(snippet).toContain("'sessions'");
  });

  it('onInvalidate calls applyLiveRefreshPolicy for test-status', () => {
    const idx = SOURCE.indexOf('onInvalidate: async () => {');
    // The test-status applyLiveRefreshPolicy call is the last section in the
    // Promise.all, so we need a larger window (~2000 chars).
    const snippet = SOURCE.slice(idx, idx + 2000);
    expect(snippet).toContain("'test-status'");
  });

  it('onInvalidate always calls refreshFeatureDetail (overview shell)', () => {
    const idx = SOURCE.indexOf('onInvalidate: async () => {');
    const snippet = SOURCE.slice(idx, idx + 1200);
    expect(snippet).toContain('refreshFeatureDetail()');
  });

  it('old unconditional refreshLinkedSessions guard is replaced by applyLiveRefreshPolicy', () => {
    // The OLD pattern was a bare ternary check. The new pattern wraps inside
    // applyLiveRefreshPolicy. The old guard comment should no longer appear in
    // the onInvalidate block.
    const idx = SOURCE.indexOf('onInvalidate: async () => {');
    const endIdx = SOURCE.indexOf('});', idx);
    const snippet = SOURCE.slice(idx, endIdx + 3);
    // Old P4-003 guard comment inside onInvalidate should be gone
    expect(snippet).not.toContain('// P4-003: only refresh sessions if they have been loaded at least once.');
  });
});

describe('P4-006 — Source-level: polling loop uses applyLiveRefreshPolicy', () => {
  it('setInterval body calls applyLiveRefreshPolicy for sessions', () => {
    const idx = SOURCE.indexOf('const interval = setInterval(() => {');
    expect(idx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(idx, idx + 1000);
    expect(snippet).toContain("applyLiveRefreshPolicy(");
    expect(snippet).toContain("'sessions'");
  });

  it('setInterval body always calls refreshFeatureDetail', () => {
    const idx = SOURCE.indexOf('const interval = setInterval(() => {');
    const snippet = SOURCE.slice(idx, idx + 1000);
    expect(snippet).toContain('refreshFeatureDetail()');
  });

  it('old unconditional sessionsFetchedRef.current guard inside polling is replaced', () => {
    const idx = SOURCE.indexOf('const interval = setInterval(() => {');
    const endIdx = SOURCE.indexOf('}, FEATURE_MODAL_POLL_INTERVAL_MS)', idx);
    const snippet = SOURCE.slice(idx, endIdx + 30);
    // Old direct guard pattern should be gone from polling body
    expect(snippet).not.toContain('// P4-003: only poll sessions if they have been loaded at least once.');
  });

  it('applyLiveRefreshPolicy is listed in the polling useEffect dep array', () => {
    const idx = SOURCE.indexOf('const interval = setInterval(() => {');
    // Dep array follows the return () => clearInterval(...) line
    const snippet = SOURCE.slice(idx, idx + 1200);
    expect(snippet).toContain('applyLiveRefreshPolicy');
    // Ensure it appears in the dep array bracket
    const depIdx = snippet.lastIndexOf('[activeTab');
    expect(depIdx).toBeGreaterThan(-1);
    const depSnippet = snippet.slice(depIdx, depIdx + 200);
    expect(depSnippet).toContain('applyLiveRefreshPolicy');
  });
});

// ────────────────────────────────────────────────────────────────────────────────
// 2. PURE POLICY LOGIC — applyLiveRefreshPolicy simulation
// ────────────────────────────────────────────────────────────────────────────────

/**
 * Simulates applyLiveRefreshPolicy from ProjectBoardFeatureModal inline.
 * Mirrors the production logic exactly:
 *
 *   const isActive = activeTab === section;
 *   const sectionStatus = modalSections[section].status;
 *   if (isActive) return refreshFn();
 *   if (sectionStatus === 'success' || sectionStatus === 'stale') {
 *     markStale(section);
 *   }
 *   return Promise.resolve();
 */
function simulateApplyLiveRefreshPolicy(
  activeTab: string,
  section: Exclude<ModalTabId, 'overview'>,
  sectionStatus: SectionStatus,
  refreshFn: AnyFn,
  markStale: AnyFn,
): Promise<void> {
  const isActive = activeTab === section;

  if (isActive) {
    return (refreshFn as () => Promise<void>)();
  }

  if (sectionStatus === 'success' || sectionStatus === 'stale') {
    (markStale as (s: ModalTabId) => void)(section);
  }
  return Promise.resolve();
}

describe('P4-006 — Policy logic: active tab triggers immediate refresh', () => {
  it('active sessions tab calls refreshFn immediately', async () => {
    const refreshFn = vi.fn().mockResolvedValue(undefined);
    const markStale = vi.fn();

    await simulateApplyLiveRefreshPolicy('sessions', 'sessions', 'success', refreshFn, markStale);

    expect(refreshFn).toHaveBeenCalledTimes(1);
    expect(markStale).not.toHaveBeenCalled();
  });

  it('active phases tab calls refreshFn immediately', async () => {
    const refreshFn = vi.fn().mockResolvedValue(undefined);
    const markStale = vi.fn();

    await simulateApplyLiveRefreshPolicy('phases', 'phases', 'idle', refreshFn, markStale);

    expect(refreshFn).toHaveBeenCalledTimes(1);
    expect(markStale).not.toHaveBeenCalled();
  });

  it('active test-status tab calls refreshFn even if status is idle', async () => {
    const refreshFn = vi.fn().mockResolvedValue(undefined);
    const markStale = vi.fn();

    await simulateApplyLiveRefreshPolicy('test-status', 'test-status', 'idle', refreshFn, markStale);

    expect(refreshFn).toHaveBeenCalledTimes(1);
    expect(markStale).not.toHaveBeenCalled();
  });
});

describe('P4-006 — Policy logic: inactive loaded tab marked stale (no fetch)', () => {
  const INACTIVE_LOADED_CASES: Array<[string, SectionStatus]> = [
    ['sessions', 'success'],
    ['sessions', 'stale'],
    ['phases', 'success'],
    ['history', 'stale'],
    ['docs', 'success'],
    ['relations', 'success'],
    ['test-status', 'stale'],
  ];

  for (const [section, status] of INACTIVE_LOADED_CASES) {
    it(`inactive '${section}' tab with status '${status}' marks stale without fetching`, async () => {
      const refreshFn = vi.fn().mockResolvedValue(undefined);
      const markStale = vi.fn();

      await simulateApplyLiveRefreshPolicy(
        'overview', // active tab is overview — all others are inactive
        section as Exclude<ModalTabId, 'overview'>,
        status,
        refreshFn,
        markStale,
      );

      expect(refreshFn).not.toHaveBeenCalled();
      expect(markStale).toHaveBeenCalledTimes(1);
      expect(markStale).toHaveBeenCalledWith(section);
    });
  }
});

describe('P4-006 — Policy logic: inactive unloaded tab is a no-op', () => {
  const INACTIVE_UNLOADED_CASES: Array<[string, SectionStatus]> = [
    ['sessions', 'idle'],
    ['phases', 'idle'],
    ['history', 'idle'],
    ['docs', 'idle'],
    ['relations', 'idle'],
    ['test-status', 'idle'],
    ['sessions', 'loading'],
    ['phases', 'error'],
  ];

  for (const [section, status] of INACTIVE_UNLOADED_CASES) {
    it(`inactive '${section}' tab with status '${status}' does nothing`, async () => {
      const refreshFn = vi.fn().mockResolvedValue(undefined);
      const markStale = vi.fn();

      await simulateApplyLiveRefreshPolicy(
        'overview',
        section as Exclude<ModalTabId, 'overview'>,
        status,
        refreshFn,
        markStale,
      );

      expect(refreshFn).not.toHaveBeenCalled();
      expect(markStale).not.toHaveBeenCalled();
    });
  }
});

// ────────────────────────────────────────────────────────────────────────────────
// 3. INVALIDATION EVENT ORCHESTRATION
// ────────────────────────────────────────────────────────────────────────────────

/**
 * Simulates the onInvalidate Promise.all call in ProjectBoardFeatureModal for a
 * given active tab and a map of section statuses.
 *
 * Returns an object summarising which refresh functions were called and which
 * sections were marked stale so tests can assert intent without rendering.
 */
// Typed callable aliases for vi.fn() mocks.  Using Function is intentional:
// vi.fn() returns Mock<Procedure|Constructable> which is not directly assignable
// to stricter function signatures; Function is the common supertype that TS accepts.
// eslint-disable-next-line @typescript-eslint/ban-types
type AnyFn = Function;

async function simulateOnInvalidate(
  activeTab: string,
  sectionStatuses: Record<Exclude<ModalTabId, 'overview'>, SectionStatus>,
  sessionsFetchedRef: { current: boolean },
  refreshFeatureDetail: AnyFn,
  refreshLinkedSessions: AnyFn,
  refreshFeatureTestHealth: AnyFn,
  markStale: AnyFn,
): Promise<void> {
  const applyPolicy = (
    section: Exclude<ModalTabId, 'overview'>,
    refreshFn: AnyFn,
  ) =>
    simulateApplyLiveRefreshPolicy(
      activeTab,
      section,
      sectionStatuses[section],
      refreshFn,
      markStale,
    );

  await Promise.all([
    (refreshFeatureDetail as () => Promise<void>)(), // overview — always
    applyPolicy('phases', () => Promise.resolve()),
    applyPolicy(
      'sessions',
      () => (sessionsFetchedRef.current ? (refreshLinkedSessions as () => Promise<void>)() : Promise.resolve()),
    ),
    applyPolicy('docs', () => Promise.resolve()),
    applyPolicy('relations', () => Promise.resolve()),
    applyPolicy('history', () => Promise.resolve()),
    applyPolicy('test-status', () => (refreshFeatureTestHealth as () => Promise<void>)()),
  ]);
}

const DEFAULT_STATUSES: Record<Exclude<ModalTabId, 'overview'>, SectionStatus> = {
  phases: 'idle',
  docs: 'idle',
  relations: 'idle',
  sessions: 'idle',
  'test-status': 'idle',
  history: 'idle',
};

describe('P4-006 — Invalidation orchestration: active tab refetches', () => {
  let refreshFeatureDetail: ReturnType<typeof vi.fn>;
  let refreshLinkedSessions: ReturnType<typeof vi.fn>;
  let refreshFeatureTestHealth: ReturnType<typeof vi.fn>;
  let markStale: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    refreshFeatureDetail = vi.fn().mockResolvedValue(undefined);
    refreshLinkedSessions = vi.fn().mockResolvedValue(undefined);
    refreshFeatureTestHealth = vi.fn().mockResolvedValue(undefined);
    markStale = vi.fn();
  });

  it('active sessions tab — refreshLinkedSessions is called when sessionsFetched=true', async () => {
    const statuses: Record<Exclude<ModalTabId, 'overview'>, SectionStatus> = {
      ...DEFAULT_STATUSES,
      sessions: 'success',
    };

    await simulateOnInvalidate(
      'sessions',
      statuses,
      { current: true },
      refreshFeatureDetail,
      refreshLinkedSessions,
      refreshFeatureTestHealth,
      markStale,
    );

    expect(refreshLinkedSessions).toHaveBeenCalledTimes(1);
    expect(markStale).not.toHaveBeenCalledWith('sessions');
  });

  it('active sessions tab — refreshLinkedSessions NOT called when sessionsFetched=false', async () => {
    const statuses: Record<Exclude<ModalTabId, 'overview'>, SectionStatus> = {
      ...DEFAULT_STATUSES,
      sessions: 'idle',
    };

    await simulateOnInvalidate(
      'sessions',
      statuses,
      { current: false },
      refreshFeatureDetail,
      refreshLinkedSessions,
      refreshFeatureTestHealth,
      markStale,
    );

    // sessions is active but sessionsFetchedRef is false → guard blocks the fetch
    expect(refreshLinkedSessions).not.toHaveBeenCalled();
    expect(markStale).not.toHaveBeenCalled();
  });

  it('active test-status tab — refreshFeatureTestHealth is called', async () => {
    const statuses: Record<Exclude<ModalTabId, 'overview'>, SectionStatus> = {
      ...DEFAULT_STATUSES,
      'test-status': 'success',
    };

    await simulateOnInvalidate(
      'test-status',
      statuses,
      { current: false },
      refreshFeatureDetail,
      refreshLinkedSessions,
      refreshFeatureTestHealth,
      markStale,
    );

    expect(refreshFeatureTestHealth).toHaveBeenCalledTimes(1);
  });

  it('overview tab active — no heavy section refresh fn is called', async () => {
    await simulateOnInvalidate(
      'overview',
      DEFAULT_STATUSES, // all idle
      { current: false },
      refreshFeatureDetail,
      refreshLinkedSessions,
      refreshFeatureTestHealth,
      markStale,
    );

    expect(refreshLinkedSessions).not.toHaveBeenCalled();
    expect(refreshFeatureTestHealth).not.toHaveBeenCalled();
    expect(markStale).not.toHaveBeenCalled();
  });
});

describe('P4-006 — Invalidation orchestration: inactive loaded tabs become stale (no fetch)', () => {
  let refreshFeatureDetail: ReturnType<typeof vi.fn>;
  let refreshLinkedSessions: ReturnType<typeof vi.fn>;
  let refreshFeatureTestHealth: ReturnType<typeof vi.fn>;
  let markStale: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    refreshFeatureDetail = vi.fn().mockResolvedValue(undefined);
    refreshLinkedSessions = vi.fn().mockResolvedValue(undefined);
    refreshFeatureTestHealth = vi.fn().mockResolvedValue(undefined);
    markStale = vi.fn();
  });

  it('invalidation on overview tab marks all success sections stale without fetching', async () => {
    const statuses: Record<Exclude<ModalTabId, 'overview'>, SectionStatus> = {
      phases: 'success',
      docs: 'success',
      relations: 'stale',
      sessions: 'success',
      'test-status': 'success',
      history: 'stale',
    };

    await simulateOnInvalidate(
      'overview',
      statuses,
      { current: true }, // sessions loaded — but inactive so should not refetch
      refreshFeatureDetail,
      refreshLinkedSessions,
      refreshFeatureTestHealth,
      markStale,
    );

    // No heavy refresh should fire — all tabs are inactive
    expect(refreshLinkedSessions).not.toHaveBeenCalled();
    expect(refreshFeatureTestHealth).not.toHaveBeenCalled();

    // All 'success'/'stale' sections should be marked stale
    const markedSections = markStale.mock.calls.map(c => c[0]);
    expect(markedSections).toContain('phases');
    expect(markedSections).toContain('docs');
    expect(markedSections).toContain('relations');
    expect(markedSections).toContain('sessions');
    expect(markedSections).toContain('test-status');
    expect(markedSections).toContain('history');
  });

  it('invalidation on phases tab does NOT mark phases stale (phases is active)', async () => {
    const statuses: Record<Exclude<ModalTabId, 'overview'>, SectionStatus> = {
      phases: 'success',
      docs: 'success',
      relations: 'idle',
      sessions: 'success',
      'test-status': 'idle',
      history: 'idle',
    };

    await simulateOnInvalidate(
      'phases',
      statuses,
      { current: true },
      refreshFeatureDetail,
      refreshLinkedSessions,
      refreshFeatureTestHealth,
      markStale,
    );

    const markedSections = markStale.mock.calls.map(c => c[0]);
    // phases is the ACTIVE tab — should NOT be marked stale
    expect(markedSections).not.toContain('phases');
    // sessions is inactive and loaded — should be marked stale
    expect(markedSections).toContain('sessions');
    // docs is inactive and loaded — should be marked stale
    expect(markedSections).toContain('docs');
    // relations is idle — should NOT be marked stale
    expect(markedSections).not.toContain('relations');
  });
});

describe('P4-006 — Invalidation orchestration: inactive idle tabs stay idle', () => {
  it('all-idle sections with overview active → no fetches, no stale marks', async () => {
    const refreshFeatureDetail = vi.fn().mockResolvedValue(undefined) as unknown as () => Promise<void>;
    const refreshLinkedSessions = vi.fn().mockResolvedValue(undefined) as unknown as () => Promise<void>;
    const refreshFeatureTestHealth = vi.fn().mockResolvedValue(undefined) as unknown as () => Promise<void>;
    const markStale = vi.fn() as unknown as (s: ModalTabId) => void;

    await simulateOnInvalidate(
      'overview',
      DEFAULT_STATUSES, // all idle
      { current: false },
      refreshFeatureDetail,
      refreshLinkedSessions,
      refreshFeatureTestHealth,
      markStale,
    );

    expect(refreshLinkedSessions).not.toHaveBeenCalled();
    expect(refreshFeatureTestHealth).not.toHaveBeenCalled();
    expect(markStale).not.toHaveBeenCalled();
    // overview shell always refreshes
    expect(refreshFeatureDetail).toHaveBeenCalledTimes(1);
  });
});
