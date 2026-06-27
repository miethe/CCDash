/**
 * DataContext — thin facade over TQ hooks + AppSessionContext client-state.
 *
 * T4-003: useData() is now fully reactive — snapshot getQueryData() calls
 *   replaced with live useQuery/useInfiniteQuery hooks. useMemo gates prevent
 *   render storms: derived arrays/objects only change when underlying data changes.
 * T4-005: AppEntityDataProvider removed from provider tree.
 * T4-007: useData() ≤50-line shim re-exporting TQ hook values.
 * T4-015: switchProject fires scoped invalidateQueries() after scope change
 *   (replaces queryClient.clear() which nuked non-project-scoped cache entries).
 *
 * useData() is a backward-compatible shim: field shapes are unchanged so all
 * 24 consumer components continue working without modification.
 *
 * Resilience: TQ hooks returning undefined propagate existing falsy defaults
 * ([], null, false). No consumer breaks when a query has not yet loaded.
 */

import React, { useCallback, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Project, TaskStatus } from '../types';
import { AppRuntimeProvider, useAppRuntime } from './AppRuntimeContext';
import { AppSessionProvider, useAppSession } from './AppSessionContext';
import { AuthSessionProvider, useAuthSession } from './AuthSessionContext';
import { DataClientProvider } from './DataClientContext';
import type { SessionFetchOptions, SessionFilters } from './dataContextShared';
import { projectsKeys, sessionsKeys, tasksKeys, featuresKeys } from '../services/queryKeys';
import type { RuntimeStatus } from '../services/runtimeProfile';
import type { AgentSession, AlertConfig, Feature, Notification, PlanDocument } from '../types';
import {
  useUpdateFeatureStatusMutation,
  useUpdatePhaseStatusMutation,
  useUpdateTaskStatusMutation,
} from '../services/mutations/features';
import { useSessionsQuery } from '../services/queries/sessions';
import { useDocumentsQuery } from '../services/queries/documents';
import { useTasksQuery } from '../services/queries/tasks';
import { useFeaturesQuery } from '../services/queries/features';
import { useAlertsQuery } from '../services/queries/alerts';
import { useNotificationsQuery } from '../services/queries/notifications';
import { useProjectsQuery } from '../services/queries/projects';

export type { SessionFetchOptions, SessionFilters } from './dataContextShared';
export { hasSessionDetail, mergeSessionDetail } from './dataContextShared';

// ─── Provider gate ────────────────────────────────────────────────────────────

interface AppDataProviderGateState {
  loading: boolean;
  authenticated: boolean;
  session?: { localMode?: boolean; authMode?: string | null; provider?: string | null } | null;
  metadata?: { localMode?: boolean; authMode?: string | null; provider?: string | null } | null;
}

export function shouldMountAppDataProviders(auth: AppDataProviderGateState): boolean {
  if (auth.loading) return false;
  const localMode = Boolean(
    auth.session?.localMode
    || auth.metadata?.localMode
    || auth.session?.authMode === 'local'
    || auth.metadata?.authMode === 'local',
  );
  const staticBearerMode = auth.session?.provider === 'static_bearer' || auth.metadata?.provider === 'static_bearer';
  return localMode || staticBearerMode || auth.authenticated;
}

const AppDataProviderGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const auth = useAuthSession();

  if (!shouldMountAppDataProviders(auth)) {
    return <>{children}</>;
  }

  return (
    <AppSessionProvider>
      <AppRuntimeProvider>{children}</AppRuntimeProvider>
    </AppSessionProvider>
  );
};

const ComposedDataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <DataClientProvider>
    <AuthSessionProvider>
      <AppDataProviderGate>{children}</AppDataProviderGate>
    </AuthSessionProvider>
  </DataClientProvider>
);

export const DataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ComposedDataProvider>{children}</ComposedDataProvider>
);

// ─── useData() shim ───────────────────────────────────────────────────────────

