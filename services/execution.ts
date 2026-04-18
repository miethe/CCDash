import {
  ExecutionPolicyResult,
  ExecutionRun,
  ExecutionRunEventPage,
  Feature,
  FeatureDependencyEvidence,
  FeatureDependencyState,
  FeatureFamilyItem,
  FeatureFamilyPosition,
  FeatureFamilySummary,
  ExecutionGateState,
  FeatureExecutionWarning,
  FeatureExecutionContext,
  RecommendedStack,
  RecommendedStackComponent,
  SimilarWorkExample,
  StackRecommendationEvidence,
  LaunchPreparationRequest,
  LaunchPreparation,
  LaunchProviderCapability,
  LaunchStartRequest,
  LaunchStartResponse,
  WorktreeContext,
  WorktreeContextStatus,
} from '../types';

const API_BASE = '/api/features';
const EXECUTION_API_BASE = '/api/execution';

const asArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

const normalizeSimilarWork = (item: SimilarWorkExample): SimilarWorkExample => ({
  ...item,
  reasons: asArray<string>(item?.reasons),
  matchedComponents: asArray<string>(item?.matchedComponents),
});

const normalizeStackEvidence = (evidence: StackRecommendationEvidence): StackRecommendationEvidence => ({
  ...evidence,
  similarWork: asArray<SimilarWorkExample>(evidence?.similarWork).map(normalizeSimilarWork),
});

const normalizeRecommendedStack = (stack?: RecommendedStack | null): RecommendedStack | null | undefined => {
  if (!stack) return stack;
  return {
    ...stack,
    components: asArray<RecommendedStackComponent>(stack.components),
  };
};

const normalizeFeatureDependencyEvidence = (
  evidence?: FeatureDependencyEvidence | null,
): FeatureDependencyEvidence | null | undefined => {
  if (!evidence) return evidence;
  return {
    ...evidence,
    dependencyCompletionEvidence: asArray<string>(evidence.dependencyCompletionEvidence),
    blockingDocumentIds: asArray<string>(evidence.blockingDocumentIds),
  };
};

const normalizeFeatureDependencyState = (
  state?: FeatureDependencyState | null,
): FeatureDependencyState | null | undefined => {
  if (!state) return state;
  return {
    ...state,
    blockingFeatureIds: asArray<string>(state.blockingFeatureIds),
    blockingDocumentIds: asArray<string>(state.blockingDocumentIds),
    completionEvidence: asArray<string>(state.completionEvidence),
    dependencies: asArray<FeatureDependencyEvidence>(state.dependencies).map((evidence) =>
      normalizeFeatureDependencyEvidence(evidence) ?? evidence,
    ),
  };
};

const normalizeFeatureFamilyItem = (item?: FeatureFamilyItem | null): FeatureFamilyItem | null | undefined => {
  if (!item) return item;
  return {
    ...item,
    dependencyState: normalizeFeatureDependencyState(item.dependencyState) ?? item.dependencyState,
  };
};

const normalizeFeatureFamilySummary = (
  summary?: FeatureFamilySummary | null,
): FeatureFamilySummary | null | undefined => {
  if (!summary) return summary;
  return {
    ...summary,
    items: asArray<FeatureFamilyItem>(summary.items).map((item) => normalizeFeatureFamilyItem(item) ?? item),
    nextRecommendedFamilyItem: normalizeFeatureFamilyItem(summary.nextRecommendedFamilyItem) ?? summary.nextRecommendedFamilyItem,
  };
};

const normalizeFeatureFamilyPosition = (
  position?: FeatureFamilyPosition | null,
): FeatureFamilyPosition | null | undefined => {
  if (!position) return position;
  return { ...position };
};

const normalizeExecutionGate = (gate?: ExecutionGateState | null): ExecutionGateState | null | undefined => {
  if (!gate) return gate;
  return {
    ...gate,
    dependencyState: normalizeFeatureDependencyState(gate.dependencyState) ?? gate.dependencyState,
    familySummary: normalizeFeatureFamilySummary(gate.familySummary) ?? gate.familySummary,
    familyPosition: normalizeFeatureFamilyPosition(gate.familyPosition) ?? gate.familyPosition,
  };
};

