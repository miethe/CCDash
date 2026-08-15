/**
 * Tests for the Are-We-Winning dashboard query hooks / adapters
 * (are-we-winning-dashboard-v1, M3).
 *
 * Strategy: mirrors services/queries/__tests__/researchRuns.test.ts —
 * exercise the adapter logic directly (no network, no @testing-library/react).
 *
 * Scenarios covered:
 *   - adaptAreWeWinningSummary preserves `reopened`/`selfCaughtRatio` nulls
 *     verbatim (resilience-by-default: absent, never a fabricated trendline/ratio)
 *   - adaptAreWeWinningSummary maps a populated reopened trendline + ratio correctly
 *   - adaptAreWeWinningDrillThroughPage maps rows + cursor fields correctly
 *   - areWeWinningKeys produce distinct cache keys per param set
 */

import { describe, expect, it } from 'vitest';
import { areWeWinningKeys } from '../../queryKeys';
import { adaptAreWeWinningDrillThroughPage, adaptAreWeWinningSummary } from '../areWeWinning';

describe('adaptAreWeWinningSummary', () => {
  it('preserves reopened=null and self_caught_ratio=null verbatim (M2 part-B not yet implemented)', () => {
    const wire = {
      created: { event_type: 'node.created', points: [] },
      completed: { event_type: 'node.completed', points: [] },
      reopened: null,
      self_caught_ratio: null,
      generated_at: '2026-08-14T00:00:00Z',
    };

    const result = adaptAreWeWinningSummary(wire);

    expect(result.reopened).toBeNull();
    expect(result.selfCaughtRatio).toBeNull();
  });

  it('maps created/completed weekly points to camelCase', () => {
    const wire = {
      created: {
        event_type: 'node.created',
        points: [{ iso_year: 2026, iso_week: 33, week_start_date: '2026-08-10', count: 12 }],
      },
      completed: { event_type: 'node.completed', points: [] },
      reopened: null,
      self_caught_ratio: null,
      generated_at: '2026-08-14T00:00:00Z',
    };

    const result = adaptAreWeWinningSummary(wire);

    expect(result.created.eventType).toBe('node.created');
    expect(result.created.points).toEqual([
      { isoYear: 2026, isoWeek: 33, weekStartDate: '2026-08-10', count: 12 },
    ]);
  });

  it('maps a populated reopened trendline + self-caught ratio when present', () => {
    const wire = {
      created: { event_type: 'node.created', points: [] },
      completed: { event_type: 'node.completed', points: [] },
      reopened: {
        event_type: 'node.reopened',
        points: [{ iso_year: 2026, iso_week: 1, week_start_date: '2026-01-05', count: 3 }],
      },
      self_caught_ratio: {
        buckets: [
          { bucket: 'self_caught', count: 5 },
          { bucket: 'other_caught', count: 2 },
          { bucket: 'unknown', count: 193 },
        ],
        total: 200,
      },
      generated_at: '2026-08-14T00:00:00Z',
    };

    const result = adaptAreWeWinningSummary(wire as any);

    expect(result.reopened).not.toBeNull();
    expect(result.reopened!.points[0].count).toBe(3);
    expect(result.selfCaughtRatio).not.toBeNull();
    expect(result.selfCaughtRatio!.total).toBe(200);
    expect(result.selfCaughtRatio!.buckets).toEqual([
      { bucket: 'self_caught', count: 5 },
      { bucket: 'other_caught', count: 2 },
      { bucket: 'unknown', count: 193 },
    ]);
  });
});

describe('adaptAreWeWinningDrillThroughPage', () => {
  it('maps rows + cursor fields to camelCase, preserving null title/nodeId', () => {
    const wire = {
      items: [
        { node_id: 'node-1', event_type: 'node.created', occurred_at: '2026-08-10T00:00:00Z', title: 'Fix the thing' },
        { node_id: null, event_type: 'node.created', occurred_at: '2026-08-11T00:00:00Z', title: null },
      ],
      total: 2,
      limit: 50,
      cursor: 'eyJvIjowfQ==',
      next_cursor: null,
    };

    const result = adaptAreWeWinningDrillThroughPage(wire);

    expect(result.items).toHaveLength(2);
    expect(result.items[0]).toEqual({
      nodeId: 'node-1',
      eventType: 'node.created',
      occurredAt: '2026-08-10T00:00:00Z',
      title: 'Fix the thing',
    });
    expect(result.items[1].nodeId).toBeNull();
    expect(result.items[1].title).toBeNull();
    expect(result.total).toBe(2);
    expect(result.nextCursor).toBeNull();
  });
});

describe('areWeWinningKeys', () => {
  it('summary() is a stable sentinel key', () => {
    expect(areWeWinningKeys.summary()).toEqual(['are-we-winning', 'summary']);
  });

  it('drillThrough() produces distinct keys per bucket coordinate', () => {
    const a = areWeWinningKeys.drillThrough('node.created', 2026, 33);
    const b = areWeWinningKeys.drillThrough('node.created', 2026, 34);
    const c = areWeWinningKeys.drillThrough('node.completed', 2026, 33);

    expect(a).not.toEqual(b);
    expect(a).not.toEqual(c);
  });

  it('drillThrough() folds cursor into the key so each page gets its own cache slot', () => {
    const page1 = areWeWinningKeys.drillThrough('node.created', 2026, 33, null);
    const page2 = areWeWinningKeys.drillThrough('node.created', 2026, 33, 'abc');

    expect(page1).not.toEqual(page2);
  });
});
