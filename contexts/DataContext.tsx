import React, { useCallback } from 'react';
import type {
  AgentSession,
  AlertConfig,
  Feature,
  Notification,
  PlanDocument,
  Project,
  ProjectTask,
  TaskStatus,
} from '../types';
import { AppEntityDataProvider, useAppEntityData } from './AppEntityDataContext';
import { AppRuntimeProvider, useAppRuntime } from './AppRuntimeContext';
import { AppSessionProvider, useAppSession } from './AppSessionContext';
import { AuthSessionProvider } from './AuthSessionContext';
import { DataClientProvider } from './DataClientContext';
import {
  hasSessionDetail,
  mergeSessionDetail,
  type SessionFetchOptions,
  type SessionFilters,
} from './dataContextShared';
import type { RuntimeStatus } from '../services/runtimeProfile';

export type { SessionFetchOptions, SessionFilters } from './dataContextShared';
export { hasSessionDetail, mergeSessionDetail } from './dataContextShared';

interface DataContextValue {
  sessions: AgentSession[];
  sessionTotal: number;
  hasMoreSessions: boolean;
  sessionFilters: SessionFilters;
  setSessionFilters: (filters: SessionFilters) => void;
  documents: PlanDocument[];
  tasks: ProjectTask[];
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

const ComposedDataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <DataClientProvider>
    <AuthSessionProvider>
      <AppSessionProvider>
        <AppEntityDataProvider>
          <AppRuntimeProvider>{children}</AppRuntimeProvider>
        </AppEntityDataProvider>
      </AppSessionProvider>
    </AuthSessionProvider>
  </DataClientProvider>
);

export const DataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ComposedDataProvider>{children}</ComposedDataProvider>
);

export function useData(): DataContextValue {
  const session = useAppSession();
  const entity = useAppEntityData();
  const runtime = useAppRuntime();

  const switchProject = useCallback(async (projectId: string) => {
    await session.switchProject(projectId);
    await runtime.refreshAll();
  }, [runtime, session]);

  const updateProject = useCallback(async (projectId: string, project: Project) => {
    await session.updateProject(projectId, project);
    await runtime.refreshAll();
  }, [runtime, session]);

  return {
    sessions: entity.sessions,
    sessionTotal: entity.sessionTotal,
    hasMoreSessions: entity.sessions.length < entity.sessionTotal,
    sessionFilters: entity.sessionFilters,
    setSessionFilters: entity.setSessionFilters,
    documents: entity.documents,
    tasks: entity.tasks,
    alerts: entity.alerts,
    notifications: entity.notifications,
    features: entity.features,
    projects: session.projects,
    activeProject: session.activeProject,
    loading: runtime.loading,
    error: runtime.error,
    runtimeStatus: runtime.runtimeStatus,
    refreshAll: runtime.refreshAll,
    refreshSessions: entity.refreshSessions,
    loadMoreSessions: entity.loadMoreSessions,
    refreshDocuments: entity.refreshDocuments,
    refreshTasks: entity.refreshTasks,
    refreshFeatures: entity.refreshFeatures,
    refreshProjects: session.refreshProjects,
    addProject: session.addProject,
    updateProject,
    switchProject,
    updateFeatureStatus: entity.updateFeatureStatus,
    updatePhaseStatus: entity.updatePhaseStatus,
    updateTaskStatus: entity.updateTaskStatus,
    getSessionById: entity.getSessionById,
  };
}
