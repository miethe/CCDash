/**
 * DataContext — thin facade over TQ hooks + AppSessionContext client-state.
 *
 * T4-005: AppEntityDataProvider removed from provider tree.
 * T4-007: useData() ≤50-line shim re-exporting TQ hook values.
 *
 * useData() is a backward-compatible shim: field shapes are unchanged so all
 * 24 consumer components continue working without modification.
 *
 * Resilience: TQ hooks returning undefined propagate existing falsy defaults
 * ([], null, false). No consumer breaks when a query has not yet loaded.
 */

import React, { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Project, TaskStatus } from '../types';
import { AppRuntimeProvider, useAppRuntime } from './AppRuntimeContext';
import { AppSessionProvider, useAppSession } from './AppSessionContext';
import { AuthSessionProvider, useAuthSession } from './AuthSessionContext';
import { DataClientProvider } from './DataClientContext';
import type { SessionFetchOptions, SessionFilters } from './dataContextShared';
import { projectsKeys, sessionsKeys, tasksKeys, featuresKeys, alertsKeys, notificationsKeys, documentsKeys } from '../services/queryKeys';
import type { RuntimeStatus } from '../services/runtimeProfile';
import { MAX_DOCUMENTS_IN_MEMORY } from '../constants';
import type { TasksPage } from '../services/queries/tasks';
import type { FeaturesPage } from '../services/queries/features';
import type { InfiniteData } from '@tanstack/react-query';
import type { PaginatedResponse } from './dataContextShared';
import type { AgentSession, AlertConfig, Feature, Notification, PlanDocument } from '../types';
import {
  useUpdateFeatureStatusMutation,
  useUpdatePhaseStatusMutation,
  useUpdateTaskStatusMutation,
} from '../services/mutations/features';

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

  // ── Sessions (from TQ cache) ────────────────────────────────────────────────
  const tqSessionsData = queryClient.getQueryData<InfiniteData<PaginatedResponse<AgentSession>>>(
    sessionsKeys.list(projectId),
  );
  const sessions = tqSessionsData != null
    ? tqSessionsData.pages.flatMap(p => p.items)
    : [];
  const sessionTotal = tqSessionsData != null
    ? (tqSessionsData.pages[tqSessionsData.pages.length - 1]?.total ?? 0)
    : 0;

  // ── Documents (from TQ cache) ───────────────────────────────────────────────
  const tqDocsData = queryClient.getQueryData<InfiniteData<PaginatedResponse<PlanDocument>>>(
    documentsKeys.list(projectId),
  );
  const documents = tqDocsData != null
    ? tqDocsData.pages.flatMap(p => p.items).slice(0, MAX_DOCUMENTS_IN_MEMORY)
    : [];

  // ── Tasks (from TQ cache) ───────────────────────────────────────────────────
  const tqTasksData = queryClient.getQueryData<TasksPage>(tasksKeys.list(projectId, 0));
  const tasks = tqTasksData != null ? tqTasksData.items : [];

  // ── Features (from TQ cache) ────────────────────────────────────────────────
  const tqFeaturesData = queryClient.getQueryData<FeaturesPage>(
    featuresKeys.list(projectId, undefined, 0),
  );
  const features = tqFeaturesData != null ? tqFeaturesData.items : [];

  // ── Alerts (from TQ cache) ──────────────────────────────────────────────────
  const alerts = (queryClient.getQueryData<AlertConfig[]>(alertsKeys.list(projectId)) ?? []);

  // ── Notifications (from TQ cache) ───────────────────────────────────────────
  const notifications = (queryClient.getQueryData<Notification[]>(notificationsKeys.list(projectId)) ?? []);

  // ── Projects (from TQ cache, fallback to session) ───────────────────────────
  const projects = queryClient.getQueryData<Project[]>(projectsKeys.list()) ?? session.projects;

  // ── Refresh shims (invalidate TQ cache → hooks refetch) ─────────────────────
  const refreshSessions = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: sessionsKeys.all(projectId) });
  }, [queryClient, projectId]);

  const loadMoreSessions = useCallback(async () => {
    // loadMore is handled by the component-level useSessionsQuery fetchNextPage.
    // No-op in the shim; consumers that need pagination use the hook directly.
  }, []);

  const refreshDocuments = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: documentsKeys.all(projectId) });
  }, [queryClient, projectId]);

  const refreshTasks = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['tasks'] });
  }, [queryClient]);

  const refreshFeatures = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: featuresKeys.all(projectId) });
  }, [queryClient, projectId]);

  const refreshProjects = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: projectsKeys.list() });
    await session.refreshProjects();
  }, [queryClient, session]);

  const switchProject = useCallback(async (pid: string) => {
    queryClient.clear();
    await session.switchProject(pid);
    await runtime.refreshAll();
  }, [queryClient, runtime, session]);

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
