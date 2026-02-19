import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { AgentSession, PlanDocument, ProjectTask, AlertConfig, Notification, Project, Feature } from '../types';

export interface SessionFilters {
    status?: string;
    model?: string;
    model_provider?: string;
    model_family?: string;
    model_version?: string;
    include_subagents?: boolean;
    root_session_id?: string;
    start_date?: string;
    end_date?: string;
    created_start?: string;
    created_end?: string;
    completed_start?: string;
    completed_end?: string;
    updated_start?: string;
    updated_end?: string;
    min_duration?: number;
    max_duration?: number;
}

// ── Types ──────────────────────────────────────────────────────────

interface DataContextValue {
    // Data
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

    // Projects
    projects: Project[];
    activeProject: Project | null;

    // Status
    loading: boolean;
    error: string | null;

    // Actions
    refreshAll: () => Promise<void>;
    refreshSessions: (reset?: boolean) => Promise<void>;
    loadMoreSessions: () => Promise<void>;
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
    getSessionById: (sessionId: string) => Promise<AgentSession | null>;
}

const DataContext = createContext<DataContextValue | null>(null);

// ── API helpers ────────────────────────────────────────────────────

const API_BASE = '/api';

interface PaginatedResponse<T> {
    items: T[];
    total: number;
    offset: number;
    limit: number;
}

