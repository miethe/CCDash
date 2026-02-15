import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { AgentSession, PlanDocument, ProjectTask, AlertConfig, Notification, Project, Feature } from '../types';

// ── Types ──────────────────────────────────────────────────────────

interface DataContextValue {
    // Data
    sessions: AgentSession[];
    documents: PlanDocument[];
    tasks: ProjectTask[];
    alerts: AlertConfig[];
    notifications: Notification[];
    features: Feature[];

    // Projects
    projects: Project[];
    activeProject: Project | null;

    // Status
    loading: boolean;
    error: string | null;

    // Actions
    refreshAll: () => Promise<void>;
    refreshSessions: () => Promise<void>;
    refreshDocuments: () => Promise<void>;
    refreshTasks: () => Promise<void>;
    refreshFeatures: () => Promise<void>;

    // Project Actions
    refreshProjects: () => Promise<void>;
    addProject: (project: Project) => Promise<void>;
    updateProject: (projectId: string, project: Project) => Promise<void>;
    switchProject: (projectId: string) => Promise<void>;

    // Status Update Actions
    updateFeatureStatus: (featureId: string, status: string) => Promise<void>;
    updatePhaseStatus: (featureId: string, phaseId: string, status: string) => Promise<void>;
    updateTaskStatus: (featureId: string, phaseId: string, taskId: string, status: string) => Promise<void>;
}

const DataContext = createContext<DataContextValue | null>(null);

// ── API helpers ────────────────────────────────────────────────────

const API_BASE = '/api';

