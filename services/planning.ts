// Wire format from the backend is snake_case. This module adapts all responses
// to camelCase before returning them, matching the convention used by analytics.ts
// and other domain helpers in this directory.

import type {
  FeaturePlanningContext,
  FeatureSummaryItem,
  FeatureTokenRollup,
  PhaseContextItem,
  PhaseOperations,
  PhaseTaskItem,
  PlanningEdge,
  PlanningNode,
  PlanningNodeCountsByType,
  PlanningPhaseBatch,
  ProjectPlanningGraph,
  ProjectPlanningSummary,
} from '../types';
import type { AgentQueryEnvelope } from '../types';

const API_BASE = '/api/agent/planning';

// ── Error type ────────────────────────────────────────────────────────────────

export class PlanningApiError extends Error {
  status: number;
  envelopeStatus: 'ok' | 'partial' | 'error';

  constructor(message: string, httpStatus: number, envelopeStatus: 'ok' | 'partial' | 'error' = 'error') {
    super(message);
    this.name = 'PlanningApiError';
    this.status = httpStatus;
    this.envelopeStatus = envelopeStatus;
  }
}

// ── Internal fetch helper ─────────────────────────────────────────────────────

async function planningFetch<T>(path: string, params?: URLSearchParams): Promise<T> {
  const qs = params?.toString();
  const url = `${API_BASE}${path}${qs ? `?${qs}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new PlanningApiError(
      `Planning API error: ${res.status} ${res.statusText} for ${url}`,
      res.status,
    );
  }
  return res.json() as Promise<T>;
}

// ── Snake-case wire shapes (internal) ─────────────────────────────────────────

interface WireEnvelope {
  status: 'ok' | 'partial' | 'error';
  data_freshness: string;
  generated_at: string;
  source_refs: string[];
}

interface WireNodeCountsByType {
  prd: number;
  design_spec: number;
  implementation_plan: number;
  progress: number;
  context: number;
  tracker: number;
  report: number;
}

interface WireFeatureSummaryItem {
  feature_id: string;
  feature_name: string;
  raw_status: string;
  effective_status: string;
  is_mismatch: boolean;
  mismatch_state: string;
  has_blocked_phases: boolean;
  phase_count: number;
  blocked_phase_count: number;
  node_count: number;
}

interface WireProjectPlanningSummary extends WireEnvelope {
  project_id: string;
  project_name: string;
  total_feature_count: number;
  active_feature_count: number;
  stale_feature_count: number;
  blocked_feature_count: number;
  mismatch_count: number;
  reversal_count: number;
  stale_feature_ids: string[];
  reversal_feature_ids: string[];
  blocked_feature_ids: string[];
  node_counts_by_type: WireNodeCountsByType;
  feature_summaries: WireFeatureSummaryItem[];
}

interface WireFeatureModelTokens {
  model: string;
  total_tokens: number;
  token_input?: number;
  token_output?: number;
}

interface WireFeatureTokenRollup {
  feature_slug: string;
  story_points: number;
  total_tokens: number;
  by_model: WireFeatureModelTokens[];
}

interface WireProjectPlanningGraph extends WireEnvelope {
  project_id: string;
  feature_id: string | null;
  depth: number | null;
  nodes: Record<string, unknown>[];
  edges: Record<string, unknown>[];
  phase_batches: Record<string, unknown>[];
  node_count: number;
  edge_count: number;
  /** T7-004: per-feature token + story-point rollups, keyed by featureSlug. */
  feature_token_rollups?: Record<string, WireFeatureTokenRollup>;
}

interface WirePhaseContextItem {
  phase_id: string;
  phase_token: string;
  phase_title: string;
  raw_status: string;
  effective_status: string;
  is_mismatch: boolean;
  mismatch_state: string;
  planning_status: Record<string, unknown>;
  batches: Record<string, unknown>[];
  blocked_batch_ids: string[];
  total_tasks: number;
  completed_tasks: number;
  deferred_tasks: number;
}

