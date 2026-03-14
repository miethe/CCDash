import React, { createContext, useCallback, useContext, useState } from 'react';
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
    setProjects(data.map(project => ({ ...project, testConfig: ensureProjectTestConfig(project.testConfig) })));
    try {
      const active = await client.getActiveProject();
      setActiveProject({ ...active, testConfig: ensureProjectTestConfig(active.testConfig) });
    } catch {
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
    await refreshProjects();
  }, [client, refreshProjects]);

  return (
    <AppSessionContext.Provider
      value={{
        projects,
        activeProject,
        refreshProjects,
        addProject,
        updateProject,
        switchProject,
      }}
    >
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
