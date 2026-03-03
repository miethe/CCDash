import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  FolderKanban,
  Gauge,
  Play,
  RefreshCw,
  Server,
  TestTube2,
  Wrench,
} from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { CacheStatusResponse, LinkAuditResponse, SyncOperation } from '../types';

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
    default:
      return kind || 'Operation';
  }
}

type OpsTab = 'general' | 'testing';

interface MappingBackfillResponse {
  project_id: string;
  run_limit: number;
  runs_processed: number;
  mappings_stored: number;
  primary_mappings: number;
  total_errors: number;
  errors: string[];
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

export const OpsPanel: React.FC = () => {
  const { projects, activeProject, sessions, sessionTotal, documents, tasks, features } = useData();

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
  const [mappingResolverDetail, setMappingResolverDetail] = useState<MappingResolverDetailResponse | null>(null);

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
      const mapRes = await fetch(`${API_BASE}/tests/mappings/backfill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, run_limit: mappingRunLimit }),
      });
      if (!mapRes.ok) throw new Error(`Mapping backfill failed (${mapRes.status})`);
      const mapPayload = await mapRes.json() as MappingBackfillResponse;
      setMappingBackfillDetail(mapPayload);
      await loadMappingResolverDetail(projectId, mappingRunLimit);
      setNotice(
        `Mapping backfill processed ${Number(mapPayload.runs_processed || 0)} runs, `
        + `stored ${Number(mapPayload.mappings_stored || 0)} mappings `
        + `(${Number(mapPayload.primary_mappings || 0)} primary, `
        + `${Number(mapPayload.total_errors || 0)} errors).`
      );
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

      const mapRes = await fetch(`${API_BASE}/tests/mappings/backfill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, run_limit: mappingRunLimit }),
      });
      if (!mapRes.ok) throw new Error(`Mapping backfill failed (${mapRes.status})`);
      const mapPayload = await mapRes.json() as MappingBackfillResponse;
      setMappingBackfillDetail(mapPayload);
      await loadMappingResolverDetail(projectId, mappingRunLimit);

      setNotice(
        `Test sync complete (synced ${Number(syncPayload.stats?.synced || 0)} files). `
        + `Mapping backfill processed ${Number(mapPayload.runs_processed || 0)} runs, `
        + `stored ${Number(mapPayload.mappings_stored || 0)} mappings `
        + `(${Number(mapPayload.primary_mappings || 0)} primary, `
        + `${Number(mapPayload.total_errors || 0)} errors).`
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
  }, [status?.operations?.activeOperationCount, selectedOperationId]);

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

  const snapshotCards = [
    { label: 'Sessions (Loaded/Total)', value: `${sessions.length} / ${sessionTotal}`, icon: Activity },
    { label: 'Documents', value: String(documents.length), icon: FolderKanban },
    { label: 'Tasks', value: String(tasks.length), icon: CheckCircle2 },
    { label: 'Features', value: String(features.length), icon: Gauge },
  ];

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

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
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
                disabled={busyAction !== null}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-700/80 border border-cyan-500/30 text-cyan-100 hover:bg-cyan-700 disabled:opacity-60"
              >
                <TestTube2 size={14} />
                Test Ingest + Mapping
              </button>
              <button
                onClick={runMappingBackfillOnly}
                disabled={busyAction !== null}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-700/80 border border-indigo-500/30 text-indigo-100 hover:bg-indigo-700 disabled:opacity-60"
              >
                <Wrench size={14} />
                Mapping Backfill Only
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
              {!mappingBackfillDetail && (
                <p className="text-sm text-slate-400">No backfill has been run from this panel yet.</p>
              )}
              {mappingBackfillDetail && (
                <div className="space-y-2 text-sm">
                  <p className="text-slate-300">Project: <span className="font-mono">{mappingBackfillDetail.project_id}</span></p>
                  <p className="text-slate-300">Runs processed: <span className="text-slate-100">{mappingBackfillDetail.runs_processed}</span></p>
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
    </div>
  );
};
