/**
 * Centralized query key registry for TanStack Query.
 *
 * Rules:
 *   - No inline string keys anywhere in the codebase.
 *   - All keys are arrays — TQ serializes them for cache identity.
 *   - projectId is ALWAYS the first segment so that per-project
 *     invalidation can be done with queryClient.invalidateQueries({ queryKey: [projectId] }).
 */

// ─── Sessions ────────────────────────────────────────────────────────────────

export const sessionsKeys = {
  all: (projectId: string) => [projectId, 'sessions'] as const,
  list: (projectId: string, filters?: Record<string, unknown>) =>
    filters != null
      ? ([projectId, 'sessions', 'list', filters] as const)
      : ([projectId, 'sessions', 'list'] as const),
  detail: (projectId: string, sessionId: string) =>
    [projectId, 'sessions', 'detail', sessionId] as const,
};

// ─── Documents ───────────────────────────────────────────────────────────────

export const documentsKeys = {
  all: (projectId: string) => [projectId, 'documents'] as const,
  list: (projectId: string, offset?: number) =>
    offset != null
      ? ([projectId, 'documents', 'list', { offset }] as const)
      : ([projectId, 'documents', 'list'] as const),
  detail: (projectId: string, documentId: string) =>
    [projectId, 'documents', 'detail', documentId] as const,
};

// ─── Tasks ────────────────────────────────────────────────────────────────────

export const tasksKeys = {
  all: (projectId: string) => [projectId, 'tasks'] as const,
  list: (projectId: string, page?: number) =>
    page != null
      ? ([projectId, 'tasks', 'list', { page }] as const)
      : ([projectId, 'tasks', 'list'] as const),
  detail: (projectId: string, taskId: string) =>
    [projectId, 'tasks', 'detail', taskId] as const,
};

// ─── Features ─────────────────────────────────────────────────────────────────

export const featuresKeys = {
  all: (projectId: string) => [projectId, 'features'] as const,
  list: (projectId: string, query?: string, page?: number) =>
    [projectId, 'features', 'list', { query, page }] as const,
  detail: (projectId: string, featureId: string) =>
    [projectId, 'features', 'detail', featureId] as const,
};

// ─── Alerts ───────────────────────────────────────────────────────────────────

export const alertsKeys = {
  all: (projectId: string) => [projectId, 'alerts'] as const,
  list: (projectId: string) => [projectId, 'alerts', 'list'] as const,
  detail: (projectId: string, alertId: string) =>
    [projectId, 'alerts', 'detail', alertId] as const,
};

// ─── Notifications ────────────────────────────────────────────────────────────

export const notificationsKeys = {
  all: (projectId: string) => [projectId, 'notifications'] as const,
  list: (projectId: string) => [projectId, 'notifications', 'list'] as const,
  detail: (projectId: string, notificationId: string) =>
    [projectId, 'notifications', 'detail', notificationId] as const,
};

// ─── Projects ─────────────────────────────────────────────────────────────────
// Projects are global (not scoped to a single project) — no projectId param.
// The list() key is a standalone array so all-project invalidation is simple.

export const projectsKeys = {
  all: () => ['projects'] as const,
  list: () => ['projects', 'list'] as const,
};

// ─── Planning ─────────────────────────────────────────────────────────────────

export const planningKeys = {
  all: (projectId: string) => [projectId, 'planning'] as const,
  list: (projectId: string) => [projectId, 'planning', 'list'] as const,
  detail: (projectId: string, featureId: string) =>
    [projectId, 'planning', 'detail', featureId] as const,
  sessionBoard: (projectId: string, featureId?: string) =>
    featureId != null
      ? ([projectId, 'planning', 'session-board', featureId] as const)
      : ([projectId, 'planning', 'session-board'] as const),
  nextRunPreview: (projectId: string, featureId: string) =>
    [projectId, 'planning', 'next-run-preview', featureId] as const,
  /**
   * OQ-2 resolution: freshnessToken is folded into the query key so that a
   * changed backend dataFreshness value produces a new cache key, triggering
   * a fresh fetch automatically.  staleTime: 0 in the hook so the token (not
   * a timer) is the sole invalidation signal.
   */
  summary: (projectId: string, freshnessToken: string | null | undefined) =>
    [projectId, 'planning', 'summary', { freshnessToken: freshnessToken ?? null }] as const,
  featureContext: (projectId: string, featureId: string) =>
    [projectId, 'planning', 'feature-context', featureId] as const,
  projectSessionBoard: (projectId: string, grouping?: string) =>
    grouping != null
      ? ([projectId, 'planning', 'project-session-board', { grouping }] as const)
      : ([projectId, 'planning', 'project-session-board'] as const),
  featureSessionBoard: (projectId: string, featureId: string, grouping?: string) =>
    grouping != null
      ? ([projectId, 'planning', 'feature-session-board', featureId, { grouping }] as const)
      : ([projectId, 'planning', 'feature-session-board', featureId] as const),
  /**
   * T5-007: Fat-read view bundle key.
   * include is sorted for stable cache identity.
   * GET /api/agent/planning/view?include=<comma-list>
   */
  view: (projectId: string, include: readonly string[]) =>
    [projectId, 'planning', 'view', { include: [...include].sort() }] as const,
};

