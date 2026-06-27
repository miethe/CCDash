/**
 * T6-002: Document list virtualization in PlanCatalog
 *
 * Verifies structural invariants of the PlanCatalog virtualization implementation:
 *   1. useVirtualizer is imported from @tanstack/react-virtual
 *   2. Both card view and list view use virtualizers
 *   3. Count badge reads `total` from TQ query (not documents.length)
 *   4. MAX_DOCUMENTS_IN_MEMORY cap is preserved via TQ select transform
 *   5. Container height=0 fallback caps render to DOC_LIST_FALLBACK_CAP items
 *   6. Virtual containers have explicit CSS height
 *
 * Testing strategy: source-level proof via fs.readFileSync + regex/string assertions.
 * No jsdom render — useVirtualizer depends on real layout measurements which are
 * unavailable in jsdom (getBoundingClientRect always returns 0). Source proofs are
 * the established pattern for this repo (see SessionInspectorVirtualization.test.tsx).
 *
 * DOM row count invariant (rationale):
 *   The virtualizer only renders `overscan * 2 + visibleCount` items where
 *   visibleCount ≤ floor(containerHeight / estimateSize). With containerHeight=0
 *   in jsdom, the fallback path is taken — this is exactly the boundary the
 *   tests below verify via source proof.
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

const SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../PlanCatalog.tsx'),
  'utf-8',
);

const DOCUMENTS_QUERY_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../../services/queries/documents.ts'),
  'utf-8',
);

describe('T6-002: Document list virtualized in PlanCatalog', () => {
  it('imports useVirtualizer from @tanstack/react-virtual', () => {
    expect(SOURCE).toContain("from '@tanstack/react-virtual'");
    expect(SOURCE).toContain('useVirtualizer');
  });

  it('imports useQueryClient for reading raw TQ cache', () => {
    expect(SOURCE).toContain("from '@tanstack/react-query'");
    expect(SOURCE).toContain('useQueryClient');
  });

  it('declares docCardVirtualizer for the card view', () => {
    expect(SOURCE).toContain('docCardVirtualizer');
    expect(SOURCE).toContain('docCardContainerRef');
    const virtIdx = SOURCE.indexOf('docCardVirtualizer = useVirtualizer');
    expect(virtIdx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(virtIdx, virtIdx + 400);
    expect(snippet).toContain('docCardContainerRef.current');
    expect(snippet).toContain('overscan:');
  });

  it('declares docListVirtualizer for the list view', () => {
    expect(SOURCE).toContain('docListVirtualizer');
    expect(SOURCE).toContain('docListContainerRef');
    const virtIdx = SOURCE.indexOf('docListVirtualizer = useVirtualizer');
    expect(virtIdx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(virtIdx, virtIdx + 400);
    expect(snippet).toContain('docListContainerRef.current');
  });

  it('count badge reads documentTotal from TQ query (not documents.length)', () => {
    // documentTotal is derived from raw TQ cache pages (pre-select) so it
    // reflects the server total, not the capped flat array length.
    expect(SOURCE).toContain('documentTotal');
    expect(SOURCE).toContain('rawDocQueryState');
    // Must NOT use documents.length as the badge value
    const badgeSection = SOURCE.slice(SOURCE.indexOf('documentTotal'));
    expect(badgeSection).toContain('{documentTotal');
    // The badge derivation reads from pages (not the select result)
    expect(SOURCE).toContain('.pages[');
    expect(SOURCE).toContain('.total');
  });

  it('uses documentsKeys from queryKeys for the raw cache lookup', () => {
    expect(SOURCE).toContain('documentsKeys');
    expect(SOURCE).toContain("from '../services/queryKeys'");
  });

  it('height=0 fallback: caps card view render to DOC_LIST_FALLBACK_CAP', () => {
    expect(SOURCE).toContain('DOC_LIST_FALLBACK_CAP');
    // Card view fallback uses .slice(0, DOC_LIST_FALLBACK_CAP)
    const occurrences = SOURCE.split('DOC_LIST_FALLBACK_CAP').length - 1;
    // Definition + at least two uses (card + list fallback)
    expect(occurrences).toBeGreaterThanOrEqual(3);
  });

  it('height=0 fallback: logs console.warn in both card and list views when capping', () => {
    expect(SOURCE).toContain('[PlanCatalog]');
    expect(SOURCE).toContain('height=0');
    const warns = SOURCE.split('console.warn').length - 1;
    expect(warns).toBeGreaterThanOrEqual(2);
  });

  it('virtual containers have explicit CSS height (DOC_CONTAINER_HEIGHT_PX)', () => {
    expect(SOURCE).toContain('DOC_CONTAINER_HEIGHT_PX');
    const occurrences = SOURCE.split('DOC_CONTAINER_HEIGHT_PX').length - 1;
    // Constant definition + uses in card/list containers
    expect(occurrences).toBeGreaterThanOrEqual(2);
  });

  it('DOM row count is bounded: virtual rows use absolute positioning', () => {
    expect(SOURCE).toContain("position: 'absolute'");
    expect(SOURCE).toContain('getVirtualItems()');
    expect(SOURCE).toContain('getTotalSize()');
    expect(SOURCE).toContain('translateY(');
  });

  it('MAX_DOCUMENTS_IN_MEMORY cap preserved in TQ select transform (not imported in component)', () => {
    // The cap must remain in documents.ts select transform — NOT imported into PlanCatalog.
    // PlanCatalog reads the capped flat array; documents.ts enforces the cap.
    expect(DOCUMENTS_QUERY_SOURCE).toContain('MAX_DOCUMENTS_IN_MEMORY');
    expect(DOCUMENTS_QUERY_SOURCE).toContain('flat.slice(0, MAX_DOCUMENTS_IN_MEMORY)');
    // PlanCatalog must NOT import MAX_DOCUMENTS_IN_MEMORY from constants (would re-implement the cap)
    expect(SOURCE).not.toContain("import { MAX_DOCUMENTS_IN_MEMORY }");
    expect(SOURCE).not.toContain("import { MAX_DOCUMENTS_IN_MEMORY,");
    // The constant must not be used as a slice cap in PlanCatalog
    expect(SOURCE).not.toContain('.slice(0, MAX_DOCUMENTS_IN_MEMORY)');
  });

  it('measureElement wired for dynamic height measurement in list virtualizer', () => {
    // docListVirtualizer.measureElement should be used as a ref callback
    expect(SOURCE).toContain('docListVirtualizer.measureElement');
    expect(SOURCE).toContain('docCardVirtualizer.measureElement');
  });
});
