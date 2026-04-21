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
} from '../types';
import type { AgentQueryEnvelope } from '../types';

const API_BASE = '/api/agent/planning';
const DEFAULT_PROJECT_CACHE_KEY = '__default__';

type PlanningBrowserCachePayloadType = 'summary' | 'facets' | 'list';

interface PlanningBrowserCacheEntry<T> {
  value: T;
  inFlight?: Promise<T>;
}

interface PlanningBrowserFreshnessBucket {
  payloads: Map<PlanningBrowserCachePayloadType, PlanningBrowserCacheEntry<unknown>>;
}

interface PlanningBrowserProjectCache {
  latestFreshness: string | null;
  freshnessBuckets: Map<string, PlanningBrowserFreshnessBucket>;
}

export interface ProjectPlanningSummaryCacheOptions {
  forceRefresh?: boolean;
  onRevalidated?: (summary: ProjectPlanningSummary) => void;
}

export const PLANNING_BROWSER_CACHE_LIMITS = {
  projects: 8,
  freshnessKeysPerProject: 3,
  payloadTypesPerFreshness: 3,
  featureContexts: 24,
} as const;

const PLANNING_BROWSER_CACHE = new Map<string, PlanningBrowserProjectCache>();
const PLANNING_FEATURE_CONTEXT_CACHE = new Map<string, PlanningBrowserCacheEntry<FeaturePlanningContext>>();
const PENDING_CACHE_FRESHNESS = '__pending__';

export interface PlanningBrowserCacheSnapshot {
  projectsCached: number;
  entries: Array<{
    projectKey: string;
    latestFreshness: string | null;
    freshnessKeys: string[];
    payloadTypes: PlanningBrowserCachePayloadType[];
  }>;
}

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

function projectCacheKey(projectId?: string): string {
  const trimmed = projectId?.trim();
  return trimmed || DEFAULT_PROJECT_CACHE_KEY;
}

function featureContextCacheKey(featureId: string, projectId?: string): string {
  return JSON.stringify([projectCacheKey(projectId), featureId]);
}

function touchMapKey<K, V>(map: Map<K, V>, key: K): void {
  const value = map.get(key);
  if (value === undefined) return;
  map.delete(key);
  map.set(key, value);
}

function trimMapToLimit<K, V>(map: Map<K, V>, limit: number): void {
  while (map.size > limit) {
    const oldestKey = map.keys().next().value as K | undefined;
    if (oldestKey === undefined) break;
    map.delete(oldestKey);
  }
}

function getProjectCache(projectKey: string): PlanningBrowserProjectCache {
  const existing = PLANNING_BROWSER_CACHE.get(projectKey);
  if (existing) {
    touchMapKey(PLANNING_BROWSER_CACHE, projectKey);
    return existing;
  }
  const created: PlanningBrowserProjectCache = {
    latestFreshness: null,
    freshnessBuckets: new Map<string, PlanningBrowserFreshnessBucket>(),
  };
  PLANNING_BROWSER_CACHE.set(projectKey, created);
  trimMapToLimit(PLANNING_BROWSER_CACHE, PLANNING_BROWSER_CACHE_LIMITS.projects);
  return created;
}

function getFreshnessBucket(projectCache: PlanningBrowserProjectCache, freshness: string): PlanningBrowserFreshnessBucket {
  const existing = projectCache.freshnessBuckets.get(freshness);
  if (existing) {
    touchMapKey(projectCache.freshnessBuckets, freshness);
    return existing;
  }
  const created: PlanningBrowserFreshnessBucket = {
    payloads: new Map<PlanningBrowserCachePayloadType, PlanningBrowserCacheEntry<unknown>>(),
  };
  projectCache.freshnessBuckets.set(freshness, created);
  trimMapToLimit(projectCache.freshnessBuckets, PLANNING_BROWSER_CACHE_LIMITS.freshnessKeysPerProject);
  return created;
}

