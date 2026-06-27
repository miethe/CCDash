/**
 * Shared fixture helpers for Multi-Project Planning Command Center (MPCC) tests.
 *
 * Exports typed builder functions and pre-assembled constant fixtures that
 * cover the full aggregate DTO contract introduced by MPCC-101:
 *
 *   ProjectDisplayMetadata, ProjectWorkItemCounts, ProjectSummary,
 *   ProjectIdentityFields, AggregateWorkItem, AggregateSessionWorkerSummary,
 *   AggregateSessionCard, AggregatePagination, ProjectWarning,
 *   MultiProjectCommandCenterResponse, AggregateBoardGroup,
 *   MultiProjectSessionBoardResponse.
 *
 * The fixture data is VALUE-CONSISTENT with the Python counterpart at
 * `backend/tests/fixtures/multi_project_planning.py` — same project IDs,
 * names, counts, and session IDs — enabling cross-layer contract tests.
 *
 * Scenarios covered
 * -----------------
 * - 3 healthy projects with distinct display metadata (color / group).
 * - 1 stale project (isStale: true, large freshnessSeconds).
 * - 1 failed project (error populated; appears in projectSummaries + a warning).
 * - Active sessions across projects, including root→worker lineage (an
 *   AggregateSessionCard with nested workers).
 * - Work items (AggregateWorkItem) with blocked / review / stale variety.
 * - Fully assembled MultiProjectCommandCenterResponse and
 *   MultiProjectSessionBoardResponse with pagination + warnings.
 */

import type {
  AggregateBoardGroup,
  AggregatePagination,
  AggregateSessionCard,
  AggregateSessionWorkerSummary,
  AggregateWorkItem,
  MultiProjectCommandCenterResponse,
  MultiProjectSessionBoardResponse,
  PlanningAgentSessionCard,
  PlanningCommandCenterItem,
  ProjectDisplayMetadata,
  ProjectIdentityFields,
  ProjectSummary,
  ProjectWarning,
  ProjectWorkItemCounts,
} from '@/types';

// ---------------------------------------------------------------------------
// Canonical project IDs / names (mirrored in the Python fixture module)
// ---------------------------------------------------------------------------

export const PROJ_ALPHA_ID = 'proj-alpha';
export const PROJ_ALPHA_NAME = 'Alpha Platform';

export const PROJ_BETA_ID = 'proj-beta';
export const PROJ_BETA_NAME = 'Beta Mobile';

export const PROJ_GAMMA_ID = 'proj-gamma';
export const PROJ_GAMMA_NAME = 'Gamma Infra';

export const PROJ_STALE_ID = 'proj-stale';
export const PROJ_STALE_NAME = 'Stale Repo';

export const PROJ_FAILED_ID = 'proj-failed';
export const PROJ_FAILED_NAME = 'Failed Repo';

/** Canonical session IDs (same values used in Python fixtures). */
export const SESSION_ROOT_ID = 'sess-root-001';
export const SESSION_WORKER_A_ID = 'sess-worker-002';
export const SESSION_WORKER_B_ID = 'sess-worker-003';
export const SESSION_BETA_ID = 'sess-beta-001';

// ---------------------------------------------------------------------------
// Display metadata builders
// ---------------------------------------------------------------------------

export function makeDisplayMetadata(overrides: Partial<ProjectDisplayMetadata> = {}): ProjectDisplayMetadata {
  return { ...overrides };
}

export const META_ALPHA: ProjectDisplayMetadata = makeDisplayMetadata({
  color: '#6366f1',
  group: 'core-platform',
  sortOrder: 1,
});

export const META_BETA: ProjectDisplayMetadata = makeDisplayMetadata({
  color: '#22c55e',
  group: 'mobile',
  sortOrder: 2,
});

export const META_GAMMA: ProjectDisplayMetadata = makeDisplayMetadata({
  color: '#f59e0b',
  group: 'infra',
  sortOrder: 3,
});

export const META_STALE: ProjectDisplayMetadata = makeDisplayMetadata({
  color: '#94a3b8',
  group: 'default',
  sortOrder: 4,
});

