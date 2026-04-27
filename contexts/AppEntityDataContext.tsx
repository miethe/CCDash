import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type {
  AgentSession,
  AlertConfig,
  Feature,
  Notification,
  PlanDocument,
  ProjectTask,
  TaskStatus,
} from '../types';
import {
  aggregateFeatureFromPhases,
  hasSessionDetail,
  matchesPhase,
  mergeSessionDetail,
  type SessionFetchOptions,
  type SessionFilters,
} from './dataContextShared';
import { useDataClient } from './DataClientContext';
import { MAX_DOCUMENTS_IN_MEMORY } from '../constants';

interface AppEntityDataContextValue {
  sessions: AgentSession[];
  sessionTotal: number;
  sessionFilters: SessionFilters;
  setSessionFilters: (filters: SessionFilters) => void;
  documents: PlanDocument[];
  documentsTruncated: boolean;
  loadMoreDocuments: () => Promise<void>;
  tasks: ProjectTask[];
  alerts: AlertConfig[];
  notifications: Notification[];
  features: Feature[];
  refreshSessions: (reset?: boolean) => Promise<void>;
  loadMoreSessions: () => Promise<void>;
  refreshDocuments: () => Promise<void>;
  refreshTasks: () => Promise<void>;
  refreshAlerts: () => Promise<void>;
  refreshNotifications: () => Promise<void>;
  refreshFeatures: () => Promise<void>;
  updateFeatureStatus: (featureId: string, status: string) => Promise<void>;
  updatePhaseStatus: (featureId: string, phaseId: string, status: string) => Promise<void>;
  updateTaskStatus: (featureId: string, phaseId: string, taskId: string, status: TaskStatus, previousStatus?: TaskStatus) => Promise<void>;
  getSessionById: (sessionId: string, options?: SessionFetchOptions) => Promise<AgentSession | null>;
}

const SESSIONS_PER_PAGE = 50;
const AppEntityDataContext = createContext<AppEntityDataContextValue | null>(null);