function findLatestCacheEntry<T>(
  projectCache: PlanningBrowserProjectCache,
  payloadType: PlanningBrowserCachePayloadType,
): PlanningBrowserCacheEntry<T> | null {
  const latestFreshness = projectCache.latestFreshness;
  if (!latestFreshness) return null;
  const bucket = projectCache.freshnessBuckets.get(latestFreshness);
  const entry = bucket?.payloads.get(payloadType);
  if (!entry) return null;
  touchMapKey(projectCache.freshnessBuckets, latestFreshness);
  touchMapKey(bucket.payloads, payloadType);
  return entry as PlanningBrowserCacheEntry<T>;
}

function storeCacheEntry<T>(
  projectKey: string,
  payloadType: PlanningBrowserCachePayloadType,
  value: T,
): PlanningBrowserCacheEntry<T> {
  const projectCache = getProjectCache(projectKey);
  const freshness = (value as AgentQueryEnvelope).dataFreshness || 'unknown';
  const bucket = getFreshnessBucket(projectCache, freshness);
  const entry: PlanningBrowserCacheEntry<T> = { value };
  bucket.payloads.set(payloadType, entry as PlanningBrowserCacheEntry<unknown>);
  touchMapKey(bucket.payloads, payloadType);
  trimMapToLimit(bucket.payloads, PLANNING_BROWSER_CACHE_LIMITS.payloadTypesPerFreshness);
  projectCache.latestFreshness = freshness;
  touchMapKey(projectCache.freshnessBuckets, freshness);
  touchMapKey(PLANNING_BROWSER_CACHE, projectKey);
  trimMapToLimit(PLANNING_BROWSER_CACHE, PLANNING_BROWSER_CACHE_LIMITS.projects);
  return entry;
}

function cacheProjectPlanningSummary(
  projectId: string | undefined,
  loader: () => Promise<ProjectPlanningSummary>,
  options: ProjectPlanningSummaryCacheOptions = {},
): Promise<ProjectPlanningSummary> {
  const key = projectCacheKey(projectId);
  const projectCache = getProjectCache(key);
  const existing = findLatestCacheEntry<ProjectPlanningSummary>(projectCache, 'summary');

  if (options.forceRefresh) {
    return loader().then((value) => {
      storeCacheEntry(key, 'summary', value);
      return value;
    });
  }

  if (existing?.value) {
    if (!existing.inFlight) {
      const pending = loader()
        .then((value) => {
          storeCacheEntry(key, 'summary', value);
          options.onRevalidated?.(value);
          return value;
        })
        .catch(() => existing.value)
        .finally(() => {
          existing.inFlight = undefined;
        });
      existing.inFlight = pending;
    }
    return Promise.resolve(existing.value);
  }

  if (existing?.inFlight) return existing.inFlight;

  let pending: Promise<ProjectPlanningSummary>;
  pending = loader()
    .then((value) => {
      storeCacheEntry(key, 'summary', value);
      return value;
    })
    .catch((error) => {
      const latestProjectCache = PLANNING_BROWSER_CACHE.get(key);
      const bucket = latestProjectCache?.freshnessBuckets.get(PENDING_CACHE_FRESHNESS);
      const pendingEntry = bucket?.payloads.get('summary');
      if (pendingEntry?.inFlight === pending) bucket?.payloads.delete('summary');
      if (latestProjectCache?.latestFreshness === PENDING_CACHE_FRESHNESS) latestProjectCache.latestFreshness = null;
      throw error;
    });

  const bucket = getFreshnessBucket(projectCache, PENDING_CACHE_FRESHNESS);
  bucket.payloads.set('summary', { value: undefined, inFlight: pending } as unknown as PlanningBrowserCacheEntry<unknown>);
  projectCache.latestFreshness = PENDING_CACHE_FRESHNESS;
  touchMapKey(projectCache.freshnessBuckets, PENDING_CACHE_FRESHNESS);
  touchMapKey(PLANNING_BROWSER_CACHE, key);
  return pending;
}

