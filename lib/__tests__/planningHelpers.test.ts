/**
 * Tests for planningHelpers utilities.
 *
 * Covers:
 *   - computeActivePhase: existing behaviour (regression guard)
 *   - formatLastActivity: Issue 4 — relative (<24h) and absolute (>=24h) display,
 *     null/empty/unparseable input, title always locale-full.
 *
 * Clock-mocking strategy:
 *   - vi.setSystemTime() is used to make Date.now() deterministic.
 *   - The `title` field is asserted via .toLocaleString() so locale differences
 *     don't break CI; absolute label assertions also use .toLocaleString() or
 *     regexp matching to stay locale-agnostic.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { computeActivePhase, formatLastActivity } from '../planningHelpers';
import type { PhaseContextItem } from '../../types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makePhase(effectiveStatus: string, id = 'p1'): PhaseContextItem {
  return {
    phaseId: id,
    phaseNumber: 1,
    effectiveStatus,
    rawStatus: effectiveStatus,
    title: 'Phase',
    docPath: '',
    schemaVersion: 0,
  } as unknown as PhaseContextItem;
}

// ── computeActivePhase ────────────────────────────────────────────────────────

describe('computeActivePhase', () => {
  it('returns null for empty array', () => {
    expect(computeActivePhase([])).toBeNull();
  });

  it('returns the in_progress phase', () => {
    const phases = [
      makePhase('done', 'p1'),
      makePhase('in_progress', 'p2'),
      makePhase('draft', 'p3'),
    ];
    expect(computeActivePhase(phases)?.phaseId).toBe('p2');
  });

  it('falls back to first non-done phase when none is in_progress', () => {
    const phases = [makePhase('done', 'p1'), makePhase('draft', 'p2')];
    expect(computeActivePhase(phases)?.phaseId).toBe('p2');
  });

  it('falls back to phases[0] when all are done', () => {
    const phases = [makePhase('done', 'p1'), makePhase('done', 'p2')];
    expect(computeActivePhase(phases)?.phaseId).toBe('p1');
  });
});

// ── formatLastActivity ────────────────────────────────────────────────────────

// Fixed "now" for deterministic tests: 2026-06-03T12:00:00.000Z
const NOW = new Date('2026-06-03T12:00:00.000Z').getTime();

describe('formatLastActivity — null / empty / unparseable', () => {
  it('returns null for null input', () => {
    expect(formatLastActivity(null)).toBeNull();
  });

  it('returns null for undefined input', () => {
    expect(formatLastActivity(undefined)).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(formatLastActivity('')).toBeNull();
  });

  it('returns null for unparseable string', () => {
    expect(formatLastActivity('not-a-date')).toBeNull();
  });
});

describe('formatLastActivity — relative display (< 24 h)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "just now" for timestamps within 5 seconds', () => {
    const iso = new Date(NOW - 2_000).toISOString(); // 2s ago
    const result = formatLastActivity(iso);
    expect(result).not.toBeNull();
    expect(result!.label).toBe('just now');
  });

  it('returns seconds label for 5–59 seconds ago', () => {
    const iso = new Date(NOW - 30_000).toISOString(); // 30s ago
    const result = formatLastActivity(iso);
    expect(result).not.toBeNull();
    expect(result!.label).toBe('30s ago');
  });

  it('returns minutes label for 1–59 minutes ago', () => {
    const iso = new Date(NOW - 15 * 60_000).toISOString(); // 15m ago
    const result = formatLastActivity(iso);
    expect(result).not.toBeNull();
    expect(result!.label).toBe('15m ago');
  });

  it('returns hours label for 1–23 hours ago', () => {
    const iso = new Date(NOW - 3 * 3_600_000).toISOString(); // 3h ago
    const result = formatLastActivity(iso);
    expect(result).not.toBeNull();
    expect(result!.label).toBe('3h ago');
  });

  it('title is always the full locale string', () => {
    const d = new Date(NOW - 60_000); // 1m ago
    const result = formatLastActivity(d.toISOString());
    expect(result).not.toBeNull();
    expect(result!.title).toBe(d.toLocaleString());
  });
});

describe('formatLastActivity — absolute display (>= 24 h)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns the locale string as label for timestamps >= 24 hours ago', () => {
    const d = new Date(NOW - 2 * 86_400_000); // 2 days ago
    const result = formatLastActivity(d.toISOString());
    expect(result).not.toBeNull();
    // For absolute branch, label equals toLocaleString()
    expect(result!.label).toBe(d.toLocaleString());
    expect(result!.title).toBe(d.toLocaleString());
  });

  it('returns absolute label for exactly 24 h ago (boundary)', () => {
    const d = new Date(NOW - 86_400_000); // exactly 24h
    const result = formatLastActivity(d.toISOString());
    expect(result).not.toBeNull();
    expect(result!.label).toBe(d.toLocaleString());
  });
});