async function fetchJson<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText} for ${path}`);
    }
    return res.json();
}

// ── Provider ───────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 30_000; // 30 seconds

export const DataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [sessions, setSessions] = useState<AgentSession[]>([]);
    const [documents, setDocuments] = useState<PlanDocument[]>([]);
    const [tasks, setTasks] = useState<ProjectTask[]>([]);
    const [alerts, setAlerts] = useState<AlertConfig[]>([]);
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [features, setFeatures] = useState<Feature[]>([]);
    const [projects, setProjects] = useState<Project[]>([]);
    const [activeProject, setActiveProject] = useState<Project | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const refreshSessions = useCallback(async () => {
        try {
            const data = await fetchJson<AgentSession[]>('/sessions');
            setSessions(data);
        } catch (e) {
            console.error('Failed to fetch sessions:', e);
        }
    }, []);

    const refreshDocuments = useCallback(async () => {
        try {
            const data = await fetchJson<PlanDocument[]>('/documents');
            setDocuments(data);
        } catch (e) {
            console.error('Failed to fetch documents:', e);
        }
    }, []);

    const refreshTasks = useCallback(async () => {
        try {
            const data = await fetchJson<ProjectTask[]>('/tasks');
            setTasks(data);
        } catch (e) {
            console.error('Failed to fetch tasks:', e);
        }
    }, []);

    const refreshAlerts = useCallback(async () => {
        try {
            const data = await fetchJson<AlertConfig[]>('/analytics/alerts');
            setAlerts(data);
        } catch (e) {
            console.error('Failed to fetch alerts:', e);
        }
    }, []);

    const refreshNotifications = useCallback(async () => {
        try {
            const data = await fetchJson<Notification[]>('/analytics/notifications');
            setNotifications(data);
        } catch (e) {
            console.error('Failed to fetch notifications:', e);
        }
    }, []);

    const refreshFeatures = useCallback(async () => {
        try {
            const data = await fetchJson<Feature[]>('/features');
            setFeatures(data);
        } catch (e) {
            console.error('Failed to fetch features:', e);
        }
    }, []);

    const refreshProjects = useCallback(async () => {
        try {
            const data = await fetchJson<Project[]>('/projects');
            setProjects(data);
            try {
                const active = await fetchJson<Project>('/projects/active');
                setActiveProject(active);
            } catch (e) {
                setActiveProject(null);
            }
        } catch (e) {
            console.error('Failed to fetch projects:', e);
        }
    }, []);

    const addProject = useCallback(async (project: Project) => {
        try {
            await fetch(`${API_BASE}/projects`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(project),
            });
            await refreshProjects();
        } catch (e) {
            console.error('Failed to add project:', e);
            throw e;
        }
    }, [refreshProjects]);

    const updateProject = useCallback(async (projectId: string, project: Project) => {
        try {
            const res = await fetch(`${API_BASE}/projects/${projectId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(project),
            });
            if (!res.ok) {
                throw new Error(`Failed to update project: ${res.status}`);
            }
            await refreshProjects();
            // Refresh all data since paths may have changed
            await Promise.all([
                refreshSessions(),
                refreshDocuments(),
                refreshTasks(),
                refreshFeatures(),
            ]);
        } catch (e) {
            console.error('Failed to update project:', e);
            throw e;
        }
    }, [refreshProjects, refreshSessions, refreshDocuments, refreshTasks, refreshFeatures]);

    const switchProject = useCallback(async (projectId: string) => {
        try {
            await fetch(`${API_BASE}/projects/active/${projectId}`, {
                method: 'POST',
            });
            await refreshProjects();
            // Refresh all data immediately
            await Promise.all([
                refreshSessions(),
                refreshDocuments(),
                refreshTasks(),
                refreshFeatures(),
                refreshAlerts(),
                refreshNotifications(),
            ]);
        } catch (e) {
            console.error('Failed to switch project:', e);
            throw e;
        }
    }, [refreshProjects, refreshSessions, refreshDocuments, refreshTasks, refreshFeatures]);

    // ── Status update methods ──────────────────────────────────────

    const updateFeatureStatus = useCallback(async (featureId: string, status: string) => {
        try {
            await fetch(`${API_BASE}/features/${featureId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status }),
            });
            await refreshFeatures();
        } catch (e) {
            console.error('Failed to update feature status:', e);
            throw e;
        }
    }, [refreshFeatures]);

    const updatePhaseStatus = useCallback(async (featureId: string, phaseId: string, status: string) => {
        try {
            await fetch(`${API_BASE}/features/${featureId}/phases/${phaseId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status }),
            });
            await refreshFeatures();
        } catch (e) {
            console.error('Failed to update phase status:', e);
            throw e;
        }
    }, [refreshFeatures]);

    const updateTaskStatus = useCallback(async (featureId: string, phaseId: string, taskId: string, status: string) => {
        try {
            await fetch(`${API_BASE}/features/${featureId}/phases/${phaseId}/tasks/${taskId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status }),
            });
            await refreshFeatures();
        } catch (e) {
            console.error('Failed to update task status:', e);
            throw e;
        }
    }, [refreshFeatures]);

    const refreshAll = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            await Promise.all([
                refreshSessions(),
                refreshDocuments(),
                refreshTasks(),
                refreshFeatures(),
                refreshAlerts(),
                refreshNotifications(),
                refreshProjects(),
            ]);
        } catch (e: any) {
            setError(e.message || 'Failed to load data');
        } finally {
            setLoading(false);
        }
    }, [refreshSessions, refreshDocuments, refreshTasks, refreshFeatures, refreshAlerts, refreshNotifications, refreshProjects]);

    // Initial load
    useEffect(() => {
        refreshAll();
    }, [refreshAll]);

    // Polling for live updates
    useEffect(() => {
        const interval = setInterval(() => {
            refreshAll();
        }, POLL_INTERVAL_MS);
        return () => clearInterval(interval);
    }, [refreshAll]);

    return (
        <DataContext.Provider
            value={{
                sessions,
                documents,
                tasks,
                alerts,
                notifications,
                features,
                loading,
                error,
                refreshAll,
                refreshSessions,
                refreshDocuments,
                refreshTasks,
                refreshFeatures,
                projects,
                activeProject,
                refreshProjects,
                addProject,
                updateProject,
                switchProject,
                updateFeatureStatus,
                updatePhaseStatus,
                updateTaskStatus,
            }}
        >
            {children}
        </DataContext.Provider>
    );
};

// ── Hook ───────────────────────────────────────────────────────────

export function useData(): DataContextValue {
    const ctx = useContext(DataContext);
    if (!ctx) {
        throw new Error('useData must be used within a DataProvider');
    }
    return ctx;
}
