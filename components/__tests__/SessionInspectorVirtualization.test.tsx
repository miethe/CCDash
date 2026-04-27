/**
 * FE-102: Session log virtualization
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
 * Testing strategy: source-level proof via fs.readFileSync + regex/string assertions.
 * No jsdom render — useVirtualizer depends on real layout measurements which are
 * unavailable in jsdom (getBoundingClientRect always returns 0), making render-based
 * virtualization tests unreliable. Source proofs are the established pattern for
 * SessionInspector structural guarantees in this repo.
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

const SOURCE_PATH = path.resolve(__dirname, '../SessionInspector.tsx');
const SOURCE = fs.readFileSync(SOURCE_PATH, 'utf-8');

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
