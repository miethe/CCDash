import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { Project } from '../types';
import { ensureProjectTestConfig } from '../services/testConfigDefaults';
import { useDataClient } from './DataClientContext';

/**
 * Pure scope-resolution decision for refreshProjects().
 *
 * Returns one of three outcomes:
 *   - 'keep'  — the scoped project is valid and active; retain it as the active project
 *   - 'clear' — the scoped project exists but is explicitly inactive while another is
 *               server-active; clear the stale scope so getActiveProject() can elect the
 *               correct one
 *   - 'keep-legacy' — the scoped project exists but no server-active project is known
 *                     (older backend or all projects inactive); preserve the stored scope
 *   - 'query' — no usable scoped project; fall through to getActiveProject()
 *
 * Exported for unit testing.
 */
export type ScopeResolutionOutcome = 'keep' | 'clear' | 'keep-legacy' | 'query';

export function resolveScopeOutcome(
  scopedProject: Project | null | undefined,
  normalizedProjects: Project[],
): ScopeResolutionOutcome {
  if (!scopedProject) return 'query';

  const scopedIsInactive = !scopedProject.is_active;
  const anyProjectIsActive = normalizedProjects.some(p => p.is_active === true);

  if (!scopedIsInactive) return 'keep';
  if (anyProjectIsActive) return 'clear';
  return 'keep-legacy';
}

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

    // Scope guard: delegate to the exported pure helper so the decision is unit-testable.
    const outcome = resolveScopeOutcome(scopedProject ?? null, normalizedProjects);
    if (outcome === 'keep') {
      // Scoped project is present and not explicitly inactive — honour the stored scope.
      setActiveProject(scopedProject!);
      return;
    }
    if (outcome === 'clear') {
      // Stale scope: clear it so we fall through to getActiveProject() below.
      client.setProjectScope(null);
    } else if (outcome === 'keep-legacy') {
      // Scoped project exists but no server-active project is known yet (older backend that
      // doesn't send is_active, or all projects inactive). Keep the stored scope as-is to
      // avoid regressing the happy-path selection on backends that predate this field.
      setActiveProject(scopedProject!);
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
