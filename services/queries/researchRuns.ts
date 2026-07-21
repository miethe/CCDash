/**
 * TanStack Query hooks for the Research Foundry run-telemetry domain
 * (research-foundry-run-telemetry-v1, Phase 3).
 *
 * T3-002: useResearchRuns / useResearchRunDetail — backed by
 * GET /api/agent/research-runs (+ /{run_id}).
 *
 * Wire contract (T3-000 seam finding, see
 * .claude/worknotes/research-foundry-run-telemetry/p3-contract-mapping.md):
 * `ResearchRunSummaryDTO` / `ResearchRunDetailDTO` / `ResearchRunListResponseDTO` /
 * `ResearchRunDetailResponseDTO` (backend/application/services/agent_queries/
 * run_intelligence.py) declare no `alias_generator` — the wire payload is pure
 * snake_case. Snake_case → camelCase adaptation happens client-side, in this
 * query-hook module, via internal WireResearchRun/WireResearchRunDetail shapes —
 * the same pattern as WirePlanningViewBundle in usePlanningViewQuery (this
 * directory's planning.ts). The public ResearchRun/ResearchRunDetail types
 * (types.ts) are never the raw wire shape.
 *
 * Structural note: the backend has NO nested `metrics` sub-object — every
 * metric field is flat and top-level on the run DTO (see types.ts's
 * ResearchRun docstring). ResearchRunMetrics (types.ts) is a client-side-only
 * derived/subset type for panel props; it is never adapted from a distinct
 * wire shape.
 */

import { useQuery } from '@tanstack/react-query';
import { apiRequestJson } from '../apiClient';
import { researchRunsKeys } from '../queryKeys';
import type {
  ResearchRun,
  ResearchRunDetail,
  ResearchRunListResponse,
  ResearchRunDetailResponse,
} from '../../types';

const RESEARCH_RUNS_API_BASE = '/api/agent/research-runs';

// ── Wire shapes (snake_case, 1:1 with run_intelligence.py DTOs) ───────────────

interface WireEnvelopeFields {
  status: 'ok' | 'partial' | 'error';
  data_freshness: string;
  generated_at: string;
  source_refs: string[];
}

/** Mirrors `ResearchRunSummaryDTO` (run_intelligence.py:194-264). */
interface WireResearchRun {
  run_id: string;
  rf_run_id: string | null;
  project_id: string;
  workspace_id: string;
  intent_id: string | null;
  task_node_id: string | null;
  rf_project: string | null;
  event_count: number;
  first_event_at: string | null;
  last_event_at: string | null;
  queries_executed: number | null;
  urls_extracted: number | null;
  useful_source_count: number | null;
  tokens_estimated: number | null;
  claims_total: number | null;
  claims_supported: number | null;
  claims_mixed: number | null;
  claims_contradicted: number | null;
  unsupported_claims: number | null;
  estimated_cost_usd: number | null;
  latency_ms: number | null;
  citation_coverage: number | null;
  duplicate_rate: number | null;
  extraction_failure_rate: number | null;
  quality_score: string | null;
  drift_score: number | null;
  mode: string | null;
  selected_providers: string[] | null;
  governance_sensitivity: string | null;
  governance_policy_passed: boolean | null;
  human_review_required: boolean | null;
  human_review_status: string | null;
  human_review_reviewer: string | null;
  reuse_meatywiki_writeback_candidate: boolean | null;
  reuse_skillbom_candidate: boolean | null;
  reuse_reusable_source_pack_candidate: boolean | null;
  linked_session_id: string | null;
  linked_session_ids: string[];
  created_at: string | null;
  updated_at: string | null;
}

/** Mirrors `ResearchRunDetailDTO` (run_intelligence.py:266-277) — additive-only. */
interface WireResearchRunDetail extends WireResearchRun {
  agent_postures: string[] | null;
  skillbom_ids: string[] | null;
  tools: string[] | null;
  input_artifacts: string[] | null;
  output_artifacts: string[] | null;
}

