/**
 * T6-003: Legacy feature list virtualization in ProjectBoard
 *
 * Verifies structural invariants of the ProjectBoard list-view virtualization:
 *   1. useVirtualizer is imported from @tanstack/react-virtual
 *   2. The list view (surfaceCards.map) uses a virtualizer
 *   3. The v2 board view (Kanban columns + StatusColumn) is unchanged
 *   4. Container height=0 fallback caps render to FEATURE_LIST_FALLBACK_CAP items
 *   5. Virtual containers have explicit CSS height
 *   6. DOM row count is bounded via absolute positioning pattern
 *
 * Testing strategy: source-level proof via fs.readFileSync + regex/string assertions.
 * No jsdom render — useVirtualizer depends on real layout measurements which are
 * unavailable in jsdom (getBoundingClientRect always returns 0). Source proofs are
 * the established pattern for this repo (see SessionInspectorVirtualization.test.tsx).
 *
 * DOM row count invariant (rationale):
 *   The virtualizer only renders `overscan * 2 + visibleCount` items where
 *   visibleCount ≤ floor(containerHeight / estimateSize). In the height=0 case
 *   (jsdom / layout-unavailable), the fallback path caps to FEATURE_LIST_FALLBACK_CAP.
 *   This is the boundary the tests below verify via source proof.
 *
 * V2 surface invariant (rationale):
 *   The v2 board (Kanban) and its StatusColumn inner cards.map() are left unchanged.
 *   The v2 list surface is paginated 50/page by the server — no virtualizer needed.
 *   Only the list-view surfaceCards.map() receives a virtualizer, which guards the
 *   legacy path where surfaceCards can accumulate up to 5000 entries.
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

const SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../ProjectBoard.tsx'),
  'utf-8',
);

describe('T6-003: Legacy feature list virtualized in ProjectBoard', () => {
  it('imports useVirtualizer from @tanstack/react-virtual', () => {
    expect(SOURCE).toContain("from '@tanstack/react-virtual'");
    expect(SOURCE).toContain('useVirtualizer');
  });

  it('declares featureListVirtualizer for the list view', () => {
    expect(SOURCE).toContain('featureListVirtualizer');
    expect(SOURCE).toContain('featureListContainerRef');
    const virtIdx = SOURCE.indexOf('featureListVirtualizer = useVirtualizer');
    expect(virtIdx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(virtIdx, virtIdx + 400);
    expect(snippet).toContain('featureListContainerRef.current');
    expect(snippet).toContain('overscan:');
    expect(snippet).toContain('surfaceCards.length');
  });

  it('height=0 fallback: caps list render to FEATURE_LIST_FALLBACK_CAP', () => {
    expect(SOURCE).toContain('FEATURE_LIST_FALLBACK_CAP');
    // Fallback uses .slice(0, FEATURE_LIST_FALLBACK_CAP)
    expect(SOURCE).toContain('surfaceCards.slice(0, FEATURE_LIST_FALLBACK_CAP)');
  });

  it('height=0 fallback: logs console.warn when capping is applied', () => {
    expect(SOURCE).toContain('[ProjectBoard]');
    expect(SOURCE).toContain('height=0');
    const warns = SOURCE.split('console.warn').length - 1;
    expect(warns).toBeGreaterThanOrEqual(1);
  });

  it('virtual containers have explicit CSS height (FEATURE_LIST_CONTAINER_HEIGHT_PX)', () => {
    expect(SOURCE).toContain('FEATURE_LIST_CONTAINER_HEIGHT_PX');
    const occurrences = SOURCE.split('FEATURE_LIST_CONTAINER_HEIGHT_PX').length - 1;
    // Constant definition + at least one use in the container render
    expect(occurrences).toBeGreaterThanOrEqual(2);
  });

  it('DOM row count is bounded: virtual rows use absolute positioning', () => {
    expect(SOURCE).toContain('featureListVirtualizer.getVirtualItems()');
    expect(SOURCE).toContain('featureListVirtualizer.getTotalSize()');
    expect(SOURCE).toContain("position: 'absolute'");
    expect(SOURCE).toContain('translateY(');
  });

  it('measureElement wired for dynamic height measurement', () => {
    expect(SOURCE).toContain('featureListVirtualizer.measureElement');
  });

  it('v2 board (Kanban) surface is unchanged: StatusColumn is still present', () => {
    // StatusColumn is the Kanban board column — it must remain untouched.
    expect(SOURCE).toContain('const StatusColumn');
    // The board view still passes surfaceCards.filter to each column
    expect(SOURCE).toContain("cardDTOBoardStage(c) === 'backlog'");
    expect(SOURCE).toContain("cardDTOBoardStage(c) === 'in-progress'");
    expect(SOURCE).toContain("cardDTOBoardStage(c) === 'done'");
  });

  it('v2 list (paginated) surface: virtualization is only in the list-view branch', () => {
    // The virtualizer ref/hook must be associated with featureListContainerRef,
    // not with the board div. Verify featureListVirtualizer is not used inside
    // StatusColumn source.
    const statusColumnStart = SOURCE.indexOf('const StatusColumn');
    const statusColumnEnd = SOURCE.indexOf('\nconst ', statusColumnStart + 1);
    const statusColumnBody = SOURCE.slice(
      statusColumnStart,
      statusColumnEnd > 0 ? statusColumnEnd : undefined,
    );
    // StatusColumn must not reference the feature list virtualizer
    expect(statusColumnBody).not.toContain('featureListVirtualizer');
    expect(statusColumnBody).not.toContain('featureListContainerRef');
  });

  it('FeatureListCard is rendered inside the virtual row wrapper', () => {
    // The virtual row div wraps FeatureListCard (not inline in the outer grid)
    const virtIdx = SOURCE.indexOf('featureListVirtualizer.getVirtualItems()');
    // 2000 chars covers the virtualItems.map block and FeatureListCard usage
    const postVirt = SOURCE.slice(virtIdx, virtIdx + 2000);
    expect(postVirt).toContain('FeatureListCard');
  });
});
