import type {
  PlanningCommandAlternative,
  PlanningCommandCapability,
  PlanningCommandCenterArtifact,
  PlanningCommandCenterBlocker,
  PlanningCommandCenterCapabilities,
  PlanningCommandCenterFeature,
  PlanningCommandCenterGitState,
  PlanningCommandCenterItem,
  PlanningCommandCenterLaunchAgent,
  PlanningCommandCenterLaunchBatch,
  PlanningCommandCenterPage,
  PlanningCommandCenterPhase,
  PlanningCommandCenterPhaseRow,
  PlanningCommandCenterPullRequest,
  PlanningCommandCenterRelatedFile,
  PlanningCommandCenterStatus,
  PlanningCommandCenterStoryPoints,
  PlanningCommandCenterWorktree,
  PlanningCommandResolution,
  PlanningCommandTargetArtifact,
} from '../types';
import { apiFetch } from './apiClient';

const API_BASE = '/api/agent/planning/command-center';

export interface PlanningCommandCenterQuery {
  projectId?: string;
  q?: string;
  status?: string;
  phase?: number;
  artifactType?: string;
  worktreeState?: string;
  prState?: string;
  launchReadiness?: string;
  sortBy?: string;
  sortDirection?: 'asc' | 'desc';
  page?: number;
  pageSize?: number;
  /** When true, backend excludes items in terminal statuses (done/completed/closed/deferred/superseded). */
  hideDone?: boolean;
}

export class PlanningCommandCenterApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'PlanningCommandCenterApiError';
    this.status = status;
  }
}

function appendParam(params: URLSearchParams, key: string, value: string | number | undefined): void {
  if (value === undefined || value === null || value === '') return;
  params.set(key, String(value));
}

function queryParams(query: PlanningCommandCenterQuery = {}): URLSearchParams {
  const params = new URLSearchParams();
  appendParam(params, 'project_id', query.projectId);
  appendParam(params, 'q', query.q);
  appendParam(params, 'status', query.status);
  appendParam(params, 'phase', query.phase);
  appendParam(params, 'artifact_type', query.artifactType);
  appendParam(params, 'worktree_state', query.worktreeState);
  appendParam(params, 'pr_state', query.prState);
  appendParam(params, 'launch_readiness', query.launchReadiness);
  appendParam(params, 'sort_by', query.sortBy);
  appendParam(params, 'sort_direction', query.sortDirection);
  appendParam(params, 'page', query.page);
  appendParam(params, 'page_size', query.pageSize);
  if (query.hideDone) params.set('hide_done', 'true');
  return params;
}

async function commandCenterFetch<T>(path = '', params?: URLSearchParams): Promise<T> {
  const qs = params?.toString();
  const url = `${API_BASE}${path}${qs ? `?${qs}` : ''}`;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new PlanningCommandCenterApiError(
      `Planning Command Center API error: ${response.status} ${response.statusText} for ${url}`,
      response.status,
    );
  }
  return response.json() as Promise<T>;
}

function capability(wire: Record<string, unknown> = {}): PlanningCommandCapability {
  return {
    name: String(wire.name ?? ''),
    supported: Boolean(wire.supported ?? true),
    required: Boolean(wire.required ?? true),
    warning: String(wire.warning ?? ''),
    fallbackCommand: String(wire.fallback_command ?? ''),
  };
}

function targetArtifact(wire: Record<string, unknown> | null | undefined): PlanningCommandTargetArtifact | null {
  if (!wire) return null;
  return {
    path: String(wire.path ?? ''),
    docType: String(wire.doc_type ?? ''),
    title: String(wire.title ?? ''),
    exists: wire.exists as boolean | null | undefined,
    sourceRef: String(wire.source_ref ?? ''),
  };
}

function commandAlternative(wire: Record<string, unknown> = {}): PlanningCommandAlternative {
  return {
    ruleId: String(wire.rule_id ?? ''),
    command: String(wire.command ?? ''),
    confidence: Number(wire.confidence ?? 0),
    rationale: String(wire.rationale ?? ''),
    targetArtifactPath: String(wire.target_artifact_path ?? ''),
    targetArtifactDocType: String(wire.target_artifact_doc_type ?? ''),
    phase: wire.phase as number | null | undefined,
    warnings: Array.isArray(wire.warnings) ? wire.warnings.map(String) : [],
    requiredCapabilities: Array.isArray(wire.required_capabilities)
      ? wire.required_capabilities.map((item) => capability(item as Record<string, unknown>))
      : [],
  };
}

function commandResolution(wire: Record<string, unknown> | null | undefined): PlanningCommandResolution | null {
  if (!wire) return null;
  return {
    command: String(wire.command ?? ''),
    ruleId: String(wire.rule_id ?? ''),
    confidence: Number(wire.confidence ?? 0),
    rationale: String(wire.rationale ?? ''),
    targetArtifactPath: String(wire.target_artifact_path ?? ''),
    targetArtifactDocType: String(wire.target_artifact_doc_type ?? ''),
    targetArtifact: targetArtifact(wire.target_artifact as Record<string, unknown> | null | undefined),
    phase: wire.phase as number | null | undefined,
    warnings: Array.isArray(wire.warnings) ? wire.warnings.map(String) : [],
    alternatives: Array.isArray(wire.alternatives)
      ? wire.alternatives.map((item) => commandAlternative(item as Record<string, unknown>))
      : [],
    requiredCapabilities: Array.isArray(wire.required_capabilities)
      ? wire.required_capabilities.map((item) => capability(item as Record<string, unknown>))
      : [],
  };
}

