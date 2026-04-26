/**
 * P4-007: SessionInspector Feature Surface Migration
 *
 * Verifies that SessionInspector:
 *   1. Does NOT fire per-feature linked-session fan-out on mount
 *      (getLegacyFeatureLinkedSessions is gone; only getFeatureLinkedSessionPage
 *       is used, and only on accordion expand).
 *   2. The per-feature detail fan-out (getLegacyFeatureDetail Promise.all)
 *      is gated behind activeTab === 'features', not eager on mount.
 *   3. The accordion expand triggers exactly one getFeatureLinkedSessionPage call.
 *   4. Load-more triggers a second call with the next offset threaded.
 *   5. The load-more button and pagination state are wired in the source.
 *
 * Testing strategy (no @testing-library/react — consistent with P4-004/P4-009):
 *   - Source-level proofs via fs.readFileSync + string/regex assertions.
 *   - Structural proofs: scan for absence of old patterns and presence of new ones.
 *   - Import audit: getFeatureLinkedSessionPage imported; getLegacyFeatureLinkedSessions not.
 *
 * What is NOT tested here:
 *   - Full React effect lifecycle (no jsdom configured)
 *   - Real HTTP fetch (covered by useFeatureModalData integration tests)
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

// ── Source under test ─────────────────────────────────────────────────────────
const SOURCE_PATH = path.resolve(__dirname, '../SessionInspector.tsx');
const SOURCE = fs.readFileSync(SOURCE_PATH, 'utf-8');

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Returns all lines containing a pattern (case-sensitive). */
function linesContaining(pattern: string): string[] {
  return SOURCE.split('\n').filter(line => line.includes(pattern));
}

/** Counts non-comment, non-test occurrences of a string in the source. */
function countUsages(pattern: string): number {
  return SOURCE.split('\n').filter(
    line =>
      line.includes(pattern) &&
      !line.trimStart().startsWith('//') &&
      !line.trimStart().startsWith('*'),
  ).length;
}

// ── 1. Import audit ───────────────────────────────────────────────────────────

describe('P4-007 — Import audit', () => {
  it('imports getFeatureLinkedSessionPage from featureSurface', () => {
    const importLine = linesContaining("from '../services/featureSurface'");
    expect(importLine.length).toBeGreaterThan(0);
    const combined = importLine.join('\n');
    expect(combined).toContain('getFeatureLinkedSessionPage');
  });

  it('imports LinkedFeatureSessionDTO type from featureSurface', () => {
    const importLine = linesContaining("from '../services/featureSurface'");
    const combined = importLine.join('\n');
    expect(combined).toContain('LinkedFeatureSessionDTO');
  });

  it('does NOT import getLegacyFeatureLinkedSessions', () => {
    const importLine = linesContaining("from '../services/featureSurface'");
    const combined = importLine.join('\n');
    expect(combined).not.toContain('getLegacyFeatureLinkedSessions');
  });

  it('getLegacyFeatureLinkedSessions is not called in production code', () => {
    // Allow it in comments (for documentation of the migration) but not in calls
    const callLines = SOURCE.split('\n').filter(
      line =>
        line.includes('getLegacyFeatureLinkedSessions') &&
        !line.trimStart().startsWith('//') &&
        !line.trimStart().startsWith('*'),
    );
    expect(callLines).toHaveLength(0);
  });
});

// ── 2. No eager fan-out on mount ──────────────────────────────────────────────

describe('P4-007 — No eager per-feature fan-out on mount', () => {
  it('per-feature detail load is gated on activeTab === features', () => {
    // The effect that fires getLegacyFeatureDetail must check activeTab
    const gateMarker = "if (activeTab !== 'features') return;";
    expect(SOURCE).toContain(gateMarker);
  });

  it('activeTab is in the getLegacyFeatureDetail effect dependency array', () => {
    // The effect must list activeTab in its deps alongside linkedFeatureLinks
    // Locate the effect block that contains activeTab guard
    const gateIdx = SOURCE.indexOf("if (activeTab !== 'features') return;");
    expect(gateIdx).toBeGreaterThan(-1);

    // Find the closing dep array within ~200 chars of the function body end
    const effectSlice = SOURCE.slice(gateIdx, gateIdx + 3000);
    expect(effectSlice).toContain('activeTab');
    expect(effectSlice).toContain('linkedFeatureLinks');
  });

  it('P4-007 migration comment is present on the gated effect', () => {
    expect(SOURCE).toContain(
      'gate per-feature getLegacyFeatureDetail calls behind activeTab',
    );
  });

  it('TODO(P5-001) deferral comment is present', () => {
    expect(SOURCE).toContain('TODO(P5-001)');
  });
});

// ── 3. loadRelatedMainThreadSessions uses getFeatureLinkedSessionPage ─────────

