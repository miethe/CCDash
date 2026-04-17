import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GitBranch, Loader2, RefreshCw, AlertCircle, PackageOpen, Clock } from 'lucide-react';

import { useData } from '../../contexts/DataContext';
import type { ProjectPlanningSummary } from '../../types';
import { getProjectPlanningSummary, PlanningApiError } from '../../services/planning';
import { getLaunchCapabilities } from '../../services/execution';
import { projectPlanningTopic, useLiveInvalidation } from '../../services/live';
import type { LiveConnectionStatus } from '../../services/live';
import { PlanningSummaryPanel } from './PlanningSummaryPanel';
import { PlanningGraphPanel } from './PlanningGraphPanel';
import { TrackerIntakePanel } from './TrackerIntakePanel';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatGeneratedAt(value?: string): string {
  if (!value) return 'n/a';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function LiveStatusDot({ status }: { status: LiveConnectionStatus }) {
  const configs: Record<LiveConnectionStatus, { color: string; label: string }> = {
    open:       { color: 'bg-emerald-400', label: 'Live' },
    connecting: { color: 'bg-amber-400 animate-pulse', label: 'Connecting' },
    backoff:    { color: 'bg-amber-500 animate-pulse', label: 'Reconnecting' },
    paused:     { color: 'bg-slate-400', label: 'Paused' },
    closed:     { color: 'bg-rose-400', label: 'Closed' },
    idle:       { color: 'bg-slate-500', label: 'Idle' },
  };
  const cfg = configs[status] ?? configs.idle;
  return (
    <span className="flex items-center gap-1.5" title={`Live updates: ${cfg.label}`}>
      <span className={`inline-block h-2 w-2 rounded-full ${cfg.color}`} />
      <span className="text-xs text-muted-foreground">{cfg.label}</span>
    </span>
  );
}

// ── Loading state ─────────────────────────────────────────────────────────────

function LoadingShell() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="flex flex-col items-center gap-4 rounded-xl border border-panel-border bg-surface-elevated px-10 py-8 shadow-sm">
        <Loader2 size={28} className="animate-spin text-info" />
        <p className="text-sm text-muted-foreground">Loading planning overview…</p>
      </div>
    </div>
  );
}

// ── Error state ───────────────────────────────────────────────────────────────

function ErrorShell({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="flex max-w-md flex-col items-center gap-4 rounded-xl border border-danger/40 bg-danger/5 px-10 py-8 shadow-sm">
        <AlertCircle size={28} className="text-danger" />
        <p className="text-center text-sm text-danger-foreground">{message}</p>
        <button
          onClick={onRetry}
          className="flex items-center gap-2 rounded-lg border border-danger/40 bg-danger/10 px-4 py-2 text-xs font-medium text-danger-foreground transition-colors hover:bg-danger/20"
        >
          <RefreshCw size={13} />
          Retry
        </button>
      </div>
    </div>
  );
}

// ── Disabled state ────────────────────────────────────────────────────────────

