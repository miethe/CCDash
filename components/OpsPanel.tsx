import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  FolderKanban,
  Gauge,
  Play,
  RefreshCw,
  Server,
  TestTube2,
  Wrench,
} from 'lucide-react';
import { useData } from '../contexts/DataContext';
import {
  CacheStatusResponse,
  LinkAuditResponse,
  SkillMeatDefinitionSyncResponse,
  SkillMeatObservationBackfillResponse,
  SyncOperation,
  TelemetryExportStatus,
} from '../types';
import { normalizeSkillMeatConfig } from '../services/agenticIntelligence';
import { createApiClient } from '../services/apiClient';
import { isOpsLiveUpdatesEnabled, projectOpsTopic, useLiveInvalidation } from '../services/live';
import { refreshSkillMeatCache } from '../services/skillmeat';

const API_BASE = '/api';

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}) for ${path}`);
  }
  return res.json() as Promise<T>;
}

function formatDate(value?: string): string {
  if (!value) return 'n/a';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function formatDuration(ms?: number): string {
  const value = Number(ms || 0);
  if (!Number.isFinite(value) || value <= 0) return '0ms';
  if (value < 1000) return `${value}ms`;
  const seconds = value / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

function statusBadgeClass(status: string): string {
  const normalized = (status || '').toLowerCase();
  if (normalized === 'completed') return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  if (normalized === 'failed') return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
  return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
}

function opKindLabel(kind: string): string {
  switch (kind) {
    case 'full_sync':
      return 'Full Sync';
    case 'rebuild_links':
      return 'Link Rebuild';
    case 'sync_changed_files':
      return 'Changed-Path Sync';
    case 'test_mapping_backfill':
      return 'Mapping Backfill';
    default:
      return kind || 'Operation';
  }
}

type OpsTab = 'general' | 'testing' | 'integrations';

interface MappingBackfillResponse {
  project_id: string;
  run_limit: number;
  runs_processed: number;
  tests_considered: number;
  tests_resolved: number;
  tests_reused_cached: number;
  mappings_stored: number;
  primary_mappings: number;
  resolver_version: string;
  cache_state: Record<string, any>;
  total_errors: number;
  errors: string[];
}

interface MappingBackfillStartResponse {
  status: string;
  mode: string;
  message: string;
  operationId: string;
}

interface OpsToast {
  id: string;
  message: string;
  tone: 'success' | 'error' | 'info';
}

interface MappingResolverRunDetail {
  run_id: string;
  timestamp: string;
  branch: string;
  git_sha: string;
  agent_session_id: string;
  total_results: number;
  mapped_primary_tests: number;
  unmapped_tests: number;
  coverage: number;
}

interface MappingResolverDetailResponse {
  project_id: string;
  run_limit: number;
  generated_at: string;
  runs: MappingResolverRunDetail[];
}

function isTerminalOperationStatus(status: string): boolean {
  const normalized = (status || '').trim().toLowerCase();
  return normalized === 'completed' || normalized === 'failed';
}

function isMappingBackfillOperation(operation: SyncOperation | null | undefined): boolean {
  return (operation?.kind || '').trim().toLowerCase() === 'test_mapping_backfill';
}

function normalizeBackfillDetail(operation: SyncOperation): MappingBackfillResponse | null {
  const stats = operation.stats || {};
  const projectId = String(stats.project_id || operation.projectId || '').trim();
  const runLimit = Number(stats.run_limit ?? stats.runLimit ?? 0);
  if (!projectId || runLimit <= 0) return null;

  const errors = Array.isArray(stats.errors) ? stats.errors.map((item: any) => String(item)) : [];
  return {
    project_id: projectId,
    run_limit: runLimit,
    runs_processed: Number(stats.runs_processed ?? stats.runsProcessed ?? 0),
    tests_considered: Number(stats.tests_considered ?? stats.testsConsidered ?? 0),
    tests_resolved: Number(stats.tests_resolved ?? stats.testsResolved ?? 0),
    tests_reused_cached: Number(stats.tests_reused_cached ?? stats.testsReusedCached ?? 0),
    mappings_stored: Number(stats.mappings_stored ?? stats.mappingsStored ?? 0),
    primary_mappings: Number(stats.primary_mappings ?? stats.primaryMappings ?? 0),
    resolver_version: String(stats.resolver_version ?? stats.resolverVersion ?? ''),
    cache_state: (stats.cache_state && typeof stats.cache_state === 'object')
      ? stats.cache_state as Record<string, any>
      : {},
    total_errors: Number(stats.total_errors ?? stats.totalErrors ?? errors.length),
    errors,
  };
}

function mappingSummaryText(detail: MappingBackfillResponse): string {
  return `Mapping backfill processed ${Number(detail.runs_processed || 0)} runs, stored ${Number(detail.mappings_stored || 0)} mappings (${Number(detail.primary_mappings || 0)} primary, ${Number(detail.total_errors || 0)} errors).`;
}

function mappingProgressPercent(operation: SyncOperation | null): number {
  if (!operation) return 0;
  const progress = operation.progress || {};
  const raw = Number(progress.percent);
  if (Number.isFinite(raw) && raw >= 0) return Math.max(0, Math.min(100, raw));
  const total = Number(progress.runsTotal || 0);
  const scanned = Number(progress.runsScanned || 0);
  if (total > 0) return Math.max(0, Math.min(100, Math.round((scanned / total) * 100)));
  return 0;
}

export const OpsPanel: React.FC = () => {
  const { projects, activeProject, sessions, sessionTotal, documents, tasks, features, refreshAll } = useData();
  const apiClient = useMemo(() => createApiClient(), []);

  const [status, setStatus] = useState<CacheStatusResponse | null>(null);
  const [health, setHealth] = useState<{ status: string; db: string; watcher: string } | null>(null);
  const [operations, setOperations] = useState<SyncOperation[]>([]);
  const [selectedOperationId, setSelectedOperationId] = useState('');
  const [selectedOperation, setSelectedOperation] = useState<SyncOperation | null>(null);
  const [audit, setAudit] = useState<LinkAuditResponse | null>(null);
  const [auditFeatureId, setAuditFeatureId] = useState('');
  const [auditLimit, setAuditLimit] = useState(50);
  const [auditPrimaryFloor, setAuditPrimaryFloor] = useState(0.55);
  const [auditFanoutFloor, setAuditFanoutFloor] = useState(10);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<string>('');
  const [pathSyncRaw, setPathSyncRaw] = useState('');
  const [pathSyncChangeType, setPathSyncChangeType] = useState<'modified' | 'added' | 'deleted'>('modified');
  const [activeTab, setActiveTab] = useState<OpsTab>('general');
  const [mappingRunLimit, setMappingRunLimit] = useState(250);
  const [mappingBackfillDetail, setMappingBackfillDetail] = useState<MappingBackfillResponse | null>(null);
  const [mappingBackfillOperationId, setMappingBackfillOperationId] = useState('');
  const [mappingResolverDetail, setMappingResolverDetail] = useState<MappingResolverDetailResponse | null>(null);
  const [skillMeatSyncResult, setSkillMeatSyncResult] = useState<SkillMeatDefinitionSyncResponse | null>(null);
  const [skillMeatBackfillResult, setSkillMeatBackfillResult] = useState<SkillMeatObservationBackfillResponse | null>(null);
  const [telemetryStatus, setTelemetryStatus] = useState<TelemetryExportStatus | null>(null);
  const [telemetryLoadError, setTelemetryLoadError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<OpsToast[]>([]);
  const handledOperationIdsRef = useRef<Set<string>>(new Set());
  const toastTimerIdsRef = useRef<number[]>([]);
  const skillMeatConfig = useMemo(() => normalizeSkillMeatConfig(activeProject), [activeProject]);

  const loadOverview = async () => {
    const [statusPayload, opsPayload, healthPayload] = await Promise.all([
      fetchJson<CacheStatusResponse>('/cache/status'),
      fetchJson<{ status: string; count: number; items: SyncOperation[] }>('/cache/operations?limit=30'),
      fetchJson<{ status: string; db: string; watcher: string }>('/health'),
    ]);
    setStatus(statusPayload);
    setOperations(opsPayload.items || []);
    setHealth(healthPayload);
    setLastRefreshAt(new Date().toISOString());

    if (!selectedOperationId && opsPayload.items?.length) {
      setSelectedOperationId(opsPayload.items[0].id);
    }
  };

  const runSync = async (force: boolean) => {
    setBusyAction('sync');
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/cache/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force, background: true, trigger: 'ops-panel' }),
      });
      if (!res.ok) throw new Error(`Sync request failed (${res.status})`);
      const payload = await res.json();
      const opId = String(payload.operationId || '');
      if (opId) setSelectedOperationId(opId);
      await loadOverview();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start sync');
    } finally {
      setBusyAction(null);
    }
  };

  const runRebuildLinks = async () => {
    setBusyAction('rebuild-links');
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/cache/rebuild-links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ background: true, captureAnalytics: false, trigger: 'ops-panel' }),
      });
      if (!res.ok) throw new Error(`Rebuild request failed (${res.status})`);
      const payload = await res.json();
      const opId = String(payload.operationId || '');
      if (opId) setSelectedOperationId(opId);
      await loadOverview();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start link rebuild');
    } finally {
      setBusyAction(null);
    }
  };

  const runPathSync = async () => {
    const paths = pathSyncRaw
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean);
    if (paths.length === 0) {
      setError('Provide one or more paths for targeted sync.');
      return;
    }
    setBusyAction('sync-paths');
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/cache/sync-paths`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          background: true,
          trigger: 'ops-panel',
          paths: paths.map(path => ({ path, changeType: pathSyncChangeType })),
        }),
      });
      if (!res.ok) throw new Error(`Path sync request failed (${res.status})`);
      const payload = await res.json();
      const opId = String(payload.operationId || '');
      if (opId) setSelectedOperationId(opId);
      await loadOverview();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start targeted path sync');
    } finally {
      setBusyAction(null);
    }
  };

  const runAudit = async () => {
    setBusyAction('audit');
    setError(null);
    try {
      const params = new URLSearchParams({
        limit: String(auditLimit),
        primary_floor: String(auditPrimaryFloor),
        fanout_floor: String(auditFanoutFloor),
      });
      if (auditFeatureId.trim()) params.set('feature_id', auditFeatureId.trim());
      const payload = await fetchJson<LinkAuditResponse>(`/links/audit?${params.toString()}`);
      setAudit(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run link audit');
    } finally {
      setBusyAction(null);
    }
  };

  const loadMappingResolverDetail = useCallback(async (projectId: string, runLimit: number) => {
    const params = new URLSearchParams({
      project_id: projectId,
      run_limit: String(runLimit),
    });
    const payload = await fetchJson<MappingResolverDetailResponse>(`/tests/mappings/resolver-detail?${params.toString()}`);
    setMappingResolverDetail(payload);
  }, []);

  const pushToast = useCallback((message: string, tone: OpsToast['tone'] = 'info') => {
    const id = `ops-toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts(prev => [...prev, { id, message, tone }].slice(-4));
    const timerId = window.setTimeout(() => {
      setToasts(prev => prev.filter(item => item.id !== id));
    }, 5000);
    toastTimerIdsRef.current.push(timerId);
  }, []);

  useEffect(() => {
    return () => {
      toastTimerIdsRef.current.forEach(id => window.clearTimeout(id));
      toastTimerIdsRef.current = [];
    };
  }, []);

  const startMappingBackfill = useCallback(async (projectId: string): Promise<string> => {
    const startRes = await fetch(`${API_BASE}/tests/mappings/backfill/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        run_limit: mappingRunLimit,
        source: 'ops-panel',
      }),
    });
    if (!startRes.ok) throw new Error(`Mapping backfill request failed (${startRes.status})`);
    const startPayload = await startRes.json() as MappingBackfillStartResponse;
    const operationId = String(startPayload.operationId || '');
    if (!operationId) throw new Error('Mapping backfill started without operation ID.');
    return operationId;
  }, [mappingRunLimit]);

  const runSkillMeatRefresh = useCallback(async () => {
    const projectId = status?.projectId || activeProject?.id || '';
    if (!projectId) {
      setError('No active project selected for SkillMeat refresh.');
      return;
    }
    if (!skillMeatConfig.enabled) {
      setError('Enable SkillMeat integration in Project Settings before running this pipeline.');
      return;
    }
    if (!skillMeatConfig.baseUrl.trim()) {
      setError('Configure a SkillMeat base URL in Project Settings before running this pipeline.');
      return;
    }

    setBusyAction('skillmeat-refresh');
    setError(null);
    setNotice(null);
    try {
      const refreshResult = await refreshSkillMeatCache(projectId);
      const syncResult = refreshResult.sync;
      const backfillResult = refreshResult.backfill;
      setSkillMeatSyncResult(syncResult);
      setSkillMeatBackfillResult(backfillResult);
      setNotice(
        `SkillMeat refresh completed: ${syncResult.totalDefinitions} definitions synced and ${backfillResult?.observationsStored ?? 0} observations rebuilt.`,
      );
      pushToast('SkillMeat refresh pipeline completed.', 'success');
      await refreshAll();
      await loadOverview();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to refresh SkillMeat caches';
      setError(message);
      pushToast(message, 'error');
    } finally {
      setBusyAction(null);
    }
  }, [activeProject?.id, loadOverview, pushToast, refreshAll, skillMeatConfig, status?.projectId]);

  const loadTelemetryStatus = useCallback(async (quiet = false) => {
    try {
      const response = await apiClient.getTelemetryExportStatus();
      setTelemetryStatus(response);
      setTelemetryLoadError(null);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to load telemetry exporter status';
      if (!quiet) setTelemetryLoadError(message);
    }
  }, [apiClient]);

  const runTelemetryPushNow = useCallback(async () => {
    if (!telemetryStatus?.configured) {
      setTelemetryLoadError('Configure the SAM endpoint and API key before triggering a manual export.');
      return;
    }
    if (!telemetryStatus.enabled) {
      setTelemetryLoadError('Enable telemetry export in Settings before triggering a manual export.');
      return;
    }

    setBusyAction('telemetry-push');
    setTelemetryLoadError(null);
    setNotice(null);
    try {
      const response = await apiClient.triggerTelemetryPushNow();
      const message = response.batchSize > 0
        ? `Telemetry push completed: ${response.batchSize} event${response.batchSize === 1 ? '' : 's'} exported in ${formatDuration(response.durationMs)}.`
        : 'Telemetry push completed: no pending events were waiting in the queue.';
      setNotice(message);
      pushToast(message, response.success ? 'success' : 'info');
      await Promise.all([loadOverview(), loadTelemetryStatus()]);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to trigger telemetry export';
      setTelemetryLoadError(message);
      pushToast(message, 'error');
    } finally {
      setBusyAction(null);
    }
  }, [apiClient, loadOverview, loadTelemetryStatus, pushToast, telemetryStatus]);

  const latestCompletedBackfillOperation = useMemo(
    () => operations.find(op => isMappingBackfillOperation(op) && (op.status || '').toLowerCase() === 'completed') || null,
    [operations],
  );

  const trackedBackfillOperation = useMemo(() => {
    if (mappingBackfillOperationId) {
      return operations.find(op => op.id === mappingBackfillOperationId) || null;
    }
    return operations.find(op => isMappingBackfillOperation(op) && !isTerminalOperationStatus(op.status)) || null;
  }, [mappingBackfillOperationId, operations]);

  const mappingBackfillRunning = Boolean(
    trackedBackfillOperation && !isTerminalOperationStatus(trackedBackfillOperation.status),
  );
  const mappingBackfillPct = mappingProgressPercent(trackedBackfillOperation);

  const runMappingBackfillOnly = async () => {
    const projectId = status?.projectId || activeProject?.id || '';
    if (!projectId) {
      setError('No active project selected for mapping backfill.');
      return;
    }

    setBusyAction('mapping-backfill');
    setError(null);
    setNotice(null);
    try {
      const operationId = await startMappingBackfill(projectId);
      setMappingBackfillOperationId(operationId);
      handledOperationIdsRef.current.delete(operationId);
      setMappingBackfillDetail(null);
      setSelectedOperationId(operationId);
      setNotice('Mapping backfill started in the background. You can navigate away and it will continue running.');
      await loadOverview();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run mapping backfill');
    } finally {
      setBusyAction(null);
    }
  };

  const runTestIngestAndMapping = async () => {
    const projectId = status?.projectId || activeProject?.id || '';
    if (!projectId) {
      setError('No active project selected for test ingest/mapping.');
      return;
    }

    setBusyAction('test-ingest-mapping');
    setError(null);
    setNotice(null);
    try {
      const syncRes = await fetch(`${API_BASE}/tests/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, force: true, platforms: [] }),
      });
      if (!syncRes.ok) throw new Error(`Test sync failed (${syncRes.status})`);
      const syncPayload = await syncRes.json() as { stats?: { synced?: number; errors?: number } };
      const operationId = await startMappingBackfill(projectId);
      setMappingBackfillOperationId(operationId);
      handledOperationIdsRef.current.delete(operationId);
      setMappingBackfillDetail(null);
      setSelectedOperationId(operationId);

      setNotice(
        `Test sync complete (synced ${Number(syncPayload.stats?.synced || 0)} files). `
        + 'Mapping backfill started in the background and will continue if you navigate away.'
      );
      await loadOverview();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run test ingest/mapping');
    } finally {
      setBusyAction(null);
    }
  };

  useEffect(() => {
    let isMounted = true;
    const run = async () => {
      try {
        await loadOverview();
      } catch (e) {
        if (!isMounted) return;
        setError(e instanceof Error ? e.message : 'Failed to load ops metadata');
      }
    };
    run();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (activeTab !== 'integrations') return;
    void loadTelemetryStatus();
  }, [activeTab, loadTelemetryStatus]);

  const opsLiveEnabled = Boolean(activeProject?.id && isOpsLiveUpdatesEnabled());
  const opsLiveStatus = useLiveInvalidation({
    topics: opsLiveEnabled && activeProject?.id ? [projectOpsTopic(activeProject.id)] : [],
    enabled: opsLiveEnabled,
    pauseWhenHidden: true,
    onInvalidate: () => loadOverview(),
  });

  useEffect(() => {
    if (opsLiveEnabled && !['backoff', 'closed'].includes(opsLiveStatus)) {
      return undefined;
    }
    let timer: number | undefined;
    const hasActiveOps = (status?.operations?.activeOperationCount || 0) > 0;
    const intervalMs = hasActiveOps ? 2500 : 15000;

    timer = window.setInterval(async () => {
      try {
        await loadOverview();
      } catch (e) {
        // Keep previous data, do not spam fatal UI failures on polling.
      }
    }, intervalMs);

    return () => {
      if (timer) window.clearInterval(timer);
    };
  }, [opsLiveEnabled, opsLiveStatus, selectedOperationId, status?.operations?.activeOperationCount]);

  useEffect(() => {
    if (activeTab !== 'integrations') return undefined;
    const timer = window.setInterval(() => {
      void loadTelemetryStatus(true);
    }, 10000);
    return () => {
      window.clearInterval(timer);
    };
  }, [activeTab, loadTelemetryStatus]);

  useEffect(() => {
    let isMounted = true;
    const run = async () => {
      if (!selectedOperationId) return;
      try {
        const payload = await fetchJson<SyncOperation>(`/cache/operations/${encodeURIComponent(selectedOperationId)}`);
        if (isMounted) setSelectedOperation(payload);
      } catch (e) {
        if (isMounted) setSelectedOperation(null);
      }
    };
    run();
    return () => {
      isMounted = false;
    };
  }, [selectedOperationId, operations.length, status?.operations?.activeOperationCount, lastRefreshAt]);

  useEffect(() => {
    if (activeTab !== 'testing') return;
    const projectId = status?.projectId || activeProject?.id || '';
    if (!projectId) return;
    loadMappingResolverDetail(projectId, mappingRunLimit).catch((e) => {
      setError(e instanceof Error ? e.message : 'Failed to load mapping resolver detail');
    });
  }, [activeTab, activeProject?.id, loadMappingResolverDetail, mappingRunLimit, status?.projectId]);

  useEffect(() => {
    if (!trackedBackfillOperation) return;
    if (mappingBackfillOperationId) return;
    setMappingBackfillOperationId(trackedBackfillOperation.id);
  }, [mappingBackfillOperationId, trackedBackfillOperation]);

  useEffect(() => {
    if (mappingBackfillDetail || !latestCompletedBackfillOperation) return;
    const detail = normalizeBackfillDetail(latestCompletedBackfillOperation);
    if (detail) {
      setMappingBackfillDetail(detail);
    }
  }, [latestCompletedBackfillOperation, mappingBackfillDetail]);

  useEffect(() => {
    const operation = trackedBackfillOperation;
    if (!operation || !isTerminalOperationStatus(operation.status)) return;
    if (handledOperationIdsRef.current.has(operation.id)) return;
    handledOperationIdsRef.current.add(operation.id);

    const operationStatus = (operation.status || '').toLowerCase();
    if (operationStatus === 'completed') {
      const detail = normalizeBackfillDetail(operation);
      if (detail) {
        setMappingBackfillDetail(detail);
        setNotice(mappingSummaryText(detail));
        if (activeTab === 'testing') {
          loadMappingResolverDetail(detail.project_id, detail.run_limit).catch((e) => {
            setError(e instanceof Error ? e.message : 'Failed to load mapping resolver detail');
          });
        }
      } else {
        setNotice(operation.message || 'Mapping backfill completed.');
      }
      setError(null);
      pushToast('Mapping backfill completed.', 'success');
      void refreshAll().catch(() => undefined);
      return;
    }

    const failureMessage = operation.error || operation.message || 'Mapping backfill failed';
    setError(failureMessage);
    setNotice(null);
    pushToast('Mapping backfill failed. Check operation details for error output.', 'error');
    void refreshAll().catch(() => undefined);
  }, [activeTab, loadMappingResolverDetail, pushToast, refreshAll, trackedBackfillOperation]);

  const snapshotCards = [
    { label: 'Sessions (Loaded/Total)', value: `${sessions.length} / ${sessionTotal}`, icon: Activity },
    { label: 'Documents', value: String(documents.length), icon: FolderKanban },
    { label: 'Tasks', value: String(tasks.length), icon: CheckCircle2 },
    { label: 'Features', value: String(features.length), icon: Gauge },
  ];
  const disableBackfillActions = busyAction !== null || mappingBackfillRunning;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold text-slate-100">Operations Center</h2>
          <p className="text-slate-400 mt-2">
            Live sync/rebuild visibility, audit controls, and app/project runtime metadata.
          </p>
        </div>
        <button
          onClick={() => loadOverview().catch((e) => setError(e instanceof Error ? e.message : 'Refresh failed'))}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      <div className="inline-flex rounded-lg border border-slate-800 bg-slate-900/70 p-1">
        <button
          type="button"
          onClick={() => setActiveTab('general')}
          className={`rounded-md px-3 py-1.5 text-sm ${activeTab === 'general' ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`}
        >
          General Ops
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('testing')}
          className={`rounded-md px-3 py-1.5 text-sm ${activeTab === 'testing' ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`}
        >
          Testing Ops
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('integrations')}
          className={`rounded-md px-3 py-1.5 text-sm ${activeTab === 'integrations' ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`}
        >
          Integrations
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
          {notice}
        </div>
      )}
      {toasts.length > 0 && (
        <div className="fixed right-6 top-6 z-50 space-y-2 pointer-events-none">
          {toasts.map(toast => (
            <div
              key={toast.id}
              className={`rounded-lg border px-4 py-3 text-sm shadow-lg backdrop-blur pointer-events-auto ${
                toast.tone === 'success'
                  ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100'
                  : toast.tone === 'error'
                    ? 'border-rose-500/40 bg-rose-500/15 text-rose-100'
                    : 'border-slate-600 bg-slate-900/90 text-slate-100'
              }`}
            >
              {toast.message}
            </div>
          ))}
        </div>
      )}

      {activeTab === 'general' && (
        <>
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {snapshotCards.map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
            <div className="flex items-center justify-between text-slate-400 text-xs uppercase tracking-wider">
              <span>{label}</span>
              <Icon size={14} />
            </div>
            <div className="text-2xl font-bold text-slate-100 mt-2">{value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="xl:col-span-2 rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-100">Sync Controls</h3>
            <span className="text-xs text-slate-500">Last refresh: {formatDate(lastRefreshAt)}</span>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => runSync(true)}
              disabled={busyAction !== null}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-60"
            >
              <Play size={14} />
              Force Full Sync
            </button>
            <button
              onClick={() => runSync(false)}
              disabled={busyAction !== null}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 disabled:opacity-60"
            >
              <Play size={14} />
              Incremental Sync
            </button>
            <button
              onClick={runRebuildLinks}
              disabled={busyAction !== null}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-700/80 border border-emerald-500/30 text-emerald-100 hover:bg-emerald-700 disabled:opacity-60"
            >
              <Wrench size={14} />
              Rebuild Links
            </button>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 space-y-2">
            <p className="text-xs text-slate-400 uppercase tracking-wide">Targeted Path Sync</p>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
              <textarea
                value={pathSyncRaw}
                onChange={(e) => setPathSyncRaw(e.target.value)}
                className="md:col-span-4 min-h-[80px] rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-slate-200 font-mono"
                placeholder={"docs/project_plans/implementation_plans/features/example-v1.md\n.claude/progress/example-v1/phase-1-progress.md"}
              />
              <div className="space-y-2">
                <select
                  value={pathSyncChangeType}
                  onChange={(e) => setPathSyncChangeType(e.target.value as 'modified' | 'added' | 'deleted')}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-2 py-2 text-xs text-slate-200"
                >
                  <option value="modified">modified</option>
                  <option value="added">added</option>
                  <option value="deleted">deleted</option>
                </select>
                <button
                  onClick={runPathSync}
                  disabled={busyAction !== null}
                  className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 disabled:opacity-60"
                >
                  <Play size={12} />
                  Sync Paths
                </button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-slate-500 text-xs uppercase tracking-wide">Backend Health</p>
              <p className="text-slate-100 mt-1">{health?.status || 'unknown'}</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-slate-500 text-xs uppercase tracking-wide">DB</p>
              <p className="text-slate-100 mt-1">{health?.db || 'unknown'}</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-slate-500 text-xs uppercase tracking-wide">Watcher</p>
              <p className="text-slate-100 mt-1">{status?.watcher || health?.watcher || 'unknown'}</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-slate-500 text-xs uppercase tracking-wide">Live Updates</p>
              <p className="text-slate-100 mt-1">
                {status?.liveUpdates
                  ? `${status.liveUpdates.active_subscribers} subs / ${status.liveUpdates.buffered_topics} buffers`
                  : 'n/a'}
              </p>
              {status?.liveUpdates && (
                <p className="mt-1 text-[11px] text-slate-400">
                  replay gaps {status.liveUpdates.replay_gaps} • dropped {status.liveUpdates.dropped_events}
                </p>
              )}
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
          <h3 className="text-lg font-semibold text-slate-100">App Metadata</h3>
          <div className="text-sm space-y-2">
            <div className="flex justify-between gap-3">
              <span className="text-slate-400">Active Project</span>
              <span className="text-slate-100 text-right">{status?.projectName || activeProject?.name || 'n/a'}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-slate-400">Project ID</span>
              <span className="text-slate-300 text-right font-mono">{status?.projectId || activeProject?.id || 'n/a'}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-slate-400">Projects Configured</span>
              <span className="text-slate-100">{projects.length}</span>
            </div>
            <div className="pt-2 border-t border-slate-800 space-y-2">
              <p className="text-slate-500 text-xs uppercase tracking-wide">Resolved Paths</p>
              <p className="text-xs text-slate-300 font-mono break-all">{status?.activePaths?.sessionsDir || 'n/a'}</p>
              <p className="text-xs text-slate-300 font-mono break-all">{status?.activePaths?.docsDir || 'n/a'}</p>
              <p className="text-xs text-slate-300 font-mono break-all">{status?.activePaths?.progressDir || 'n/a'}</p>
            </div>
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="xl:col-span-2 rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-100">Operation Timeline</h3>
            <span className="text-xs text-slate-500">
              Active: {status?.operations?.activeOperationCount ?? 0} / Tracked: {status?.operations?.trackedOperationCount ?? 0}
            </span>
          </div>

          <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
            {operations.length === 0 && (
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
                No operations recorded yet.
              </div>
            )}
            {operations.map(op => (
              <button
                key={op.id}
                onClick={() => setSelectedOperationId(op.id)}
                className={`w-full text-left rounded-lg border p-3 transition-colors ${
                  selectedOperationId === op.id
                    ? 'border-indigo-500/40 bg-indigo-500/10'
                    : 'border-slate-800 bg-slate-950/70 hover:bg-slate-800/60'
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-slate-100">{opKindLabel(op.kind)}</p>
                    <p className="text-xs text-slate-400 mt-1">{op.phase || 'queued'} • {op.message || 'Working...'}</p>
                  </div>
                  <span className={`text-[11px] px-2 py-1 rounded border ${statusBadgeClass(op.status)}`}>
                    {op.status}
                  </span>
                </div>
                <div className="mt-2 text-[11px] text-slate-500 flex justify-between">
                  <span className="font-mono">{op.id}</span>
                  <span>{formatDate(op.startedAt)}</span>
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
          <h3 className="text-lg font-semibold text-slate-100">Operation Detail</h3>
          {!selectedOperation && (
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
              Select an operation from the timeline.
            </div>
          )}
          {selectedOperation && (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Status</span>
                <span className={`text-[11px] px-2 py-1 rounded border ${statusBadgeClass(selectedOperation.status)}`}>
                  {selectedOperation.status}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Kind</span>
                <span className="text-slate-100">{opKindLabel(selectedOperation.kind)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Phase</span>
                <span className="text-slate-100">{selectedOperation.phase || 'n/a'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Duration</span>
                <span className="text-slate-100">{formatDuration(selectedOperation.durationMs)}</span>
              </div>
              <div className="text-xs text-slate-500 space-y-1 pt-2 border-t border-slate-800">
                <p>Started: {formatDate(selectedOperation.startedAt)}</p>
                <p>Updated: {formatDate(selectedOperation.updatedAt)}</p>
                <p>Finished: {formatDate(selectedOperation.finishedAt)}</p>
                <p className="font-mono break-all">ID: {selectedOperation.id}</p>
              </div>
              {selectedOperation.error && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
                  {selectedOperation.error}
                </div>
              )}
              <details className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                <summary className="cursor-pointer text-slate-300 text-xs font-semibold">Raw Metadata</summary>
                <pre className="mt-2 text-[11px] text-slate-400 whitespace-pre-wrap break-all">
                  {JSON.stringify(
                    {
                      metadata: selectedOperation.metadata,
                      progress: selectedOperation.progress,
                      counters: selectedOperation.counters,
                      stats: selectedOperation.stats,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </div>
          )}
        </section>
      </div>

      <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-100">Link Audit</h3>
          <button
            onClick={runAudit}
            disabled={busyAction !== null}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 disabled:opacity-60"
          >
            <Server size={14} />
            Run Audit
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label className="text-xs text-slate-400">
            Feature ID (optional)
            <input
              value={auditFeatureId}
              onChange={(e) => setAuditFeatureId(e.target.value)}
              className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
              placeholder="marketplace-source-detection-improvements-v1"
            />
          </label>
          <label className="text-xs text-slate-400">
            Limit
            <input
              type="number"
              min={1}
              max={500}
              value={auditLimit}
              onChange={(e) => setAuditLimit(Math.max(1, Math.min(500, Number(e.target.value || 50))))}
              className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
          </label>
          <label className="text-xs text-slate-400">
            Primary Floor
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={auditPrimaryFloor}
              onChange={(e) => setAuditPrimaryFloor(Math.max(0, Math.min(1, Number(e.target.value || 0.55))))}
              className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
          </label>
          <label className="text-xs text-slate-400">
            Fanout Floor
            <input
              type="number"
              min={1}
              max={1000}
              value={auditFanoutFloor}
              onChange={(e) => setAuditFanoutFloor(Math.max(1, Math.min(1000, Number(e.target.value || 10))))}
              className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
          </label>
        </div>

        {audit && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-3 text-xs text-slate-400">
              <span>Analyzed: <span className="text-slate-200">{audit.row_count}</span></span>
              <span>Suspects: <span className="text-slate-200">{audit.suspect_count}</span></span>
              <span>Generated: <span className="text-slate-200">{formatDate(audit.generated_at)}</span></span>
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-950/80 text-slate-400 text-xs uppercase tracking-wide">
                  <tr>
                    <th className="px-3 py-2 text-left">Feature</th>
                    <th className="px-3 py-2 text-left">Session</th>
                    <th className="px-3 py-2 text-left">Confidence</th>
                    <th className="px-3 py-2 text-left">Fanout</th>
                    <th className="px-3 py-2 text-left">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.suspects.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-3 py-4 text-center text-slate-400">
                        No suspect mappings for current thresholds.
                      </td>
                    </tr>
                  )}
                  {audit.suspects.map((row, idx) => (
                    <tr key={`${row.feature_id}-${row.session_id}-${idx}`} className="border-t border-slate-800 bg-slate-900/40">
                      <td className="px-3 py-2 text-slate-200 font-mono text-xs">{row.feature_id}</td>
                      <td className="px-3 py-2 text-slate-300 font-mono text-xs">{row.session_id}</td>
                      <td className="px-3 py-2 text-slate-200">{row.confidence}</td>
                      <td className="px-3 py-2 text-slate-200">{row.fanout_count}</td>
                      <td className="px-3 py-2 text-amber-300 text-xs">{row.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
        <h3 className="text-lg font-semibold text-slate-100">Projects Metadata</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {projects.map(project => (
            <div
              key={project.id}
              className={`rounded-lg border p-3 ${
                activeProject?.id === project.id
                  ? 'border-indigo-500/40 bg-indigo-500/10'
                  : 'border-slate-800 bg-slate-950/60'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-slate-100">{project.name}</p>
                {activeProject?.id === project.id ? (
                  <span className="text-[10px] px-2 py-1 rounded border border-indigo-500/30 text-indigo-300">Active</span>
                ) : (
                  <span className="text-[10px] px-2 py-1 rounded border border-slate-700 text-slate-400">Inactive</span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-1 font-mono break-all">{project.id}</p>
              <p className="text-xs text-slate-500 mt-2 break-all">{project.path}</p>
              <div className="mt-2 text-[11px] text-slate-400 space-y-1">
                <p>Plans: <span className="text-slate-200 font-mono">{project.planDocsPath}</span></p>
                <p>Progress: <span className="text-slate-200 font-mono">{project.progressPath}</span></p>
                <p>Sessions: <span className="text-slate-200 font-mono">{project.sessionsPath || '~/.claude/sessions'}</span></p>
              </div>
            </div>
          ))}
          {projects.length === 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
              No projects configured.
            </div>
          )}
        </div>
      </section>

      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-xs text-slate-500 flex items-start gap-2">
        <AlertTriangle size={14} className="mt-0.5 text-amber-400" />
        <p>
          Operations polling accelerates while jobs are running and slows when idle. Use the operation ID to trace long
          rebuild windows and capture audit output for mapping reviews.
        </p>
      </div>
        </>
      )}

      {activeTab === 'testing' && (
        <section className="space-y-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <p className="text-sm font-semibold text-slate-100">Testing Controls</p>
                <p className="text-xs text-slate-400 mt-1">
                  Trigger test ingestion plus mapping backfill, or run mapping backfill only.
                </p>
              </div>
              <label className="text-xs text-slate-400">
                Run Limit
                <input
                  type="number"
                  min={1}
                  max={5000}
                  value={mappingRunLimit}
                  onChange={(e) => setMappingRunLimit(Math.max(1, Math.min(5000, Number(e.target.value || 250))))}
                  className="ml-2 w-28 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1.5 text-sm text-slate-200"
                />
              </label>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                onClick={runTestIngestAndMapping}
                disabled={disableBackfillActions}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-700/80 border border-cyan-500/30 text-cyan-100 hover:bg-cyan-700 disabled:opacity-60"
              >
                <TestTube2 size={14} />
                Test Ingest + Mapping
              </button>
              <button
                onClick={runMappingBackfillOnly}
                disabled={disableBackfillActions}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-700/80 border border-indigo-500/30 text-indigo-100 hover:bg-indigo-700 disabled:opacity-60"
              >
                <Wrench size={14} />
                {mappingBackfillRunning ? 'Mapping Backfill Running...' : 'Mapping Backfill Only'}
              </button>
              <button
                onClick={() => {
                  const projectId = status?.projectId || activeProject?.id || '';
                  if (!projectId) {
                    setError('No active project selected for resolver detail refresh.');
                    return;
                  }
                  loadMappingResolverDetail(projectId, mappingRunLimit).catch((e) => {
                    setError(e instanceof Error ? e.message : 'Failed to refresh mapping resolver detail');
                  });
                }}
                disabled={busyAction !== null}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 disabled:opacity-60"
              >
                <RefreshCw size={14} />
                Refresh Resolver Detail
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
              <h3 className="text-lg font-semibold text-slate-100">Last Backfill Run</h3>
              {mappingBackfillRunning && trackedBackfillOperation && (
                <div className="space-y-3">
                  <p className="text-sm text-slate-300">
                    Status: <span className="text-slate-100">{trackedBackfillOperation.message || trackedBackfillOperation.phase || 'Running'}</span>
                  </p>
                  <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-cyan-500 transition-all duration-500"
                      style={{ width: `${Math.max(2, mappingBackfillPct)}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>{mappingBackfillPct}%</span>
                    <span className="font-mono">{trackedBackfillOperation.id}</span>
                  </div>
                  <p className="text-xs text-cyan-200/90 bg-cyan-500/10 border border-cyan-500/30 rounded-lg px-3 py-2">
                    This operation runs in the background. You can navigate away and it will continue until completion.
                  </p>
                </div>
              )}
              {!mappingBackfillRunning && !mappingBackfillDetail && (
                <p className="text-sm text-slate-400">No backfill has been run from this panel yet.</p>
              )}
              {!mappingBackfillRunning && mappingBackfillDetail && (
                <div className="space-y-2 text-sm">
                  <p className="text-slate-300">Project: <span className="font-mono">{mappingBackfillDetail.project_id}</span></p>
                  <p className="text-slate-300">Runs processed: <span className="text-slate-100">{mappingBackfillDetail.runs_processed}</span></p>
                  <p className="text-slate-300">Tests considered: <span className="text-slate-100">{mappingBackfillDetail.tests_considered}</span></p>
                  <p className="text-slate-300">Tests resolved: <span className="text-slate-100">{mappingBackfillDetail.tests_resolved}</span></p>
                  <p className="text-slate-300">Mappings stored: <span className="text-slate-100">{mappingBackfillDetail.mappings_stored}</span></p>
                  <p className="text-slate-300">Primary mappings: <span className="text-slate-100">{mappingBackfillDetail.primary_mappings}</span></p>
                  <p className="text-slate-300">Errors: <span className="text-slate-100">{mappingBackfillDetail.total_errors}</span></p>
                  {mappingBackfillDetail.errors.length > 0 && (
                    <details className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <summary className="cursor-pointer text-xs font-semibold text-slate-300">Resolver Errors</summary>
                      <ul className="mt-2 space-y-1 text-xs text-rose-300">
                        {mappingBackfillDetail.errors.slice(0, 20).map((item, index) => (
                          <li key={`${item}-${index}`}>{item}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
              <h3 className="text-lg font-semibold text-slate-100">Mapping Resolver Detail</h3>
              {!mappingResolverDetail && (
                <p className="text-sm text-slate-400">Loading mapping resolver detail...</p>
              )}
              {mappingResolverDetail && (
                <div className="space-y-2">
                  <p className="text-xs text-slate-400">
                    Generated: <span className="text-slate-200">{formatDate(mappingResolverDetail.generated_at)}</span>
                  </p>
                  <div className="overflow-x-auto rounded-lg border border-slate-800">
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-950/80 text-slate-400 text-xs uppercase tracking-wide">
                        <tr>
                          <th className="px-3 py-2 text-left">Run</th>
                          <th className="px-3 py-2 text-left">Results</th>
                          <th className="px-3 py-2 text-left">Mapped</th>
                          <th className="px-3 py-2 text-left">Unmapped</th>
                          <th className="px-3 py-2 text-left">Coverage</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mappingResolverDetail.runs.length === 0 && (
                          <tr>
                            <td colSpan={5} className="px-3 py-4 text-center text-slate-400">No runs found.</td>
                          </tr>
                        )}
                        {mappingResolverDetail.runs.map(row => (
                          <tr key={row.run_id} className="border-t border-slate-800 bg-slate-900/40">
                            <td className="px-3 py-2 text-slate-200 font-mono text-xs">{row.run_id}</td>
                            <td className="px-3 py-2 text-slate-200">{row.total_results}</td>
                            <td className="px-3 py-2 text-emerald-300">{row.mapped_primary_tests}</td>
                            <td className="px-3 py-2 text-amber-300">{row.unmapped_tests}</td>
                            <td className="px-3 py-2 text-slate-200">{Math.round((row.coverage || 0) * 100)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </section>
          </div>
        </section>
      )}

      {activeTab === 'integrations' && (
        <section className="space-y-4">
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)] gap-4">
            <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/25 bg-cyan-500/10 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-cyan-100">
                    <Database size={12} />
                    SkillMeat Pipeline
                  </div>
                  <h3 className="mt-3 text-lg font-semibold text-slate-100">Definition Sync + Observation Backfill</h3>
                  <p className="mt-1 text-sm text-slate-400">
                    Run the full SkillMeat refresh pipeline for the active project so recommendations and workflow intelligence surfaces have fresh cached data.
                  </p>
                </div>
                <button
                  onClick={() => { void runSkillMeatRefresh(); }}
                  disabled={busyAction !== null}
                  className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/35 bg-cyan-500/15 px-4 py-2 text-sm font-medium text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-60"
                >
                  <RefreshCw size={14} className={busyAction === 'skillmeat-refresh' ? 'animate-spin' : ''} />
                  {busyAction === 'skillmeat-refresh' ? 'Refreshing SkillMeat…' : 'Run SkillMeat Refresh'}
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Integration</p>
                  <p className="mt-2 text-lg font-semibold text-slate-100">{skillMeatConfig.enabled ? 'Enabled' : 'Disabled'}</p>
                  <p className="mt-2 text-xs text-slate-400 break-all">{skillMeatConfig.baseUrl || 'No base URL configured'}</p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Project Path</p>
                  <p className="mt-2 text-sm font-mono text-slate-100 break-all">{skillMeatConfig.projectId || 'Not configured'}</p>
                  <p className="mt-2 text-xs text-slate-400">Collection: {skillMeatConfig.collectionId || 'default'}</p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Feature Flags</p>
                  <p className="mt-2 text-sm text-slate-100">
                    Stack: {skillMeatConfig.featureFlags.stackRecommendationsEnabled ? 'on' : 'off'}
                  </p>
                  <p className="mt-1 text-sm text-slate-100">
                    Workflow: {skillMeatConfig.featureFlags.workflowAnalyticsEnabled ? 'on' : 'off'}
                  </p>
                  <p className="mt-1 text-sm text-slate-100">
                    Attribution: {skillMeatConfig.featureFlags.usageAttributionEnabled ? 'on' : 'off'}
                  </p>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
              <h3 className="text-lg font-semibold text-slate-100">Operator Notes</h3>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-sm text-slate-300">
                This button runs the same combined pipeline used after saving SkillMeat settings and during backend startup.
              </div>
              <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-sm text-amber-100">
                Use this after changing SkillMeat base URL, project mapping, auth mode, or collection scope when you want the new cache immediately.
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)] gap-4">
            <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/25 bg-indigo-500/10 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-indigo-100">
                    <Activity size={12} />
                    Telemetry Exporter
                  </div>
                  <h3 className="mt-3 text-lg font-semibold text-slate-100">SAM Queue Health + Manual Push</h3>
                  <p className="mt-1 text-sm text-slate-400">
                    Monitor outbound telemetry queue depth, export freshness, and recent errors. Use Push Now to force a batch outside the scheduled worker interval.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => { void loadTelemetryStatus(); }}
                    disabled={busyAction !== null}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 hover:border-slate-600 disabled:opacity-60"
                  >
                    <RefreshCw size={14} className={busyAction === 'telemetry-push' ? 'animate-spin' : ''} />
                    Refresh Status
                  </button>
                  <button
                    onClick={() => { void runTelemetryPushNow(); }}
                    disabled={busyAction !== null || !telemetryStatus?.enabled}
                    className="inline-flex items-center gap-2 rounded-lg border border-indigo-500/35 bg-indigo-500/15 px-4 py-2 text-sm font-medium text-indigo-100 hover:bg-indigo-500/20 disabled:opacity-60"
                  >
                    <Play size={14} />
                    {busyAction === 'telemetry-push' ? 'Pushing…' : 'Push Now'}
                  </button>
                </div>
              </div>

              {telemetryLoadError && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                  {telemetryLoadError}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Exporter State</p>
                  <p className="mt-2 text-lg font-semibold text-slate-100">
                    {telemetryStatus?.enabled ? 'Active' : telemetryStatus?.configured ? 'Paused' : 'Offline'}
                  </p>
                  <p className="mt-2 text-xs text-slate-400">
                    {telemetryStatus?.envLocked
                      ? 'Environment lock is forcing the exporter off.'
                      : telemetryStatus?.configured
                        ? 'Persisted setting controls the worker.'
                        : 'Backend config is incomplete.'}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">SAM Endpoint</p>
                  <p className="mt-2 text-sm font-mono text-slate-100 break-all">
                    {telemetryStatus?.samEndpointMasked || 'Not configured'}
                  </p>
                  <p className="mt-2 text-xs text-slate-400">Hostname only. Secrets never leave the backend.</p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Last Push</p>
                  <p className="mt-2 text-sm text-slate-100">
                    {telemetryStatus?.lastPushTimestamp ? formatDate(telemetryStatus.lastPushTimestamp) : 'Never'}
                  </p>
                  <p className="mt-2 text-xs text-slate-400">Successful or attempted batch completion time.</p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Last 24 Hours</p>
                  <p className="mt-2 text-lg font-semibold text-slate-100">{telemetryStatus?.eventsPushed24h ?? 0}</p>
                  <p className="mt-2 text-xs text-slate-400">Events exported to SAM in the trailing window.</p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                {[
                  ['Pending', telemetryStatus?.queueStats.pending ?? 0, 'text-slate-100'],
                  ['Failed', telemetryStatus?.queueStats.failed ?? 0, 'text-amber-300'],
                  ['Abandoned', telemetryStatus?.queueStats.abandoned ?? 0, 'text-rose-300'],
                  ['Synced', telemetryStatus?.queueStats.synced ?? 0, 'text-emerald-300'],
                ].map(([label, value, tone]) => (
                  <div key={label} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</p>
                    <p className={`mt-2 text-2xl font-semibold ${tone}`}>{value}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
              <h3 className="text-lg font-semibold text-slate-100">Exporter Notes</h3>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-sm text-slate-300">
                Push Now uses the same re-entrancy guard as the scheduled worker. If another export is already running, the backend rejects the request instead of overlapping batches.
              </div>
              <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-sm text-amber-100">
                Queue counts refresh every 10 seconds while this tab is open. Use Settings → Integrations → SkillMeat to enable or disable the exporter.
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-sm text-slate-300">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Recent Error</p>
                <p className="mt-2 text-sm text-slate-100">{telemetryStatus?.lastError || 'No recent exporter errors recorded.'}</p>
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-slate-100">Last Definition Sync</h3>
                <span className="text-xs text-slate-500">{formatDate(skillMeatSyncResult?.fetchedAt)}</span>
              </div>
              {!skillMeatSyncResult && (
                <p className="text-sm text-slate-400">No SkillMeat sync has been run from this panel yet.</p>
              )}
              {skillMeatSyncResult && (
                <div className="space-y-2 text-sm">
                  <p className="text-slate-300">Definitions synced: <span className="text-slate-100">{skillMeatSyncResult.totalDefinitions}</span></p>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(skillMeatSyncResult.countsByType || {}).map(([key, value]) => (
                      <div key={key} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{key.replace(/_/g, ' ')}</p>
                        <p className="mt-1 text-lg font-semibold text-slate-100">{value}</p>
                      </div>
                    ))}
                  </div>
                  {skillMeatSyncResult.warnings.length > 0 && (
                    <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-100">Warnings</p>
                      <ul className="mt-2 space-y-1 text-xs text-amber-100/90">
                        {skillMeatSyncResult.warnings.slice(0, 6).map((warning, index) => (
                          <li key={`${warning.section}-${index}`}>{warning.section}: {warning.message}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-slate-100">Last Observation Backfill</h3>
                <span className="text-xs text-slate-500">{formatDate(skillMeatBackfillResult?.generatedAt)}</span>
              </div>
              {!skillMeatBackfillResult && (
                <p className="text-sm text-slate-400">No SkillMeat backfill has been run from this panel yet.</p>
              )}
              {skillMeatBackfillResult && (
                <div className="space-y-2 text-sm">
                  <p className="text-slate-300">Sessions processed: <span className="text-slate-100">{skillMeatBackfillResult.sessionsProcessed}</span></p>
                  <p className="text-slate-300">Observations stored: <span className="text-slate-100">{skillMeatBackfillResult.observationsStored}</span></p>
                  <p className="text-slate-300">Resolved components: <span className="text-emerald-300">{skillMeatBackfillResult.resolvedComponents}</span></p>
                  <p className="text-slate-300">Unresolved components: <span className="text-amber-300">{skillMeatBackfillResult.unresolvedComponents}</span></p>
                  <p className="text-slate-300">Skipped sessions: <span className="text-slate-100">{skillMeatBackfillResult.skippedSessions}</span></p>
                  {skillMeatBackfillResult.warnings.length > 0 && (
                    <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-100">Warnings</p>
                      <ul className="mt-2 space-y-1 text-xs text-amber-100/90">
                        {skillMeatBackfillResult.warnings.slice(0, 6).map((warning, index) => (
                          <li key={`${warning.section}-${index}`}>{warning.section}: {warning.message}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </section>
          </div>
        </section>
      )}
    </div>
  );
};
