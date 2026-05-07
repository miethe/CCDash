import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { GitBranch, Inbox, Loader2, RefreshCw, AlertCircle, PackageOpen, Clock } from 'lucide-react';

import { useData } from '../../contexts/DataContext';
import type { Feature, FeaturePlanningContext, FeatureSummaryItem, ProjectPlanningSummary } from '../../types';
import {
  getCachedProjectPlanningSummary,
  getFeaturePlanningContext,
  getProjectPlanningSummary,
  PlanningApiError,
  prefetchFeaturePlanningContext,
} from '../../services/planning';
import { getLaunchCapabilities } from '../../services/execution';
import { projectPlanningTopic, useLiveInvalidation } from '../../services/live';
import {
  planningArtifactsHref,
  removePlanningRouteFeatureModalSearch,
  resolvePlanningRouteFeatureModalState,
  setPlanningRouteFeatureModalSearch,
  usePlanningFilter,
  type PlanningFeatureModalTab,
  type PlanningStatusBucket,
  type PlanningSignal,
} from '../../services/planningRoutes';
import { featureMatchesBucket, featureMatchesSignal } from '../../services/planning';
import type { LiveConnectionStatus } from '../../services/live';
import { ProjectBoardFeatureModal } from '../ProjectBoard';
import { PlanningSummaryPanel } from './PlanningSummaryPanel';
import type { ArtifactDrillDownType } from './ArtifactDrillDownPage';
import { PlanningGraphPanel } from './PlanningGraphPanel';
import { PlanningMetricsStrip } from './PlanningMetricsStrip';
import { PlanningArtifactChipRow } from './PlanningArtifactChipRow';
import { TrackerIntakePanel, type NodeClickResolution } from './TrackerIntakePanel';
import {
  PlanningQuickViewPanel,
  usePlanningQuickView,
} from './PlanningQuickViewPanel';
import { PlanningDensityToggle } from './PlanningRouteLayout';
import { PlanningTriagePanel } from './PlanningTriagePanel';
import { PlanningAgentRosterPanel } from './PlanningAgentRosterPanel';
import { PlanningAgentSessionBoard } from './PlanningAgentSessionBoard';
import {
  Chip,
  EffectiveStatusChips,
  MismatchBadge,
  Panel,
  PlanningNodeTypeIcon,
} from './primitives';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatGeneratedAt(value?: string): string {
  if (!value) return 'n/a';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function getFeatureBaseSlug(featureId: string): string {
  const segments = featureId.split('/');
  return segments[segments.length - 1] || featureId;
}

function createModalFeatureFromSummary(item: FeatureSummaryItem): Feature {
  return {
    id: item.featureId,
    name: item.featureName || item.featureId,
    status: item.rawStatus || item.effectiveStatus || 'unknown',
    totalTasks: 0,
    completedTasks: 0,
    category: '',
    tags: [],
    updatedAt: '',
    linkedDocs: [],
    phases: [],
    relatedFeatures: [],
  };
}

export function resolvePlanningModalFeature(
  featureId: string,
  features: Feature[],
  summary: ProjectPlanningSummary,
): Feature | null {
  const requestedBase = getFeatureBaseSlug(featureId);
  const fullFeature =
    features.find((feature) => feature.id === featureId) ||
    features.find((feature) => getFeatureBaseSlug(feature.id) === requestedBase);
  if (fullFeature) return fullFeature;

  const summaryFeature =
    summary.featureSummaries.find((feature) => feature.featureId === featureId) ||
    summary.featureSummaries.find((feature) => getFeatureBaseSlug(feature.featureId) === requestedBase);
  return summaryFeature ? createModalFeatureFromSummary(summaryFeature) : null;
}

// ── Hero header ───────────────────────────────────────────────────────────────

/**
 * Derives lightweight corpus stats from the planning summary.
 * contextPerPhase and tokensSaved are not yet in the API payload — they are
 * computed heuristically here.
 * TODO(T2-001): add contextPerPhase + tokensSaved to GET /api/agent/planning/summary
 * once the backend query surface exposes them.
 */
function deriveCorpusStats(summary: import('../../types').ProjectPlanningSummary) {
  const { nodeCountsByType } = summary;

  // Total context docs (context + tracker types serve as ctx anchors)
  const ctxCount = (nodeCountsByType.context ?? 0) + (nodeCountsByType.tracker ?? 0);

  // Phase count: count progress nodes (one per phase)
  const phaseCount = nodeCountsByType.progress ?? 0;

  // ctx/phase ratio — show as integer if clean, else one decimal place
  const ctxPerPhase = phaseCount > 0 ? ctxCount / phaseCount : 0;

  // Token-saved heuristic: each context doc anchored to a phase saves
  // an estimated 3KB vs full-file reads (~15KB). We cap the display at 95%.
  // TODO: replace with real telemetry once the exporter tracks this.
  const tokensSavedPct = Math.min(
    95,
    Math.round((ctxCount / Math.max(phaseCount, 1)) * 4.2),
  );

  // Spark history: build a 12-point series from the feature health counts.
  // Real historical data is not yet available; we synthesise a plausible
  // monotone growth curve ending at the current totals.
  // TODO: replace with actual per-day aggregate when the backend exposes it.
  const total = summary.totalFeatureCount;
  const active = summary.activeFeatureCount;
  const sparkHistory = Array.from({ length: 12 }, (_, i) => {
    const t = i / 11;
    return Math.round(total * (0.3 + 0.7 * t) + active * Math.sin(t * Math.PI) * 0.5);
  });
  sparkHistory[11] = total; // pin last point to current total

  return { ctxCount, phaseCount, ctxPerPhase, tokensSavedPct, sparkHistory };
}

/** CLS-safe animated spark: the polyline is drawn on mount via stroke-dasharray trick. */
function AnimatedSpark({
  data,
  color = 'var(--brand)',
  width = 120,
  height = 28,
}: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  const polyRef = useRef<SVGPolylineElement>(null);
  const safeData = data.length > 1 ? data : [0, ...data];
  const max = Math.max(...safeData, 1);
  const stepX = width / (safeData.length - 1);
  const points = safeData
    .map(
      (v, i) =>
        `${(i * stepX).toFixed(1)},${(height - (v / max) * (height - 4) - 2).toFixed(1)}`,
    )
    .join(' ');

  // Animate dash on mount
  useEffect(() => {
    const el = polyRef.current;
    if (!el) return;
    const len = el.getTotalLength?.() ?? 200;
    el.style.strokeDasharray = String(len);
    el.style.strokeDashoffset = String(len);
    // rAF to ensure layout has computed the length before animating
    const id = requestAnimationFrame(() => {
      el.style.transition = 'stroke-dashoffset 900ms cubic-bezier(0.4,0,0.2,1)';
      el.style.strokeDashoffset = '0';
    });
    return () => cancelAnimationFrame(id);
  }, [points]);

  return (
    <svg width={width} height={height} aria-hidden="true" style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id="spark-grad" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor={color} stopOpacity="0.4" />
          <stop offset="100%" stopColor={color} stopOpacity="1" />
        </linearGradient>
      </defs>
      <polyline
        ref={polyRef}
        points={points}
        fill="none"
        stroke="url(#spark-grad)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function HeroHeader({
  summary,
}: {
  summary: import('../../types').ProjectPlanningSummary;
}) {
  const { ctxCount, phaseCount, ctxPerPhase, tokensSavedPct, sparkHistory } =
    deriveCorpusStats(summary);

  const todayLabel = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

  const ctxPhaseLabel =
    phaseCount > 0
      ? `${ctxCount} ctx · ${phaseCount} phases · ${ctxPerPhase.toFixed(1)} ctx/phase`
      : `${ctxCount} ctx docs`;

  return (
    <div
      className="flex flex-wrap items-end justify-between gap-6 border-b pb-5"
      style={{ borderColor: 'var(--line-1)' }}
      data-testid="planning-hero-header"
    >
      {/* Left: title + subtitle */}
      <div>
        <div
          className="planning-caps mb-2.5"
          style={{ fontSize: 10.5, color: 'var(--ink-3)' }}
        >
          ccdash · planning &mdash; ai-native sdlc &middot; {summary.projectName || 'active project'}
        </div>
        <h1
          className="planning-serif m-0 italic"
          style={{
            fontSize: 'clamp(32px, 4vw, 48px)',
            fontWeight: 400,
            letterSpacing: '-0.025em',
            lineHeight: 1.05,
            color: 'var(--ink-0)',
            fontVariationSettings: '"opsz" 60',
          }}
        >
          The Planning Deck.
        </h1>
        <p
          className="m-0 mt-2"
          style={{ fontSize: 13.5, color: 'var(--ink-2)', maxWidth: 580, lineHeight: 1.55 }}
        >
          Eight artifact types. Specialized agents. One surface to orchestrate — from idea
          through retrospective, with token-disciplined delegation at every step.
        </p>
      </div>

      {/* Right: corpus stats */}
      <div
        className="flex shrink-0 flex-col items-end gap-2"
        aria-label="Corpus statistics"
      >
        {/* Date + ctx/phase */}
        <div
          className="planning-mono planning-tnum"
          style={{ fontSize: 11, color: 'var(--ink-3)' }}
        >
          {todayLabel} &middot; {ctxPhaseLabel}
        </div>

        {/* Spark + tokens-saved */}
        <div className="flex items-center gap-3">
          <AnimatedSpark data={sparkHistory} color="var(--brand)" width={120} height={28} />
          <span
            className="planning-mono planning-tnum"
            style={{ fontSize: 11, color: 'var(--ok)', fontWeight: 500 }}
          >
            +{tokensSavedPct}% tokens saved
          </span>
        </div>
      </div>
    </div>
  );
}

function LiveStatusDot({ status }: { status: LiveConnectionStatus }) {
  const configs: Record<LiveConnectionStatus, { color: string; label: string }> = {
    open: { color: 'var(--ok)', label: 'Live' },
    connecting: { color: 'var(--warn)', label: 'Connecting' },
    backoff: { color: 'var(--warn)', label: 'Reconnecting' },
    paused: { color: 'var(--ink-2)', label: 'Paused' },
    closed: { color: 'var(--err)', label: 'Closed' },
    idle: { color: 'var(--ink-3)', label: 'Idle' },
  };
  const cfg = configs[status] ?? configs.idle;
  return (
    <Chip className="border-[color:var(--line-1)] bg-[color:var(--bg-2)] text-[color:var(--ink-1)]" title={`Live updates: ${cfg.label}`}>
      <span className="planning-dot" style={{ background: cfg.color }} />
      {cfg.label}
    </Chip>
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

// ── Planning feature row ──────────────────────────────────────────────────────

function PlanningFeatureRow({
  feature,
  onClick,
  onPrefetch,
}: {
  feature: FeatureSummaryItem;
  onClick: () => void;
  onPrefetch?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={onPrefetch}
      onFocus={onPrefetch}
      data-testid={`planning-feature-row-${feature.featureId}`}
      className="planning-density-row planning-row flex w-full items-start gap-2.5 rounded-lg border border-[color:var(--line-1)] bg-[color:var(--bg-2)] px-3 py-2.5 text-left transition-all hover:border-[color:var(--brand)] hover:bg-[color:var(--bg-3)] focus:outline-none"
    >
      <span className="mt-0.5 shrink-0 text-[color:var(--brand)]">
        <PlanningNodeTypeIcon type="implementation_plan" size={13} />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <span className="truncate font-medium leading-snug text-[color:var(--ink-0)]" style={{ fontSize: 'var(--row-font)' }}>
            {feature.featureName}
          </span>
          <div className="flex shrink-0 items-center gap-1.5">
            <EffectiveStatusChips
              rawStatus={feature.rawStatus}
              effectiveStatus={feature.effectiveStatus}
              isMismatch={feature.isMismatch}
            />
          </div>
        </div>
        {feature.isMismatch && (
          <MismatchBadge compact state={feature.mismatchState} reason="" />
        )}
        <div className="flex items-center gap-2 text-[color:var(--ink-2)]" style={{ fontSize: 'var(--row-meta-font)' }}>
          <span className="planning-mono">{feature.featureId}</span>
          {feature.phaseCount > 0 && (
            <span>
              {feature.phaseCount} phase{feature.phaseCount !== 1 ? 's' : ''}
            </span>
          )}
          {feature.hasBlockedPhases && (
            <span style={{ color: 'var(--warn)' }}>{feature.blockedPhaseCount} blocked</span>
          )}
        </div>
      </div>
    </button>
  );
}

// ── Column empty state ────────────────────────────────────────────────────────

function ColumnEmptyState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[color:var(--line-1)] py-8 text-center">
      <Inbox size={18} className="text-[color:var(--ink-3)]" />
      <p className="text-xs text-[color:var(--ink-2)]">{label}</p>
    </div>
  );
}

// ── Active plans column ───────────────────────────────────────────────────────

/**
 * Features whose effectiveStatus is "in_progress" or "in-progress".
 * Reads effectiveStatus directly from FeatureSummaryItem — castPlanningStatus
 * is not needed here because the field is already a plain string on this type.
 */
export function ActivePlansColumn({
  features,
  onSelectFeature,
  onPrefetchFeature,
  activeBucket,
  activeSignal,
}: {
  features: FeatureSummaryItem[];
  onSelectFeature: (featureId: string) => void;
  onPrefetchFeature?: (featureId: string) => void;
  activeBucket?: PlanningStatusBucket | null;
  activeSignal?: PlanningSignal | null;
}) {
  // Base: in-progress features
  const base = features.filter(
    (f) => f.effectiveStatus === 'in_progress' || f.effectiveStatus === 'in-progress',
  );
  // P13-003: Apply route filter if set
  const active = (activeBucket || activeSignal)
    ? base.filter((f) => {
        if (activeBucket && !featureMatchesBucket(f, activeBucket)) return false;
        if (activeSignal && !featureMatchesSignal(f, activeSignal)) return false;
        return true;
      })
    : base;

  return (
    <Panel
      data-testid="active-plans-column"
      className="space-y-3 p-5"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[color:var(--ink-0)]">Active Plans</h2>
        <span className="rounded-full px-2 py-0.5 text-[11px] font-medium text-[color:var(--brand)]" style={{ background: 'color-mix(in oklab, var(--brand) 16%, transparent)' }}>
          {active.length}
        </span>
      </div>
      {active.length === 0 ? (
        <ColumnEmptyState label="No active implementation plans" />
      ) : (
        <div className="space-y-1.5">
          {active.map((f) => (
            <PlanningFeatureRow
              key={f.featureId}
              feature={f}
              onClick={() => onSelectFeature(f.featureId)}
              onPrefetch={() => onPrefetchFeature?.(f.featureId)}
            />
          ))}
        </div>
      )}
    </Panel>
  );
}

// ── Planned features column ───────────────────────────────────────────────────

/**
 * Features whose effectiveStatus is "draft" or "approved" (not yet started).
 */
export function PlannedFeaturesColumn({
  features,
  onSelectFeature,
  onPrefetchFeature,
  activeBucket,
  activeSignal,
}: {
  features: FeatureSummaryItem[];
  onSelectFeature: (featureId: string) => void;
  onPrefetchFeature?: (featureId: string) => void;
  activeBucket?: PlanningStatusBucket | null;
  activeSignal?: PlanningSignal | null;
}) {
  // Base: draft or approved features
  const base = features.filter(
    (f) => f.effectiveStatus === 'draft' || f.effectiveStatus === 'approved',
  );
  // P13-003: Apply route filter if set
  const planned = (activeBucket || activeSignal)
    ? base.filter((f) => {
        if (activeBucket && !featureMatchesBucket(f, activeBucket)) return false;
        if (activeSignal && !featureMatchesSignal(f, activeSignal)) return false;
        return true;
      })
    : base;

  return (
    <Panel
      data-testid="planned-features-column"
      className="space-y-3 p-5"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[color:var(--ink-0)]">Planned Features</h2>
        <span className="rounded-full px-2 py-0.5 text-[11px] font-medium text-[color:var(--ink-2)]" style={{ background: 'color-mix(in oklab, var(--ink-2) 14%, transparent)' }}>
          {planned.length}
        </span>
      </div>
      {planned.length === 0 ? (
        <ColumnEmptyState label="No draft or approved features" />
      ) : (
        <div className="space-y-1.5">
          {planned.map((f) => (
            <PlanningFeatureRow
              key={f.featureId}
              feature={f}
              onClick={() => onSelectFeature(f.featureId)}
              onPrefetch={() => onPrefetchFeature?.(f.featureId)}
            />
          ))}
        </div>
      )}
    </Panel>
  );
}

// ── P14-002: Quick view content components ───────────────────────────────────

/**
 * Rendered inside PlanningQuickViewPanel when the clicked row has a featureSlug.
 * Loads FeaturePlanningContext and renders a lightweight summary —
 * reusing the same data already fetched/cached by prefetchFeaturePlanningContext.
 */
function FeatureQuickViewContent({
  featureSlug,
  projectId,
}: {
  featureSlug: string;
  projectId: string | null;
}) {
  const [ctx, setCtx] = useState<FeaturePlanningContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getFeaturePlanningContext(featureSlug, { projectId: projectId ?? undefined })
      .then((data) => {
        setCtx(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load feature context.');
        setLoading(false);
      });
  }, [featureSlug, projectId]);

  if (loading) {
    return (
      <div className="animate-pulse space-y-3">
        <div className="h-4 rounded bg-slate-700/40 w-3/5" />
        <div className="h-3 rounded bg-slate-700/30 w-4/5" />
        <div className="h-3 rounded bg-slate-700/30 w-2/5" />
        <div className="h-px bg-slate-700/30 my-3" />
        <div className="space-y-2">
          <div className="h-8 rounded bg-slate-700/30" />
          <div className="h-8 rounded bg-slate-700/30" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-xs text-danger">{error}</p>
    );
  }

  if (!ctx) return null;

  const statusLabel = ctx.effectiveStatus || ctx.rawStatus || 'unknown';
  const mismatch = ctx.mismatchState && ctx.mismatchState !== 'aligned' ? ctx.mismatchState : null;

  return (
    <div className="space-y-4 text-sm">
      {/* Feature identity */}
      <div>
        <p className="text-xs text-muted-foreground/60 mb-1 uppercase tracking-wide font-semibold">Feature</p>
        <p className="font-medium text-panel-foreground truncate">{ctx.featureName || ctx.featureId}</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-700/60 text-slate-300">
            {statusLabel}
          </span>
          {mismatch && (
            <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-amber-600/20 text-amber-400">
              {mismatch}
            </span>
          )}
          {ctx.readyToPromote && (
            <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-emerald-600/20 text-emerald-400">
              ready to promote
            </span>
          )}
          {ctx.isStale && (
            <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-rose-600/20 text-rose-400">
              stale
            </span>
          )}
        </div>
      </div>

      {/* Phases */}
      {ctx.phases && ctx.phases.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground/60 mb-1.5 uppercase tracking-wide font-semibold">
            Phases ({ctx.phases.length})
          </p>
          <div className="space-y-1">
            {ctx.phases.slice(0, 6).map((ph) => (
              <div
                key={ph.phaseToken || String(ph.phaseNumber)}
                className="flex items-center gap-2 rounded border border-panel-border/40 bg-slate-800/40 px-2.5 py-1.5"
              >
                <span className="planning-mono text-[10px] text-muted-foreground/60 shrink-0 tabular-nums">
                  P{ph.phaseNumber}
                </span>
                <span className="flex-1 min-w-0 truncate text-xs text-panel-foreground">
                  {ph.phaseTitle || ph.phaseToken || `Phase ${ph.phaseNumber}`}
                </span>
                <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-700/60 text-slate-300 shrink-0">
                  {ph.effectiveStatus || ph.rawStatus || 'unknown'}
                </span>
              </div>
            ))}
            {ctx.phases.length > 6 && (
              <p className="text-[10px] text-muted-foreground/50 pl-1">
                +{ctx.phases.length - 6} more phases
              </p>
            )}
          </div>
        </div>
      )}

      {/* Artifact refs */}
      {((ctx.specs?.length ?? 0) + (ctx.prds?.length ?? 0) + (ctx.plans?.length ?? 0)) > 0 && (
        <div>
          <p className="text-xs text-muted-foreground/60 mb-1.5 uppercase tracking-wide font-semibold">
            Artifacts
          </p>
          <div className="flex flex-wrap gap-1.5">
            {ctx.specs?.map((ref) => (
              <span key={ref.artifactId} className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-700/40 text-slate-300">
                spec
              </span>
            ))}
            {ctx.prds?.map((ref) => (
              <span key={ref.artifactId} className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-700/40 text-slate-300">
                prd
              </span>
            ))}
            {ctx.plans?.map((ref) => (
              <span key={ref.artifactId} className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-700/40 text-slate-300">
                plan
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Open questions */}
      {ctx.openQuestions && ctx.openQuestions.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground/60 mb-1.5 uppercase tracking-wide font-semibold">
            Open Questions ({ctx.openQuestions.length})
          </p>
          <ul className="space-y-1">
            {ctx.openQuestions.slice(0, 3).map((q, i) => (
              <li key={i} className="text-xs text-muted-foreground truncate" title={q.question}>
                <span className="mr-1 text-muted-foreground/40">·</span>
                {q.question}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Rendered inside PlanningQuickViewPanel when the clicked row is doc-only
 * (no featureSlug). Shows a minimal doc summary while the DocumentModal is
 * opened by the parent for full content viewing.
 */
function DocQuickViewContent({
  node,
}: {
  node: import('../../types').PlanningNode;
}) {
  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="text-xs text-muted-foreground/60 mb-1 uppercase tracking-wide font-semibold">Document</p>
        <p className="font-medium text-panel-foreground">{node.title || node.type}</p>
        {node.path && (
          <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground/50" title={node.path}>
            {node.path.length > 72 ? `…${node.path.slice(-69)}` : node.path}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {node.rawStatus && (
          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-700/60 text-slate-300">
            {node.rawStatus}
          </span>
        )}
        {node.effectiveStatus && node.effectiveStatus !== node.rawStatus && (
          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-amber-600/20 text-amber-400">
            {node.effectiveStatus}
          </span>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground/60 italic">
        Open full document modal for content and linked artifacts.
      </p>
    </div>
  );
}

// ── Page shell (ready state) ──────────────────────────────────────────────────

function PlanningShell({
  summary,
  liveStatus,
  onSelectFeature,
  onPrefetchFeature,
  onDrillDown,
  onRefresh,
  onNodeQuickView,
  activeStatusBucket,
  activeSignal,
  onStatusBucketClick,
  onSignalClick,
}: {
  summary: ProjectPlanningSummary;
  liveStatus: LiveConnectionStatus;
  onSelectFeature: (featureId: string) => void;
  onPrefetchFeature?: (featureId: string) => void;
  onDrillDown: (type: ArtifactDrillDownType) => void;
  onRefresh?: () => void;
  /** P14-002: Row-click handler for tracker/intake panel rows. */
  onNodeQuickView?: (resolution: NodeClickResolution, triggerEl: HTMLElement | null) => void;
  /** P13-003: Active status bucket filter from URL. */
  activeStatusBucket?: PlanningStatusBucket | null;
  /** P13-003: Active health signal filter from URL. */
  activeSignal?: PlanningSignal | null;
  /** P13-003: Called when a status bucket tile is clicked. */
  onStatusBucketClick?: (bucket: PlanningStatusBucket) => void;
  /** P13-003: Called when a health signal pill is clicked. */
  onSignalClick?: (signal: PlanningSignal) => void;
}) {
  return (
    <div className="max-w-screen-2xl space-y-6 px-1 py-2">
      {/* T2-001: Hero header — Fraunces italic h1 + corpus stats */}
      <Panel className="p-5">
        {/* Top bar: breadcrumb + live controls */}
        <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <GitBranch size={14} style={{ color: 'var(--brand)' }} />
            <span
              className="planning-caps"
              style={{ fontSize: 10, color: 'var(--ink-3)' }}
            >
              Planning Control Plane
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {summary.generatedAt && (
              <Chip className="border-[color:var(--line-1)] bg-[color:var(--bg-2)] text-[color:var(--ink-2)]">
                <Clock size={11} />
                {formatGeneratedAt(summary.generatedAt)}
              </Chip>
            )}
            <LiveStatusDot status={liveStatus} />
            <PlanningDensityToggle />
          </div>
        </div>

        <HeroHeader summary={summary} />
      </Panel>

      {/* T2-002 / P13-003: Metrics strip — clickable status bucket + signal filters */}
      <PlanningMetricsStrip
        summary={summary}
        activeStatusBucket={activeStatusBucket}
        activeSignal={activeSignal}
        onStatusBucketClick={onStatusBucketClick}
        onSignalClick={onSignalClick}
      />

      {/* T2-003: Artifact composition chip row — 8 artifact types with counts */}
      <Panel className="px-5 py-3" data-testid="planning-artifact-chip-row-section">
        <PlanningArtifactChipRow nodeCountsByType={summary.nodeCountsByType} />
      </Panel>

      {/* T3-003: Two-up layout — Triage (1.3fr) + Agent Roster (1fr); stacks below 1280px */}
      <div
        className="grid grid-cols-1 gap-4 xl:grid-cols-[1.3fr_1fr]"
        data-testid="planning-triage-roster-grid"
      >
        <PlanningTriagePanel
          summary={summary}
          onSelectFeature={onSelectFeature}
          onPrefetchFeature={onPrefetchFeature}
          onRefresh={onRefresh}
        />
        <PlanningAgentRosterPanel />
      </div>

      {/* PCP-302: Planning Summary */}
      <div data-testid="planning-summary-section">
        <PlanningSummaryPanel
          summary={summary}
          onSelectFeature={onSelectFeature}
          onPrefetchFeature={onPrefetchFeature}
          onDrillDown={onDrillDown}
          activeStatusBucket={activeStatusBucket}
          activeSignal={activeSignal}
        />
      </div>

      {/* PCP-702: Active Plans + Planned Features columns */}
      <div
        data-testid="planning-feature-columns"
        className="grid grid-cols-1 gap-4 lg:grid-cols-2"
      >
        <ActivePlansColumn
          features={summary.featureSummaries}
          onSelectFeature={onSelectFeature}
          onPrefetchFeature={onPrefetchFeature}
          activeBucket={activeStatusBucket}
          activeSignal={activeSignal}
        />
        <PlannedFeaturesColumn
          features={summary.featureSummaries}
          onSelectFeature={onSelectFeature}
          onPrefetchFeature={onPrefetchFeature}
          activeBucket={activeStatusBucket}
          activeSignal={activeSignal}
        />
      </div>

      {/* PCP-303: Planning Graph Panel */}
      <Panel data-testid="planning-graph-section" className="p-5">
        <PlanningGraphPanel
          projectId={summary.projectId ?? null}
          featureSummaries={summary.featureSummaries}
          onSelectFeature={onSelectFeature}
          onPrefetchFeature={onPrefetchFeature}
          activeStatusBucket={activeStatusBucket}
          activeSignal={activeSignal}
        />
      </Panel>
      <Panel data-testid="planning-tracker-section" className="p-5">
        <TrackerIntakePanel
          projectId={summary.projectId ?? null}
          summary={summary}
          onSelectFeature={onSelectFeature}
          onNodeQuickView={onNodeQuickView}
          activeStatusBucket={activeStatusBucket}
          activeSignal={activeSignal}
        />
      </Panel>

      {/* PASB-201: Agent Session Board */}
      <div data-testid="planning-agent-session-board-section">
        <PlanningAgentSessionBoard />
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
  const { activeProject, features = [] } = useData();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [fetchState, setFetchState] = useState<FetchState>({ phase: 'idle' });
  const [planningEnabled, setPlanningEnabled] = useState<boolean>(true);
  const selectedFeatureModal = useMemo(
    () => resolvePlanningRouteFeatureModalState(searchParams),
    [searchParams],
  );

  // P13-003: Filter state from URL search params
  const { filter, setStatusBucket, setSignal } = usePlanningFilter();

  // Check capability flag on mount. Defaults to true; silently falls back to
  // true if the capabilities endpoint is unreachable so existing deploys are
  // unaffected.
  useEffect(() => {
    getLaunchCapabilities()
      .then((caps) => setPlanningEnabled(caps.planningEnabled ?? true))
      .catch(() => setPlanningEnabled(true));
  }, []);

  const loadSummary = useCallback(async (options: { forceRefresh?: boolean } = {}) => {
    if (!activeProject?.id) {
      setFetchState({ phase: 'idle' });
      return;
    }
    const projectId = activeProject.id;
    const warmSummary = options.forceRefresh ? null : getCachedProjectPlanningSummary(projectId);
    if (warmSummary) {
      setFetchState({ phase: 'ready', summary: warmSummary });
    } else {
      setFetchState({ phase: 'loading' });
    }
    try {
      const summary = await getProjectPlanningSummary(projectId, {
        forceRefresh: options.forceRefresh,
        onRevalidated: (revalidatedSummary) => {
          setFetchState((current) => {
            if (current.phase !== 'ready') return current;
            if (revalidatedSummary.projectId && revalidatedSummary.projectId !== projectId) return current;
            return { phase: 'ready', summary: revalidatedSummary };
          });
        },
      });
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
    onInvalidate: () => loadSummary({ forceRefresh: true }),
  });

  const openFeatureModal = useCallback((featureId: string, tab: PlanningFeatureModalTab = 'overview') => {
    navigate(`/planning${setPlanningRouteFeatureModalSearch(searchParams, featureId, tab)}`);
  }, [navigate, searchParams]);

  const prefetchFeature = useCallback((featureId: string) => {
    if (!activeProject?.id) return;
    void prefetchFeaturePlanningContext(featureId, { projectId: activeProject.id });
  }, [activeProject?.id]);

  const closeFeatureModal = useCallback(() => {
    navigate(`/planning${removePlanningRouteFeatureModalSearch(searchParams)}`, { replace: true });
  }, [navigate, searchParams]);

  const selectedFeature = useMemo(() => {
    if (!selectedFeatureModal || fetchState.phase !== 'ready') return null;
    return resolvePlanningModalFeature(selectedFeatureModal.featureId, features, fetchState.summary);
  }, [features, fetchState, selectedFeatureModal]);

  // P14-002: Quick view panel state — hosted here so PlanningShell can pass
  // the handler down to TrackerIntakePanel without owning the panel itself.
  const quickView = usePlanningQuickView();
  // Stores the last node that triggered the quick view, so we can render the
  // correct content variant (feature vs. doc) inside the panel.
  const [quickViewNode, setQuickViewNode] = useState<import('../../types').PlanningNode | null>(null);

  const handleNodeQuickView = useCallback(
    (resolution: NodeClickResolution, triggerEl: HTMLElement | null) => {
      setQuickViewNode(resolution.node);
      const title =
        resolution.kind === 'feature'
          ? resolution.featureSlug
          : resolution.node.title || resolution.node.type;
      quickView.openPanel(title, triggerEl);
    },
    [quickView],
  );

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
    <>
      <PlanningShell
        summary={summary}
        liveStatus={liveStatus}
        onSelectFeature={openFeatureModal}
        onPrefetchFeature={prefetchFeature}
        onDrillDown={(type) =>
          navigate(planningArtifactsHref(type))
        }
        onRefresh={() => void loadSummary()}
        onNodeQuickView={handleNodeQuickView}
        activeStatusBucket={filter.statusBucket}
        activeSignal={filter.signal}
        onStatusBucketClick={setStatusBucket}
        onSignalClick={setSignal}
      />
      {selectedFeature && selectedFeatureModal ? (
        <ProjectBoardFeatureModal
          feature={selectedFeature}
          initialTab={selectedFeatureModal.tab}
          onClose={closeFeatureModal}
          launchedFromPlanning={true}
        />
      ) : null}
      {/* P14-002: Tracker/intake row quick view panel */}
      <PlanningQuickViewPanel
        open={quickView.open}
        onClose={quickView.closePanel}
        title={quickView.title}
      >
        {quickViewNode &&
          (quickViewNode.featureSlug ? (
            <FeatureQuickViewContent
              featureSlug={quickViewNode.featureSlug}
              projectId={activeProject.id ?? null}
            />
          ) : (
            <DocQuickViewContent node={quickViewNode} />
          ))}
      </PlanningQuickViewPanel>
    </>
  );
}