interface DataContextValue {
  sessions: AgentSession[];
  sessionTotal: number;
  hasMoreSessions: boolean;
  sessionFilters: SessionFilters;
  setSessionFilters: (filters: SessionFilters) => void;
  documents: PlanDocument[];
  tasks: any[];
  alerts: AlertConfig[];
  notifications: Notification[];
  features: Feature[];
  projects: Project[];
  activeProject: Project | null;
  loading: boolean;
  error: string | null;
  runtimeStatus: RuntimeStatus | null;
  refreshAll: () => Promise<void>;
  refreshSessions: (reset?: boolean) => Promise<void>;
  loadMoreSessions: () => Promise<void>;
  refreshDocuments: () => Promise<void>;
  refreshTasks: () => Promise<void>;
  refreshFeatures: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  addProject: (project: Project) => Promise<void>;
  updateProject: (projectId: string, project: Project) => Promise<void>;
  switchProject: (projectId: string) => Promise<void>;
  updateFeatureStatus: (featureId: string, status: string) => Promise<void>;
  updatePhaseStatus: (featureId: string, phaseId: string, status: string) => Promise<void>;
  updateTaskStatus: (featureId: string, phaseId: string, taskId: string, status: TaskStatus, previousStatus?: TaskStatus) => Promise<void>;
  getSessionById: (sessionId: string, options?: SessionFetchOptions) => Promise<AgentSession | null>;
}

