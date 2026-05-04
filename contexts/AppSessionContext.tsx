import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
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
    if (scopedProject) {
      setActiveProject(scopedProject);
      return;
    }

    try {
      const active = await client.getActiveProject();
      const normalizedActive = { ...active, testConfig: ensureProjectTestConfig(active.testConfig) };
      client.setProjectScope(normalizedActive.id);
      setActiveProject(normalizedActive);
    } catch {
      client.setProjectScope(null);
      setActiveProject(null);
    }
  }, [client]);

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