interface WireFeaturePlanningContext extends WireEnvelope {
  feature_id: string;
  feature_name: string;
  raw_status: string;
  effective_status: string;
  mismatch_state: string;
  planning_status: Record<string, unknown>;
  graph: Record<string, unknown>;
  phases: WirePhaseContextItem[];
  blocked_batch_ids: string[];
  linked_artifact_refs: string[];
}

interface WirePhaseTaskItem {
  task_id: string;
  title: string;
  status: string;
  assignees: string[];
  blockers: string[];
  batch_id: string;
}

interface WirePhaseOperations extends WireEnvelope {
  feature_id: string;
  phase_number: number;
  phase_token: string;
  phase_title: string;
  raw_status: string;
  effective_status: string;
  is_ready: boolean;
  readiness_state: string;
  phase_batches: Record<string, unknown>[];
  blocked_batch_ids: string[];
  tasks: WirePhaseTaskItem[];
  dependency_resolution: Record<string, unknown>;
  progress_evidence: string[];
}

// ── Adapters (snake_case → camelCase) ─────────────────────────────────────────

function adaptEnvelope(wire: WireEnvelope): AgentQueryEnvelope {
  return {
    status: wire.status,
    dataFreshness: wire.data_freshness,
    generatedAt: wire.generated_at,
    sourceRefs: wire.source_refs ?? [],
  };
}

/** Check envelope status="error" and throw a PlanningApiError with a 404 code.
 *  The backend raises HTTP 404 for missing entities, but we guard the
 *  sentinel path (status="error" + empty primary field) here too for resilience. */
function guardEnvelopeError(
  envelope: WireEnvelope,
  hint: string,
  isMissing: boolean,
): void {
  if (envelope.status === 'error' && isMissing) {
    throw new PlanningApiError(hint, 404, 'error');
  }
}

function adaptNodeCountsByType(wire: WireNodeCountsByType): PlanningNodeCountsByType {
  return {
    prd: wire.prd ?? 0,
    designSpec: wire.design_spec ?? 0,
    implementationPlan: wire.implementation_plan ?? 0,
    progress: wire.progress ?? 0,
    context: wire.context ?? 0,
    tracker: wire.tracker ?? 0,
    report: wire.report ?? 0,
  };
}

function adaptFeatureSummaryItem(wire: WireFeatureSummaryItem): FeatureSummaryItem {
  return {
    featureId: wire.feature_id ?? '',
    featureName: wire.feature_name ?? '',
    rawStatus: wire.raw_status ?? '',
    effectiveStatus: wire.effective_status ?? '',
    isMismatch: wire.is_mismatch ?? false,
    mismatchState: wire.mismatch_state ?? 'unknown',
    hasBlockedPhases: wire.has_blocked_phases ?? false,
    phaseCount: wire.phase_count ?? 0,
    blockedPhaseCount: wire.blocked_phase_count ?? 0,
    nodeCount: wire.node_count ?? 0,
  };
}

// Planning primitives arrive as plain dicts; cast them using the existing
// frontend types (PlanningNode, PlanningEdge, PlanningPhaseBatch).
// Phase 3 consumers should treat these as structurally compatible but not
// deeply validated — full validation happens on the backend.
function castNodes(dicts: Record<string, unknown>[]): PlanningNode[] {
  return dicts as unknown as PlanningNode[];
}

function castEdges(dicts: Record<string, unknown>[]): PlanningEdge[] {
  return dicts as unknown as PlanningEdge[];
}

function castPhaseBatches(dicts: Record<string, unknown>[]): PlanningPhaseBatch[] {
  return dicts as unknown as PlanningPhaseBatch[];
}