/** Mirrors `ResearchRunListResponseDTO` — the GET /api/agent/research-runs envelope. */
interface WireResearchRunListResponse extends WireEnvelopeFields {
  project_id: string;
  items: WireResearchRun[];
  cursor: string;
  limit: number;
  next_cursor: string | null;
}

/** Mirrors `ResearchRunDetailResponseDTO` — the GET /api/agent/research-runs/{run_id} envelope. */
interface WireResearchRunDetailResponse extends WireEnvelopeFields {
  project_id: string;
  run_id: string;
  found: boolean;
  run: WireResearchRunDetail | null;
}

// ── Adapters (snake_case wire → camelCase public contract) ───────────────────

function adaptEnvelopeFields(wire: WireEnvelopeFields) {
  return {
    status: wire.status,
    dataFreshness: wire.data_freshness,
    generatedAt: wire.generated_at,
    sourceRefs: wire.source_refs ?? [],
  };
}

/**
 * Adapt a single wire run row to the camelCase ResearchRun shape. Exported so
 * tests can exercise the mapping directly without hitting the network.
 */
export function adaptResearchRun(wire: WireResearchRun): ResearchRun {
  return {
    runId: wire.run_id,
    rfRunId: wire.rf_run_id ?? null,
    projectId: wire.project_id,
    workspaceId: wire.workspace_id,
    intentId: wire.intent_id ?? null,
    taskNodeId: wire.task_node_id ?? null,
    rfProject: wire.rf_project ?? null,
    eventCount: wire.event_count ?? 0,
    firstEventAt: wire.first_event_at ?? null,
    lastEventAt: wire.last_event_at ?? null,
    queriesExecuted: wire.queries_executed ?? null,
    urlsExtracted: wire.urls_extracted ?? null,
    usefulSourceCount: wire.useful_source_count ?? null,
    tokensEstimated: wire.tokens_estimated ?? null,
    claimsTotal: wire.claims_total ?? null,
    claimsSupported: wire.claims_supported ?? null,
    claimsMixed: wire.claims_mixed ?? null,
    claimsContradicted: wire.claims_contradicted ?? null,
    unsupportedClaims: wire.unsupported_claims ?? null,
    estimatedCostUsd: wire.estimated_cost_usd ?? null,
    latencyMs: wire.latency_ms ?? null,
    citationCoverage: wire.citation_coverage ?? null,
    duplicateRate: wire.duplicate_rate ?? null,
    extractionFailureRate: wire.extraction_failure_rate ?? null,
    qualityScore: wire.quality_score ?? null,
    driftScore: wire.drift_score ?? null,
    mode: wire.mode ?? null,
    selectedProviders: wire.selected_providers ?? null,
    governanceSensitivity: wire.governance_sensitivity ?? null,
    governancePolicyPassed: wire.governance_policy_passed ?? null,
    humanReviewRequired: wire.human_review_required ?? null,
    humanReviewStatus: wire.human_review_status ?? null,
    humanReviewReviewer: wire.human_review_reviewer ?? null,
    reuseMeatywikiWritebackCandidate: wire.reuse_meatywiki_writeback_candidate ?? null,
    reuseSkillbomCandidate: wire.reuse_skillbom_candidate ?? null,
    reuseReusableSourcePackCandidate: wire.reuse_reusable_source_pack_candidate ?? null,
    linkedSessionId: wire.linked_session_id ?? null,
    linkedSessionIds: wire.linked_session_ids ?? [],
    createdAt: wire.created_at ?? null,
    updatedAt: wire.updated_at ?? null,
  };
}

/**
 * Adapt a single wire run-detail row (additive-only over the summary shape).
 * Exported so tests can exercise the mapping directly without hitting the
 * network.
 */
export function adaptResearchRunDetail(wire: WireResearchRunDetail): ResearchRunDetail {
  return {
    ...adaptResearchRun(wire),
    agentPostures: wire.agent_postures ?? null,
    skillbomIds: wire.skillbom_ids ?? null,
    tools: wire.tools ?? null,
    inputArtifacts: wire.input_artifacts ?? null,
    outputArtifacts: wire.output_artifacts ?? null,
  };
}

// ── useResearchRuns ───────────────────────────────────────────────────────────

