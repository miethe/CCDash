// Feature-surface API client for the Phase 2/3 bounded card-board design.
//
// All endpoints live under /api/v1/.  The backend wraps every response in
// ClientV1Envelope<T> (shape: { status, data, meta }).  This module unwraps the
// envelope and adapts snake_case wire fields to camelCase before returning,
// matching the pattern used in services/planning.ts.
//
// Do NOT add raw fetch() calls for feature-surface endpoints in components.
// Use the typed helpers exported from this module instead.

// ── Base URL ──────────────────────────────────────────────────────────────────

const API_V1_BASE = '/api/v1';

// ── Error type ────────────────────────────────────────────────────────────────

export class FeatureSurfaceApiError extends Error {
  status: number;
  envelopeStatus: 'ok' | 'partial' | 'error';

  constructor(
    message: string,
    httpStatus: number,
    envelopeStatus: 'ok' | 'partial' | 'error' = 'error',
  ) {
    super(message);
    this.name = 'FeatureSurfaceApiError';
    this.status = httpStatus;
    this.envelopeStatus = envelopeStatus;
  }
}

// ── Internal fetch helpers ────────────────────────────────────────────────────

async function v1Fetch<T>(path: string, params?: URLSearchParams): Promise<T> {
  const qs = params?.toString();
  const url = `${API_V1_BASE}${path}${qs ? `?${qs}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new FeatureSurfaceApiError(
      `Feature-surface API error: ${res.status} ${res.statusText} for ${url}`,
      res.status,
    );
  }
  const envelope = (await res.json()) as WireClientV1Envelope<T>;
  if (envelope.status === 'error') {
    throw new FeatureSurfaceApiError(
      `Feature-surface API returned status=error for ${url}`,
      res.status,
      'error',
    );
  }
  return envelope.data;
}

