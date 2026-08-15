/**
 * TanStack Query hooks for the Are-We-Winning dashboard (are-we-winning-
 * dashboard-v1, M3). Backed by:
 *   GET /api/agent/are-we-winning/summary
 *   GET /api/agent/are-we-winning/drill-through
 *
 * Wire contract: `AreWeWinningSummaryDTO` / `AreWeWinningDrillThroughPageDTO`
 * (backend/models.py) declare no `alias_generator` — the wire payload is
 * pure snake_case. Adaptation to the camelCase public contract (types.ts)
 * happens client-side in this module, same pattern as
 * services/queries/researchRuns.ts's WireResearchRun adapter.
 *
 * Resilience: both hooks catch every error (including the 404
 * `are_we_winning_disabled` response when `CCDASH_ARE_WE_WINNING_ENABLED`
 * is off) and resolve to `null` — a disabled/absent surface is a contract
 * state for the caller to render explicitly, never a thrown error.
 */

import { useQuery } from '@tanstack/react-query';
import { apiRequestJson } from '../apiClient';
import { areWeWinningKeys } from '../queryKeys';
import type {
  AreWeWinningDrillThroughPage,
  AreWeWinningDrillThroughRow,
  AreWeWinningSummary,
  AreWeWinningTrendline,
  AreWeWinningWeeklyPoint,
  SelfCaughtRatio,
  SelfCaughtRatioBucket,
} from '../../types';

const AREWEWINNING_API_BASE = '/api/agent/are-we-winning';

// ── Wire shapes (snake_case, 1:1 with backend/models.py DTOs) ───────────────

interface WireWeeklyPoint {
  iso_year: number;
  iso_week: number;
  week_start_date: string;
  count: number;
}

interface WireTrendline {
  event_type: string;
  points: WireWeeklyPoint[];
}

interface WireRatioBucket {
  bucket: 'self_caught' | 'other_caught' | 'unknown';
  count: number;
}

interface WireRatio {
  buckets: WireRatioBucket[];
  total: number;
}

interface WireSummary {
  created: WireTrendline;
  completed: WireTrendline;
  reopened: WireTrendline | null;
  self_caught_ratio: WireRatio | null;
  generated_at: string;
}

interface WireDrillThroughRow {
  node_id: string | null;
  event_type: string;
  occurred_at: string;
  title: string | null;
}

interface WireDrillThroughPage {
  items: WireDrillThroughRow[];
  total: number;
  limit: number;
  cursor: string;
  next_cursor: string | null;
}

// ── Adapters (snake_case wire → camelCase public contract) ──────────────────

function adaptWeeklyPoint(wire: WireWeeklyPoint): AreWeWinningWeeklyPoint {
  return {
    isoYear: wire.iso_year,
    isoWeek: wire.iso_week,
    weekStartDate: wire.week_start_date,
    count: wire.count ?? 0,
  };
}

function adaptTrendline(wire: WireTrendline): AreWeWinningTrendline {
  return {
    eventType: wire.event_type,
    points: (wire.points ?? []).map(adaptWeeklyPoint),
  };
}

function adaptRatioBucket(wire: WireRatioBucket): SelfCaughtRatioBucket {
  return { bucket: wire.bucket, count: wire.count ?? 0 };
}

function adaptRatio(wire: WireRatio): SelfCaughtRatio {
  return {
    buckets: (wire.buckets ?? []).map(adaptRatioBucket),
    total: wire.total ?? 0,
  };
}

/** Exported so tests can exercise the mapping directly without hitting the network. */
export function adaptAreWeWinningSummary(wire: WireSummary): AreWeWinningSummary {
  return {
    created: adaptTrendline(wire.created),
    completed: adaptTrendline(wire.completed),
    reopened: wire.reopened ? adaptTrendline(wire.reopened) : null,
    selfCaughtRatio: wire.self_caught_ratio ? adaptRatio(wire.self_caught_ratio) : null,
    generatedAt: wire.generated_at,
  };
}

function adaptDrillThroughRow(wire: WireDrillThroughRow): AreWeWinningDrillThroughRow {
  return {
    nodeId: wire.node_id ?? null,
    eventType: wire.event_type,
    occurredAt: wire.occurred_at,
    title: wire.title ?? null,
  };
}

/** Exported so tests can exercise the mapping directly without hitting the network. */
export function adaptAreWeWinningDrillThroughPage(
  wire: WireDrillThroughPage,
): AreWeWinningDrillThroughPage {
  return {
    items: (wire.items ?? []).map(adaptDrillThroughRow),
    total: wire.total ?? 0,
    limit: wire.limit ?? 0,
    cursor: wire.cursor ?? '',
    nextCursor: wire.next_cursor ?? null,
  };
}

// ── useAreWeWinningSummaryQuery ──────────────────────────────────────────────

export interface UseAreWeWinningSummaryQueryOptions {
  /** Set false to suppress the query (e.g. tab not yet visible). */
  enabled?: boolean;
}

/**
 * Weekly created/completed/reopened trendlines + the self-caught ratio.
 * `reopened`/`selfCaughtRatio` are `null` until M2-part-B lands; a disabled
 * feature flag or any other fetch failure also resolves to `null` (never
 * thrown) so the tab always has a definite "not available" state to render.
 */
export function useAreWeWinningSummaryQuery({
  enabled = true,
}: UseAreWeWinningSummaryQueryOptions = {}) {
  return useQuery<AreWeWinningSummary | null>({
    queryKey: areWeWinningKeys.summary(),
    queryFn: async (): Promise<AreWeWinningSummary | null> => {
      try {
        const wire = await apiRequestJson<WireSummary>(`${AREWEWINNING_API_BASE}/summary`);
        return adaptAreWeWinningSummary(wire);
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
    gcTime: 300_000,
    enabled,
    placeholderData: null,
  });
}

// ── useAreWeWinningDrillThroughQuery ─────────────────────────────────────────

export interface UseAreWeWinningDrillThroughQueryOptions {
  eventType: string | null;
  isoYear: number | null;
  isoWeek: number | null;
  cursor?: string | null;
  limit?: number;
  /** Set false to suppress the query (e.g. drill-through modal closed). */
  enabled?: boolean;
}

/**
 * The exact underlying `intent_tree_events` rows behind one rendered
 * (eventType, isoYear, isoWeek) bucket. Only enabled once a bucket
 * coordinate is selected — i.e. only after a user click, never on render.
 */
export function useAreWeWinningDrillThroughQuery({
  eventType,
  isoYear,
  isoWeek,
  cursor = null,
  limit = 50,
  enabled = true,
}: UseAreWeWinningDrillThroughQueryOptions) {
  return useQuery<AreWeWinningDrillThroughPage | null>({
    queryKey: areWeWinningKeys.drillThrough(eventType ?? '', isoYear ?? 0, isoWeek ?? 0, cursor),
    queryFn: async (): Promise<AreWeWinningDrillThroughPage | null> => {
      if (!eventType || isoYear == null || isoWeek == null) return null;
      try {
        const params = new URLSearchParams();
        params.set('event_type', eventType);
        params.set('iso_year', String(isoYear));
        params.set('iso_week', String(isoWeek));
        if (cursor) params.set('cursor', cursor);
        params.set('limit', String(limit));
        const wire = await apiRequestJson<WireDrillThroughPage>(
          `${AREWEWINNING_API_BASE}/drill-through?${params.toString()}`,
        );
        return adaptAreWeWinningDrillThroughPage(wire);
      } catch {
        return null;
      }
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!eventType && isoYear != null && isoWeek != null && enabled,
    placeholderData: null,
  });
}