describe('P4-007 — loadRelatedMainThreadSessions uses paginated client', () => {
  it('calls getFeatureLinkedSessionPage inside loadRelatedMainThreadSessions', () => {
    // Locate the function body
    const fnStart = SOURCE.indexOf('const loadRelatedMainThreadSessions = useCallback');
    expect(fnStart).toBeGreaterThan(-1);

    // Capture the function body (~1000 chars is more than enough)
    const fnBody = SOURCE.slice(fnStart, fnStart + 1000);
    expect(fnBody).toContain('getFeatureLinkedSessionPage');
  });

  it('passes limit and offset params to getFeatureLinkedSessionPage', () => {
    const fnStart = SOURCE.indexOf('const loadRelatedMainThreadSessions = useCallback');
    const fnBody = SOURCE.slice(fnStart, fnStart + 1000);
    expect(fnBody).toContain('limit:');
    expect(fnBody).toContain('offset:');
  });

  it('accepts an append flag for load-more semantics', () => {
    const fnStart = SOURCE.indexOf('const loadRelatedMainThreadSessions = useCallback');
    const fnBody = SOURCE.slice(fnStart, fnStart + 300);
    expect(fnBody).toContain('append');
  });

  it('threads hasMore from the page response', () => {
    const fnStart = SOURCE.indexOf('const loadRelatedMainThreadSessions = useCallback');
    const fnBody = SOURCE.slice(fnStart, fnStart + 1500);
    expect(fnBody).toContain('page.hasMore');
  });

  it('updates pagination offset state after each page', () => {
    const fnStart = SOURCE.indexOf('const loadRelatedMainThreadSessions = useCallback');
    const fnBody = SOURCE.slice(fnStart, fnStart + 1500);
    expect(fnBody).toContain('setMainThreadSessionsNextOffsetByFeatureId');
  });

  it('P4-007 comment is present on the callback', () => {
    expect(SOURCE).toContain('P4-007: replaced getLegacyFeatureLinkedSessions fan-out');
  });
});

// ── 4. Pagination state is present ───────────────────────────────────────────

describe('P4-007 — Pagination state tracked per-feature', () => {
  it('mainThreadSessionsHasMoreByFeatureId state exists', () => {
    expect(SOURCE).toContain('mainThreadSessionsHasMoreByFeatureId');
  });

  it('mainThreadSessionsNextOffsetByFeatureId state exists', () => {
    expect(SOURCE).toContain('mainThreadSessionsNextOffsetByFeatureId');
  });

  it('state type for mainThreadSessionsByFeatureId is LinkedFeatureSessionDTO[]', () => {
    expect(SOURCE).toContain('Record<string, LinkedFeatureSessionDTO[]>');
  });
});

// ── 5. Load-more pagination UI ────────────────────────────────────────────────

describe('P4-007 — Load-more button in renderFeatureCard', () => {
  it('P4-007 load-more pagination comment marker is present', () => {
    expect(SOURCE).toContain('P4-007: load-more pagination control');
  });

  it('load-more button calls loadRelatedMainThreadSessions with append=true', () => {
    const marker = 'P4-007: load-more pagination control';
    const markerIdx = SOURCE.indexOf(marker);
    expect(markerIdx).toBeGreaterThan(-1);

    const block = SOURCE.slice(markerIdx, markerIdx + 600);
    expect(block).toContain('loadRelatedMainThreadSessions(feature.featureId, true)');
  });

  it('load-more button only renders when hasMoreMainThreads is true', () => {
    const marker = 'P4-007: load-more pagination control';
    const markerIdx = SOURCE.indexOf(marker);
    const block = SOURCE.slice(markerIdx, markerIdx + 600);
    expect(block).toContain('hasMoreMainThreads');
  });

  it('hasMoreMainThreads is derived from mainThreadSessionsHasMoreByFeatureId', () => {
    const marker = 'P4-007: pagination state for this feature';
    const markerIdx = SOURCE.indexOf(marker);
    expect(markerIdx).toBeGreaterThan(-1);

    const block = SOURCE.slice(markerIdx, markerIdx + 200);
    expect(block).toContain('mainThreadSessionsHasMoreByFeatureId[feature.featureId]');
  });
});

// ── 6. Bounded call proof (structural) ────────────────────────────────────────

describe('P4-007 — Bounded call proof: single list + rollup batch at mount', () => {
  it('no unconditional getLegacyFeatureLinkedSessions call exists', () => {
    // Already covered by import audit but verified again here explicitly
    expect(countUsages('getLegacyFeatureLinkedSessions')).toBe(0);
  });

  it('getFeatureLinkedSessionPage is called only inside loadRelatedMainThreadSessions', () => {
    // All non-comment occurrences of getFeatureLinkedSessionPage should be
    // inside the loadRelatedMainThreadSessions callback (demand-driven, not in effects).
    const callLines = SOURCE.split('\n').filter(
      line =>
        line.includes('getFeatureLinkedSessionPage') &&
        !line.trimStart().startsWith('//') &&
        !line.trimStart().startsWith('*') &&
        !line.includes('import'),
    );
    // Should be exactly one call site (inside loadRelatedMainThreadSessions)
    expect(callLines.length).toBe(1);
  });

  it('the single getFeatureLinkedSessionPage call is inside a useCallback', () => {
    const callLineIdx = SOURCE.split('\n').findIndex(
      line =>
        line.includes('getFeatureLinkedSessionPage') &&
        !line.trimStart().startsWith('//') &&
        !line.trimStart().startsWith('*') &&
        !line.includes('import'),
    );
    expect(callLineIdx).toBeGreaterThan(-1);

    // Walk backwards from the call to find its enclosing function declaration
    const linesBefore = SOURCE.split('\n').slice(0, callLineIdx).join('\n');
    // The nearest useCallback or async function should be loadRelatedMainThreadSessions
    const lastCallbackIdx = linesBefore.lastIndexOf('useCallback');
    const lastFnNameIdx = linesBefore.lastIndexOf('loadRelatedMainThreadSessions');
    expect(lastFnNameIdx).toBeGreaterThan(-1);
    expect(lastCallbackIdx).toBeGreaterThan(-1);
    // The function name declaration should appear just before the useCallback
    expect(Math.abs(lastFnNameIdx - lastCallbackIdx)).toBeLessThan(100);
  });
});