export function clearPlanningBrowserCache(projectId?: string): void {
  if (projectId?.trim()) {
    const key = projectCacheKey(projectId);
    PLANNING_BROWSER_CACHE.delete(key);
    for (const cacheKey of Array.from(PLANNING_FEATURE_CONTEXT_CACHE.keys())) {
      const [cachedProjectKey] = JSON.parse(cacheKey) as [string, string];
      if (cachedProjectKey === key) PLANNING_FEATURE_CONTEXT_CACHE.delete(cacheKey);
    }
    return;
  }
  PLANNING_BROWSER_CACHE.clear();
  PLANNING_FEATURE_CONTEXT_CACHE.clear();
}

export function getCachedProjectPlanningSummary(projectId?: string): ProjectPlanningSummary | null {
  const cache = PLANNING_BROWSER_CACHE.get(projectCacheKey(projectId));
  if (!cache) return null;
  return findLatestCacheEntry<ProjectPlanningSummary>(cache, 'summary')?.value ?? null;
}

export function getPlanningBrowserCacheSnapshot(): PlanningBrowserCacheSnapshot {
  return {
    projectsCached: PLANNING_BROWSER_CACHE.size,
    entries: Array.from(PLANNING_BROWSER_CACHE.entries()).map(([projectKey, cache]) => ({
      projectKey,
      latestFreshness: cache.latestFreshness,
      freshnessKeys: Array.from(cache.freshnessBuckets.keys()),
      payloadTypes: Array.from(new Set(
        Array.from(cache.freshnessBuckets.values()).flatMap((bucket) => Array.from(bucket.payloads.keys())),
      )),
    })),
  };
}

async function fetchFeaturePlanningContext(
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

async function planningWriteFetch<T>(
  path: string,
  init: RequestInit,
  base = API_BASE,
): Promise<T> {
  const url = `${base}${path}`;
  const { headers, ...rest } = init;
  const res = await fetch(url, {
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

// ── Public API helpers ────────────────────────────────────────────────────────

/**
 * Fetch project-level planning health counts and per-feature summaries.
 *
 * Mirrors: GET /api/agent/planning/summary
 */
export async function getProjectPlanningSummary(
  projectId?: string,
  options: ProjectPlanningSummaryCacheOptions = {},
): Promise<ProjectPlanningSummary> {
  return cacheProjectPlanningSummary(projectId, async () => {
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
  }, options);
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
  opts?: { projectId?: string; forceRefresh?: boolean },
): Promise<FeaturePlanningContext> {
  const cacheKey = featureContextCacheKey(featureId, opts?.projectId);
  const existing = PLANNING_FEATURE_CONTEXT_CACHE.get(cacheKey);
  if (!opts?.forceRefresh && existing?.value) {
    touchMapKey(PLANNING_FEATURE_CONTEXT_CACHE, cacheKey);
    return existing.value;
  }
  if (!opts?.forceRefresh && existing?.inFlight) return existing.inFlight;

  const pending = fetchFeaturePlanningContext(featureId, opts)
    .then((value) => {
      PLANNING_FEATURE_CONTEXT_CACHE.set(cacheKey, { value });
      touchMapKey(PLANNING_FEATURE_CONTEXT_CACHE, cacheKey);
      trimMapToLimit(PLANNING_FEATURE_CONTEXT_CACHE, PLANNING_BROWSER_CACHE_LIMITS.featureContexts);
      return value;
    })
    .catch((error) => {
      const latest = PLANNING_FEATURE_CONTEXT_CACHE.get(cacheKey);
      if (latest?.inFlight === pending && !latest.value) PLANNING_FEATURE_CONTEXT_CACHE.delete(cacheKey);
      throw error;
    });

  PLANNING_FEATURE_CONTEXT_CACHE.set(cacheKey, {
    value: existing?.value as FeaturePlanningContext,
    inFlight: pending,
  });
  touchMapKey(PLANNING_FEATURE_CONTEXT_CACHE, cacheKey);
  trimMapToLimit(PLANNING_FEATURE_CONTEXT_CACHE, PLANNING_BROWSER_CACHE_LIMITS.featureContexts);
  return pending;
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