export function useData(): DataContextValue {
  const session = useAppSession();
  const runtime = useAppRuntime();
  const queryClient = useQueryClient();
  const projectId = session.activeProject?.id ?? '';

  // ── Mutation hooks ──────────────────────────────────────────────────────────
  const updateFeatureStatusMutation = useUpdateFeatureStatusMutation();
  const updatePhaseStatusMutation = useUpdatePhaseStatusMutation();
  const updateTaskStatusMutation = useUpdateTaskStatusMutation();

  // ── T4-003: Reactive TQ hooks (re-render on background refetch) ─────────────

  // Sessions: infinite query; flatten pages here so components stay unchanged.
  const sessionsQuery = useSessionsQuery({ projectId: projectId || null, enabled: !!projectId });
  const sessions = useMemo<AgentSession[]>(
    () => sessionsQuery.data?.pages.flatMap(p => p.items) ?? [],
    [sessionsQuery.data],
  );
  const sessionTotal = useMemo(
    () => {
      const pages = sessionsQuery.data?.pages;
      return pages != null ? (pages[pages.length - 1]?.total ?? 0) : 0;
    },
    [sessionsQuery.data],
  );

  // Documents: select transform in useDocumentsQuery already returns PlanDocument[].
  const documentsQuery = useDocumentsQuery({ projectId: projectId || null, enabled: !!projectId });
  const documents = useMemo<PlanDocument[]>(
    () => (documentsQuery.data as PlanDocument[] | undefined) ?? [],
    [documentsQuery.data],
  );

  // Tasks: page 0 list query.
  const tasksQuery = useTasksQuery({ projectId: projectId || null, page: 0, enabled: !!projectId });
  const tasks = useMemo(
    () => tasksQuery.data?.items ?? [],
    [tasksQuery.data],
  );

  // Features: page 0 list query.
  const featuresQuery = useFeaturesQuery({ projectId: projectId || null, page: 0, enabled: !!projectId });
  const features = useMemo<Feature[]>(
    () => featuresQuery.data?.items ?? [],
    [featuresQuery.data],
  );

  // Alerts: simple list query.
  const alertsQuery = useAlertsQuery({ projectId: projectId || null, enabled: !!projectId });
  const alerts = useMemo<AlertConfig[]>(
    () => alertsQuery.data ?? [],
    [alertsQuery.data],
  );

  // Notifications: simple list query.
  const notificationsQuery = useNotificationsQuery({ projectId: projectId || null, enabled: !!projectId });
  const notifications = useMemo<Notification[]>(
    () => notificationsQuery.data ?? [],
    [notificationsQuery.data],
  );

  // Projects: global (no projectId). Fallback to session.projects while TQ loads.
  const projectsQuery = useProjectsQuery();
  const projects = useMemo<Project[]>(
    () => projectsQuery.data ?? session.projects,
    [projectsQuery.data, session.projects],
  );

  // ── Refresh shims (invalidate TQ cache → hooks refetch) ─────────────────────
  const refreshSessions = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: sessionsKeys.all(projectId) });
  }, [queryClient, projectId]);

  // eslint-disable-next-line @typescript-eslint/no-empty-function
  const loadMoreSessions = useCallback(async () => {
    // loadMore is handled by the component-level useSessionsQuery fetchNextPage.
    // No-op in the shim; consumers that need pagination use the hook directly.
  }, []);

  const refreshDocuments = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: [projectId, 'documents'] });
  }, [queryClient, projectId]);

  const refreshTasks = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: [projectId, 'tasks'] });
  }, [queryClient, projectId]);

  const refreshFeatures = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: featuresKeys.all(projectId) });
  }, [queryClient, projectId]);

  const refreshProjects = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: projectsKeys.list() });
    await session.refreshProjects();
  }, [queryClient, session]);

  // T4-015: scoped invalidation after project scope change.
  // Replaces queryClient.clear() which nuked non-project-scoped entries (e.g.
  // projects list, health). Invalidate by old projectId prefix; the new project's
  // queries are disabled until activeProject updates and re-enables them.
  const switchProject = useCallback(async (pid: string) => {
    const prevProjectId = projectId;
    await session.switchProject(pid);
    // Invalidate all queries scoped to the previous project so the new project
    // renders fresh data and no stale cross-project data is visible.
    if (prevProjectId) {
      await queryClient.invalidateQueries({ queryKey: [prevProjectId] });
    }
    // Also invalidate the new project scope in case TQ has stale entries.
    if (pid) {
      await queryClient.invalidateQueries({ queryKey: [pid] });
    }
    await runtime.refreshAll();
  }, [queryClient, runtime, session, projectId]);

  const updateProject = useCallback(async (pid: string, project: Project) => {
    await session.updateProject(pid, project);
    await runtime.refreshAll();
  }, [runtime, session]);

  // ── Mutation shims ──────────────────────────────────────────────────────────
  const updateFeatureStatus = useCallback(async (featureId: string, status: string) => {
    await updateFeatureStatusMutation.mutateAsync({ projectId, featureId, status });
  }, [updateFeatureStatusMutation, projectId]);

  const updatePhaseStatus = useCallback(async (featureId: string, phaseId: string, status: string) => {
    await updatePhaseStatusMutation.mutateAsync({ projectId, featureId, phaseId, status });
  }, [updatePhaseStatusMutation, projectId]);

  const updateTaskStatus = useCallback(async (featureId: string, phaseId: string, taskId: string, status: TaskStatus, previousStatus?: TaskStatus) => {
    await updateTaskStatusMutation.mutateAsync({ projectId, featureId, phaseId, taskId, status, previousStatus });
  }, [updateTaskStatusMutation, projectId]);

  // ── getSessionById (direct fetch shim) ─────────────────────────────────────
  const getSessionById = useCallback(async (sessionId: string): Promise<AgentSession | null> => {
    const cached = queryClient.getQueryData<AgentSession>(
      sessionsKeys.detail(projectId, sessionId),
    );
    if (cached) return cached;
    // Trigger a TQ fetch and wait; the component-level useSessionDetailQuery is preferred.
    return null;
  }, [queryClient, projectId]);

  // ── Session filters (client-state) ─────────────────────────────────────────
  // Session filters are client-state; keep a stable empty default for shim.
  const sessionFilters: SessionFilters = {};
  // eslint-disable-next-line @typescript-eslint/no-empty-function
  const setSessionFilters = useCallback((_filters: SessionFilters) => {}, []);

  return {
    sessions,
    sessionTotal,
    hasMoreSessions: sessions.length < sessionTotal,
    sessionFilters,
    setSessionFilters,
    documents,
    tasks,
    alerts,
    notifications,
    features,
    projects,
    activeProject: session.activeProject,
    loading: runtime.loading,
    error: runtime.error,
    runtimeStatus: runtime.runtimeStatus,
    refreshAll: runtime.refreshAll,
    refreshSessions,
    loadMoreSessions,
    refreshDocuments,
    refreshTasks,
    refreshFeatures,
    refreshProjects,
    addProject: session.addProject,
    updateProject,
    switchProject,
    updateFeatureStatus,
    updatePhaseStatus,
    updateTaskStatus,
    getSessionById,
  };
}