// ─── Feature Surface ──────────────────────────────────────────────────────────
// Two-tier surface: list-tier (paginated cards) + rollup-tier (batched rollups).
// freshnessToken is folded into the rollup key so a changed backend dataFreshness
// produces a new cache entry (same pattern as planningKeys.summary).

export const featureSurfaceKeys = {
  /** Invalidates ALL feature surface data for a project (list + rollups). */
  all: (projectId: string) => [projectId, 'featureSurface'] as const,
  /**
   * List-tier: paginated card list keyed by the full normalized query.
   * query is the serialized FeatureSurfaceQuery object; page is extracted
   * separately to allow page-only invalidation in future.
   */
  list: (projectId: string, query: Record<string, unknown>, page: number) =>
    [projectId, 'featureSurface', 'list', { query, page }] as const,
  /**
   * Rollup-tier: batched rollup keyed by sorted feature IDs + freshnessToken.
   * staleTime: 30_000 in the hook (30 s soft-TTL matches the old LRU TTL).
   */
  rollup: (projectId: string, ids: string[], freshnessToken: string | null | undefined) =>
    [projectId, 'featureSurface', 'rollup', { ids: [...ids].sort(), freshnessToken: freshnessToken ?? null }] as const,
};

// ─── UI State (scroll position persistence) ───────────────────────────────────
// Stores transient UI state (e.g. virtualizer scroll offsets) in the TQ cache
// so it survives back-nav without touching the server-state cache.

export const uiStateKeys = {
  sessionListScrollOffset: (projectId: string) =>
    [projectId, 'ui', 'sessionList', 'scrollOffset'] as const,
};

// ─── Dashboard ────────────────────────────────────────────────────────────────

export const dashboardKeys = {
  all: (projectId: string) => [projectId, 'dashboard'] as const,
  summary: (projectId: string) => [projectId, 'dashboard', 'summary'] as const,
  analytics: (projectId: string, range?: string) =>
    range != null
      ? ([projectId, 'dashboard', 'analytics', { range }] as const)
      : ([projectId, 'dashboard', 'analytics'] as const),
  /**
   * T5-005: Fat-read bundle key.
   * One request replaces the separate sessions + task_counts fetches.
   * staleTime: 10_000 matches backend @memoized_query TTL (10 s live counts).
   */
  bundle: (projectId: string) => [projectId, 'dashboard', 'bundle'] as const,
};

// ─── Analytics ────────────────────────────────────────────────────────────────

export const analyticsKeys = {
  all: (projectId: string) => [projectId, 'analytics'] as const,
  /**
   * T5-007 best-effort: overview-bundle key for above-fold analytics data.
   * Replaces the separate analyticsService.getOverview() + getSeries() calls.
   */
  overviewBundle: (projectId: string) =>
    [projectId, 'analytics', 'overview-bundle'] as const,
};

// ─── Multi-Project Planning (aggregate / portfolio) ───────────────────────────
// Aggregate queries span multiple projects so there is no single projectId.
// The sentinel 'multi-project' prefix is used instead.  Project-level
// invalidation via [projectId] still works for single-project views; the
// multi-project views are invalidated by their own namespace keys.

export interface MultiProjectCommandCenterFilters {
  projectIds?: string[];
  status?: string;
  kind?: string;
  group?: string;
  search?: string;
  sort?: string;
  page?: number;
  pageSize?: number;
}

export interface MultiProjectSessionBoardFilters {
  projectIds?: string[];
  group?: string;
  groupBy?: string;
  activeWindowMinutes?: number;
  includeWorkers?: boolean;
  page?: number;
  pageSize?: number;
  includeStale?: boolean;
}

export const multiProjectPlanningKeys = {
  /** Invalidates ALL aggregate planning data (command center + session board). */
  all: () => ['multi-project', 'planning'] as const,

  /**
   * Aggregate command-center key.
   * Includes the full filter set (status, kind, group, search, projectIds,
   * page, pageSize, sort) for stable cache identity across filter changes.
   * The feature flag is NOT in the key — a flag change causes a page reload.
   */
  commandCenter: (filters: MultiProjectCommandCenterFilters = {}) =>
    [
      'multi-project',
      'planning',
      'command-center',
      {
        projectIds: filters.projectIds ? [...filters.projectIds].sort() : [],
        status: filters.status ?? null,
        kind: filters.kind ?? null,
        group: filters.group ?? null,
        search: filters.search ?? null,
        sort: filters.sort ?? null,
        page: filters.page ?? 1,
        pageSize: filters.pageSize ?? 50,
      },
    ] as const,

  /**
   * Aggregate session-board key.
   * Includes groupBy, projectIds, group, activeWindowMinutes, includeWorkers,
   * includeStale, page, and pageSize for stable cache identity.
   */
  sessionBoard: (filters: MultiProjectSessionBoardFilters = {}) =>
    [
      'multi-project',
      'planning',
      'session-board',
      {
        projectIds: filters.projectIds ? [...filters.projectIds].sort() : [],
        group: filters.group ?? null,
        groupBy: filters.groupBy ?? 'state',
        activeWindowMinutes: filters.activeWindowMinutes ?? 30,
        includeWorkers: filters.includeWorkers ?? true,
        page: filters.page ?? 1,
        pageSize: filters.pageSize ?? 50,
        includeStale: filters.includeStale ?? false,
      },
    ] as const,
};