async function v1PostFetch<TBody, TResponse>(
  path: string,
  body: TBody,
): Promise<TResponse> {
  const url = `${API_V1_BASE}${path}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new FeatureSurfaceApiError(
      `Feature-surface API error: ${res.status} ${res.statusText} for POST ${url}`,
      res.status,
    );
  }
  const envelope = (await res.json()) as WireClientV1Envelope<TResponse>;
  if (envelope.status === 'error') {
    throw new FeatureSurfaceApiError(
      `Feature-surface API returned status=error for POST ${url}`,
      res.status,
      'error',
    );
  }
  return envelope.data;
}

// ── Wire shapes (internal, snake_case from backend) ───────────────────────────

/** Outer ClientV1Envelope wrapper returned by every /api/v1/ route. */
interface WireClientV1Envelope<T> {
  status: 'ok' | 'partial' | 'error';
  data: T;
  meta?: {
    generated_at?: string;
    instance_id?: string;
    request_id?: string;
  };
}

type WireFeatureSurfacePrecision = 'exact' | 'eventually_consistent' | 'partial';

type WireFeatureModalSectionKey =
  | 'overview'
  | 'phases'
  | 'documents'
  | 'relations'
  | 'sessions'
  | 'test_status'
  | 'activity';

interface WireDTOFreshness {
  observed_at?: string | null;
  source_revision?: string;
  cache_version?: string;
}

interface WireFeatureDocumentCoverageDTO {
  present?: string[];
  missing?: string[];
  counts_by_type?: Record<string, number>;
}

interface WireFeatureQualitySignalsDTO {
  blocker_count?: number;
  at_risk_task_count?: number;
  has_blocking_signals?: boolean;
  test_impact?: string;
  integrity_signal_refs?: string[];
}

interface WireFeatureDependencySummaryDTO {
  state?: string;
  blocking_reason?: string;
  blocked_by_count?: number;
  ready_dependency_count?: number;
}

interface WireFeatureFamilyPositionDTO {
  position?: number | null;
  total?: number | null;
  label?: string;
  next_item_id?: string;
  next_item_label?: string;
}

interface WireFeatureDocumentSummaryDTO {
  document_id?: string;
  title?: string;
  doc_type?: string;
  status?: string;
  file_path?: string;
  updated_at?: string;
}

interface WireFeatureCardDTO {
  id?: string;
  name?: string;
  status?: string;
  effective_status?: string;
  category?: string;
  tags?: string[];
  summary?: string;
  description_preview?: string;
  priority?: string;
  risk_level?: string;
  complexity?: string;
  total_tasks?: number;
  completed_tasks?: number;
  deferred_tasks?: number;
  phase_count?: number;
  planned_at?: string;
  started_at?: string;
  completed_at?: string;
  updated_at?: string;
  document_coverage?: WireFeatureDocumentCoverageDTO;
  quality_signals?: WireFeatureQualitySignalsDTO;
  dependency_state?: WireFeatureDependencySummaryDTO;
  primary_documents?: WireFeatureDocumentSummaryDTO[];
  family_position?: WireFeatureFamilyPositionDTO | null;
  related_feature_count?: number;
  precision?: WireFeatureSurfacePrecision;
  freshness?: WireDTOFreshness | null;
}

interface WireFeatureCardPageDTO {
  items?: WireFeatureCardDTO[];
  total?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
  query_hash?: string;
  precision?: WireFeatureSurfacePrecision;
  freshness?: WireDTOFreshness | null;
}

interface WireFeatureRollupBucketDTO {
  key?: string;
  label?: string;
  count?: number | null;
  share?: number | null;
}

interface WireFeatureRollupFreshnessDTO extends WireDTOFreshness {
  session_sync_at?: string;
  links_updated_at?: string;
  test_health_at?: string;
}

interface WireFeatureRollupDTO {
  feature_id?: string;
  session_count?: number | null;
  primary_session_count?: number | null;
  subthread_count?: number | null;
  unresolved_subthread_count?: number | null;
  total_cost?: number | null;
  display_cost?: number | null;
  observed_tokens?: number | null;
  model_io_tokens?: number | null;
  cache_input_tokens?: number | null;
  latest_session_at?: string;
  latest_activity_at?: string;
  model_families?: WireFeatureRollupBucketDTO[];
  providers?: WireFeatureRollupBucketDTO[];
  workflow_types?: WireFeatureRollupBucketDTO[];
  linked_doc_count?: number | null;
  linked_doc_counts_by_type?: WireFeatureRollupBucketDTO[];
  linked_task_count?: number | null;
  linked_commit_count?: number | null;
  linked_pr_count?: number | null;
  test_count?: number | null;
  failing_test_count?: number | null;
  precision?: WireFeatureSurfacePrecision;
  freshness?: WireFeatureRollupFreshnessDTO | null;
}

interface WireFeatureRollupErrorDTO {
  code?: string;
  message?: string;
  detail?: Record<string, unknown>;
}

interface WireFeatureRollupResponseDTO {
  rollups?: Record<string, WireFeatureRollupDTO>;
  missing?: string[];
  errors?: Record<string, WireFeatureRollupErrorDTO>;
  generated_at?: string;
  cache_version?: string;
}

interface WireFeatureModalOverviewDTO {
  feature_id?: string;
  card?: WireFeatureCardDTO;
  rollup?: WireFeatureRollupDTO | null;
  description?: string;
  precision?: WireFeatureSurfacePrecision;
  freshness?: WireDTOFreshness | null;
}

interface WireFeatureModalSectionItemDTO {
  item_id?: string;
  label?: string;
  kind?: string;
  status?: string;
  description?: string;
  href?: string;
  badges?: string[];
  metadata?: Record<string, unknown>;
}

interface WireFeatureModalSectionDTO {
  feature_id?: string;
  section?: WireFeatureModalSectionKey;
  title?: string;
  items?: WireFeatureModalSectionItemDTO[];
  total?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
  includes?: string[];
  precision?: WireFeatureSurfacePrecision;
  freshness?: WireDTOFreshness | null;
}

interface WireLinkedFeatureSessionTaskDTO {
  task_id?: string;
  task_title?: string;
  phase_id?: string;
  phase?: string;
  matched_by?: string;
}

interface WireLinkedFeatureSessionDTO {
  session_id?: string;
  title?: string;
  status?: string;
  model?: string;
  model_provider?: string;
  model_family?: string;
  started_at?: string;
  ended_at?: string;
  updated_at?: string;
  total_cost?: number;
  observed_tokens?: number;
  root_session_id?: string;
  parent_session_id?: string | null;
  workflow_type?: string;
  is_primary_link?: boolean;
  is_subthread?: boolean;
  thread_child_count?: number;
  reasons?: string[];
  commands?: string[];
  related_tasks?: WireLinkedFeatureSessionTaskDTO[];
}

interface WireLinkedSessionEnrichmentDTO {
  includes?: string[];
  logs_read?: boolean;
  command_count_included?: boolean;
  task_refs_included?: boolean;
  thread_children_included?: boolean;
}

interface WireLinkedFeatureSessionPageDTO {
  items?: WireLinkedFeatureSessionDTO[];
  total?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
  next_cursor?: string | null;
  enrichment?: WireLinkedSessionEnrichmentDTO;
  precision?: WireFeatureSurfacePrecision;
  freshness?: WireDTOFreshness | null;
}

// ── Public TypeScript DTO types ───────────────────────────────────────────────

export type FeatureSurfacePrecision = 'exact' | 'eventually_consistent' | 'partial';

export type FeatureModalSectionKey =
  | 'overview'
  | 'phases'
  | 'documents'
  | 'relations'
  | 'sessions'
  | 'test_status'
  | 'activity';

export type FeatureRollupFieldKey =
  | 'session_counts'
  | 'token_cost_totals'
  | 'model_provider_summary'
  | 'latest_activity'
  | 'doc_metrics'
  | 'test_metrics'
  | 'freshness';

export interface DTOFreshness {
  observedAt: string | null;
  sourceRevision: string;
  cacheVersion: string;
}

export interface FeatureDocumentCoverageDTO {
  present: string[];
  missing: string[];
  countsByType: Record<string, number>;
}

export interface FeatureQualitySignalsDTO {
  blockerCount: number;
  atRiskTaskCount: number;
  hasBlockingSignals: boolean;
  testImpact: string;
  integritySignalRefs: string[];
}

export interface FeatureDependencySummaryDTO {
  state: string;
  blockingReason: string;
  blockedByCount: number;
  readyDependencyCount: number;
}

export interface FeatureFamilyPositionDTO {
  position: number | null;
  total: number | null;
  label: string;
  nextItemId: string;
  nextItemLabel: string;
}

export interface FeatureDocumentSummaryDTO {
  documentId: string;
  title: string;
  docType: string;
  status: string;
  filePath: string;
  updatedAt: string;
}

export interface FeatureCardDTO {
  id: string;
  name: string;
  status: string;
  effectiveStatus: string;
  category: string;
  tags: string[];
  summary: string;
  descriptionPreview: string;
  priority: string;
  riskLevel: string;
  complexity: string;
  totalTasks: number;
  completedTasks: number;
  deferredTasks: number;
  phaseCount: number;
  plannedAt: string;
  startedAt: string;
  completedAt: string;
  updatedAt: string;
  documentCoverage: FeatureDocumentCoverageDTO;
  qualitySignals: FeatureQualitySignalsDTO;
  dependencyState: FeatureDependencySummaryDTO;
  primaryDocuments: FeatureDocumentSummaryDTO[];
  familyPosition: FeatureFamilyPositionDTO | null;
  relatedFeatureCount: number;
  precision: FeatureSurfacePrecision;
  freshness: DTOFreshness | null;
}

export interface FeatureCardPageDTO {
  items: FeatureCardDTO[];
  total: number;
  offset: number;
  limit: number;
  hasMore: boolean;
  queryHash: string;
  precision: FeatureSurfacePrecision;
  freshness: DTOFreshness | null;
}

export interface FeatureRollupBucketDTO {
  key: string;
  label: string;
  count: number | null;
  share: number | null;
}

export interface FeatureRollupFreshnessDTO extends DTOFreshness {
  sessionSyncAt: string;
  linksUpdatedAt: string;
  testHealthAt: string;
}

export interface FeatureRollupDTO {
  featureId: string;
  sessionCount: number | null;
  primarySessionCount: number | null;
  subthreadCount: number | null;
  unresolvedSubthreadCount: number | null;
  totalCost: number | null;
  displayCost: number | null;
  observedTokens: number | null;
  modelIoTokens: number | null;
  cacheInputTokens: number | null;
  latestSessionAt: string;
  latestActivityAt: string;
  modelFamilies: FeatureRollupBucketDTO[];
  providers: FeatureRollupBucketDTO[];
  workflowTypes: FeatureRollupBucketDTO[];
  linkedDocCount: number | null;
  linkedDocCountsByType: FeatureRollupBucketDTO[];
  linkedTaskCount: number | null;
  linkedCommitCount: number | null;
  linkedPrCount: number | null;
  testCount: number | null;
  failingTestCount: number | null;
  precision: FeatureSurfacePrecision;
  freshness: FeatureRollupFreshnessDTO | null;
}

export interface FeatureRollupErrorDTO {
  code: string;
  message: string;
  detail: Record<string, unknown>;
}

export interface FeatureRollupResponseDTO {
  rollups: Record<string, FeatureRollupDTO>;
  missing: string[];
  errors: Record<string, FeatureRollupErrorDTO>;
  generatedAt: string;
  cacheVersion: string;
}

export interface FeatureRollupRequestDTO {
  featureIds: string[];
  fields?: FeatureRollupFieldKey[];
  includeInheritedThreads?: boolean;
  includeFreshness?: boolean;
  includeTestMetrics?: boolean;
}

export interface FeatureModalOverviewDTO {
  featureId: string;
  card: FeatureCardDTO;
  rollup: FeatureRollupDTO | null;
  description: string;
  precision: FeatureSurfacePrecision;
  freshness: DTOFreshness | null;
}

export interface FeatureModalSectionItemDTO {
  itemId: string;
  label: string;
  kind: string;
  status: string;
  description: string;
  href: string;
  badges: string[];
  metadata: Record<string, unknown>;
}

export interface FeatureModalSectionDTO {
  featureId: string;
  section: FeatureModalSectionKey;
  title: string;
  items: FeatureModalSectionItemDTO[];
  total: number;
  offset: number;
  limit: number;
  hasMore: boolean;
  includes: string[];
  precision: FeatureSurfacePrecision;
  freshness: DTOFreshness | null;
}

export interface LinkedFeatureSessionTaskDTO {
  taskId: string;
  taskTitle: string;
  phaseId: string;
  phase: string;
  matchedBy: string;
}

export interface LinkedFeatureSessionDTO {
  sessionId: string;
  title: string;
  status: string;
  model: string;
  modelProvider: string;
  modelFamily: string;
  startedAt: string;
  endedAt: string;
  updatedAt: string;
  totalCost: number;
  observedTokens: number;
  rootSessionId: string;
  parentSessionId: string | null;
  workflowType: string;
  isPrimaryLink: boolean;
  isSubthread: boolean;
  threadChildCount: number;
  reasons: string[];
  commands: string[];
  relatedTasks: LinkedFeatureSessionTaskDTO[];
}

export interface LinkedSessionEnrichmentDTO {
  includes: string[];
  logsRead: boolean;
  commandCountIncluded: boolean;
  taskRefsIncluded: boolean;
  threadChildrenIncluded: boolean;
}

export interface LinkedFeatureSessionPageDTO {
  items: LinkedFeatureSessionDTO[];
  total: number;
  offset: number;
  limit: number;
  hasMore: boolean;
  nextCursor: string | null;
  enrichment: LinkedSessionEnrichmentDTO;
  precision: FeatureSurfacePrecision;
  freshness: DTOFreshness | null;
}

export interface FeatureCardsListParams {
  projectId?: string;
  page?: number;
  pageSize?: number;
  offset?: number;
  q?: string;
  status?: string[];
  stage?: string[];
  category?: string;
  tags?: string[];
  hasDeferred?: boolean;
  plannedFrom?: string;
  plannedTo?: string;
  startedFrom?: string;
  startedTo?: string;
  completedFrom?: string;
  completedTo?: string;
  updatedFrom?: string;
  updatedTo?: string;
  progressMin?: number;
  progressMax?: number;
  taskCountMin?: number;
  taskCountMax?: number;
  sortBy?: string;
  sortDirection?: string;
  include?: string[];
}

export interface FeatureModalSectionParams {
  include?: string[];
  limit?: number;
  offset?: number;
}

export interface LinkedSessionPageParams {
  limit?: number;
  offset?: number;
}

// ── Adapters (snake_case wire → camelCase public) ─────────────────────────────

function adaptDTOFreshness(wire: WireDTOFreshness | null | undefined): DTOFreshness | null {
  if (!wire) return null;
  return {
    observedAt: wire.observed_at ?? null,
    sourceRevision: wire.source_revision ?? '',
    cacheVersion: wire.cache_version ?? '',
  };
}

function adaptFeatureRollupFreshness(
  wire: WireFeatureRollupFreshnessDTO | null | undefined,
): FeatureRollupFreshnessDTO | null {
  if (!wire) return null;
  return {
    observedAt: wire.observed_at ?? null,
    sourceRevision: wire.source_revision ?? '',
    cacheVersion: wire.cache_version ?? '',
    sessionSyncAt: wire.session_sync_at ?? '',
    linksUpdatedAt: wire.links_updated_at ?? '',
    testHealthAt: wire.test_health_at ?? '',
  };
}

function adaptDocumentCoverage(
  wire: WireFeatureDocumentCoverageDTO | undefined,
): FeatureDocumentCoverageDTO {
  return {
    present: wire?.present ?? [],
    missing: wire?.missing ?? [],
    countsByType: wire?.counts_by_type ?? {},
  };
}

function adaptQualitySignals(
  wire: WireFeatureQualitySignalsDTO | undefined,
): FeatureQualitySignalsDTO {
  return {
    blockerCount: wire?.blocker_count ?? 0,
    atRiskTaskCount: wire?.at_risk_task_count ?? 0,
    hasBlockingSignals: wire?.has_blocking_signals ?? false,
    testImpact: wire?.test_impact ?? '',
    integritySignalRefs: wire?.integrity_signal_refs ?? [],
  };
}

function adaptDependencyState(
  wire: WireFeatureDependencySummaryDTO | undefined,
): FeatureDependencySummaryDTO {
  return {
    state: wire?.state ?? '',
    blockingReason: wire?.blocking_reason ?? '',
    blockedByCount: wire?.blocked_by_count ?? 0,
    readyDependencyCount: wire?.ready_dependency_count ?? 0,
  };
}

function adaptFamilyPosition(
  wire: WireFeatureFamilyPositionDTO | null | undefined,
): FeatureFamilyPositionDTO | null {
  if (!wire) return null;
  return {
    position: wire.position ?? null,
    total: wire.total ?? null,
    label: wire.label ?? '',
    nextItemId: wire.next_item_id ?? '',
    nextItemLabel: wire.next_item_label ?? '',
  };
}

function adaptDocumentSummary(wire: WireFeatureDocumentSummaryDTO): FeatureDocumentSummaryDTO {
  return {
    documentId: wire.document_id ?? '',
    title: wire.title ?? '',
    docType: wire.doc_type ?? '',
    status: wire.status ?? '',
    filePath: wire.file_path ?? '',
    updatedAt: wire.updated_at ?? '',
  };
}

function adaptFeatureCard(wire: WireFeatureCardDTO): FeatureCardDTO {
  return {
    id: wire.id ?? '',
    name: wire.name ?? '',
    status: wire.status ?? '',
    effectiveStatus: wire.effective_status ?? '',
    category: wire.category ?? '',
    tags: wire.tags ?? [],
    summary: wire.summary ?? '',
    descriptionPreview: wire.description_preview ?? '',
    priority: wire.priority ?? '',
    riskLevel: wire.risk_level ?? '',
    complexity: wire.complexity ?? '',
    totalTasks: wire.total_tasks ?? 0,
    completedTasks: wire.completed_tasks ?? 0,
    deferredTasks: wire.deferred_tasks ?? 0,
    phaseCount: wire.phase_count ?? 0,
    plannedAt: wire.planned_at ?? '',
    startedAt: wire.started_at ?? '',
    completedAt: wire.completed_at ?? '',
    updatedAt: wire.updated_at ?? '',
    documentCoverage: adaptDocumentCoverage(wire.document_coverage),
    qualitySignals: adaptQualitySignals(wire.quality_signals),
    dependencyState: adaptDependencyState(wire.dependency_state),
    primaryDocuments: (wire.primary_documents ?? []).map(adaptDocumentSummary),
    familyPosition: adaptFamilyPosition(wire.family_position),
    relatedFeatureCount: wire.related_feature_count ?? 0,
    precision: wire.precision ?? 'exact',
    freshness: adaptDTOFreshness(wire.freshness),
  };
}

function adaptRollupBucket(wire: WireFeatureRollupBucketDTO): FeatureRollupBucketDTO {
  return {
    key: wire.key ?? '',
    label: wire.label ?? '',
    count: wire.count ?? null,
    share: wire.share ?? null,
  };
}

function adaptFeatureRollup(wire: WireFeatureRollupDTO): FeatureRollupDTO {
  return {
    featureId: wire.feature_id ?? '',
    sessionCount: wire.session_count ?? null,
    primarySessionCount: wire.primary_session_count ?? null,
    subthreadCount: wire.subthread_count ?? null,
    unresolvedSubthreadCount: wire.unresolved_subthread_count ?? null,
    totalCost: wire.total_cost ?? null,
    displayCost: wire.display_cost ?? null,
    observedTokens: wire.observed_tokens ?? null,
    modelIoTokens: wire.model_io_tokens ?? null,
    cacheInputTokens: wire.cache_input_tokens ?? null,
    latestSessionAt: wire.latest_session_at ?? '',
    latestActivityAt: wire.latest_activity_at ?? '',
    modelFamilies: (wire.model_families ?? []).map(adaptRollupBucket),
    providers: (wire.providers ?? []).map(adaptRollupBucket),
    workflowTypes: (wire.workflow_types ?? []).map(adaptRollupBucket),
    linkedDocCount: wire.linked_doc_count ?? null,
    linkedDocCountsByType: (wire.linked_doc_counts_by_type ?? []).map(adaptRollupBucket),
    linkedTaskCount: wire.linked_task_count ?? null,
    linkedCommitCount: wire.linked_commit_count ?? null,
    linkedPrCount: wire.linked_pr_count ?? null,
    testCount: wire.test_count ?? null,
    failingTestCount: wire.failing_test_count ?? null,
    precision: wire.precision ?? 'eventually_consistent',
    freshness: adaptFeatureRollupFreshness(wire.freshness),
  };
}

function adaptLinkedSessionTask(wire: WireLinkedFeatureSessionTaskDTO): LinkedFeatureSessionTaskDTO {
  return {
    taskId: wire.task_id ?? '',
    taskTitle: wire.task_title ?? '',
    phaseId: wire.phase_id ?? '',
    phase: wire.phase ?? '',
    matchedBy: wire.matched_by ?? '',
  };
}

function adaptLinkedSession(wire: WireLinkedFeatureSessionDTO): LinkedFeatureSessionDTO {
  return {
    sessionId: wire.session_id ?? '',
    title: wire.title ?? '',
    status: wire.status ?? '',
    model: wire.model ?? '',
    modelProvider: wire.model_provider ?? '',
    modelFamily: wire.model_family ?? '',
    startedAt: wire.started_at ?? '',
    endedAt: wire.ended_at ?? '',
    updatedAt: wire.updated_at ?? '',
    totalCost: wire.total_cost ?? 0,
    observedTokens: wire.observed_tokens ?? 0,
    rootSessionId: wire.root_session_id ?? '',
    parentSessionId: wire.parent_session_id ?? null,
    workflowType: wire.workflow_type ?? '',
    isPrimaryLink: wire.is_primary_link ?? false,
    isSubthread: wire.is_subthread ?? false,
    threadChildCount: wire.thread_child_count ?? 0,
    reasons: wire.reasons ?? [],
    commands: wire.commands ?? [],
    relatedTasks: (wire.related_tasks ?? []).map(adaptLinkedSessionTask),
  };
}

function adaptLinkedSessionEnrichment(
  wire: WireLinkedSessionEnrichmentDTO | undefined,
): LinkedSessionEnrichmentDTO {
  return {
    includes: wire?.includes ?? [],
    logsRead: wire?.logs_read ?? false,
    commandCountIncluded: wire?.command_count_included ?? false,
    taskRefsIncluded: wire?.task_refs_included ?? false,
    threadChildrenIncluded: wire?.thread_children_included ?? false,
  };
}

// ── Public API methods ────────────────────────────────────────────────────────

/**
 * Fetch a bounded, paginated page of feature cards.
 *
 * Mirrors: GET /api/v1/features?view=cards
 */
export async function listFeatureCards(
  params: FeatureCardsListParams = {},
): Promise<FeatureCardPageDTO> {
  const qs = new URLSearchParams({ view: 'cards' });

  if (params.q) qs.set('q', params.q);
  if (params.category) qs.set('category', params.category);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortDirection) qs.set('sort_direction', params.sortDirection);
  if (typeof params.hasDeferred === 'boolean') qs.set('has_deferred', String(params.hasDeferred));

  if (params.plannedFrom) qs.set('planned_from', params.plannedFrom);
  if (params.plannedTo) qs.set('planned_to', params.plannedTo);
  if (params.startedFrom) qs.set('started_from', params.startedFrom);
  if (params.startedTo) qs.set('started_to', params.startedTo);
  if (params.completedFrom) qs.set('completed_from', params.completedFrom);
  if (params.completedTo) qs.set('completed_to', params.completedTo);
  if (params.updatedFrom) qs.set('updated_from', params.updatedFrom);
  if (params.updatedTo) qs.set('updated_to', params.updatedTo);
  if (typeof params.progressMin === 'number') qs.set('progress_min', String(params.progressMin));
  if (typeof params.progressMax === 'number') qs.set('progress_max', String(params.progressMax));
  if (typeof params.taskCountMin === 'number') qs.set('task_count_min', String(params.taskCountMin));
  if (typeof params.taskCountMax === 'number') qs.set('task_count_max', String(params.taskCountMax));

  // Repeatable multi-value params
  (params.status ?? []).forEach((s) => qs.append('status', s));
  (params.stage ?? []).forEach((s) => qs.append('stage', s));
  (params.tags ?? []).forEach((t) => qs.append('tags', t));
  (params.include ?? []).forEach((i) => qs.append('include', i));

  // Pagination: support both (page, pageSize) and raw (offset, limit).
  const pageSize = params.pageSize ?? 50;
  const offset =
    params.offset !== undefined
      ? params.offset
      : ((params.page ?? 1) - 1) * pageSize;
  qs.set('limit', String(pageSize));
  qs.set('offset', String(offset));

  const wire = await v1Fetch<WireFeatureCardPageDTO>('/features', qs);

  return {
    items: (wire.items ?? []).map(adaptFeatureCard),
    total: wire.total ?? 0,
    offset: wire.offset ?? 0,
    limit: wire.limit ?? pageSize,
    hasMore: wire.has_more ?? false,
    queryHash: wire.query_hash ?? '',
    precision: wire.precision ?? 'exact',
    freshness: adaptDTOFreshness(wire.freshness),
  };
}

/**
 * Fetch batched rollup metrics for a bounded list of feature IDs.
 *
 * Mirrors: POST /api/v1/features/rollups
 */
export async function getFeatureRollups(
  request: FeatureRollupRequestDTO,
): Promise<FeatureRollupResponseDTO> {
  const wireBody = {
    feature_ids: request.featureIds,
    fields: request.fields ?? [],
    include_inherited_threads: request.includeInheritedThreads ?? true,
    include_freshness: request.includeFreshness ?? true,
    include_test_metrics: request.includeTestMetrics ?? false,
  };

  const wire = await v1PostFetch<typeof wireBody, WireFeatureRollupResponseDTO>(
    '/features/rollups',
    wireBody,
  );

  const rollups: Record<string, FeatureRollupDTO> = {};
  for (const [id, r] of Object.entries(wire.rollups ?? {})) {
    rollups[id] = adaptFeatureRollup(r);
  }

  const errors: Record<string, FeatureRollupErrorDTO> = {};
  for (const [id, e] of Object.entries(wire.errors ?? {})) {
    errors[id] = {
      code: e.code ?? '',
      message: e.message ?? '',
      detail: e.detail ?? {},
    };
  }

  return {
    rollups,
    missing: wire.missing ?? [],
    errors,
    generatedAt: wire.generated_at ?? '',
    cacheVersion: wire.cache_version ?? '',
  };
}

/**
 * Fetch the modal overview payload (card + rollup + description) for one feature.
 *
 * Mirrors: GET /api/v1/features/{featureId}/modal
 */
export async function getFeatureModalOverview(featureId: string): Promise<FeatureModalOverviewDTO> {
  const wire = await v1Fetch<WireFeatureModalOverviewDTO>(
    `/features/${encodeURIComponent(featureId)}/modal`,
  );

  return {
    featureId: wire.feature_id ?? featureId,
    card: adaptFeatureCard(wire.card ?? {}),
    rollup: wire.rollup ? adaptFeatureRollup(wire.rollup) : null,
    description: wire.description ?? '',
    precision: wire.precision ?? 'exact',
    freshness: adaptDTOFreshness(wire.freshness),
  };
}

/**
 * Fetch a single modal section/tab payload for a feature.
 *
 * Mirrors: GET /api/v1/features/{featureId}/modal/{section}
 */
export async function getFeatureModalSection(
  featureId: string,
  section: FeatureModalSectionKey,
  params: FeatureModalSectionParams = {},
): Promise<FeatureModalSectionDTO> {
  const qs = new URLSearchParams();
  if (typeof params.limit === 'number') qs.set('limit', String(params.limit));
  if (typeof params.offset === 'number') qs.set('offset', String(params.offset));
  (params.include ?? []).forEach((i) => qs.append('include', i));

  const wire = await v1Fetch<WireFeatureModalSectionDTO>(
    `/features/${encodeURIComponent(featureId)}/modal/${encodeURIComponent(section)}`,
    qs.toString() ? qs : undefined,
  );

  return {
    featureId: wire.feature_id ?? featureId,
    section: wire.section ?? section,
    title: wire.title ?? '',
    items: (wire.items ?? []).map((item) => ({
      itemId: item.item_id ?? '',
      label: item.label ?? '',
      kind: item.kind ?? '',
      status: item.status ?? '',
      description: item.description ?? '',
      href: item.href ?? '',
      badges: item.badges ?? [],
      metadata: item.metadata ?? {},
    })),
    total: wire.total ?? 0,
    offset: wire.offset ?? 0,
    limit: wire.limit ?? 20,
    hasMore: wire.has_more ?? false,
    includes: wire.includes ?? [],
    precision: wire.precision ?? 'exact',
    freshness: adaptDTOFreshness(wire.freshness),
  };
}

/**
 * Fetch the paginated linked-session page for a feature.
 *
 * Replaces ad hoc fan-out calls to the legacy /api/features/{id}/linked-sessions.
 * Mirrors: GET /api/v1/features/{featureId}/sessions/page
 */
export async function getFeatureLinkedSessionPage(
  featureId: string,
  params: LinkedSessionPageParams = {},
): Promise<LinkedFeatureSessionPageDTO> {
  const qs = new URLSearchParams();
  if (typeof params.limit === 'number') qs.set('limit', String(params.limit));
  if (typeof params.offset === 'number') qs.set('offset', String(params.offset));

  const wire = await v1Fetch<WireLinkedFeatureSessionPageDTO>(
    `/features/${encodeURIComponent(featureId)}/sessions/page`,
    qs.toString() ? qs : undefined,
  );

  return {
    items: (wire.items ?? []).map(adaptLinkedSession),
    total: wire.total ?? 0,
    offset: wire.offset ?? 0,
    limit: wire.limit ?? 20,
    hasMore: wire.has_more ?? false,
    nextCursor: wire.next_cursor ?? null,
    enrichment: adaptLinkedSessionEnrichment(wire.enrichment),
    precision: wire.precision ?? 'eventually_consistent',
    freshness: adaptDTOFreshness(wire.freshness),
  };
}

// ── Legacy v0 feature helpers (encoded IDs) ─────────────────────────────────
// These thin wrappers replace inline fetch() calls scattered across components.
// They call the /api/features/ legacy endpoints (not /api/v1/) and return the
// raw wire shapes those endpoints emit.  The important guarantee is that the
// feature ID is always encoded before being interpolated into the URL, so IDs
// containing /, spaces, #, ?, and & are handled correctly.

const API_LEGACY_FEATURES_BASE = '/api/features';

async function legacyFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_LEGACY_FEATURES_BASE}${path}`, init);
  if (!res.ok) {
    throw new FeatureSurfaceApiError(
      `Legacy feature API error: ${res.status} ${res.statusText} for ${API_LEGACY_FEATURES_BASE}${path}`,
      res.status,
    );
  }
  return res.json() as Promise<T>;
}