function feature(wire: Record<string, unknown> = {}): PlanningCommandCenterFeature {
  return {
    featureId: String(wire.feature_id ?? ''),
    featureSlug: String(wire.feature_slug ?? ''),
    name: String(wire.name ?? ''),
    category: String(wire.category ?? ''),
    tags: Array.isArray(wire.tags) ? wire.tags.map(String) : [],
    priority: String(wire.priority ?? ''),
    summary: String(wire.summary ?? ''),
  };
}

function status(wire: Record<string, unknown> = {}): PlanningCommandCenterStatus {
  return {
    rawStatus: String(wire.raw_status ?? ''),
    effectiveStatus: String(wire.effective_status ?? ''),
    planningSignal: String(wire.planning_signal ?? ''),
    mismatchState: String(wire.mismatch_state ?? ''),
    isMismatch: Boolean(wire.is_mismatch),
  };
}

function storyPoints(wire: Record<string, unknown> = {}): PlanningCommandCenterStoryPoints {
  return {
    total: Number(wire.total ?? 0),
    remaining: Number(wire.remaining ?? 0),
    completed: Number(wire.completed ?? 0),
  };
}

function phase(wire: Record<string, unknown> = {}): PlanningCommandCenterPhase {
  return {
    currentPhase: wire.current_phase as number | null | undefined,
    nextPhase: wire.next_phase as number | null | undefined,
    totalPhases: Number(wire.total_phases ?? 0),
    completedPhases: Number(wire.completed_phases ?? 0),
  };
}

function artifact(wire: Record<string, unknown> = {}): PlanningCommandCenterArtifact {
  return {
    artifactId: String(wire.artifact_id ?? ''),
    path: String(wire.path ?? ''),
    docType: String(wire.doc_type ?? ''),
    title: String(wire.title ?? ''),
    status: String(wire.status ?? ''),
    exists: wire.exists as boolean | null | undefined,
  };
}

function relatedFile(wire: Record<string, unknown> = {}): PlanningCommandCenterRelatedFile {
  return {
    path: String(wire.path ?? ''),
    docType: String(wire.doc_type ?? ''),
    sizeBytes: wire.size_bytes as number | null | undefined,
    lastModified: String(wire.last_modified ?? ''),
    addable: Boolean(wire.addable ?? true),
  };
}

function phaseRow(wire: Record<string, unknown> = {}): PlanningCommandCenterPhaseRow {
  return {
    phaseNumber: wire.phase_number as number | null | undefined,
    name: String(wire.name ?? ''),
    storyPoints: wire.story_points as number | null | undefined,
    phaseFiles: Array.isArray(wire.phase_files) ? wire.phase_files.map(String) : [],
    domain: String(wire.domain ?? ''),
    model: String(wire.model ?? ''),
    agents: Array.isArray(wire.agents) ? wire.agents.map(String) : [],
    status: String(wire.status ?? ''),
    details: (wire.details as Record<string, unknown>) ?? {},
  };
}

function launchAgent(wire: Record<string, unknown> = {}): PlanningCommandCenterLaunchAgent {
  return {
    agentId: String(wire.agent_id ?? ''),
    label: String(wire.label ?? ''),
    skills: Array.isArray(wire.skills) ? wire.skills.map(String) : [],
    tools: Array.isArray(wire.tools) ? wire.tools.map(String) : [],
    state: String(wire.state ?? ''),
  };
}

function launchBatch(wire: Record<string, unknown> | null | undefined): PlanningCommandCenterLaunchBatch | null {
  if (!wire) return null;
  return {
    batchId: String(wire.batch_id ?? ''),
    label: String(wire.label ?? ''),
    readiness: String(wire.readiness ?? ''),
    agents: Array.isArray(wire.agents) ? wire.agents.map((item) => launchAgent(item as Record<string, unknown>)) : [],
    queuedCount: Number(wire.queued_count ?? 0),
    runningCount: Number(wire.running_count ?? 0),
  };
}

function worktree(wire: Record<string, unknown> | null | undefined): PlanningCommandCenterWorktree | null {
  if (!wire) return null;
  return {
    contextId: String(wire.context_id ?? ''),
    path: String(wire.path ?? ''),
    branch: String(wire.branch ?? ''),
    status: String(wire.status ?? ''),
    phaseNumber: wire.phase_number as number | null | undefined,
    batchId: String(wire.batch_id ?? ''),
  };
}

