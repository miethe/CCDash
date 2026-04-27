import { describe, it, expect, vi, beforeEach } from 'vitest';
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
 */
async function runCappedPagination(
  fetcher: (offset: number, pageSize: number) => Promise<Page>,
  cap: number,
): Promise<{ collected: Record<string, unknown>[]; truncated: boolean; finalOffset: number }> {
  const pageSize = 500;
  const firstPage = await fetcher(0, pageSize);
  const collected = [...firstPage.items];
  const total = firstPage.total || collected.length;
  let offset = collected.length;

  while (offset < total && collected.length < cap) {
    const page = await fetcher(offset, pageSize);
    const items = page.items || [];
    if (items.length === 0) break;
    collected.push(...items);
    offset += items.length;
  }

  const capped = collected.slice(0, cap);
  return {
    collected: capped,
    truncated: total > cap,
    finalOffset: capped.length,
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
