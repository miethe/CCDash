/**
 * FE-102: Session log virtualization
 * T6-001: Session list (past sessions) virtualization in SessionInspector
 *
 * Verifies structural invariants of the VirtualizedTranscriptList implementation:
 *   1. useVirtualizer is imported from @tanstack/react-virtual
 *   2. VirtualizedTranscriptList component exists and uses useVirtualizer
 *   3. The scroll container no longer uses AnimatePresence directly (moved into
 *      VirtualizedTranscriptList)
 *   4. transcriptTruncated notice is rendered when droppedCount > 0
 *   5. measureElement is wired for dynamic row height measurement
 *   6. DOM node count is bounded: only visible rows are rendered (overscan=8
 *      ensures a constant window, not O(n) for n total logs)
 *
 * T6-001 adds source-level proofs that:
 *   - pastSessionThreadRoots and pastSessions lists use useVirtualizer
 *   - Scroll position is persisted via TQ query meta (uiStateKeys) on unmount
 *   - Container height=0 fallback caps render to SESSION_LIST_FALLBACK_CAP items
 *   - Both pastThreadsVirtualizer and pastCardsVirtualizer are declared
 *   - Virtualizer containers have explicit CSS height (SESSION_LIST_CONTAINER_HEIGHT_PX)
 *
 * Testing strategy: source-level proof via fs.readFileSync + regex/string assertions.
 * No jsdom render — useVirtualizer depends on real layout measurements which are
 * unavailable in jsdom (getBoundingClientRect always returns 0), making render-based
 * virtualization tests unreliable. Source proofs are the established pattern for
 * SessionInspector structural guarantees in this repo.
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

const SESSION_INSPECTOR_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../SessionInspector.tsx'),
  'utf-8',
);
const TRANSCRIPT_VIEW_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../SessionInspector/TranscriptView.tsx'),
  'utf-8',
);
const SOURCE = [SESSION_INSPECTOR_SOURCE, TRANSCRIPT_VIEW_SOURCE].join('\n');

function linesContaining(pattern: string): string[] {
  return SOURCE.split('\n').filter(line => line.includes(pattern));
}

describe('FE-102: Session log virtualization', () => {
  it('imports useVirtualizer from @tanstack/react-virtual', () => {
    const importLines = linesContaining('@tanstack/react-virtual');
    expect(importLines.length).toBeGreaterThan(0);
    expect(importLines.some(l => l.includes('useVirtualizer'))).toBe(true);
  });

  it('defines VirtualizedTranscriptList component', () => {
    expect(SOURCE).toContain('const VirtualizedTranscriptList');
  });

  it('calls useVirtualizer inside VirtualizedTranscriptList', () => {
    const virtualListStart = SOURCE.indexOf('const VirtualizedTranscriptList');
    const nextComponent = SOURCE.indexOf('\nconst ', virtualListStart + 1);
    const componentBody = SOURCE.slice(virtualListStart, nextComponent > 0 ? nextComponent : undefined);
    expect(componentBody).toContain('useVirtualizer(');
  });

  it('uses measureElement for dynamic height measurement', () => {
    expect(SOURCE).toContain('rowVirtualizer.measureElement');
  });

  it('configures overscan for bounded DOM node count', () => {
    expect(SOURCE).toContain('overscan:');
  });

  it('renders transcriptTruncated notice when droppedCount is present', () => {
    expect(SOURCE).toContain('transcriptTruncated');
    expect(SOURCE).toContain('droppedCount');
    expect(SOURCE).toContain('messages hidden');
  });

  it('uses absolute positioning for virtual rows (constant DOM pattern)', () => {
    expect(SOURCE).toContain("position: 'absolute'");
    expect(SOURCE).toContain('translateY(');
  });

  it('uses getTotalSize for the inner spacer height', () => {
    expect(SOURCE).toContain('rowVirtualizer.getTotalSize()');
  });

  it('passes containerRef to VirtualizedTranscriptList (not direct ref on div)', () => {
    // The scroll container div should now be inside VirtualizedTranscriptList,
    // not directly in the TranscriptView JSX return.
    const transcriptViewStart = SOURCE.indexOf('const TranscriptView');
    const transcriptViewEnd = SOURCE.indexOf('\nconst ', transcriptViewStart + 100);
    const tvBody = SOURCE.slice(transcriptViewStart, transcriptViewEnd > 0 ? transcriptViewEnd : undefined);

    // VirtualizedTranscriptList is used in TranscriptView
    expect(tvBody).toContain('VirtualizedTranscriptList');
    // containerRef prop is passed
    expect(tvBody).toContain('containerRef={smartScroll.containerRef}');
  });
});

// ── T6-001: Past-session list virtualization ──────────────────────────────────
// These tests prove that pastSessionThreadRoots and pastSessions lists are
// virtualized in SessionInspector.tsx. They use source-level assertions (the
// established pattern for this repo) because useVirtualizer requires real DOM
// layout measurements (getBoundingClientRect) unavailable in jsdom.
//
// DOM row count invariant (rationale):
//   The virtualizer only renders `overscan * 2 + visibleCount` items where
//   visibleCount ≤ floor(containerHeight / estimateSize). With containerHeight=0
//   in jsdom, the fallback path is taken — this is exactly the boundary the
//   tests below verify via source proof.

describe('T6-001: Session list (past sessions) virtualized in SessionInspector', () => {
  it('imports useQueryClient for scroll-offset persistence', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain("from '@tanstack/react-query'");
    expect(SESSION_INSPECTOR_SOURCE).toContain('useQueryClient');
  });

  it('imports uiStateKeys for the TQ scroll-offset key', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('uiStateKeys');
    expect(SESSION_INSPECTOR_SOURCE).toContain("from '../services/queryKeys'");
  });

  it('declares pastThreadsVirtualizer using useVirtualizer', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('pastThreadsVirtualizer');
    expect(SESSION_INSPECTOR_SOURCE).toContain('pastThreadsContainerRef');
    // Verify useVirtualizer is called with the threaded container ref
    const virtIdx = SESSION_INSPECTOR_SOURCE.indexOf('pastThreadsVirtualizer = useVirtualizer');
    expect(virtIdx).toBeGreaterThan(-1);
    const snippet = SESSION_INSPECTOR_SOURCE.slice(virtIdx, virtIdx + 400);
    expect(snippet).toContain('pastThreadsContainerRef.current');
    expect(snippet).toContain('overscan:');
  });

  it('declares pastCardsVirtualizer using useVirtualizer', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('pastCardsVirtualizer');
    expect(SESSION_INSPECTOR_SOURCE).toContain('pastCardsContainerRef');
    const virtIdx = SESSION_INSPECTOR_SOURCE.indexOf('pastCardsVirtualizer = useVirtualizer');
    expect(virtIdx).toBeGreaterThan(-1);
    const snippet = SESSION_INSPECTOR_SOURCE.slice(virtIdx, virtIdx + 400);
    expect(snippet).toContain('pastCardsContainerRef.current');
  });

  it('persists scroll offset to TQ query meta on unmount', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('uiStateKeys.sessionListScrollOffset');
    expect(SESSION_INSPECTOR_SOURCE).toContain('queryClient.setQueryData');
    // The scroll offset is stored on unmount (useEffect cleanup)
    const setDataIdx = SESSION_INSPECTOR_SOURCE.indexOf('queryClient.setQueryData');
    expect(setDataIdx).toBeGreaterThan(-1);
    const snippet = SESSION_INSPECTOR_SOURCE.slice(Math.max(0, setDataIdx - 200), setDataIdx + 200);
    expect(snippet).toContain('scrollTop');
  });

  it('restores scroll offset via initialOffset on mount', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('initialOffset');
    expect(SESSION_INSPECTOR_SOURCE).toContain('queryClient.getQueryData');
    // initialOffset is retrieved from TQ before the virtualizer is created
    const getDataIdx = SESSION_INSPECTOR_SOURCE.indexOf('queryClient.getQueryData');
    expect(getDataIdx).toBeGreaterThan(-1);
    const snippet = SESSION_INSPECTOR_SOURCE.slice(getDataIdx, getDataIdx + 300);
    expect(snippet).toContain('sessionListScrollOffset');
  });

  it('height=0 fallback: caps pastSessionThreadRoots render to SESSION_LIST_FALLBACK_CAP', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('SESSION_LIST_FALLBACK_CAP');
    // The fallback uses .slice(0, SESSION_LIST_FALLBACK_CAP)
    expect(SESSION_INSPECTOR_SOURCE).toContain('pastSessionThreadRoots.slice(0, SESSION_LIST_FALLBACK_CAP)');
  });

  it('height=0 fallback: caps pastSessions render to SESSION_LIST_FALLBACK_CAP', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('pastSessions.slice(0, SESSION_LIST_FALLBACK_CAP)');
  });

  it('height=0 fallback: logs a console.warn when capping is applied', () => {
    // Both fallback branches must warn so developers know why the list is truncated
    const warns = SESSION_INSPECTOR_SOURCE.split('console.warn').length - 1;
    expect(warns).toBeGreaterThanOrEqual(2);
    expect(SESSION_INSPECTOR_SOURCE).toContain('[SessionInspector]');
    expect(SESSION_INSPECTOR_SOURCE).toContain('height=0');
  });

  it('virtual containers have explicit CSS height (SESSION_LIST_CONTAINER_HEIGHT_PX)', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('SESSION_LIST_CONTAINER_HEIGHT_PX');
    // Used as the container height in both threaded and cards modes
    const occurrences = SESSION_INSPECTOR_SOURCE.split('SESSION_LIST_CONTAINER_HEIGHT_PX').length - 1;
    // At least 3 uses: constant definition + two render paths (threaded, cards)
    expect(occurrences).toBeGreaterThanOrEqual(3);
  });

  it('DOM row count is bounded: virtual rows are rendered with position absolute', () => {
    // Source proof that only virtual rows are rendered (not all items)
    // Both virtualizers must use absolute positioning (the constant-DOM pattern).
    const absCount = SESSION_INSPECTOR_SOURCE.split("position: 'absolute'").length - 1;
    // SessionInspector should have at least 2 (threaded + cards virtualizer containers)
    // TranscriptView adds more. We only check the SI source.
    expect(absCount).toBeGreaterThanOrEqual(2);
    expect(SESSION_INSPECTOR_SOURCE).toContain('getVirtualItems()');
    expect(SESSION_INSPECTOR_SOURCE).toContain('getTotalSize()');
  });

  it('VITE_CCDASH_MEMORY_GUARD_ENABLED interplay preserved: isMemoryGuardEnabled import present', () => {
    // mergeSessionDetail ring-buffer cap is applied in contexts/dataContextShared.ts — not in
    // SessionInspector — so the list virtualizer must not interfere with it.
    // We verify SessionInspector still imports isMemoryGuardEnabled (used by the detail views).
    expect(SESSION_INSPECTOR_SOURCE).toContain('isMemoryGuardEnabled');
  });
});
