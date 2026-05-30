// Wire format from the backend is snake_case. This module adapts all responses
// to camelCase before returning them, matching the convention used by analytics.ts
// and other domain helpers in this directory.

import type {
  FeaturePlanningContext,
  FeatureSummaryItem,
  PlanningArtifactRef,
  FeatureTokenRollup,
  PlanningOpenQuestionItem,
  PhaseContextItem,
  PhaseOperations,
  PhaseTaskItem,
  PlanningEdge,
  PlanningNode,
  PlanningNodeCountsByType,
  PlanningPhaseBatch,
  PlanningSpikeItem,
  PlanningTokenUsageByModel,
  ProjectPlanningGraph,
  ProjectPlanningSummary,
  PlanningStatusCounts,
  PlanningCtxPerPhase,
  PlanningTokenTelemetry,
  PlanningAgentSessionBoard,
  PlanningAgentSessionCard,
  PlanningBoardGroup,
  PlanningBoardGroupingMode,
  SessionCorrelation,
  SessionCorrelationEvidence,
  BoardSessionRelationship,
  SessionActivityMarker,
  SessionTokenSummary,
  NextRunContextRef,
  PlanningNextRunPreview,
  PromptContextSelection,
} from '../types';
import type { AgentQueryEnvelope } from '../types';
import type { PlanningStatusBucket } from './planningRoutes';
import { apiFetch } from './apiClient';

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
  const res = await apiFetch(url);
  if (!res.ok) {
    throw new PlanningApiError(
      `Planning API error: ${res.status} ${res.statusText} for ${url}`,
      res.status,
    );
  }
  return res.json() as Promise<T>;
}


async function planningWriteFetch<T>(
  path: string,
  init: RequestInit,
  base = API_BASE,
): Promise<T> {
  const url = `${base}${path}`;
  const { headers, ...rest } = init;
  const res = await apiFetch(url, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      ...(headers ?? {}),
    },
  });
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

interface WireStatusCounts {
  shaping: number;
  planned: number;
  active: number;
  blocked: number;
  review: number;
  completed: number;
  deferred: number;
  stale_or_mismatched: number;
}

interface WireCtxPerPhase {
  context_count: number;
  phase_count: number;
  ratio: number | null;
  source: 'backend' | 'unavailable';
}

interface WireTokenTelemetryEntry {
  model_family: string;
  total_tokens: number;
}

interface WireTokenTelemetry {
  total_tokens: number | null;
  by_model_family: WireTokenTelemetryEntry[];
  source: 'session_attribution' | 'unavailable';
}

