import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { Project } from '../types';
import { ensureProjectTestConfig } from '../services/testConfigDefaults';
import { useDataClient } from './DataClientContext';

interface AppSessionContextValue {
  projects: Project[];
  activeProject: Project | null;
  refreshProjects: () => Promise<void>;
  addProject: (project: Project) => Promise<void>;
  updateProject: (projectId: string, project: Project) => Promise<void>;
  switchProject: (projectId: string) => Promise<void>;
}

const AppSessionContext = createContext<AppSessionContextValue | null>(null);

export const AppSessionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const client = useDataClient();
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);

  const refreshProjects = useCallback(async () => {
    const data = await client.getProjects();
    const normalizedProjects = data.map(project => ({ ...project, testConfig: ensureProjectTestConfig(project.testConfig) }));
    setProjects(normalizedProjects);

    const scopedProjectId = client.getProjectScope();
    const scopedProject = scopedProjectId
      ? normalizedProjects.find(project => project.id === scopedProjectId)
      : null;

    // Scope guard: if the localStorage-scoped project is explicitly inactive AND at least
    // one project in the registry is active, the stored scope is stale — clear it and let
    // getActiveProject() pick the correct one. Treat missing/null is_active as false.
    const scopedIsInactive = scopedProject != null && !scopedProject.is_active;
    const anyProjectIsActive = normalizedProjects.some(p => p.is_active === true);
    if (scopedProject && !scopedIsInactive) {
      // Scoped project is present and not explicitly inactive — honour the stored scope.
      setActiveProject(scopedProject);
      return;
    }
    if (scopedIsInactive && anyProjectIsActive) {
      // Stale scope: clear it so we fall through to getActiveProject() below.
      client.setProjectScope(null);
    } else if (scopedProject) {
      // Scoped project exists but no server-active project is known yet (older backend that
      // doesn't send is_active, or all projects inactive). Keep the stored scope as-is to
      // avoid regressing the happy-path selection on backends that predate this field.
      setActiveProject(scopedProject);
      return;
    }

    try {
      const active = await client.getActiveProject();
      const normalizedActive = { ...active, testConfig: ensureProjectTestConfig(active.testConfig) };
      client.setProjectScope(normalizedActive.id);
      setActiveProject(normalizedActive);
    } catch {
      // 404 (no active project) or any other error: clear scope and active project gracefully.
      client.setProjectScope(null);
      setActiveProject(null);
    }
  }, [client]);

  useEffect(() => { void refreshProjects(); }, [refreshProjects]);

  const addProject = useCallback(async (project: Project) => {
    await client.addProject(project);
    await refreshProjects();
  }, [client, refreshProjects]);

  const updateProject = useCallback(async (projectId: string, project: Project) => {
    await client.updateProject(projectId, project);
    await refreshProjects();
  }, [client, refreshProjects]);

  const switchProject = useCallback(async (projectId: string) => {
    await client.switchProject(projectId);
    const project = projects.find(candidate => candidate.id === projectId);
    if (project) {
      setActiveProject(project);
    }
    await refreshProjects();
  }, [client, projects, refreshProjects]);

  const contextValue = useMemo(() => ({
    projects,
    activeProject,
    refreshProjects,
    addProject,
    updateProject,
    switchProject,
  }), [projects, activeProject, refreshProjects, addProject, updateProject, switchProject]);

  return (
    <AppSessionContext.Provider value={contextValue}>
      {children}
    </AppSessionContext.Provider>
  );
};

export function useAppSession(): AppSessionContextValue {
  const ctx = useContext(AppSessionContext);
  if (!ctx) {
    throw new Error('useAppSession must be used within an AppSessionProvider');
  }
  return ctx;
}
