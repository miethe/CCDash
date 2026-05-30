/**
 * MPCC-401: Multi-project Planning Command Center data layer.
 *
 * Typed fetch helpers + explicit snake→camel adapters for:
 *   - GET /api/agent/planning/multi-project/command-center
 *   - GET /api/agent/planning/multi-project/session-board
 *
 * Adapter functions map every wire field to the existing camelCase DTOs in
 * types.ts.  No generic deep-camelize — each field is explicit so that
 * TypeScript can catch missing/renamed fields at compile time.
 *
 * Wire shapes are snake_case (Python convention).  All FE DTOs are camelCase.
 *
 * Endpoints:
 *   command-center: ?status, kind, project_ids (csv), group, search,
 *                    page, page_size, sort (default updated_desc)
 *   session-board:  ?group_by (default state), project_ids, group,
 *                    active_window_minutes (default 30),
 *                    include_workers (default true), page, page_size,
 *                    include_stale (default false)
 */

import { apiRequestJson, ApiError } from './apiClient';
import type {
  AggregateBoardGroup,
  AggregatePagination,
  AggregateSessionCard,
  AggregateSessionWorkerSummary,
  AggregateWorkItem,
  MultiProjectCommandCenterResponse,
  MultiProjectSessionBoardResponse,
  PlanningAgentSessionCard,
  PlanningBoardGroupingMode,
  PlanningCommandCenterItem,
  ProjectDisplayMetadata,
  ProjectIdentityFields,
  ProjectSummary,
  ProjectWarning,
  ProjectWorkItemCounts,
} from '../types';

// Re-export ApiError so callers can import it from this module.
export { ApiError };

// ─── Query param shapes ───────────────────────────────────────────────────────

export interface MultiProjectCommandCenterQuery {
  /** Comma-separated project IDs to include.  Omit for all visible projects. */
  projectIds?: string[];
  /** Work-item status filter, e.g. "active" | "blocked" | "review" | "stale". */
  status?: string;
  /** Work-item kind filter. */
  kind?: string;
  /** Group label filter (matches ProjectDisplayMetadata.group). */
  group?: string;
  /** Free-text search across feature names / summaries. */
  search?: string;
  /** 1-based page number. */
  page?: number;
  /** Items per page. */
  pageSize?: number;
  /** Sort order — backend default is "updated_desc". */
  sort?: string;
}

export interface MultiProjectSessionBoardQuery {
  /** Comma-separated project IDs to include. */
  projectIds?: string[];
  /** Group label filter. */
  group?: string;
  /** Board grouping dimension — backend default is "state". */
  groupBy?: PlanningBoardGroupingMode;
  /** Active-window look-back in minutes — backend default is 30. */
  activeWindowMinutes?: number;
  /** Whether to include worker/subagent summaries — backend default is true. */
  includeWorkers?: boolean;
  /** 1-based page number. */
  page?: number;
  /** Cards per page. */
  pageSize?: number;
  /** Whether to include stale sessions (default false). */
  includeStale?: boolean;
}

// ─── Wire shapes (snake_case from backend) ────────────────────────────────────

interface WireDisplayMetadata {
  color?: string;
  group?: string;
  sort_order?: number;
  label_override?: string;
}

interface WireWorkItemCounts {
  work_items?: number;
  blocked?: number;
  review?: number;
  stale?: number;
  active_sessions?: number;
  errors?: number;
}

interface WireProjectSummary {
  project_id: string;
  name: string;
  display_metadata?: WireDisplayMetadata;
  counts?: WireWorkItemCounts;
  is_stale?: boolean | null;
  error?: string | null;
  last_updated?: string | null;
  freshness_seconds?: number | null;
}

interface WireProjectIdentity {
  project_id: string;
  project_name: string;
  project_color?: string;
  project_group?: string;
}

interface WireProjectWarning {
  project_id: string;
  message: string;
  severity?: string;
  code?: string;
}

interface WireAggregatePagination {
  page?: number;
  page_size?: number;
  total?: number;
  has_more?: boolean;
}

interface WireWorkerSummary {
  session_id: string;
  agent_name?: string;
  state?: string;
  model?: string;
  started_at?: string;
  last_activity_at?: string;
  duration_seconds?: number;
}

// Wire V1 work-item and session-card shapes are passed through as unknown
// and adapted via the existing planningCommandCenter adapter helpers.
// We avoid re-implementing those adapters here — instead we import them.
import {
  adaptPlanningCommandCenterItem,
} from './planningCommandCenter';