function adaptFeatureTokenRollups(
  wire: Record<string, WireFeatureTokenRollup> | undefined,
): Record<string, FeatureTokenRollup> | undefined {
  if (!wire) return undefined;
  const result: Record<string, FeatureTokenRollup> = {};
  for (const [slug, r] of Object.entries(wire)) {
    result[slug] = {
      featureSlug: r.feature_slug ?? slug,
      storyPoints: r.story_points ?? 0,
      totalTokens: r.total_tokens ?? 0,
      byModel: (r.by_model ?? []).map(m => ({
        model: m.model ?? '',
        totalTokens: m.total_tokens ?? 0,
        tokenInput: m.token_input,
        tokenOutput: m.token_output,
      })),
    };
  }
  return result;
}

function adaptPhaseContextItem(wire: WirePhaseContextItem): PhaseContextItem {
  return {
    phaseId: wire.phase_id ?? '',
    phaseToken: wire.phase_token ?? '',
    phaseTitle: wire.phase_title ?? '',
    rawStatus: wire.raw_status ?? '',
    effectiveStatus: wire.effective_status ?? '',
    isMismatch: wire.is_mismatch ?? false,
    mismatchState: wire.mismatch_state ?? 'unknown',
    planningStatus: wire.planning_status ?? {},
    batches: castPhaseBatches(wire.batches ?? []),
    blockedBatchIds: wire.blocked_batch_ids ?? [],
    totalTasks: wire.total_tasks ?? 0,
    completedTasks: wire.completed_tasks ?? 0,
    deferredTasks: wire.deferred_tasks ?? 0,
  };
}

function adaptPhaseTaskItem(wire: WirePhaseTaskItem): PhaseTaskItem {
  return {
    taskId: wire.task_id ?? '',
    title: wire.title ?? '',
    status: wire.status ?? '',
    assignees: wire.assignees ?? [],
    blockers: wire.blockers ?? [],
    batchId: wire.batch_id ?? '',
  };
}

// ── Public API helpers ────────────────────────────────────────────────────────

/**
 * Fetch project-level planning health counts and per-feature summaries.
 *
 * Mirrors: GET /api/agent/planning/summary
 */
export async function getProjectPlanningSummary(projectId?: string): Promise<ProjectPlanningSummary> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const wire = await planningFetch<WireProjectPlanningSummary>('/summary', params.toString() ? params : undefined);

  return {
    ...adaptEnvelope(wire),
    projectId: wire.project_id ?? '',
    projectName: wire.project_name ?? '',
    totalFeatureCount: wire.total_feature_count ?? 0,
    activeFeatureCount: wire.active_feature_count ?? 0,
    staleFeatureCount: wire.stale_feature_count ?? 0,
    blockedFeatureCount: wire.blocked_feature_count ?? 0,
    mismatchCount: wire.mismatch_count ?? 0,
    reversalCount: wire.reversal_count ?? 0,
    staleFeatureIds: wire.stale_feature_ids ?? [],
    reversalFeatureIds: wire.reversal_feature_ids ?? [],
    blockedFeatureIds: wire.blocked_feature_ids ?? [],
    nodeCountsByType: adaptNodeCountsByType(wire.node_counts_by_type ?? {} as WireNodeCountsByType),
    featureSummaries: (wire.feature_summaries ?? []).map(adaptFeatureSummaryItem),
  };
}

/**
 * Fetch aggregated planning graph nodes and edges for the project or a feature seed.
 *
 * Mirrors: GET /api/agent/planning/graph
 */
export async function getProjectPlanningGraph(opts?: {
  projectId?: string;
  featureId?: string;
  depth?: number;
}): Promise<ProjectPlanningGraph> {
  const params = new URLSearchParams();
  if (opts?.projectId) params.set('project_id', opts.projectId);
  if (opts?.featureId) params.set('feature_id', opts.featureId);
  if (typeof opts?.depth === 'number') params.set('depth', String(opts.depth));

  const wire = await planningFetch<WireProjectPlanningGraph>('/graph', params.toString() ? params : undefined);

  // Surface the sentinel 404 path (feature_id supplied but entity missing).
  guardEnvelopeError(wire, `Feature '${opts?.featureId}' not found in planning graph.`, !!(opts?.featureId) && !wire.nodes?.length);

  return {
    ...adaptEnvelope(wire),
    projectId: wire.project_id ?? '',
    featureId: wire.feature_id ?? null,
    depth: wire.depth ?? null,
    nodes: castNodes(wire.nodes ?? []),
    edges: castEdges(wire.edges ?? []),
    phaseBatches: castPhaseBatches(wire.phase_batches ?? []),
    nodeCount: wire.node_count ?? 0,
    edgeCount: wire.edge_count ?? 0,
    featureTokenRollups: adaptFeatureTokenRollups(wire.feature_token_rollups),
  };
}