/**
 * Fetch a single feature by ID from the legacy /api/features/{featureId} endpoint.
 *
 * The feature ID is percent-encoded so that IDs containing /, spaces, #, ?, and
 * & are transmitted correctly.
 */
export async function getLegacyFeatureDetail<T = unknown>(featureId: string): Promise<T> {
  return legacyFetch<T>(`/${encodeURIComponent(featureId)}`);
}

/**
 * Fetch the linked-sessions list for a feature from the legacy
 * /api/features/{featureId}/linked-sessions endpoint.
 *
 * The feature ID is percent-encoded so that IDs containing /, spaces, #, ?, and
 * & are transmitted correctly.
 *
 * @deprecated Use {@link getFeatureLinkedSessionPage} instead.
 *   P5-006: All production call sites have been migrated. This export is retained
 *   for test harnesses that directly exercise the legacy endpoint contract
 *   (see components/__tests__/FeatureModalEncodedIds.test.tsx). It will be
 *   removed when the legacy /api/features/{id}/linked-sessions route is retired.
 */
export async function getLegacyFeatureLinkedSessions<T = unknown[]>(featureId: string): Promise<T> {
  return legacyFetch<T>(`/${encodeURIComponent(featureId)}/linked-sessions`);
}

/**
 * Fetch task source file content from /api/features/task-source.
 *
 * Uses the typed client (via legacyFetch base URL) to eliminate the raw
 * fetch(`/api/features/task-source?file=...`) call in TaskSourceDialog.
 * P4-010: last raw /api/features/ interpolation in components/ removed.
 */
export async function getFeatureTaskSource(sourceFile: string): Promise<{ content: string }> {
  const params = new URLSearchParams({ file: sourceFile });
  const res = await fetch(`${API_LEGACY_FEATURES_BASE}/task-source?${params.toString()}`);
  if (!res.ok) {
    throw new FeatureSurfaceApiError(
      `Feature task-source error: ${res.status} ${res.statusText}`,
      res.status,
    );
  }
  return res.json() as Promise<{ content: string }>;
}