async function fetchJson<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText} for ${path}`);
    }
    return res.json();
}

// ── Provider ───────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 30_000; // 30 seconds
const FEATURE_POLL_INTERVAL_MS = 5_000; // 5 seconds
const SESSIONS_PER_PAGE = 50;

export const DataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [sessions, setSessions] = useState<AgentSession[]>([]);
    const [sessionTotal, setSessionTotal] = useState(0);
    const [sessionFilters, setSessionFilters] = useState<SessionFilters>({ include_subagents: true });
    const [documents, setDocuments] = useState<PlanDocument[]>([]);
    const [tasks, setTasks] = useState<ProjectTask[]>([]);
    const [alerts, setAlerts] = useState<AlertConfig[]>([]);
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [features, setFeatures] = useState<Feature[]>([]);
    const [pendingFeatureStatusById, setPendingFeatureStatusById] = useState<Record<string, string>>({});
    const [projects, setProjects] = useState<Project[]>([]);
    const [activeProject, setActiveProject] = useState<Project | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const upsertFeatureInState = useCallback((updatedFeature: Feature) => {
        setFeatures(prev => {
            const idx = prev.findIndex(f => f.id === updatedFeature.id);
            if (idx === -1) return [updatedFeature, ...prev];
            const next = [...prev];
            next[idx] = updatedFeature;
            return next;
        });
    }, []);

    const applyPendingFeatureStatuses = useCallback((serverFeatures: Feature[]) => {
        const pendingIds = Object.keys(pendingFeatureStatusById);
        if (pendingIds.length === 0) return serverFeatures;
        return serverFeatures.map(feature => {
            const pendingStatus = pendingFeatureStatusById[feature.id];
            if (!pendingStatus || pendingStatus === feature.status) return feature;
            return { ...feature, status: pendingStatus };
        });
    }, [pendingFeatureStatusById]);

    const refreshSessions = useCallback(async (reset = true) => {
        try {
            // If resetting (background poll), we want to fetch enough items to cover what the user has currently loaded
            // so they don't lose their scroll position or see items disappear.
            // Minimum 50, but if they loaded 300, fetch 300.
            const currentCount = sessions.length;
            const limit = reset ? Math.max(SESSIONS_PER_PAGE, currentCount) : SESSIONS_PER_PAGE;
            const offset = reset ? 0 : currentCount;

            const params = new URLSearchParams({
                offset: offset.toString(),
                limit: limit.toString(),
                sort_by: 'started_at',
                sort_order: 'desc'
            });

            if (sessionFilters.status) params.append('status', sessionFilters.status);
            if (sessionFilters.model) params.append('model', sessionFilters.model);
            if (sessionFilters.model_provider) params.append('model_provider', sessionFilters.model_provider);
            if (sessionFilters.model_family) params.append('model_family', sessionFilters.model_family);
            if (sessionFilters.model_version) params.append('model_version', sessionFilters.model_version);
            if (sessionFilters.include_subagents) params.append('include_subagents', 'true');
            if (sessionFilters.root_session_id) params.append('root_session_id', sessionFilters.root_session_id);
            if (sessionFilters.start_date) params.append('start_date', sessionFilters.start_date);
            if (sessionFilters.end_date) params.append('end_date', sessionFilters.end_date);
            if (sessionFilters.created_start) params.append('created_start', sessionFilters.created_start);
            if (sessionFilters.created_end) params.append('created_end', sessionFilters.created_end);
            if (sessionFilters.completed_start) params.append('completed_start', sessionFilters.completed_start);
            if (sessionFilters.completed_end) params.append('completed_end', sessionFilters.completed_end);
            if (sessionFilters.updated_start) params.append('updated_start', sessionFilters.updated_start);
            if (sessionFilters.updated_end) params.append('updated_end', sessionFilters.updated_end);
            if (sessionFilters.min_duration) params.append('min_duration', sessionFilters.min_duration.toString());
            if (sessionFilters.max_duration) params.append('max_duration', sessionFilters.max_duration.toString());

            const data = await fetchJson<PaginatedResponse<AgentSession>>(`/sessions?${params}`);

            if (reset) {
                setSessions(data.items);
            } else {
                setSessions(prev => [...prev, ...data.items]);
            }
            setSessionTotal(data.total);
        } catch (e) {
            console.error('Failed to fetch sessions:', e);
        }
    }, [sessions.length, sessionFilters]);

    // Refresh when filters change
    useEffect(() => {
        refreshSessions(true);
    }, [sessionFilters]);

    const loadMoreSessions = useCallback(async () => {
        if (sessions.length < sessionTotal) {
            await refreshSessions(false);
        }
    }, [sessions.length, sessionTotal, refreshSessions]);

    const getSessionById = useCallback(async (sessionId: string): Promise<AgentSession | null> => {
        // First check if we already have it in state
        const existing = sessions.find(s => s.id === sessionId);

        // Only return cached if it has logs (meaning it's a full detail object, not a list item)
        // List items have empty logs arrays usually.
        if (existing && existing.logs && existing.logs.length > 0) {
            return existing;
        }

        // If not, fetch it
        try {
            const fetched = await fetchJson<AgentSession>(`/sessions/${sessionId}`);
            setSessions(prev => {
                const idx = prev.findIndex(s => s.id === sessionId);
                if (idx === -1) return prev;
                const next = [...prev];
                next[idx] = fetched;
                return next;
            });
            return fetched;
        } catch (e) {
            console.error(`Failed to fetch session ${sessionId}:`, e);
            return null;
        }
    }, [sessions]);

    const refreshDocuments = useCallback(async () => {
        try {
            const pageSize = 500;
            const firstPage = await fetchJson<PaginatedResponse<PlanDocument> | PlanDocument[]>(
                `/documents?offset=0&limit=${pageSize}&include_progress=true`
            );
            if (Array.isArray(firstPage)) {
                setDocuments(firstPage);
                return;
            }

            const collected = [...(firstPage.items || [])];
            const total = firstPage.total || collected.length;
            let offset = collected.length;

            while (offset < total) {
                const page = await fetchJson<PaginatedResponse<PlanDocument>>(
                    `/documents?offset=${offset}&limit=${pageSize}&include_progress=true`
                );
                const items = page.items || [];
                if (items.length === 0) break;
                collected.push(...items);
                offset += items.length;
            }

            setDocuments(collected);
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
            setFeatures(applyPendingFeatureStatuses(data));
        } catch (e) {
            console.error('Failed to fetch features:', e);
        }
    }, [applyPendingFeatureStatuses]);

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
        let previousStatus: string | null = null;
        setPendingFeatureStatusById(prev => ({ ...prev, [featureId]: status }));
        setFeatures(prev => prev.map(f => {
            if (f.id !== featureId) return f;
            previousStatus = f.status;
            return { ...f, status };
        }));

        try {
            const res = await fetch(`${API_BASE}/features/${featureId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status }),
            });
            if (!res.ok) {
                throw new Error(`Failed to update feature status: ${res.status} ${res.statusText}`);
            }
            const updated = await res.json() as Feature;
            setPendingFeatureStatusById(prev => {
                const { [featureId]: _ignore, ...rest } = prev;
                return rest;
            });
            upsertFeatureInState(updated);
        } catch (e) {
            setPendingFeatureStatusById(prev => {
                const { [featureId]: _ignore, ...rest } = prev;
                return rest;
            });
            if (previousStatus !== null) {
                setFeatures(prev => prev.map(f => (
                    f.id === featureId ? { ...f, status: previousStatus as string } : f
                )));
            }
            console.error('Failed to update feature status:', e);
            throw e;
        }
    }, [upsertFeatureInState]);

    const updatePhaseStatus = useCallback(async (featureId: string, phaseId: string, status: string) => {
        try {
            const res = await fetch(`${API_BASE}/features/${featureId}/phases/${phaseId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status }),
            });
            if (!res.ok) {
                throw new Error(`Failed to update phase status: ${res.status} ${res.statusText}`);
            }
            const updated = await res.json() as Feature;
            upsertFeatureInState(updated);
        } catch (e) {
            console.error('Failed to update phase status:', e);
            throw e;
        }
    }, [upsertFeatureInState]);

    const updateTaskStatus = useCallback(async (featureId: string, phaseId: string, taskId: string, status: string) => {
        try {
            const res = await fetch(`${API_BASE}/features/${featureId}/phases/${phaseId}/tasks/${taskId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status }),
            });
            if (!res.ok) {
                throw new Error(`Failed to update task status: ${res.status} ${res.statusText}`);
            }
            const updated = await res.json() as Feature;
            upsertFeatureInState(updated);
        } catch (e) {
            console.error('Failed to update task status:', e);
            throw e;
        }
    }, [upsertFeatureInState]);

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

    // Faster feature polling to keep Kanban and Feature modal responsive to background updates.
    useEffect(() => {
        const interval = setInterval(() => {
            refreshFeatures();
        }, FEATURE_POLL_INTERVAL_MS);
        return () => clearInterval(interval);
    }, [refreshFeatures]);

    return (
        <DataContext.Provider
            value={{
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
                loading,
                error,
                refreshAll,
                refreshSessions,
                loadMoreSessions,
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
                getSessionById,
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