export const META_FAILED: ProjectDisplayMetadata = makeDisplayMetadata({
  color: '#ef4444',
  group: 'default',
  sortOrder: 5,
});

// ---------------------------------------------------------------------------
// ProjectWorkItemCounts builder
// ---------------------------------------------------------------------------

export function makeWorkItemCounts(overrides: Partial<ProjectWorkItemCounts> = {}): ProjectWorkItemCounts {
  return {
    workItems: 0,
    blocked: 0,
    review: 0,
    stale: 0,
    activeSessions: 0,
    errors: 0,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// ProjectSummary builders
// ---------------------------------------------------------------------------

export function makeProjectSummary(
  projectId: string,
  name: string,
  overrides: Partial<ProjectSummary> = {},
): ProjectSummary {
  return {
    projectId,
    name,
    displayMetadata: {},
    counts: makeWorkItemCounts(),
    isStale: false,
    error: null,
    lastUpdated: '2026-05-29T08:00:00+00:00',
    freshnessSeconds: 120,
    ...overrides,
  };
}

// ── 3 healthy projects ───────────────────────────────────────────────────────

export const SUMMARY_ALPHA: ProjectSummary = makeProjectSummary(PROJ_ALPHA_ID, PROJ_ALPHA_NAME, {
  displayMetadata: META_ALPHA,
  counts: makeWorkItemCounts({ workItems: 8, blocked: 1, review: 2, stale: 0, activeSessions: 2, errors: 0 }),
  isStale: false,
  freshnessSeconds: 60,
});

export const SUMMARY_BETA: ProjectSummary = makeProjectSummary(PROJ_BETA_ID, PROJ_BETA_NAME, {
  displayMetadata: META_BETA,
  counts: makeWorkItemCounts({ workItems: 5, blocked: 0, review: 1, stale: 1, activeSessions: 1, errors: 0 }),
  isStale: false,
  freshnessSeconds: 90,
});

export const SUMMARY_GAMMA: ProjectSummary = makeProjectSummary(PROJ_GAMMA_ID, PROJ_GAMMA_NAME, {
  displayMetadata: META_GAMMA,
  counts: makeWorkItemCounts({ workItems: 3, blocked: 0, review: 0, stale: 0, activeSessions: 0, errors: 0 }),
  isStale: false,
  freshnessSeconds: 200,
});

// ── Stale project ────────────────────────────────────────────────────────────

export const SUMMARY_STALE: ProjectSummary = makeProjectSummary(PROJ_STALE_ID, PROJ_STALE_NAME, {
  displayMetadata: META_STALE,
  counts: makeWorkItemCounts({ workItems: 2, stale: 2 }),
  isStale: true,
  freshnessSeconds: 7200, // 2 hours — clearly stale
  lastUpdated: '2026-05-29T06:00:00+00:00',
});

// ── Failed project ───────────────────────────────────────────────────────────

export const SUMMARY_FAILED: ProjectSummary = makeProjectSummary(PROJ_FAILED_ID, PROJ_FAILED_NAME, {
  displayMetadata: META_FAILED,
  counts: makeWorkItemCounts(), // partial / empty
  isStale: null,
  error: 'aggregate query timed out after 30s',
  freshnessSeconds: null,
  lastUpdated: null,
});

/** All five summaries in declaration order. */
export const ALL_PROJECT_SUMMARIES: ProjectSummary[] = [
  SUMMARY_ALPHA,
  SUMMARY_BETA,
  SUMMARY_GAMMA,
  SUMMARY_STALE,
  SUMMARY_FAILED,
];

// ---------------------------------------------------------------------------
// ProjectIdentityFields constants
// ---------------------------------------------------------------------------

export function makeIdentity(
  projectId: string,
  projectName: string,
  overrides: Partial<ProjectIdentityFields> = {},
): ProjectIdentityFields {
  return { projectId, projectName, ...overrides };
}

export const IDENTITY_ALPHA: ProjectIdentityFields = makeIdentity(PROJ_ALPHA_ID, PROJ_ALPHA_NAME, {
  projectColor: '#6366f1',
  projectGroup: 'core-platform',
});

export const IDENTITY_BETA: ProjectIdentityFields = makeIdentity(PROJ_BETA_ID, PROJ_BETA_NAME, {
  projectColor: '#22c55e',
  projectGroup: 'mobile',
});

export const IDENTITY_GAMMA: ProjectIdentityFields = makeIdentity(PROJ_GAMMA_ID, PROJ_GAMMA_NAME, {
  projectColor: '#f59e0b',
  projectGroup: 'infra',
});

export const IDENTITY_FAILED: ProjectIdentityFields = makeIdentity(PROJ_FAILED_ID, PROJ_FAILED_NAME, {
  projectColor: '#ef4444',
  projectGroup: 'default',
});

// ---------------------------------------------------------------------------
// V1 PlanningCommandCenterItem builder
// ---------------------------------------------------------------------------

export function makeV1Item(overrides: {
  featureId: string;
  featureSlug: string;
  name: string;
  effectiveStatus?: PlanningCommandCenterItem['status']['effectiveStatus'];
  rawStatus?: string;
  planningSignal?: string;
  isMismatch?: boolean;
  totalPhases?: number;
  completedPhases?: number;
  currentPhase?: number | null;
  storyPointsTotal?: number;
  storyPointsRemaining?: number;
  storyPointsCompleted?: number;
  blockers?: PlanningCommandCenterItem['blockers'];
  category?: string;
  priority?: string;
  summary?: string;
}): PlanningCommandCenterItem {
  const {
    featureId,
    featureSlug,
    name,
    effectiveStatus = 'in-progress',
    rawStatus = 'in-progress',
    planningSignal = 'active',
    isMismatch = false,
    totalPhases = 4,
    completedPhases = 1,
    currentPhase = 2,
    storyPointsTotal = 8,
    storyPointsRemaining = 5,
    storyPointsCompleted = 3,
    blockers = [],
    category = 'enhancement',
    priority = 'high',
    summary = name,
  } = overrides;

  return {
    feature: { featureId, featureSlug, name, category, tags: [], priority, summary },
    status: {
      rawStatus,
      effectiveStatus,
      planningSignal,
      mismatchState: 'none',
      isMismatch,
    },
    storyPoints: {
      total: storyPointsTotal,
      remaining: storyPointsRemaining,
      completed: storyPointsCompleted,
    },
    phase: {
      currentPhase,
      nextPhase: currentPhase != null ? currentPhase + 1 : null,
      totalPhases,
      completedPhases,
    },
    artifacts: [],
    targetArtifact: null,
    command: null,
    relatedFiles: [],
    phaseRows: [],
    launchBatch: null,
    worktree: null,
    gitState: null,
    pullRequest: null,
    blockers,
    lastActivity: {},
    capabilities: {
      copyCommand: true,
      launch: true,
      review: false,
      merge: false,
      cleanup: false,
      openPr: false,
      editCommand: true,
    },
  };
}

// ── Work items covering blocked / review / stale variety ─────────────────────

export const ITEM_ALPHA_BLOCKED: AggregateWorkItem = {
  project: IDENTITY_ALPHA,
  item: makeV1Item({
    featureId: 'feat-alpha-001',
    featureSlug: 'auth-hardening',
    name: 'Auth Hardening',
    effectiveStatus: 'blocked',
    planningSignal: 'blocked',
    blockers: [{ label: 'Awaiting security review', reason: 'external', severity: 'high' }],
  }),
};

export const ITEM_ALPHA_REVIEW: AggregateWorkItem = {
  project: IDENTITY_ALPHA,
  item: makeV1Item({
    featureId: 'feat-alpha-002',
    featureSlug: 'api-rate-limiting',
    name: 'API Rate Limiting',
    rawStatus: 'review',
    effectiveStatus: 'review',
    planningSignal: 'review',
  }),
};

export const ITEM_BETA_STALE: AggregateWorkItem = {
  project: IDENTITY_BETA,
  item: makeV1Item({
    featureId: 'feat-beta-001',
    featureSlug: 'push-notifications',
    name: 'Push Notifications',
    rawStatus: 'completed',
    effectiveStatus: 'stale',
    planningSignal: 'stale',
    storyPointsRemaining: 0,
  }),
};

export const ITEM_BETA_INPROGRESS: AggregateWorkItem = {
  project: IDENTITY_BETA,
  item: makeV1Item({
    featureId: 'feat-beta-002',
    featureSlug: 'offline-mode',
    name: 'Offline Mode',
  }),
};

export const ITEM_GAMMA_INPROGRESS: AggregateWorkItem = {
  project: IDENTITY_GAMMA,
  item: makeV1Item({
    featureId: 'feat-gamma-001',
    featureSlug: 'k8s-autoscaling',
    name: 'K8s Autoscaling',
    priority: 'medium',
  }),
};

/** All five work items in declaration order. */
export const ALL_WORK_ITEMS: AggregateWorkItem[] = [
  ITEM_ALPHA_BLOCKED,
  ITEM_ALPHA_REVIEW,
  ITEM_BETA_STALE,
  ITEM_BETA_INPROGRESS,
  ITEM_GAMMA_INPROGRESS,
];

// ---------------------------------------------------------------------------
// V1 PlanningAgentSessionCard builder
// ---------------------------------------------------------------------------

export function makeV1Card(overrides: {
  sessionId: string;
  state?: PlanningAgentSessionCard['state'];
  model?: string;
  agentName?: string;
  parentSessionId?: string;
  rootSessionId?: string;
  startedAt?: string;
  lastActivityAt?: string;
  durationSeconds?: number;
  featureId?: string;
  featureName?: string;
}): PlanningAgentSessionCard {
  const {
    sessionId,
    state = 'running',
    model = 'claude-sonnet-4-6',
    agentName = 'dev-agent',
    parentSessionId,
    rootSessionId = sessionId,
    startedAt = '2026-05-29T09:00:00+00:00',
    lastActivityAt = '2026-05-29T09:30:00+00:00',
    durationSeconds = 1800,
    featureId,
    featureName,
  } = overrides;

  return {
    sessionId,
    agentName,
    agentType: 'claude_code',
    state,
    model,
    correlation: featureId
      ? {
          featureId,
          featureName: featureName ?? featureId,
          phaseNumber: 2,
          confidence: 'high' as const,
          evidence: [
            {
              sourceType: 'explicit_link',
              sourceLabel: 'entity_links',
              confidence: 'high' as const,
              detail: 'linked via entity_links',
            },
          ],
        }
      : undefined,
    transcriptHref: `/sessions/${sessionId}`,
    planningHref: featureId ? `/planning/${featureId}` : undefined,
    phaseHref: undefined,
    parentSessionId,
    rootSessionId,
    startedAt,
    lastActivityAt,
    durationSeconds,
    tokenSummary: {
      tokensIn: 20000,
      tokensOut: 10000,
      totalTokens: 45000,
      contextWindowPct: 0.35,
      model,
    },
    relationships: [],
    activityMarkers: [],
  };
}

// ---------------------------------------------------------------------------
// AggregateSessionWorkerSummary constants
// ---------------------------------------------------------------------------

export const WORKER_A: AggregateSessionWorkerSummary = {
  sessionId: SESSION_WORKER_A_ID,
  agentName: 'python-backend-engineer',
  state: 'running',
  model: 'claude-sonnet-4-6',
  startedAt: '2026-05-29T09:05:00+00:00',
  lastActivityAt: '2026-05-29T09:35:00+00:00',
  durationSeconds: 1800,
};

export const WORKER_B: AggregateSessionWorkerSummary = {
  sessionId: SESSION_WORKER_B_ID,
  agentName: 'frontend-engineer',
  state: 'completed',
  model: 'claude-sonnet-4-6',
  startedAt: '2026-05-29T09:05:00+00:00',
  lastActivityAt: '2026-05-29T09:25:00+00:00',
  durationSeconds: 1200,
};

// ---------------------------------------------------------------------------
// AggregateSessionCard constants
// ---------------------------------------------------------------------------

/** Root session (alpha project) with two nested workers. */
export const CARD_ALPHA_ROOT: AggregateSessionCard = {
  project: IDENTITY_ALPHA,
  card: makeV1Card({
    sessionId: SESSION_ROOT_ID,
    state: 'running',
    rootSessionId: SESSION_ROOT_ID,
    featureId: 'feat-alpha-001',
    featureName: 'Auth Hardening',
  }),
  workers: [WORKER_A, WORKER_B],
};

/** Beta project — standalone session, no children. */
export const CARD_BETA: AggregateSessionCard = {
  project: IDENTITY_BETA,
  card: makeV1Card({
    sessionId: SESSION_BETA_ID,
    state: 'thinking',
    featureId: 'feat-beta-002',
    featureName: 'Offline Mode',
  }),
  workers: [],
};

/** All session cards in declaration order. */
export const ALL_SESSION_CARDS: AggregateSessionCard[] = [CARD_ALPHA_ROOT, CARD_BETA];

// ---------------------------------------------------------------------------
// Pagination / warnings
// ---------------------------------------------------------------------------

export const PAGINATION_FULL: AggregatePagination = {
  page: 1,
  pageSize: 50,
  total: 5,
  hasMore: false,
};

export const PAGINATION_PAGE2: AggregatePagination = {
  page: 2,
  pageSize: 3,
  total: 5,
  hasMore: false,
};

export const WARNING_STALE: ProjectWarning = {
  projectId: PROJ_STALE_ID,
  message: 'Project data is stale — last sync was 2 hours ago.',
  severity: 'low',
  code: 'sync_stale',
};

export const WARNING_FAILED: ProjectWarning = {
  projectId: PROJ_FAILED_ID,
  message: 'Aggregate query timed out after 30s — displaying partial data.',
  severity: 'high',
  code: 'feature_load_failed',
};

/** Both warnings. */
export const ALL_WARNINGS: ProjectWarning[] = [WARNING_STALE, WARNING_FAILED];

// ---------------------------------------------------------------------------
// Assembled top-level responses
// ---------------------------------------------------------------------------

export function makeCommandCenterResponse(
  overrides: Partial<MultiProjectCommandCenterResponse> = {},
): MultiProjectCommandCenterResponse {
  return {
    status: 'partial',
    items: ALL_WORK_ITEMS,
    projectSummaries: ALL_PROJECT_SUMMARIES,
    pagination: PAGINATION_FULL,
    warnings: ALL_WARNINGS,
    generatedAt: '2026-05-29T09:00:00+00:00',
    dataFreshness: '2026-05-29T08:00:00+00:00',
    ...overrides,
  };
}

/** Fully assembled constant — the canonical MPCC fixture. */
export const COMMAND_CENTER_RESPONSE: MultiProjectCommandCenterResponse = makeCommandCenterResponse();

export function makeBoardGroup(
  groupKey: string,
  groupLabel: string,
  cards: AggregateSessionCard[],
  groupType = 'state',
): AggregateBoardGroup {
  return {
    groupKey,
    groupLabel,
    groupType,
    cards,
    cardCount: cards.length,
  };
}

export const BOARD_GROUP_RUNNING: AggregateBoardGroup = makeBoardGroup('running', 'Running', [CARD_ALPHA_ROOT]);
export const BOARD_GROUP_THINKING: AggregateBoardGroup = makeBoardGroup('thinking', 'Thinking', [CARD_BETA]);

export const ALL_BOARD_GROUPS: AggregateBoardGroup[] = [BOARD_GROUP_RUNNING, BOARD_GROUP_THINKING];

export function makeSessionBoardResponse(
  overrides: Partial<MultiProjectSessionBoardResponse> = {},
): MultiProjectSessionBoardResponse {
  return {
    status: 'partial',
    grouping: 'state',
    groups: ALL_BOARD_GROUPS,
    projectSummaries: ALL_PROJECT_SUMMARIES,
    pagination: { page: 1, pageSize: 50, total: 2, hasMore: false },
    warnings: ALL_WARNINGS,
    totalCardCount: 2,
    activeCount: 2,
    completedCount: 0,
    generatedAt: '2026-05-29T09:00:00+00:00',
    dataFreshness: '2026-05-29T08:00:00+00:00',
    ...overrides,
  };
}

/** Fully assembled constant — the canonical session board fixture. */
export const SESSION_BOARD_RESPONSE: MultiProjectSessionBoardResponse = makeSessionBoardResponse();
