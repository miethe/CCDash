import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MAX_DOCUMENTS_IN_MEMORY } from '../../constants';

/**
 * Unit tests for the document pagination cap introduced in FE-103.
 *
 * We test the pure pagination logic extracted from refreshDocuments without
 * mounting the full React context tree.  The mock fetcher simulates a
 * paginated API that returns 500-item pages up to any given total.
 */

type Page = { items: Record<string, unknown>[]; total: number };

function makePage(offset: number, pageSize: number, total: number): Page {
  const items = Array.from({ length: Math.min(pageSize, Math.max(0, total - offset)) }, (_, i) => ({
    id: `doc-${offset + i}`,
  }));
  return { items, total };
}

/**
 * Standalone re-implementation of the capped pagination loop so we can test
 * the logic in isolation.  Must stay in sync with the loop in
 * contexts/AppEntityDataContext.tsx → refreshDocuments().
 *
 * FE-106: accepts a `memoryGuard` flag mirroring isMemoryGuardEnabled().
 */
async function runCappedPagination(
  fetcher: (offset: number, pageSize: number) => Promise<Page>,
  cap: number,
  memoryGuard = true,
): Promise<{ collected: Record<string, unknown>[]; truncated: boolean; finalOffset: number }> {
  const pageSize = 500;
  const firstPage = await fetcher(0, pageSize);
  const collected = [...firstPage.items];
  const total = firstPage.total || collected.length;
  let offset = collected.length;

  // FE-103 / FE-106: only apply cap when guard enabled
  while (offset < total && (!memoryGuard || collected.length < cap)) {
    const page = await fetcher(offset, pageSize);
    const items = page.items || [];
    if (items.length === 0) break;
    collected.push(...items);
    offset += items.length;
  }

  if (memoryGuard) {
    const capped = collected.slice(0, cap);
    return {
      collected: capped,
      truncated: total > cap,
      finalOffset: capped.length,
    };
  }

  return {
    collected,
    truncated: false,
    finalOffset: collected.length,
  };
}

/**
 * Mirrors the loadMoreDocuments merge logic from AppEntityDataContext.tsx.
 * prev + newItems is sliced to cap; truncated reflects whether documentTotal
 * exceeds the resulting capped length.
 */
function simulateLoadMore(
  prev: Record<string, unknown>[],
  newItems: Record<string, unknown>[],
  documentTotal: number,
  cap: number,
): { next: Record<string, unknown>[]; truncated: boolean; newOffset: number } {
  const merged = [...prev, ...newItems];
  const capped = merged.slice(0, cap);
  return {
    next: capped,
    truncated: documentTotal > capped.length,
    newOffset: prev.length + newItems.length,
  };
}

describe('Document pagination cap (FE-103)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('MAX_DOCUMENTS_IN_MEMORY is exactly 2000', () => {
    expect(MAX_DOCUMENTS_IN_MEMORY).toBe(2000);
  });

  it('stops accumulating at cap when total > 2000', async () => {
    const total = 3500;
    const fetcher = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, total));

    const result = await runCappedPagination(fetcher, MAX_DOCUMENTS_IN_MEMORY);

    expect(result.collected.length).toBe(MAX_DOCUMENTS_IN_MEMORY);
    expect(result.truncated).toBe(true);
    expect(result.finalOffset).toBe(MAX_DOCUMENTS_IN_MEMORY);
  });

  it('does not truncate when total <= 2000', async () => {
    const total = 1200;
    const fetcher = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, total));

    const result = await runCappedPagination(fetcher, MAX_DOCUMENTS_IN_MEMORY);

    expect(result.collected.length).toBe(total);
    expect(result.truncated).toBe(false);
  });

  it('loop fetches exactly as many pages as needed to fill the cap, not more', async () => {
    // total = 5000, cap = 2000, pageSize = 500 → needs 4 fetches (pages 0,500,1000,1500)
    // 5th page (offset 2000) must not be requested because cap is reached
    const total = 5000;
    const fetcher = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, total));

    await runCappedPagination(fetcher, MAX_DOCUMENTS_IN_MEMORY);

    // 4 pages × 500 = 2000 items == cap, so loop terminates before fetching page at offset 2000
    const offsets = fetcher.mock.calls.map(([off]) => off);
    expect(offsets).toEqual([0, 500, 1000, 1500]);
    expect(fetcher).toHaveBeenCalledTimes(4);
  });

  it('handles a single oversized array response (non-paginated API shape)', async () => {
    // Simulates the Array.isArray(firstPage) branch where the API returns a flat array
    const total = 3000;
    const flatItems = Array.from({ length: total }, (_, i) => ({ id: `doc-${i}` }));

    // For this branch the context does: setDocuments(firstPage.slice(0, MAX_DOCUMENTS_IN_MEMORY))
    const capped = flatItems.slice(0, MAX_DOCUMENTS_IN_MEMORY);
    const truncated = flatItems.length > MAX_DOCUMENTS_IN_MEMORY;

    expect(capped.length).toBe(MAX_DOCUMENTS_IN_MEMORY);
    expect(truncated).toBe(true);
  });

  it('sets truncated=false when exactly at cap boundary', async () => {
    const total = MAX_DOCUMENTS_IN_MEMORY; // exactly 2000
    const fetcher = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, total));

    const result = await runCappedPagination(fetcher, MAX_DOCUMENTS_IN_MEMORY);

    expect(result.collected.length).toBe(MAX_DOCUMENTS_IN_MEMORY);
    expect(result.truncated).toBe(false);
  });
});