function DisabledShell() {
  return (
    <div className="flex items-center justify-center py-24" data-testid="planning-disabled-shell">
      <div className="flex max-w-md flex-col items-center gap-4 rounded-xl border border-panel-border bg-surface-elevated/60 px-10 py-10 text-center">
        <AlertCircle size={28} className="text-muted-foreground/60" />
        <div>
          <p className="text-sm font-medium text-muted-foreground">
            Planning control plane is disabled
          </p>
          <p className="mt-1.5 text-xs text-muted-foreground/70">
            Set <code className="rounded bg-surface-base px-1 py-0.5 font-mono text-xs">CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true</code> to enable planning surfaces.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyShell({ hasProject }: { hasProject: boolean }) {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="flex max-w-md flex-col items-center gap-4 rounded-xl border border-dashed border-panel-border bg-surface-elevated/40 px-10 py-10 text-center">
        <PackageOpen size={32} className="text-muted-foreground/50" />
        <div>
          <p className="text-sm font-medium text-muted-foreground">
            {hasProject ? 'No planning artifacts found' : 'No project selected'}
          </p>
          <p className="mt-1.5 text-xs text-muted-foreground/70">
            {hasProject
              ? 'Planning artifacts — PRDs, implementation plans, progress files — will appear here once they are discovered and synced by the backend.'
              : 'Select a project from the sidebar to view its planning overview.'}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Page shell (ready state) ──────────────────────────────────────────────────

function PlanningShell({
  summary,
  liveStatus,
  onSelectFeature,
}: {
  summary: ProjectPlanningSummary;
  liveStatus: LiveConnectionStatus;
  onSelectFeature: (featureId: string) => void;
}) {
  return (
    <div className="max-w-screen-2xl space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <GitBranch size={22} className="shrink-0 text-info" />
          <div>
            <h1 className="text-xl font-semibold text-panel-foreground">Planning</h1>
            <p className="text-sm text-muted-foreground">
              {summary.projectName || 'Unknown project'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {summary.generatedAt && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock size={12} />
              {formatGeneratedAt(summary.generatedAt)}
            </span>
          )}
          <LiveStatusDot status={liveStatus} />
        </div>
      </div>

      {/* PCP-302: Planning Summary */}
      <div data-testid="planning-summary-section">
        <PlanningSummaryPanel summary={summary} onSelectFeature={onSelectFeature} />
      </div>

      {/* PCP-303: Planning Graph Panel */}
      <div data-testid="planning-graph-section" className="rounded-xl border border-panel-border bg-surface-elevated p-5">
        <PlanningGraphPanel
          projectId={summary.projectId ?? null}
          onSelectFeature={onSelectFeature}
        />
      </div>
      <div data-testid="planning-tracker-section" className="rounded-xl border border-panel-border bg-surface-elevated p-5">
        <TrackerIntakePanel
          projectId={summary.projectId ?? null}
          summary={summary}
          onSelectFeature={onSelectFeature}
        />
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type FetchState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; summary: ProjectPlanningSummary };

export default function PlanningHomePage() {
  const { activeProject } = useData();
  const navigate = useNavigate();
  const [fetchState, setFetchState] = useState<FetchState>({ phase: 'idle' });
  const [planningEnabled, setPlanningEnabled] = useState<boolean>(true);

  // Check capability flag on mount. Defaults to true; silently falls back to
  // true if the capabilities endpoint is unreachable so existing deploys are
  // unaffected.
  useEffect(() => {
    getLaunchCapabilities()
      .then((caps) => setPlanningEnabled(caps.planningEnabled ?? true))
      .catch(() => setPlanningEnabled(true));
  }, []);

  const loadSummary = useCallback(async () => {
    if (!activeProject?.id) {
      setFetchState({ phase: 'idle' });
      return;
    }
    setFetchState({ phase: 'loading' });
    try {
      const summary = await getProjectPlanningSummary(activeProject.id);
      setFetchState({ phase: 'ready', summary });
    } catch (err) {
      const message =
        err instanceof PlanningApiError
          ? `Planning API error (${err.status}): ${err.message}`
          : err instanceof Error
            ? err.message
            : 'An unexpected error occurred while loading planning data.';
      setFetchState({ phase: 'error', message });
    }
  }, [activeProject?.id]);

  // Initial load + re-fetch when active project changes.
  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  // Live invalidation subscription.
  const liveTopics = activeProject?.id ? [projectPlanningTopic(activeProject.id)] : [];
  const liveStatus = useLiveInvalidation({
    topics: liveTopics,
    enabled: liveTopics.length > 0,
    onInvalidate: () => loadSummary(),
  });

  // Render
  if (!planningEnabled) {
    return (
      <div className="max-w-screen-2xl space-y-6">
        <DisabledShell />
      </div>
    );
  }

  if (!activeProject) {
    return (
      <div className="max-w-screen-2xl space-y-6">
        <EmptyShell hasProject={false} />
      </div>
    );
  }

  if (fetchState.phase === 'loading' || fetchState.phase === 'idle') {
    return (
      <div className="max-w-screen-2xl space-y-6">
        <LoadingShell />
      </div>
    );
  }

  if (fetchState.phase === 'error') {
    return (
      <div className="max-w-screen-2xl space-y-6">
        <ErrorShell message={fetchState.message} onRetry={() => void loadSummary()} />
      </div>
    );
  }

  const { summary } = fetchState;
  if (summary.totalFeatureCount === 0) {
    return (
      <div className="max-w-screen-2xl space-y-6">
        <EmptyShell hasProject={true} />
      </div>
    );
  }

  return (
    <PlanningShell
      summary={summary}
      liveStatus={liveStatus}
      onSelectFeature={(featureId) => navigate(`/planning/feature/${featureId}`)}
    />
  );
}