export interface WireProjectPlanningSummary extends WireEnvelope {
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
  status_counts?: WireStatusCounts;
  ctx_per_phase?: WireCtxPerPhase | null;
  token_telemetry?: WireTokenTelemetry | null;
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

interface WirePlanningArtifactRef {
  artifact_id: string;
  title: string;
  file_path: string;
  canonical_path: string;
  doc_type: string;
  status: string;
  updated_at: string;
  source_ref: string;
}

interface WirePlanningSpikeItem {
  spike_id: string;
  title: string;
  status: string;
  file_path: string;
  source_ref: string;
}

interface WirePlanningOpenQuestionItem {
  oq_id: string;
  question: string;
  severity: string;
  answer_text: string;
  resolved: boolean;
  pending_sync: boolean;
  source_document_id: string;
  source_document_path: string;
  updated_at: string;
}

interface WireOpenQuestionResolution {
  feature_id: string;
  oq: WirePlanningOpenQuestionItem;
}

interface WirePlanningTokenUsageByModel {
  opus: number;
  sonnet: number;
  haiku: number;
  other: number;
  total: number;
}

export interface WireProjectPlanningGraph extends WireEnvelope {
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
  specs?: WirePlanningArtifactRef[];
  prds?: WirePlanningArtifactRef[];
  plans?: WirePlanningArtifactRef[];
  ctxs?: WirePlanningArtifactRef[];
  reports?: WirePlanningArtifactRef[];
  spikes?: WirePlanningSpikeItem[];
  open_questions?: WirePlanningOpenQuestionItem[];
  ready_to_promote?: boolean;
  is_stale?: boolean;
  total_tokens?: number;
  token_usage_by_model?: WirePlanningTokenUsageByModel;
  category?: string;
  slug?: string;
  complexity?: string;
  tags?: string[];
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

// ── Session-board wire shapes ─────────────────────────────────────────────────

interface WireSessionCorrelationEvidence {
  source_type: string;
  source_id?: string;
  source_label: string;
  confidence: 'high' | 'medium' | 'low' | 'unknown';
  detail?: string;
}

interface WireSessionCorrelation {
  feature_id?: string;
  feature_name?: string;
  phase_number?: number;
  phase_title?: string;
  batch_id?: string;
  task_id?: string;
  task_title?: string;
  confidence: 'high' | 'medium' | 'low' | 'unknown';
  evidence: WireSessionCorrelationEvidence[];
}

interface WireBoardSessionRelationship {
  related_session_id: string;
  relation_type: 'parent' | 'root' | 'sibling' | 'child';
  agent_name?: string;
  state?: string;
}

interface WireSessionActivityMarker {
  marker_type: 'tool_call' | 'file_edit' | 'command' | 'error' | 'completion';
  label: string;
  timestamp?: string;
  detail?: string;
}

interface WireSessionTokenSummary {
  tokens_in: number;
  tokens_out: number;
  total_tokens: number;
  context_window_pct?: number;
  model?: string;
}

interface WirePlanningAgentSessionCard {
  session_id: string;
  agent_name?: string;
  agent_type?: string;
  state: 'running' | 'thinking' | 'completed' | 'failed' | 'cancelled' | 'unknown';
  model?: string;
  correlation?: WireSessionCorrelation;
  transcript_href?: string;
  planning_href?: string;
  phase_href?: string;
  parent_session_id?: string;
  root_session_id?: string;
  started_at?: string;
  last_activity_at?: string;
  duration_seconds?: number;
  token_summary?: WireSessionTokenSummary;
  relationships: WireBoardSessionRelationship[];
  activity_markers: WireSessionActivityMarker[];
}

interface WirePlanningBoardGroup {
  group_key: string;
  group_label: string;
  group_type: 'state' | 'feature' | 'phase' | 'agent' | 'model';
  cards: WirePlanningAgentSessionCard[];
  card_count: number;
}

export interface WirePlanningAgentSessionBoard {
  project_id: string;
  feature_id?: string;
  grouping: PlanningBoardGroupingMode;
  groups: WirePlanningBoardGroup[];
  total_card_count: number;
  active_count: number;
  completed_count: number;
  data_freshness?: string;
  generated_at?: string;
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

function adaptPlanningArtifactRef(wire: WirePlanningArtifactRef): PlanningArtifactRef {
  return {
    artifactId: wire.artifact_id ?? '',
    title: wire.title ?? '',
    filePath: wire.file_path ?? '',
    canonicalPath: wire.canonical_path ?? '',
    docType: wire.doc_type ?? '',
    status: wire.status ?? '',
    updatedAt: wire.updated_at ?? '',
    sourceRef: wire.source_ref ?? '',
  };
}

function adaptPlanningSpikeItem(wire: WirePlanningSpikeItem): PlanningSpikeItem {
  return {
    spikeId: wire.spike_id ?? '',
    title: wire.title ?? '',
    status: wire.status ?? '',
    filePath: wire.file_path ?? '',
    sourceRef: wire.source_ref ?? '',
  };
}

function adaptPlanningOpenQuestionItem(wire: WirePlanningOpenQuestionItem): PlanningOpenQuestionItem {
  return {
    oqId: wire.oq_id ?? '',
    question: wire.question ?? '',
    severity: wire.severity ?? 'medium',
    answerText: wire.answer_text ?? '',
    resolved: wire.resolved ?? false,
    pendingSync: wire.pending_sync ?? false,
    sourceDocumentId: wire.source_document_id ?? '',
    sourceDocumentPath: wire.source_document_path ?? '',
    updatedAt: wire.updated_at ?? '',
  };
}

function adaptPlanningTokenUsageByModel(
  wire: WirePlanningTokenUsageByModel | undefined,
): PlanningTokenUsageByModel {
  return {
    opus: wire?.opus ?? 0,
    sonnet: wire?.sonnet ?? 0,
    haiku: wire?.haiku ?? 0,
    other: wire?.other ?? 0,
    total: wire?.total ?? 0,
  };
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

function adaptStatusCounts(wire: WireStatusCounts): PlanningStatusCounts {
  return {
    shaping: wire.shaping ?? 0,
    planned: wire.planned ?? 0,
    active: wire.active ?? 0,
    blocked: wire.blocked ?? 0,
    review: wire.review ?? 0,
    completed: wire.completed ?? 0,
    deferred: wire.deferred ?? 0,
    staleOrMismatched: wire.stale_or_mismatched ?? 0,
  };
}

function adaptCtxPerPhase(wire: WireCtxPerPhase | null | undefined): PlanningCtxPerPhase | null {
  if (!wire) return null;
  return {
    contextCount: wire.context_count ?? 0,
    phaseCount: wire.phase_count ?? 0,
    ratio: wire.ratio ?? null,
    source: wire.source ?? 'unavailable',
  };
}

function adaptTokenTelemetry(wire: WireTokenTelemetry | null | undefined): PlanningTokenTelemetry | null {
  if (!wire) return null;
  return {
    totalTokens: wire.total_tokens ?? null,
    byModelFamily: (wire.by_model_family ?? []).map((e) => ({
      modelFamily: e.model_family ?? '',
      totalTokens: e.total_tokens ?? 0,
    })),
    source: wire.source ?? 'unavailable',
  };
}

// ── Session-board adapters ────────────────────────────────────────────────────

function adaptSessionCorrelationEvidence(wire: WireSessionCorrelationEvidence): SessionCorrelationEvidence {
  return {
    sourceType: wire.source_type ?? '',
    sourceId: wire.source_id,
    sourceLabel: wire.source_label ?? '',
    confidence: wire.confidence ?? 'unknown',
    detail: wire.detail,
  };
}

function adaptSessionCorrelation(wire: WireSessionCorrelation | undefined): SessionCorrelation | undefined {
  if (!wire) return undefined;
  return {
    featureId: wire.feature_id,
    featureName: wire.feature_name,
    phaseNumber: wire.phase_number,
    phaseTitle: wire.phase_title,
    batchId: wire.batch_id,
    taskId: wire.task_id,
    taskTitle: wire.task_title,
    confidence: wire.confidence ?? 'unknown',
    evidence: (wire.evidence ?? []).map(adaptSessionCorrelationEvidence),
  };
}

function adaptBoardSessionRelationship(wire: WireBoardSessionRelationship): BoardSessionRelationship {
  return {
    relatedSessionId: wire.related_session_id ?? '',
    relationType: wire.relation_type ?? 'sibling',
    agentName: wire.agent_name,
    state: wire.state,
  };
}

function adaptSessionActivityMarker(wire: WireSessionActivityMarker): SessionActivityMarker {
  return {
    markerType: wire.marker_type ?? 'tool_call',
    label: wire.label ?? '',
    timestamp: wire.timestamp,
    detail: wire.detail,
  };
}

function adaptSessionTokenSummary(wire: WireSessionTokenSummary | undefined): SessionTokenSummary | undefined {
  if (!wire) return undefined;
  return {
    tokensIn: wire.tokens_in ?? 0,
    tokensOut: wire.tokens_out ?? 0,
    totalTokens: wire.total_tokens ?? 0,
    contextWindowPct: wire.context_window_pct,
    model: wire.model,
  };
}

function adaptPlanningAgentSessionCard(wire: WirePlanningAgentSessionCard): PlanningAgentSessionCard {
  return {
    sessionId: wire.session_id ?? '',
    agentName: wire.agent_name,
    agentType: wire.agent_type,
    state: wire.state ?? 'unknown',
    model: wire.model,
    correlation: adaptSessionCorrelation(wire.correlation),
    transcriptHref: wire.transcript_href,
    planningHref: wire.planning_href,
    phaseHref: wire.phase_href,
    parentSessionId: wire.parent_session_id,
    rootSessionId: wire.root_session_id,
    startedAt: wire.started_at,
    lastActivityAt: wire.last_activity_at,
    durationSeconds: wire.duration_seconds,
    tokenSummary: adaptSessionTokenSummary(wire.token_summary),
    relationships: (wire.relationships ?? []).map(adaptBoardSessionRelationship),
    activityMarkers: (wire.activity_markers ?? []).map(adaptSessionActivityMarker),
  };
}

function adaptPlanningBoardGroup(wire: WirePlanningBoardGroup): PlanningBoardGroup {
  return {
    groupKey: wire.group_key ?? '',
    groupLabel: wire.group_label ?? '',
    groupType: wire.group_type ?? 'state',
    cards: (wire.cards ?? []).map(adaptPlanningAgentSessionCard),
    cardCount: wire.card_count ?? 0,
  };
}

export function adaptPlanningAgentSessionBoard(wire: WirePlanningAgentSessionBoard): PlanningAgentSessionBoard {
  return {
    projectId: wire.project_id ?? '',
    featureId: wire.feature_id,
    grouping: wire.grouping ?? 'state',
    groups: (wire.groups ?? []).map(adaptPlanningBoardGroup),
    totalCardCount: wire.total_card_count ?? 0,
    activeCount: wire.active_count ?? 0,
    completedCount: wire.completed_count ?? 0,
    dataFreshness: wire.data_freshness,
    generatedAt: wire.generated_at,
  };
}

// ── Public API helpers ────────────────────────────────────────────────────────

/**
 * Adapt a raw snake_case wire summary payload to the camelCase
 * ProjectPlanningSummary shape.  Exported so that usePlanningViewQuery
 * (services/queries/planning.ts) can reuse this logic when adapting the
 * bundled summary inside GET /api/agent/planning/view — the backend does NOT
 * pre-adapt wire fields; all snake→camel conversion happens here.
 */
export function adaptPlanningSummary(wire: WireProjectPlanningSummary): ProjectPlanningSummary {
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
    ...(wire.status_counts !== undefined ? { statusCounts: adaptStatusCounts(wire.status_counts) } : {}),
    ...(wire.ctx_per_phase !== undefined ? { ctxPerPhase: adaptCtxPerPhase(wire.ctx_per_phase) } : {}),
    ...(wire.token_telemetry !== undefined ? { tokenTelemetry: adaptTokenTelemetry(wire.token_telemetry) } : {}),
  };
}

/**
 * Fetch project-level planning health counts and per-feature summaries.
 *
 * Mirrors: GET /api/agent/planning/summary
 */
export async function getProjectPlanningSummary(
  projectId?: string,
): Promise<ProjectPlanningSummary> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const wire = await planningFetch<WireProjectPlanningSummary>('/summary', params.toString() ? params : undefined);
  return adaptPlanningSummary(wire);
}

/**
 * Fetch aggregated planning graph nodes and edges for the project or a feature seed.
 *
 * Mirrors: GET /api/agent/planning/graph
 */
/**
 * Adapt a raw snake_case wire graph payload to the camelCase ProjectPlanningGraph
 * shape.  Exported so that usePlanningViewQuery can reuse this logic when the
 * graph sub-payload is present in the view bundle response.
 */
export function adaptPlanningGraph(wire: WireProjectPlanningGraph): ProjectPlanningGraph {
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

  return adaptPlanningGraph(wire);
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
    specs: (wire.specs ?? []).map(adaptPlanningArtifactRef),
    prds: (wire.prds ?? []).map(adaptPlanningArtifactRef),
    plans: (wire.plans ?? []).map(adaptPlanningArtifactRef),
    ctxs: (wire.ctxs ?? []).map(adaptPlanningArtifactRef),
    reports: (wire.reports ?? []).map(adaptPlanningArtifactRef),
    spikes: (wire.spikes ?? []).map(adaptPlanningSpikeItem),
    openQuestions: (wire.open_questions ?? []).map(adaptPlanningOpenQuestionItem),
    readyToPromote: wire.ready_to_promote ?? false,
    isStale: wire.is_stale ?? false,
    totalTokens: wire.total_tokens ?? 0,
    tokenUsageByModel: adaptPlanningTokenUsageByModel(wire.token_usage_by_model),
    category: wire.category,
    slug: wire.slug,
    complexity: wire.complexity,
    tags: wire.tags,
  };
}

export function prefetchFeaturePlanningContext(
  featureId: string,
  opts?: { projectId?: string },
): Promise<FeaturePlanningContext | null> {
  return getFeaturePlanningContext(featureId, opts).catch(() => null);
}

/**
 * Resolve one open question in the planning writeback API.
 *
 * Mirrors: PATCH /api/planning/features/{featureId}/open-questions/{oqId}
 */
export async function resolvePlanningOpenQuestion(
  featureId: string,
  oqId: string,
  answer: string,
): Promise<PlanningOpenQuestionItem> {
  const wire = await planningWriteFetch<WireOpenQuestionResolution>(
    `/features/${encodeURIComponent(featureId)}/open-questions/${encodeURIComponent(oqId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ answer }),
    },
    '/api/planning',
  );

  return adaptPlanningOpenQuestionItem(wire.oq);
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

/**
 * Fetch the project-wide Planning Agent Session Board.
 *
 * Returns all agent sessions grouped by the chosen dimension (default: "state").
 *
 * Mirrors: GET /api/agent/planning/session-board
 */
export async function getSessionBoard(
  projectId?: string,
  grouping?: PlanningBoardGroupingMode,
): Promise<PlanningAgentSessionBoard> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (grouping) params.set('grouping', grouping);

  const wire = await planningFetch<WirePlanningAgentSessionBoard>(
    '/session-board',
    params.toString() ? params : undefined,
  );
  return adaptPlanningAgentSessionBoard(wire);
}

/**
 * Fetch a feature-scoped Planning Agent Session Board.
 *
 * Only sessions correlated to the given feature are included.
 *
 * Mirrors: GET /api/agent/planning/session-board/{featureId}
 */
export async function getFeatureSessionBoard(
  featureId: string,
  projectId?: string,
  grouping?: PlanningBoardGroupingMode,
): Promise<PlanningAgentSessionBoard> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (grouping) params.set('grouping', grouping);

  const wire = await planningFetch<WirePlanningAgentSessionBoard>(
    `/session-board/${encodeURIComponent(featureId)}`,
    params.toString() ? params : undefined,
  );
  return adaptPlanningAgentSessionBoard(wire);
}

// ── Status bucket derivation (P13-003) ───────────────────────────────────────

/**
 * Client-side mirror of the backend `_derive_status_bucket` function.
 *
 * Precedence (descending): blocked > review > active > planned > shaping >
 *   completed > deferred > stale_or_mismatched.
 */
export function deriveStatusBucket(feature: FeatureSummaryItem): PlanningStatusBucket {
  const eff = (feature.effectiveStatus ?? '').toLowerCase().trim();
  const raw = (feature.rawStatus ?? '').toLowerCase().trim();

  if (feature.hasBlockedPhases || eff === 'blocked' || raw === 'blocked') return 'blocked';
  if (eff === 'in_review' || eff === 'in-review' || raw === 'in_review' || raw === 'in-review' || eff === 'review' || raw === 'review') return 'review';
  if (eff === 'in_progress' || eff === 'in-progress' || raw === 'in_progress' || raw === 'in-progress') return 'active';
  if (eff === 'approved' || eff === 'planned' || raw === 'approved' || raw === 'planned') return 'planned';
  if (eff === 'draft' || eff === 'shaping' || eff === 'idea' || raw === 'draft' || raw === 'shaping' || raw === 'idea') return 'shaping';
  if (eff === 'completed' || eff === 'done' || eff === 'merged' || eff === 'promoted' || raw === 'completed' || raw === 'done' || raw === 'merged') return 'completed';
  if (eff === 'deferred' || eff === 'deprecated' || eff === 'superseded' || eff === 'future' || raw === 'deferred' || raw === 'deprecated' || raw === 'superseded') return 'deferred';

  return 'stale_or_mismatched';
}

/** Returns true if a FeatureSummaryItem matches the given status bucket. */
export function featureMatchesBucket(
  feature: FeatureSummaryItem,
  bucket: PlanningStatusBucket,
): boolean {
  return deriveStatusBucket(feature) === bucket;
}

/**
 * Returns true if a FeatureSummaryItem matches the given signal filter.
 *   blocked  → hasBlockedPhases or effectiveStatus contains 'blocked'
 *   stale    → mismatchState contains 'stale', 'reversed', or 'unresolved'
 *   mismatch → isMismatch
 */
export function featureMatchesSignal(
  feature: FeatureSummaryItem,
  signal: 'blocked' | 'stale' | 'mismatch',
): boolean {
  switch (signal) {
    case 'blocked':
      return (
        feature.hasBlockedPhases ||
        (feature.effectiveStatus ?? '').toLowerCase().includes('blocked')
      );
    case 'stale':
      return (
        (feature.mismatchState ?? '').toLowerCase().includes('stale') ||
        (feature.mismatchState ?? '').toLowerCase().includes('reversed') ||
        (feature.mismatchState ?? '').toLowerCase().includes('unresolved')
      );
    case 'mismatch':
      return feature.isMismatch;
  }
}

// ── Next-run preview wire shapes ──────────────────────────────────────────────

interface WireNextRunContextRef {
  ref_type: string;
  ref_id: string;
  ref_label: string;
  ref_path?: string;
}

interface WirePlanningNextRunPreview {
  status: string;
  feature_id: string;
  feature_name?: string;
  phase_number?: number;
  command: string;
  prompt_skeleton: string;
  context_refs: WireNextRunContextRef[];
  warnings: string[];
  data_freshness?: string;
  generated_at?: string;
}

// ── Next-run preview adapters ─────────────────────────────────────────────────

function adaptNextRunContextRef(wire: WireNextRunContextRef): NextRunContextRef {
  return {
    refType: (wire.ref_type ?? 'session') as NextRunContextRef['refType'],
    refId: wire.ref_id ?? '',
    refLabel: wire.ref_label ?? '',
    refPath: wire.ref_path,
  };
}

function adaptPlanningNextRunPreview(wire: WirePlanningNextRunPreview): PlanningNextRunPreview {
  return {
    featureId: wire.feature_id ?? '',
    featureName: wire.feature_name,
    phaseNumber: wire.phase_number,
    command: wire.command ?? '',
    promptSkeleton: wire.prompt_skeleton ?? '',
    contextRefs: (wire.context_refs ?? []).map(adaptNextRunContextRef),
    warnings: wire.warnings ?? [],
    dataFreshness: wire.data_freshness,
    generatedAt: wire.generated_at,
  };
}

// ── Next-run preview public API ───────────────────────────────────────────────

/**
 * Fetch a scaffolded next-run command + prompt preview for a feature.
 *
 * Preview data is request-specific and not cached — each call reflects
 * the current state of the feature and any selected context.
 *
 * Mirrors: GET /api/agent/planning/next-run-preview/{featureId}
 */
export async function getNextRunPreview(
  featureId: string,
  phaseNumber?: number,
  projectId?: string,
): Promise<PlanningNextRunPreview> {
  const params = new URLSearchParams();
  if (phaseNumber != null) params.set('phase_number', String(phaseNumber));
  if (projectId) params.set('project_id', projectId);

  const wire = await planningFetch<WirePlanningNextRunPreview>(
    `/next-run-preview/${encodeURIComponent(featureId)}`,
    params.toString() ? params : undefined,
  );

  return adaptPlanningNextRunPreview(wire);
}

/**
 * Fetch a scaffolded next-run preview with an explicit context selection.
 *
 * Use this variant when the user has curated which sessions, phases, tasks,
 * artifacts, and transcripts should be included in the prompt skeleton.
 *
 * Mirrors: POST /api/agent/planning/next-run-preview/{featureId}
 */
export async function postNextRunPreview(
  featureId: string,
  contextSelection: PromptContextSelection,
  phaseNumber?: number,
  projectId?: string,
): Promise<PlanningNextRunPreview> {
  const params = new URLSearchParams();
  if (phaseNumber != null) params.set('phase_number', String(phaseNumber));
  if (projectId) params.set('project_id', projectId);

  const qs = params.toString();
  const url = `${API_BASE}/next-run-preview/${encodeURIComponent(featureId)}${qs ? `?${qs}` : ''}`;

  const res = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_ids: contextSelection.sessionIds,
      phase_refs: contextSelection.phaseRefs,
      task_refs: contextSelection.taskRefs,
      artifact_refs: contextSelection.artifactRefs,
      transcript_refs: contextSelection.transcriptRefs,
    }),
  });

  if (!res.ok) {
    throw new PlanningApiError(
      `Planning API error: ${res.status} ${res.statusText} for ${url}`,
      res.status,
    );
  }

  const wire = (await res.json()) as WirePlanningNextRunPreview;
  return adaptPlanningNextRunPreview(wire);
}