// V1 PlanningAgentSessionCard adapter (mirrors backend parsers/sessions.py)
function adaptV1SessionCard(wire: Record<string, unknown>): PlanningAgentSessionCard {
  const correlation = wire.correlation as Record<string, unknown> | null | undefined;
  const tokenSummary = wire.token_summary as Record<string, unknown> | null | undefined;

  function adaptEvidence(arr: unknown[]): import('../types').SessionCorrelationEvidence[] {
    return arr.map((e) => {
      const ev = e as Record<string, unknown>;
      return {
        sourceType: String(ev.source_type ?? ev.sourceType ?? ''),
        sourceLabel: String(ev.source_label ?? ev.sourceLabel ?? ''),
        confidence: (ev.confidence as 'high' | 'medium' | 'low') ?? 'low',
        detail: String(ev.detail ?? ''),
      };
    });
  }

  return {
    sessionId: String(wire.session_id ?? ''),
    agentName: wire.agent_name != null ? String(wire.agent_name) : undefined,
    agentType: wire.agent_type != null ? String(wire.agent_type) : undefined,
    state: (wire.state as PlanningAgentSessionCard['state']) ?? 'unknown',
    model: wire.model != null ? String(wire.model) : undefined,
    correlation: correlation
      ? {
          featureId: String(correlation.feature_id ?? ''),
          featureName: correlation.feature_name != null ? String(correlation.feature_name) : undefined,
          phaseNumber: correlation.phase_number != null ? Number(correlation.phase_number) : undefined,
          confidence: (correlation.confidence as 'high' | 'medium' | 'low') ?? 'low',
          evidence: Array.isArray(correlation.evidence)
            ? adaptEvidence(correlation.evidence)
            : [],
        }
      : undefined,
    transcriptHref: wire.transcript_href != null ? String(wire.transcript_href) : undefined,
    planningHref: wire.planning_href != null ? String(wire.planning_href) : undefined,
    phaseHref: wire.phase_href != null ? String(wire.phase_href) : undefined,
    parentSessionId: wire.parent_session_id != null ? String(wire.parent_session_id) : undefined,
    rootSessionId: wire.root_session_id != null ? String(wire.root_session_id) : undefined,
    startedAt: wire.started_at != null ? String(wire.started_at) : undefined,
    lastActivityAt: wire.last_activity_at != null ? String(wire.last_activity_at) : undefined,
    durationSeconds: wire.duration_seconds != null ? Number(wire.duration_seconds) : undefined,
    tokenSummary: tokenSummary
      ? {
          tokensIn: Number(tokenSummary.tokens_in ?? tokenSummary.tokensIn ?? 0),
          tokensOut: Number(tokenSummary.tokens_out ?? tokenSummary.tokensOut ?? 0),
          totalTokens: Number(tokenSummary.total_tokens ?? tokenSummary.totalTokens ?? 0),
          contextWindowPct: Number(tokenSummary.context_window_pct ?? tokenSummary.contextWindowPct ?? 0),
          model: tokenSummary.model != null ? String(tokenSummary.model) : undefined,
        }
      : undefined,
    relationships: Array.isArray(wire.relationships)
      ? wire.relationships.map((r) => {
          const rel = r as Record<string, unknown>;
          return {
            relatedSessionId: String(rel.related_session_id ?? rel.relatedSessionId ?? ''),
            relationType: (rel.relation_type ?? rel.relationType ?? 'child') as 'parent' | 'root' | 'sibling' | 'child',
            agentName: rel.agent_name != null ? String(rel.agent_name) : undefined,
            state: rel.state != null ? String(rel.state) : undefined,
          };
        })
      : [],
    activityMarkers: Array.isArray(wire.activity_markers)
      ? wire.activity_markers.map((m) => {
          const marker = m as Record<string, unknown>;
          const rawMarkerType = String(marker.marker_type ?? marker.markerType ?? 'tool_call');
          const validMarkerTypes = ['tool_call', 'file_edit', 'command', 'error', 'completion'] as const;
          const markerType = validMarkerTypes.includes(rawMarkerType as typeof validMarkerTypes[number])
            ? (rawMarkerType as typeof validMarkerTypes[number])
            : 'tool_call' as const;
          return {
            markerType,
            label: marker.label != null ? String(marker.label) : '',
            timestamp: marker.timestamp != null ? String(marker.timestamp) : undefined,
            detail: marker.detail != null ? String(marker.detail) : undefined,
          };
        })
      : [],
  };
}

// ─── Adapter functions (snake_case wire → camelCase DTO) ─────────────────────

function adaptDisplayMetadata(wire: WireDisplayMetadata | undefined | null): ProjectDisplayMetadata {
  if (!wire) return {};
  return {
    color: wire.color,
    group: wire.group,
    sortOrder: wire.sort_order,
    labelOverride: wire.label_override,
  };
}