/**
 * Fetch one feature's planning subgraph, status provenance, and per-phase context.
 *
 * Mirrors: GET /api/agent/planning/features/{featureId}
 */
export async function getFeaturePlanningContext(
  featureId: string,
  opts?: { projectId?: string },
): Promise<FeaturePlanningContext> {
  const params = new URLSearchParams();
  if (opts?.projectId) params.set('project_id', opts.projectId);

  const wire = await planningFetch<WireFeaturePlanningContext>(
    `/features/${encodeURIComponent(featureId)}`,
    params.toString() ? params : undefined,
  );

  // Sentinel: status="error" + empty feature_name means entity not found.
  guardEnvelopeError(wire, `Feature '${featureId}' not found.`, !wire.feature_name);

  const rawGraph = wire.graph ?? {};
  return {
    ...adaptEnvelope(wire),
    featureId: wire.feature_id ?? featureId,
    featureName: wire.feature_name ?? '',
    rawStatus: wire.raw_status ?? '',
    effectiveStatus: wire.effective_status ?? '',
    mismatchState: wire.mismatch_state ?? 'unknown',
    planningStatus: wire.planning_status ?? {},
    graph: {
      nodes: castNodes((rawGraph.nodes as Record<string, unknown>[] | undefined) ?? []),
      edges: castEdges((rawGraph.edges as Record<string, unknown>[] | undefined) ?? []),
      phaseBatches: castPhaseBatches((rawGraph.phase_batches as Record<string, unknown>[] | undefined) ?? []),
    },
    phases: (wire.phases ?? []).map(adaptPhaseContextItem),
    blockedBatchIds: wire.blocked_batch_ids ?? [],
    linkedArtifactRefs: wire.linked_artifact_refs ?? [],
  };
}

/**
 * Fetch operational detail — batch readiness, tasks, and dependency state — for
 * a single phase.
 *
 * Mirrors: GET /api/agent/planning/features/{featureId}/phases/{phaseNumber}
 */
export async function getPhaseOperations(
  featureId: string,
  phaseNumber: number,
  opts?: { projectId?: string },
): Promise<PhaseOperations> {
  const params = new URLSearchParams();
  if (opts?.projectId) params.set('project_id', opts.projectId);

  const wire = await planningFetch<WirePhaseOperations>(
    `/features/${encodeURIComponent(featureId)}/phases/${phaseNumber}`,
    params.toString() ? params : undefined,
  );

  // Sentinel: status="error" + empty phase_token means phase not found.
  guardEnvelopeError(wire, `Phase ${phaseNumber} for feature '${featureId}' not found.`, !wire.phase_token);

  return {
    ...adaptEnvelope(wire),
    featureId: wire.feature_id ?? featureId,
    phaseNumber: wire.phase_number ?? phaseNumber,
    phaseToken: wire.phase_token ?? '',
    phaseTitle: wire.phase_title ?? '',
    rawStatus: wire.raw_status ?? '',
    effectiveStatus: wire.effective_status ?? '',
    isReady: wire.is_ready ?? false,
    readinessState: wire.readiness_state ?? 'unknown',
    phaseBatches: castPhaseBatches(wire.phase_batches ?? []),
    blockedBatchIds: wire.blocked_batch_ids ?? [],
    tasks: (wire.tasks ?? []).map(adaptPhaseTaskItem),
    dependencyResolution: wire.dependency_resolution ?? {},
    progressEvidence: wire.progress_evidence ?? [],
  };
}
