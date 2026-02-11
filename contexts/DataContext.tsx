import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { AgentSession, PlanDocument, ProjectTask, AlertConfig, Notification } from '../types';

// ── Types ──────────────────────────────────────────────────────────

interface DataContextValue {
    // Data
    sessions: AgentSession[];
    documents: PlanDocument[];
    tasks: ProjectTask[];
    alerts: AlertConfig[];
    notifications: Notification[];

    // Status
    loading: boolean;
    error: string | null;

    // Actions
    refreshAll: () => Promise<void>;
    refreshSessions: () => Promise<void>;
    refreshDocuments: () => Promise<void>;
    refreshTasks: () => Promise<void>;
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

    const refreshAll = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            await Promise.all([
                refreshSessions(),
                refreshDocuments(),
                refreshTasks(),
                refreshAlerts(),
                refreshNotifications(),
            ]);
        } catch (e: any) {
            setError(e.message || 'Failed to load data');
        } finally {
            setLoading(false);
        }
    }, [refreshSessions, refreshDocuments, refreshTasks, refreshAlerts, refreshNotifications]);

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
                loading,
                error,
                refreshAll,
                refreshSessions,
                refreshDocuments,
                refreshTasks,
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