function gitState(wire: Record<string, unknown> | null | undefined): PlanningCommandCenterGitState | null {
  if (!wire) return null;
  return {
    pathExists: wire.path_exists as boolean | null | undefined,
    head: String(wire.head ?? ''),
    dirtyCount: wire.dirty_count as number | null | undefined,
    stashCount: wire.stash_count as number | null | undefined,
    upstream: String(wire.upstream ?? ''),
    ahead: wire.ahead as number | null | undefined,
    behind: wire.behind as number | null | undefined,
    probedAt: String(wire.probed_at ?? ''),
    warnings: Array.isArray(wire.warnings) ? wire.warnings.map(String) : [],
  };
}

function pullRequest(wire: Record<string, unknown> | null | undefined): PlanningCommandCenterPullRequest | null {
  if (!wire) return null;
  return {
    provider: String(wire.provider ?? ''),
    number: wire.number as number | null | undefined,
    url: String(wire.url ?? ''),
    state: String(wire.state ?? ''),
    reviewStatus: String(wire.review_status ?? ''),
  };
}

function blocker(wire: Record<string, unknown> = {}): PlanningCommandCenterBlocker {
  return {
    label: String(wire.label ?? ''),
    reason: String(wire.reason ?? ''),
    severity: String(wire.severity ?? ''),
  };
}

function capabilities(wire: Record<string, unknown> = {}): PlanningCommandCenterCapabilities {
  return {
    copyCommand: Boolean(wire.copy_command ?? true),
    launch: Boolean(wire.launch),
    review: Boolean(wire.review),
    merge: Boolean(wire.merge),
    cleanup: Boolean(wire.cleanup),
    openPr: Boolean(wire.open_pr),
    editCommand: Boolean(wire.edit_command ?? true),
  };
}

export function adaptPlanningCommandCenterItem(wire: Record<string, unknown>): PlanningCommandCenterItem {
  return {
    feature: feature((wire.feature as Record<string, unknown>) ?? {}),
    status: status((wire.status as Record<string, unknown>) ?? {}),
    storyPoints: storyPoints((wire.story_points as Record<string, unknown>) ?? {}),
    phase: phase((wire.phase as Record<string, unknown>) ?? {}),
    artifacts: Array.isArray(wire.artifacts) ? wire.artifacts.map((item) => artifact(item as Record<string, unknown>)) : [],
    targetArtifact: targetArtifact(wire.target_artifact as Record<string, unknown> | null | undefined),
    command: commandResolution(wire.command as Record<string, unknown> | null | undefined),
    relatedFiles: Array.isArray(wire.related_files) ? wire.related_files.map((item) => relatedFile(item as Record<string, unknown>)) : [],
    phaseRows: Array.isArray(wire.phase_rows) ? wire.phase_rows.map((item) => phaseRow(item as Record<string, unknown>)) : [],
    launchBatch: launchBatch(wire.launch_batch as Record<string, unknown> | null | undefined),
    worktree: worktree(wire.worktree as Record<string, unknown> | null | undefined),
    gitState: gitState(wire.git_state as Record<string, unknown> | null | undefined),
    pullRequest: pullRequest(wire.pull_request as Record<string, unknown> | null | undefined),
    blockers: Array.isArray(wire.blockers) ? wire.blockers.map((item) => blocker(item as Record<string, unknown>)) : [],
    lastActivity: (wire.last_activity as Record<string, unknown>) ?? {},
    capabilities: capabilities((wire.capabilities as Record<string, unknown>) ?? {}),
  };
}

export function adaptPlanningCommandCenterPage(wire: Record<string, unknown>): PlanningCommandCenterPage {
  return {
    status: (wire.status as 'ok' | 'partial' | 'error') ?? 'ok',
    dataFreshness: String(wire.data_freshness ?? ''),
    generatedAt: String(wire.generated_at ?? ''),
    sourceRefs: Array.isArray(wire.source_refs) ? wire.source_refs.map(String) : [],
    projectId: String(wire.project_id ?? ''),
    items: Array.isArray(wire.items) ? wire.items.map((item) => adaptPlanningCommandCenterItem(item as Record<string, unknown>)) : [],
    total: Number(wire.total ?? 0),
    page: Number(wire.page ?? 1),
    pageSize: Number(wire.page_size ?? 50),
    sortBy: String(wire.sort_by ?? ''),
    sortDirection: wire.sort_direction === 'asc' ? 'asc' : 'desc',
    warnings: Array.isArray(wire.warnings) ? wire.warnings.map(String) : [],
  };
}

export async function getPlanningCommandCenter(query: PlanningCommandCenterQuery = {}): Promise<PlanningCommandCenterPage> {
  const wire = await commandCenterFetch<Record<string, unknown>>('', queryParams(query));
  return adaptPlanningCommandCenterPage(wire);
}

export async function getPlanningCommandCenterItem(
  featureId: string,
  query: Pick<PlanningCommandCenterQuery, 'projectId'> = {},
): Promise<PlanningCommandCenterItem> {
  const params = new URLSearchParams();
  appendParam(params, 'project_id', query.projectId);
  const wire = await commandCenterFetch<Record<string, unknown>>(`/${encodeURIComponent(featureId)}`, params);
  return adaptPlanningCommandCenterItem(wire);
}