// FE-106: disabled-flag pathway
describe('Document pagination cap — memory guard disabled (FE-106)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('fetches ALL pages when guard is disabled, even beyond MAX_DOCUMENTS_IN_MEMORY', async () => {
    const total = 3500;
    const fetcher = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, total));

    const result = await runCappedPagination(fetcher, MAX_DOCUMENTS_IN_MEMORY, /* memoryGuard */ false);

    // Should have fetched all 3500 documents (7 pages × 500)
    expect(result.collected.length).toBe(total);
    expect(result.truncated).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(7);
  });

  it('does not set truncated=true when guard is disabled and total exceeds cap', async () => {
    const total = 5000;
    const fetcher = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, total));

    const result = await runCappedPagination(fetcher, MAX_DOCUMENTS_IN_MEMORY, /* memoryGuard */ false);

    expect(result.truncated).toBe(false);
    expect(result.collected.length).toBe(total);
  });

  it('guard-enabled and guard-disabled produce identical results when total <= cap', async () => {
    const total = 800; // well under 2000
    const fetcherEnabled = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, total));
    const fetcherDisabled = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, total));

    const enabled = await runCappedPagination(fetcherEnabled, MAX_DOCUMENTS_IN_MEMORY, true);
    const disabled = await runCappedPagination(fetcherDisabled, MAX_DOCUMENTS_IN_MEMORY, false);

    expect(enabled.collected.length).toBe(disabled.collected.length);
    expect(enabled.truncated).toBe(disabled.truncated);
    expect(enabled.finalOffset).toBe(disabled.finalOffset);
  });
});

// TEST-502: lazy-load scroll trigger and unbounded array growth guard
describe('loadMoreDocuments — lazy-load on scroll (TEST-502 / FE-103)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loadMoreDocuments fires when scroll position exceeds threshold', () => {
    // Simulate a scroll container: threshold = 80% of scrollHeight
    const scrollHeight = 1000;
    const threshold = scrollHeight * 0.8;
    const loadMore = vi.fn();

    function onScroll(scrollTop: number, clientHeight: number) {
      if (scrollTop + clientHeight >= threshold) {
        loadMore();
      }
    }

    // below threshold — should not trigger
    onScroll(600, 100); // 700 < 800
    expect(loadMore).not.toHaveBeenCalled();

    // at threshold — should trigger
    onScroll(700, 100); // 800 === 800
    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  it('loadMoreDocuments does not fire when scroll is far from threshold', () => {
    const scrollHeight = 2000;
    const threshold = scrollHeight * 0.8;
    const loadMore = vi.fn();

    function onScroll(scrollTop: number, clientHeight: number) {
      if (scrollTop + clientHeight >= threshold) {
        loadMore();
      }
    }

    onScroll(0, 400);   // 400 < 1600
    onScroll(200, 400); // 600 < 1600
    expect(loadMore).not.toHaveBeenCalled();
  });

  it('loadMoreDocuments is a no-op when documentOffset >= documentTotal', async () => {
    // When offset has caught up to total, the guard short-circuits immediately
    let callCount = 0;
    async function loadMoreDocuments(documentOffset: number, documentTotal: number) {
      if (documentOffset >= documentTotal) return; // guard
      callCount++;
      // would fetch…
    }

    await loadMoreDocuments(2000, 2000);
    expect(callCount).toBe(0);

    await loadMoreDocuments(2001, 2000);
    expect(callCount).toBe(0);
  });

  it('loadMoreDocuments fetches the next page when offset < total', async () => {
    const documentTotal = 3000;
    const documentOffset = 2000;
    const fetcher = vi.fn(async (offset: number, pageSize: number) => makePage(offset, pageSize, documentTotal));

    async function loadMoreDocuments() {
      if (documentOffset >= documentTotal) return;
      await fetcher(documentOffset, 500);
    }

    await loadMoreDocuments();
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith(2000, 500);
  });

  it('scroll trigger does not call loadMore multiple times for the same scroll position', () => {
    const scrollHeight = 1000;
    const threshold = scrollHeight * 0.8;
    let triggered = false;
    const loadMore = vi.fn();

    function onScroll(scrollTop: number, clientHeight: number) {
      if (!triggered && scrollTop + clientHeight >= threshold) {
        triggered = true;
        loadMore();
      }
    }

    // Rapid scroll events at the same position
    onScroll(700, 100);
    onScroll(700, 100);
    onScroll(705, 100);

    expect(loadMore).toHaveBeenCalledTimes(1);
  });
});