function adaptWorkItemCounts(wire: WireWorkItemCounts | undefined | null): ProjectWorkItemCounts {
  return {
    workItems: Number(wire?.work_items ?? 0),
    blocked: Number(wire?.blocked ?? 0),
    review: Number(wire?.review ?? 0),
    stale: Number(wire?.stale ?? 0),
    activeSessions: Number(wire?.active_sessions ?? 0),
    errors: Number(wire?.errors ?? 0),
  };
}

function adaptProjectSummary(wire: WireProjectSummary): ProjectSummary {
  return {
    projectId: String(wire.project_id ?? ''),
    name: String(wire.name ?? ''),
    displayMetadata: adaptDisplayMetadata(wire.display_metadata),
    counts: adaptWorkItemCounts(wire.counts),
    isStale: wire.is_stale ?? null,
    error: wire.error ?? null,
    lastUpdated: wire.last_updated ?? null,
    freshnessSeconds: wire.freshness_seconds ?? null,
  };
}

function adaptProjectIdentity(wire: WireProjectIdentity): ProjectIdentityFields {
  return {
    projectId: String(wire.project_id ?? ''),
    projectName: String(wire.project_name ?? ''),
    projectColor: wire.project_color,
    projectGroup: wire.project_group,
  };
}

function adaptProjectWarning(wire: WireProjectWarning): ProjectWarning {
  return {
    projectId: String(wire.project_id ?? ''),
    message: String(wire.message ?? ''),
    severity: (wire.severity as ProjectWarning['severity']) ?? 'low',
    code: String(wire.code ?? ''),
  };
}

function adaptPagination(wire: WireAggregatePagination | undefined | null): AggregatePagination {
  return {
    page: Number(wire?.page ?? 1),
    pageSize: Number(wire?.page_size ?? 50),
    total: Number(wire?.total ?? 0),
    hasMore: Boolean(wire?.has_more ?? false),
  };
}

function adaptWorkerSummary(wire: WireWorkerSummary): AggregateSessionWorkerSummary {
  return {
    sessionId: String(wire.session_id ?? ''),
    agentName: wire.agent_name,
    state: String(wire.state ?? 'unknown'),
    model: wire.model,
    startedAt: wire.started_at,
    lastActivityAt: wire.last_activity_at,
    durationSeconds: wire.duration_seconds,
  };
}

function adaptAggregateWorkItem(wire: Record<string, unknown>): AggregateWorkItem {
  return {
    project: adaptProjectIdentity(wire.project as WireProjectIdentity),
    item: adaptPlanningCommandCenterItem(wire.item as Record<string, unknown>),
  };
}

function adaptAggregateSessionCard(wire: Record<string, unknown>): AggregateSessionCard {
  const workersWire = Array.isArray(wire.workers) ? wire.workers : [];
  return {
    project: adaptProjectIdentity(wire.project as WireProjectIdentity),
    card: adaptV1SessionCard(wire.card as Record<string, unknown>),
    workers: workersWire.map((w) => adaptWorkerSummary(w as WireWorkerSummary)),
  };
}

function adaptBoardGroup(wire: Record<string, unknown>): AggregateBoardGroup {
  const cardsWire = Array.isArray(wire.cards) ? wire.cards : [];
  return {
    groupKey: String(wire.group_key ?? ''),
    groupLabel: String(wire.group_label ?? ''),
    groupType: String(wire.group_type ?? 'state'),
    cards: cardsWire.map((c) => adaptAggregateSessionCard(c as Record<string, unknown>)),
    cardCount: Number(wire.card_count ?? cardsWire.length),
  };
}

// ─── Top-level response adapters ──────────────────────────────────────────────

/**
 * Adapts the wire response from
 * GET /api/agent/planning/multi-project/command-center
 * into the camelCase MultiProjectCommandCenterResponse DTO.
 */
export function adaptMultiProjectCommandCenterResponse(
  wire: Record<string, unknown>,
): MultiProjectCommandCenterResponse {
  const itemsWire = Array.isArray(wire.items) ? wire.items : [];
  const summariesWire = Array.isArray(wire.project_summaries) ? wire.project_summaries : [];
  const warningsWire = Array.isArray(wire.warnings) ? wire.warnings : [];

  return {
    status: (wire.status as MultiProjectCommandCenterResponse['status']) ?? 'ok',
    items: itemsWire.map((i) => adaptAggregateWorkItem(i as Record<string, unknown>)),
    projectSummaries: summariesWire.map((s) => adaptProjectSummary(s as WireProjectSummary)),
    pagination: adaptPagination(wire.pagination as WireAggregatePagination | undefined),
    warnings: warningsWire.map((w) => adaptProjectWarning(w as WireProjectWarning)),
    generatedAt: wire.generated_at != null ? String(wire.generated_at) : undefined,
    dataFreshness: wire.data_freshness != null ? String(wire.data_freshness) : undefined,
  };
}