const normalizeFeature = (feature?: Feature | null): Feature | null | undefined => {
  if (!feature) return feature;
  return {
    ...feature,
    linkedDocs: asArray(feature.linkedDocs),
    linkedFeatures: asArray(feature.linkedFeatures),
    phases: asArray(feature.phases),
    relatedFeatures: asArray<string>(feature.relatedFeatures),
    blockingFeatures: asArray<FeatureDependencyEvidence>(feature.blockingFeatures).map((evidence) =>
      normalizeFeatureDependencyEvidence(evidence) ?? evidence,
    ),
    dependencyState: normalizeFeatureDependencyState(feature.dependencyState) ?? feature.dependencyState,
    familySummary: normalizeFeatureFamilySummary(feature.familySummary) ?? feature.familySummary,
    familyPosition: normalizeFeatureFamilyPosition(feature.familyPosition) ?? feature.familyPosition,
    executionGate: normalizeExecutionGate(feature.executionGate) ?? feature.executionGate,
    nextRecommendedFamilyItem:
      normalizeFeatureFamilyItem(feature.nextRecommendedFamilyItem) ?? feature.nextRecommendedFamilyItem,
  };
};

const normalizeFeatureExecutionContext = (context: FeatureExecutionContext): FeatureExecutionContext => ({
  ...context,
  feature: normalizeFeature(context?.feature) ?? context.feature,
  documents: asArray(context?.documents),
  sessions: asArray(context?.sessions),
  warnings: asArray<FeatureExecutionWarning>(context?.warnings),
  recommendedStack: normalizeRecommendedStack(context?.recommendedStack),
  dependencyState: normalizeFeatureDependencyState(context?.dependencyState) ?? context.dependencyState,
  familySummary: normalizeFeatureFamilySummary(context?.familySummary) ?? context.familySummary,
  familyPosition: normalizeFeatureFamilyPosition(context?.familyPosition) ?? context.familyPosition,
  executionGate: normalizeExecutionGate(context?.executionGate) ?? context.executionGate,
  recommendedFamilyItem:
    normalizeFeatureFamilyItem(context?.recommendedFamilyItem) ?? context.recommendedFamilyItem,
  stackAlternatives: asArray<RecommendedStack>(context?.stackAlternatives).map((stack) => {
    const normalized = normalizeRecommendedStack(stack);
    return normalized ?? {
      ...stack,
      components: [],
    };
  }),
  stackEvidence: asArray<StackRecommendationEvidence>(context?.stackEvidence).map(normalizeStackEvidence),
  definitionResolutionWarnings: asArray<FeatureExecutionWarning>(context?.definitionResolutionWarnings),
});

export interface ExecutionEventPayload {
  eventType:
    | 'execution_workbench_opened'
    | 'execution_begin_work_clicked'
    | 'execution_recommendation_generated'
    | 'execution_blocked_state_viewed'
    | 'execution_dependency_navigated'
    | 'execution_family_item_selected'
    | 'execution_command_copied'
    | 'execution_source_link_clicked';
  featureId?: string;
  recommendationRuleId?: string;
  command?: string;
  metadata?: Record<string, unknown>;
}

export interface ExecutionRunRequest {
  command: string;
  cwd?: string;
  envProfile?: string;
  featureId?: string;
  recommendationRuleId?: string;
  metadata?: Record<string, unknown>;
}

export interface ExecutionRunApprovalRequest {
  decision: 'approved' | 'denied';
  reason?: string;
  actor?: string;
}

export interface ExecutionRunCancelRequest {
  reason?: string;
  actor?: string;
}

export interface ExecutionRunRetryRequest {
  acknowledgeFailure: boolean;
  actor?: string;
  metadata?: Record<string, unknown>;
}

export async function getFeatureExecutionContext(featureId: string): Promise<FeatureExecutionContext> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(featureId)}/execution-context`);
  if (!res.ok) {
    throw new Error(`Failed to fetch execution context (${res.status})`);
  }
  const payload = await res.json() as FeatureExecutionContext;
  return normalizeFeatureExecutionContext(payload);
}

export async function trackExecutionEvent(payload: ExecutionEventPayload): Promise<void> {
  try {
    await fetch(`${API_BASE}/execution-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    // Telemetry should never block UX flows.
  }
}

export async function checkExecutionPolicy(payload: {
  command: string;
  cwd?: string;
  envProfile?: string;
}): Promise<ExecutionPolicyResult> {
  const res = await fetch(`${EXECUTION_API_BASE}/policy-check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to evaluate execution policy (${res.status})`);
  }
  return res.json();
}