export const AppEntityDataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const client = useDataClient();
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [sessionTotal, setSessionTotal] = useState(0);
  const [sessionFilters, setSessionFilters] = useState<SessionFilters>({ include_subagents: true });
  const [documents, setDocuments] = useState<PlanDocument[]>([]);
  const [documentsTruncated, setDocumentsTruncated] = useState(false);
  const [documentOffset, setDocumentOffset] = useState(0);
  const [documentTotal, setDocumentTotal] = useState(0);
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  const [alerts, setAlerts] = useState<AlertConfig[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [pendingFeatureStatusById, setPendingFeatureStatusById] = useState<Record<string, string>>({});
  const sessionsCountRef = useRef(0);
  const sessionsRef = useRef<AgentSession[]>([]);
  const refreshFeaturesInFlightRef = useRef<Promise<void> | null>(null);
  const sessionDetailRequestsRef = useRef<Map<string, Promise<AgentSession | null>>>(new Map());
  const sessionDetailTimestampsRef = useRef<Map<string, number>>(new Map());
  const SESSION_DETAIL_TTL_MS = 30_000;

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

  useEffect(() => {
    sessionsRef.current = sessions;
    sessionsCountRef.current = sessions.length;
  }, [sessions]);

  const refreshSessions = useCallback(async (reset = true) => {
    const currentCount = sessionsCountRef.current;
    const limit = reset ? Math.max(SESSIONS_PER_PAGE, currentCount) : SESSIONS_PER_PAGE;
    const offset = reset ? 0 : currentCount;
    const data = await client.getSessions(sessionFilters, { offset, limit });

    if (reset) {
      setSessions(data.items);
    } else {
      setSessions(prev => [...prev, ...data.items]);
    }
    setSessionTotal(data.total);
  }, [client, sessionFilters]);

  useEffect(() => {
    void refreshSessions(true);
  }, [refreshSessions]);

  const loadMoreSessions = useCallback(async () => {
    if (sessions.length < sessionTotal) {
      await refreshSessions(false);
    }
  }, [refreshSessions, sessionTotal, sessions.length]);

  const gcSessionDetailRequests = useCallback(() => {
    const now = Date.now();
    for (const [key, ts] of sessionDetailTimestampsRef.current) {
      if (now - ts > SESSION_DETAIL_TTL_MS) {
        sessionDetailRequestsRef.current.delete(key);
        sessionDetailTimestampsRef.current.delete(key);
      }
    }
  }, [SESSION_DETAIL_TTL_MS]);

  const getSessionById = useCallback(async (sessionId: string, options?: SessionFetchOptions): Promise<AgentSession | null> => {
    const forceFetch = Boolean(options?.force);
    const cachedSessions = sessionsRef.current;
    const existing = cachedSessions.find(s => s.id === sessionId);

    if (!forceFetch && hasSessionDetail(existing)) {
      return existing;
    }

    // GC expired entries before checking/inserting
    gcSessionDetailRequests();

    const inFlight = sessionDetailRequestsRef.current.get(sessionId);
    if (inFlight) {
      return inFlight;
    }

    const request = (async () => {
      try {
        const fetched = await client.getSession(sessionId);
        setSessions(prev => mergeSessionDetail(prev, fetched));
        return fetched;
      } catch (error) {
        console.error(`Failed to fetch session ${sessionId}:`, error);
        return null;
      } finally {
        sessionDetailRequestsRef.current.delete(sessionId);
        sessionDetailTimestampsRef.current.delete(sessionId);
      }
    })();

    sessionDetailRequestsRef.current.set(sessionId, request);
    sessionDetailTimestampsRef.current.set(sessionId, Date.now());
    return request;
  }, [client, gcSessionDetailRequests]);

  const refreshDocuments = useCallback(async () => {
    const pageSize = 500;
    const firstPage = await client.getDocuments(0, pageSize);
    if (Array.isArray(firstPage)) {
      setDocuments(firstPage.slice(0, MAX_DOCUMENTS_IN_MEMORY));
      setDocumentsTruncated(firstPage.length > MAX_DOCUMENTS_IN_MEMORY);
      setDocumentOffset(Math.min(firstPage.length, MAX_DOCUMENTS_IN_MEMORY));
      setDocumentTotal(firstPage.length);
      return;
    }

    const collected = [...(firstPage.items || [])];
    const total = firstPage.total || collected.length;
    setDocumentTotal(total);
    let offset = collected.length;

    while (offset < total && collected.length < MAX_DOCUMENTS_IN_MEMORY) {
      const page = await client.getDocuments(offset, pageSize);
      if (Array.isArray(page)) {
        if (page.length === 0) break;
        collected.push(...page);
        offset += page.length;
        continue;
      }
      const items = page.items || [];
      if (items.length === 0) break;
      collected.push(...items);
      offset += items.length;
    }

    const capped = collected.slice(0, MAX_DOCUMENTS_IN_MEMORY);
    setDocuments(capped);
    setDocumentsTruncated(total > MAX_DOCUMENTS_IN_MEMORY);
    setDocumentOffset(capped.length);
  }, [client]);

  const loadMoreDocuments = useCallback(async () => {
    if (documentOffset >= documentTotal) return;
    const pageSize = 500;
    const page = await client.getDocuments(documentOffset, pageSize);
    const items = Array.isArray(page) ? page : (page.items || []);
    if (items.length === 0) return;
    setDocuments(prev => {
      const merged = [...prev, ...items];
      const capped = merged.slice(0, MAX_DOCUMENTS_IN_MEMORY);
      setDocumentsTruncated(documentTotal > capped.length);
      setDocumentOffset(prev.length + items.length);
      return capped;
    });
  }, [client, documentOffset, documentTotal]);

  const refreshTasks = useCallback(async () => {
    const data = await client.getTasks();
    setTasks(Array.isArray(data) ? data : (data.items || []));
  }, [client]);

  const refreshAlerts = useCallback(async () => {
    setAlerts(await client.getAlerts());
  }, [client]);

  const refreshNotifications = useCallback(async () => {
    setNotifications(await client.getNotifications());
  }, [client]);

  const refreshFeatures = useCallback(async () => {
    if (refreshFeaturesInFlightRef.current) {
      return refreshFeaturesInFlightRef.current;
    }
    const task = (async () => {
      const data = await client.getFeatures();
      const items = Array.isArray(data) ? data : (data.items || []);
      setFeatures(applyPendingFeatureStatuses(items));
    })();
    refreshFeaturesInFlightRef.current = task;
    try {
      await task;
    } finally {
      if (refreshFeaturesInFlightRef.current === task) {
        refreshFeaturesInFlightRef.current = null;
      }
    }
  }, [applyPendingFeatureStatuses, client]);

  const updateFeatureStatus = useCallback(async (featureId: string, status: string) => {
    let previousStatus: string | null = null;
    setPendingFeatureStatusById(prev => ({ ...prev, [featureId]: status }));
    setFeatures(prev => prev.map(f => {
      if (f.id !== featureId) return f;
      previousStatus = f.status;
      return { ...f, status };
    }));

    try {
      const updated = await client.updateFeatureStatus(featureId, status);
      if (updated.id !== featureId) {
        setFeatures(prev => prev.filter(f => f.id !== featureId));
      }
      setPendingFeatureStatusById(prev => {
        const { [featureId]: _ignore, ...rest } = prev;
        return rest;
      });
      upsertFeatureInState(updated);
    } catch (error) {
      setPendingFeatureStatusById(prev => {
        const { [featureId]: _ignore, ...rest } = prev;
        return rest;
      });
      if (previousStatus !== null) {
        setFeatures(prev => prev.map(f => (
          f.id === featureId ? { ...f, status: previousStatus as string } : f
        )));
      }
      throw error;
    }
  }, [client, upsertFeatureInState]);

  const updatePhaseStatus = useCallback(async (featureId: string, phaseId: string, status: string) => {
    let previousFeatureSnapshot: Feature | null = null;
    setFeatures(prev => prev.map(feature => {
      if (feature.id !== featureId) return feature;
      previousFeatureSnapshot = feature;
      const nextPhases = (feature.phases || []).map(phase => {
        if (!matchesPhase(phase, phaseId)) return phase;
        const totalTasks = Math.max(phase.totalTasks || 0, 0);
        const doneFromTasks = (phase.tasks || []).filter(task => task.status === 'done').length;
        const deferredFromTasks = (phase.tasks || []).filter(task => task.status === 'deferred').length;
        let completedTasks = phase.tasks && phase.tasks.length > 0
          ? doneFromTasks + deferredFromTasks
          : Math.max(phase.completedTasks || 0, 0);
        let deferredTasks = phase.tasks && phase.tasks.length > 0
          ? deferredFromTasks
          : Math.max(phase.deferredTasks || 0, 0);
        if (status === 'deferred' && totalTasks > 0) {
          completedTasks = totalTasks;
          deferredTasks = totalTasks;
        }
        if (totalTasks > 0 && completedTasks > totalTasks) completedTasks = totalTasks;
        if (deferredTasks > completedTasks) deferredTasks = completedTasks;
        return { ...phase, status, completedTasks, deferredTasks };
      });
      return aggregateFeatureFromPhases(feature, nextPhases);
    }));

    try {
      const updated = await client.updatePhaseStatus(featureId, phaseId, status);
      if (updated.id !== featureId) {
        setFeatures(prev => prev.filter(f => f.id !== featureId));
      }
      upsertFeatureInState(updated);
    } catch (error) {
      if (previousFeatureSnapshot) {
        upsertFeatureInState(previousFeatureSnapshot);
      }
      throw error;
    }
  }, [client, upsertFeatureInState]);

  const updateTaskStatus = useCallback(async (featureId: string, phaseId: string, taskId: string, status: TaskStatus, previousStatus?: TaskStatus) => {
    let previousFeatureSnapshot: Feature | null = null;
    setFeatures(prev => prev.map(feature => {
      if (feature.id !== featureId) return feature;
      previousFeatureSnapshot = feature;
      const nextPhases = (feature.phases || []).map(phase => {
        if (!matchesPhase(phase, phaseId)) return phase;
        let tasks = phase.tasks || [];
        let changed = false;
        if (Array.isArray(phase.tasks) && phase.tasks.length > 0) {
          tasks = phase.tasks.map(task => {
            if (task.id !== taskId) return task;
            changed = true;
            return { ...task, status };
          });
        } else if (previousStatus && previousStatus !== status) {
          changed = true;
        }
        if (!changed) return phase;

        const totalTasks = Math.max(phase.totalTasks || 0, tasks.length);
        let completedTasks = Math.max(phase.completedTasks || 0, 0);
        let deferredTasks = Math.max(phase.deferredTasks || 0, 0);

        if (tasks.length > 0) {
          const doneCount = tasks.filter(task => task.status === 'done').length;
          const deferredCount = tasks.filter(task => task.status === 'deferred').length;
          completedTasks = doneCount + deferredCount;
          deferredTasks = deferredCount;
        } else if (previousStatus && previousStatus !== status) {
          if (previousStatus === 'done') completedTasks -= 1;
          if (previousStatus === 'deferred') {
            completedTasks -= 1;
            deferredTasks -= 1;
          }
          if (status === 'done') completedTasks += 1;
          if (status === 'deferred') {
            completedTasks += 1;
            deferredTasks += 1;
          }
        }

        if (phase.status === 'deferred' && totalTasks > 0) {
          completedTasks = totalTasks;
          deferredTasks = totalTasks;
        }
        if (completedTasks < 0) completedTasks = 0;
        if (deferredTasks < 0) deferredTasks = 0;
        if (totalTasks > 0 && completedTasks > totalTasks) completedTasks = totalTasks;
        return {
          ...phase,
          tasks,
          completedTasks,
          deferredTasks: Math.min(deferredTasks, completedTasks),
        };
      });
      return aggregateFeatureFromPhases(feature, nextPhases);
    }));

    try {
      const updated = await client.updateTaskStatus(featureId, phaseId, taskId, status);
      if (updated.id !== featureId) {
        setFeatures(prev => prev.filter(f => f.id !== featureId));
      }
      upsertFeatureInState(updated);
    } catch (error) {
      if (previousFeatureSnapshot) {
        upsertFeatureInState(previousFeatureSnapshot);
      }
      throw error;
    }
  }, [client, upsertFeatureInState]);

  return (
    <AppEntityDataContext.Provider
      value={{
        sessions,
        sessionTotal,
        sessionFilters,
        setSessionFilters,
        documents,
        tasks,
        alerts,
        notifications,
        features,
        refreshSessions,
        loadMoreSessions,
        documentsTruncated,
        loadMoreDocuments,
        refreshDocuments,
        refreshTasks,
        refreshAlerts,
        refreshNotifications,
        refreshFeatures,
        updateFeatureStatus,
        updatePhaseStatus,
        updateTaskStatus,
        getSessionById,
      }}
    >
      {children}
    </AppEntityDataContext.Provider>
  );
};

export function useAppEntityData(): AppEntityDataContextValue {
  const ctx = useContext(AppEntityDataContext);
  if (!ctx) {
    throw new Error('useAppEntityData must be used within an AppEntityDataProvider');
  }
  return ctx;
}