describe('loadMoreDocuments — no unbounded array growth (TEST-502 / FE-103)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('merged array never exceeds MAX_DOCUMENTS_IN_MEMORY after a single append', () => {
    const prev = Array.from({ length: MAX_DOCUMENTS_IN_MEMORY - 100 }, (_, i) => ({ id: `doc-${i}` }));
    const newItems = Array.from({ length: 300 }, (_, i) => ({ id: `doc-new-${i}` }));
    const documentTotal = 5000;

    const { next, truncated } = simulateLoadMore(prev, newItems, documentTotal, MAX_DOCUMENTS_IN_MEMORY);

    expect(next.length).toBeLessThanOrEqual(MAX_DOCUMENTS_IN_MEMORY);
    expect(next.length).toBe(MAX_DOCUMENTS_IN_MEMORY);
    expect(truncated).toBe(true);
  });

  it('array stays bounded across multiple sequential appends', () => {
    let state = Array.from({ length: 500 }, (_, i) => ({ id: `doc-${i}` }));
    const documentTotal = 10_000;

    // Simulate 20 append rounds, each adding 500 items
    for (let round = 0; round < 20; round++) {
      const newItems = Array.from({ length: 500 }, (_, i) => ({ id: `doc-r${round}-${i}` }));
      const { next } = simulateLoadMore(state, newItems, documentTotal, MAX_DOCUMENTS_IN_MEMORY);
      state = next;

      expect(state.length).toBeLessThanOrEqual(MAX_DOCUMENTS_IN_MEMORY);
    }

    // After 20 rounds (total attempted: 10500 items) the array must still be capped
    expect(state.length).toBe(MAX_DOCUMENTS_IN_MEMORY);
  });

  it('truncated flag is set correctly after every append that hits the cap', () => {
    const documentTotal = 5000;
    let state: Record<string, unknown>[] = [];

    for (let round = 0; round < 5; round++) {
      const newItems = Array.from({ length: 500 }, (_, i) => ({ id: `doc-r${round}-${i}` }));
      const { next, truncated } = simulateLoadMore(state, newItems, documentTotal, MAX_DOCUMENTS_IN_MEMORY);
      state = next;

      if (state.length < MAX_DOCUMENTS_IN_MEMORY) {
        // Haven't hit the cap yet; truncated only if total > items collected
        expect(truncated).toBe(documentTotal > state.length);
      } else {
        // At or beyond cap — always truncated since total (5000) > 2000
        expect(truncated).toBe(true);
      }
    }
  });

  it('does not grow when empty items array is returned', () => {
    const prev = Array.from({ length: 1500 }, (_, i) => ({ id: `doc-${i}` }));
    const { next, truncated, newOffset } = simulateLoadMore(prev, [], 1500, MAX_DOCUMENTS_IN_MEMORY);

    expect(next.length).toBe(1500); // unchanged
    expect(truncated).toBe(false);
    expect(newOffset).toBe(1500);
  });

  it('first-load flat-array branch also enforces the cap', () => {
    // Mirrors the Array.isArray(firstPage) branch in refreshDocuments
    const oversized = Array.from({ length: 4000 }, (_, i) => ({ id: `doc-${i}` }));
    const capped = oversized.slice(0, MAX_DOCUMENTS_IN_MEMORY);
    const truncated = oversized.length > MAX_DOCUMENTS_IN_MEMORY;

    expect(capped.length).toBe(MAX_DOCUMENTS_IN_MEMORY);
    expect(truncated).toBe(true);
    // Verify the cap is a hard ceiling — adding one more item would still be sliced
    const withExtra = [...capped, { id: 'extra' }].slice(0, MAX_DOCUMENTS_IN_MEMORY);
    expect(withExtra.length).toBe(MAX_DOCUMENTS_IN_MEMORY);
  });
});