export async function createExecutionRun(payload: ExecutionRunRequest): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to create execution run (${res.status})`);
  }
  return res.json();
}

export async function listExecutionRuns(params?: {
  featureId?: string;
  limit?: number;
  offset?: number;
}): Promise<ExecutionRun[]> {
  const query = new URLSearchParams();
  if (params?.featureId) query.set('feature_id', params.featureId);
  if (typeof params?.limit === 'number') query.set('limit', String(params.limit));
  if (typeof params?.offset === 'number') query.set('offset', String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : '';

  const res = await fetch(`${EXECUTION_API_BASE}/runs${suffix}`);
  if (!res.ok) {
    throw new Error(`Failed to list execution runs (${res.status})`);
  }
  return res.json();
}

export async function getExecutionRun(runId: string): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch execution run (${res.status})`);
  }
  return res.json();
}

export async function listExecutionRunEvents(
  runId: string,
  params?: { afterSequence?: number; limit?: number },
): Promise<ExecutionRunEventPage> {
  const query = new URLSearchParams();
  if (typeof params?.afterSequence === 'number') query.set('after_sequence', String(params.afterSequence));
  if (typeof params?.limit === 'number') query.set('limit', String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}/events${suffix}`);
  if (!res.ok) {
    throw new Error(`Failed to list run events (${res.status})`);
  }
  return res.json();
}

export async function approveExecutionRun(
  runId: string,
  payload: ExecutionRunApprovalRequest,
): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to update execution approval (${res.status})`);
  }
  return res.json();
}

export async function cancelExecutionRun(
  runId: string,
  payload: ExecutionRunCancelRequest,
): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to cancel execution run (${res.status})`);
  }
  return res.json();
}

export async function retryExecutionRun(
  runId: string,
  payload: ExecutionRunRetryRequest,
): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}/retry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to retry execution run (${res.status})`);
  }
  return res.json();
}

export async function prepareLaunch(
  payload: LaunchPreparationRequest,
): Promise<LaunchPreparation> {
  const res = await fetch(`${EXECUTION_API_BASE}/launch/prepare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to prepare launch (${res.status})`);
  return res.json();
}

export async function startLaunch(
  payload: LaunchStartRequest,
): Promise<LaunchStartResponse> {
  const res = await fetch(`${EXECUTION_API_BASE}/launch/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Failed to start launch (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  return res.json();
}

export async function listWorktreeContexts(params?: {
  featureId?: string;
  phaseNumber?: number;
  batchId?: string;
  status?: WorktreeContextStatus;
  limit?: number;
  offset?: number;
}): Promise<{ items: WorktreeContext[]; total: number }> {
  const query = new URLSearchParams();
  if (params?.featureId) query.set('feature_id', params.featureId);
  if (typeof params?.phaseNumber === 'number') query.set('phase_number', String(params.phaseNumber));
  if (params?.batchId) query.set('batch_id', params.batchId);
  if (params?.status) query.set('status', params.status);
  if (typeof params?.limit === 'number') query.set('limit', String(params.limit));
  if (typeof params?.offset === 'number') query.set('offset', String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await fetch(`${EXECUTION_API_BASE}/worktree-contexts${suffix}`);
  if (!res.ok) throw new Error(`Failed to list worktree contexts (${res.status})`);
  return res.json();
}

export async function createWorktreeContext(payload: {
  projectId: string;
  featureId?: string;
  phaseNumber?: number;
  batchId?: string;
  branch?: string;
  worktreePath?: string;
  baseBranch?: string;
  provider?: string;
  notes?: string;
  metadata?: Record<string, unknown>;
  createdBy?: string;
}): Promise<WorktreeContext> {
  const res = await fetch(`${EXECUTION_API_BASE}/worktree-contexts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to create worktree context (${res.status})`);
  return res.json();
}

export interface LaunchCapabilities {
  enabled: boolean;
  disabledReason: string;
  providers: LaunchProviderCapability[];
  /** Whether the planning control plane surfaces are enabled (PCP-603). */
  planningEnabled: boolean;
}

export async function getLaunchCapabilities(): Promise<LaunchCapabilities> {
  const res = await fetch(`${EXECUTION_API_BASE}/launch/capabilities`);
  if (!res.ok) throw new Error(`Failed to load launch capabilities (${res.status})`);
  return res.json();
}