/**
 * Adapts the wire response from
 * GET /api/agent/planning/multi-project/session-board
 * into the camelCase MultiProjectSessionBoardResponse DTO.
 */
export function adaptMultiProjectSessionBoardResponse(
  wire: Record<string, unknown>,
): MultiProjectSessionBoardResponse {
  const groupsWire = Array.isArray(wire.groups) ? wire.groups : [];
  const summariesWire = Array.isArray(wire.project_summaries) ? wire.project_summaries : [];
  const warningsWire = Array.isArray(wire.warnings) ? wire.warnings : [];

  return {
    status: (wire.status as MultiProjectSessionBoardResponse['status']) ?? 'ok',
    grouping: String(wire.grouping ?? 'state'),
    groups: groupsWire.map((g) => adaptBoardGroup(g as Record<string, unknown>)),
    projectSummaries: summariesWire.map((s) => adaptProjectSummary(s as WireProjectSummary)),
    pagination: adaptPagination(wire.pagination as WireAggregatePagination | undefined),
    warnings: warningsWire.map((w) => adaptProjectWarning(w as WireProjectWarning)),
    totalCardCount: Number(wire.total_card_count ?? 0),
    activeCount: Number(wire.active_count ?? 0),
    completedCount: Number(wire.completed_count ?? 0),
    generatedAt: wire.generated_at != null ? String(wire.generated_at) : undefined,
    dataFreshness: wire.data_freshness != null ? String(wire.data_freshness) : undefined,
  };
}

// ─── Fetch helpers ────────────────────────────────────────────────────────────

function appendParam(
  params: URLSearchParams,
  key: string,
  value: string | number | boolean | undefined,
): void {
  if (value === undefined || value === null || value === '') return;
  params.set(key, String(value));
}

function buildCommandCenterParams(query: MultiProjectCommandCenterQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.projectIds && query.projectIds.length > 0) {
    params.set('project_ids', query.projectIds.join(','));
  }
  appendParam(params, 'status', query.status);
  appendParam(params, 'kind', query.kind);
  appendParam(params, 'group', query.group);
  appendParam(params, 'search', query.search);
  appendParam(params, 'page', query.page);
  appendParam(params, 'page_size', query.pageSize);
  appendParam(params, 'sort', query.sort);
  return params;
}

function buildSessionBoardParams(query: MultiProjectSessionBoardQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.projectIds && query.projectIds.length > 0) {
    params.set('project_ids', query.projectIds.join(','));
  }
  appendParam(params, 'group', query.group);
  appendParam(params, 'group_by', query.groupBy);
  appendParam(params, 'active_window_minutes', query.activeWindowMinutes);
  if (query.includeWorkers !== undefined) {
    params.set('include_workers', String(query.includeWorkers));
  }
  appendParam(params, 'page', query.page);
  appendParam(params, 'page_size', query.pageSize);
  if (query.includeStale !== undefined) {
    params.set('include_stale', String(query.includeStale));
  }
  return params;
}

/**
 * Fetches the multi-project aggregate command center.
 * Throws ApiError on HTTP failure.
 */
export async function fetchMultiProjectCommandCenter(
  query: MultiProjectCommandCenterQuery = {},
): Promise<MultiProjectCommandCenterResponse> {
  const params = buildCommandCenterParams(query);
  const qs = params.toString();
  const path = `/api/agent/planning/multi-project/command-center${qs ? `?${qs}` : ''}`;
  const wire = await apiRequestJson<Record<string, unknown>>(path);
  return adaptMultiProjectCommandCenterResponse(wire);
}

/**
 * Fetches the multi-project aggregate session board.
 * Throws ApiError on HTTP failure.
 */
export async function fetchMultiProjectSessionBoard(
  query: MultiProjectSessionBoardQuery = {},
): Promise<MultiProjectSessionBoardResponse> {
  const params = buildSessionBoardParams(query);
  const qs = params.toString();
  const path = `/api/agent/planning/multi-project/session-board${qs ? `?${qs}` : ''}`;
  const wire = await apiRequestJson<Record<string, unknown>>(path);
  return adaptMultiProjectSessionBoardResponse(wire);
}

// Re-export V1 item adapter so tests can exercise the adapter independently.
export { adaptPlanningCommandCenterItem as adaptV1WorkItem };
export type { PlanningCommandCenterItem };