export interface UseResearchRunsOptions {
  projectId: string | null | undefined;
  /** Opaque backend pagination cursor. Omit/null for page 1. */
  cursor?: string | null;
  /** Max items per page (backend default 50, max 200). */
  limit?: number;
  /** Bypass the server-side query cache and fetch fresh data. */
  bypassCache?: boolean;
  /** Set false to suppress the query (e.g. project not yet loaded). */
  enabled?: boolean;
}

/**
 * Cursor-paginated page of Research Foundry `research_runs` rollups
 * (newest-first, by `last_event_at`).
 *
 * Mirrors: GET /api/agent/research-runs
 *
 * Cache policy: TanStack Query, staleTime 30s / gcTime 5min — matches the
 * sibling planning/session list hooks (docs/guides/feature-surface-architecture.md
 * § Cache Tiers). Keyed via researchRunsKeys.list(projectId, cursor, limit) so
 * each page occupies its own cache slot; fetch until `nextCursor` is `null`.
 */
export function useResearchRuns({
  projectId,
  cursor = null,
  limit,
  bypassCache = false,
  enabled = true,
}: UseResearchRunsOptions) {
  return useQuery<ResearchRunListResponse>({
    queryKey: researchRunsKeys.list(projectId ?? '', cursor, limit),
    queryFn: async (): Promise<ResearchRunListResponse> => {
      if (!projectId) throw new Error('projectId is required');
      const params = new URLSearchParams();
      params.set('project_id', projectId);
      if (cursor) params.set('cursor', cursor);
      if (limit != null) params.set('limit', String(limit));
      if (bypassCache) params.set('bypass_cache', 'true');

      const wire = await apiRequestJson<WireResearchRunListResponse>(
        `${RESEARCH_RUNS_API_BASE}?${params.toString()}`,
      );

      return {
        ...adaptEnvelopeFields(wire),
        projectId: wire.project_id ?? '',
        items: (wire.items ?? []).map(adaptResearchRun),
        cursor: wire.cursor ?? '',
        limit: wire.limit ?? 0,
        nextCursor: wire.next_cursor ?? null,
      };
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
  });
}

// ── useResearchRunDetail ──────────────────────────────────────────────────────

export interface UseResearchRunDetailOptions {
  projectId: string | null | undefined;
  runId: string | null | undefined;
  /** Bypass the server-side query cache and fetch fresh data. */
  bypassCache?: boolean;
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * Single Research Foundry run rollup plus its linked-session summary and the
 * detail-only additive fields (agentPostures, skillbomIds, tools,
 * inputArtifacts, outputArtifacts).
 *
 * Mirrors: GET /api/agent/research-runs/{run_id}
 *
 * `found: false, run: null` is the documented normal "no such run" shape
 * (status "ok") — consumers must branch on `found`, not treat a resolved
 * query as an error, for the "run not found" empty state.
 *
 * Cache policy: TanStack Query, staleTime 30s / gcTime 5min. Keyed via
 * researchRunsKeys.detail(projectId, runId).
 */
export function useResearchRunDetail({
  projectId,
  runId,
  bypassCache = false,
  enabled = true,
}: UseResearchRunDetailOptions) {
  return useQuery<ResearchRunDetailResponse>({
    queryKey: researchRunsKeys.detail(projectId ?? '', runId ?? ''),
    queryFn: async (): Promise<ResearchRunDetailResponse> => {
      if (!runId) throw new Error('runId is required');
      const params = new URLSearchParams();
      if (projectId) params.set('project_id', projectId);
      if (bypassCache) params.set('bypass_cache', 'true');
      const qs = params.toString();

      const wire = await apiRequestJson<WireResearchRunDetailResponse>(
        `${RESEARCH_RUNS_API_BASE}/${encodeURIComponent(runId)}${qs ? `?${qs}` : ''}`,
      );

      return {
        ...adaptEnvelopeFields(wire),
        projectId: wire.project_id ?? '',
        runId: wire.run_id ?? runId,
        found: wire.found ?? false,
        run: wire.run ? adaptResearchRunDetail(wire.run) : null,
      };
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && !!runId && enabled,
  });
}
