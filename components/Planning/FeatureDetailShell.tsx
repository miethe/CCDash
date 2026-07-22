/**
 * P5-006: FeatureDetailShell — tabbed full-page feature detail route.
 *
 * Rendered at /planning/feature/:featureId.
 *
 * Tab discipline:
 *   - Overview is the ONLY eager tab. Plan/Tasks/Blockers/Decisions/Next reuse
 *     the same usePlanningFeatureContextQuery payload (AC-3: shared cache key,
 *     no double-fetch).
 *   - All other tabs are conditionally mounted only on first activation (lazy
 *     mount — do NOT use hidden-attribute with eager fetch).
 *
 * AC-4: Sessions + Logs tabs delegate to PlanningFeatureAgentLane which uses
 *   usePlanningFeatureSessionBoardQuery (cursor-paginated, never bulk-loads
 *   transcripts).
 *
 * AC-6: Research + Council tabs gate on useLaunchCapabilitiesQuery caps
 *   (meatyWikiEnabled / arcEnabled). Disabled cap → clean empty-state, never
 *   an error/crash.
 *
 * Resilience: every absent context field renders a defined fallback.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  ArrowLeft,
  BarChart3,
  BookOpen,
  Bot,
  ChevronRight,
  FileSearch,
  GitBranch,
  Layers,
  List,
  Loader2,
  Network,
  ScrollText,
  Shield,
  Telescope,
  Zap,
} from 'lucide-react';

import { useData } from '../../contexts/DataContext';
import { usePlanningFeatureContextQuery } from '../../services/queries/planning';
import { useLaunchCapabilitiesQuery } from '../../services/queries/capabilities';
import { useArtifactRankingsQuery } from '../../services/queries/analytics';
import {
  FEATURE_DETAIL_TABS,
  type FeatureDetailTab,
  resolveFeatureDetailTab,
} from '../../services/planningRoutes';
import { cn } from '../../lib/utils';
import { PlanningFeatureAgentLane } from './PlanningFeatureAgentLane';
import { buildLineageTiles, deriveFeatureMeta } from './PlanningNodeDetail';
import {
  StatusPill,
  Dot,
} from './primitives/PhaseZeroPrimitives';
import type {
  FeaturePlanningContext,
  PhaseContextItem,
} from '../../types';
import { apiRequestJson } from '../../services/apiClient';

const FeatureAnalyticsPanel = React.lazy(() => import('./FeatureAnalyticsPanel'));

// ── Tab metadata ──────────────────────────────────────────────────────────────

interface TabMeta {
  id: FeatureDetailTab;
  label: string;
  icon: React.ElementType;
  /** True → skip mount until first activation (lazy tab). */
  lazy: boolean;
}

const TAB_META: TabMeta[] = [
  { id: 'overview',   label: 'Overview',   icon: Network,     lazy: false },
  { id: 'plan',       label: 'Plan',       icon: GitBranch,   lazy: false },
  { id: 'tasks',      label: 'Tasks',      icon: List,        lazy: false },
  { id: 'sessions',   label: 'Sessions',   icon: Bot,         lazy: true  },
  { id: 'analytics',  label: 'Analytics',  icon: BarChart3,   lazy: true  },
  { id: 'artifacts',  label: 'Artifacts',  icon: Layers,      lazy: true  },
  { id: 'research',   label: 'Research',   icon: Telescope,   lazy: true  },
  { id: 'council',    label: 'Council',    icon: Shield,      lazy: true  },
  { id: 'logs',       label: 'Logs',       icon: ScrollText,  lazy: true  },
  { id: 'decisions',  label: 'Decisions',  icon: FileSearch,  lazy: false },
  { id: 'blockers',   label: 'Blockers',   icon: AlertCircle, lazy: false },
  { id: 'next',       label: 'Next',       icon: Zap,         lazy: false },
];

// ── Shared-context tabs (reuse Overview payload, no extra fetch) ──────────────
const SHARED_CONTEXT_TABS = new Set<FeatureDetailTab>([
  'overview', 'plan', 'tasks', 'blockers', 'decisions', 'next',
]);

// ── Empty-state helper ────────────────────────────────────────────────────────

function EmptyState({ icon: Icon, title, body }: {
  icon: React.ElementType;
  title: string;
  body?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Icon size={32} className="text-muted-foreground/40" aria-hidden="true" />
      <p className="text-sm font-medium text-muted-foreground">{title}</p>
      {body && <p className="max-w-xs text-xs text-muted-foreground/70">{body}</p>}
    </div>
  );
}

function LazyTabFallback({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground" role="status">
      <Loader2 size={16} className="animate-spin" aria-hidden="true" />
      <span className="text-xs">Loading {label}...</span>
    </div>
  );
}

// ── Status dot helper ─────────────────────────────────────────────────────────

function statusToDotTone(status: string): string {
  if (status === 'completed') return 'var(--ok)';
  if (status === 'blocked') return 'var(--err)';
  if (status === 'in-progress' || status === 'in_progress') return 'var(--brand)';
  return 'var(--ink-4)';
}

// ── Overview tab ──────────────────────────────────────────────────────────────

function OverviewTab({ ctx }: { ctx: FeaturePlanningContext }) {
  const tiles = buildLineageTiles(ctx);
  const meta = deriveFeatureMeta(ctx);

  const status = ctx.effectiveStatus ?? ctx.rawStatus ?? null;
  const tokenTotal = ctx.totalTokens ?? null;

  return (
    <div className="space-y-6">
      {/* Identity strip */}
      <div className="flex flex-wrap items-center gap-3">
        {status && <StatusPill status={status} />}
        {meta.category && (
          <span className="rounded-sm bg-surface-1 px-2 py-0.5 text-xs text-muted-foreground">
            {meta.category}
          </span>
        )}
        {meta.slug && (
          <span className="font-mono text-xs text-muted-foreground">{meta.slug}</span>
        )}
        {ctx.complexity && (
          <span className="text-xs text-muted-foreground">Complexity: {ctx.complexity}</span>
        )}
      </div>

      {/* Lineage tiles */}
      {tiles.length > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-7">
          {tiles.map(tile => (
            <div
              key={tile.kind}
              className="flex flex-col items-center gap-1 rounded-lg border border-border/40 bg-surface-1 p-3 text-center"
              style={{ borderTopColor: tile.color, borderTopWidth: 2 }}
            >
              <span className="text-xs font-medium text-muted-foreground">{tile.label}</span>
              <span className="text-lg font-bold tabular-nums">{tile.count}</span>
              {tile.status && (
                <span
                  className="inline-block rounded-full"
                  style={{
                    width: 6,
                    height: 6,
                    backgroundColor: statusToDotTone(tile.status),
                  }}
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Token telemetry */}
      {tokenTotal != null && (
        <div className="flex items-center gap-2 rounded-md border border-border/30 bg-surface-0 px-3 py-2">
          <span className="text-xs text-muted-foreground">Total tokens</span>
          <span className="ml-auto font-mono text-xs tabular-nums">
            {tokenTotal.toLocaleString()}
          </span>
        </div>
      )}

      {/* Tags */}
      {ctx.tags && ctx.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {ctx.tags.map(tag => (
            <span
              key={tag}
              className="rounded-sm border border-border/40 bg-surface-1 px-2 py-0.5 text-xs text-muted-foreground"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Open questions */}
      {ctx.openQuestions && ctx.openQuestions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Open Questions ({ctx.openQuestions.length})
          </p>
          <ul className="space-y-1">
            {ctx.openQuestions.slice(0, 5).map(q => (
              <li key={q.oqId} className="flex items-start gap-2 text-xs text-muted-foreground">
                <ChevronRight size={12} className="mt-0.5 shrink-0 text-warn" />
                <span>{q.question}</span>
              </li>
            ))}
            {ctx.openQuestions.length > 5 && (
              <li className="text-xs text-muted-foreground/60">
                +{ctx.openQuestions.length - 5} more
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Plan tab ──────────────────────────────────────────────────────────────────

function PlanTab({ ctx }: { ctx: FeaturePlanningContext }) {
  const phases: PhaseContextItem[] = ctx.phases ?? [];

  if (phases.length === 0) {
    return <EmptyState icon={GitBranch} title="No phases found" body="This feature has no plan phases recorded." />;
  }

  return (
    <div className="space-y-3">
      {phases.map((phase, i) => {
        const num = phase.phaseNumber ?? i + 1;
        const title = phase.phaseTitle ?? `Phase ${num}`;
        const status = phase.effectiveStatus ?? phase.rawStatus ?? 'pending';
        const pct = phase.totalTasks > 0
          ? Math.round((phase.completedTasks / phase.totalTasks) * 100)
          : null;

        return (
          <div
            key={phase.phaseId}
            className="rounded-lg border border-border/40 bg-surface-1 p-4"
          >
            <div className="flex items-center gap-3">
              <span className="min-w-[2rem] font-mono text-xs text-muted-foreground">
                P{num}
              </span>
              <span className="flex-1 text-sm font-medium">{title}</span>
              <StatusPill status={status} />
              {pct != null && (
                <span className="font-mono text-xs tabular-nums text-muted-foreground">
                  {pct}%
                </span>
              )}
            </div>
            {phase.isMismatch && (
              <p className="mt-1 text-xs text-warn">Status mismatch detected</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Tasks tab ─────────────────────────────────────────────────────────────────
// Tasks are nested inside batches inside phases.

function TasksTab({ ctx }: { ctx: FeaturePlanningContext }) {
  const phases: PhaseContextItem[] = ctx.phases ?? [];
  const allBatches = phases.flatMap(p => p.batches ?? []);

  // Render a summary table from the phase-level task counts
  if (phases.length === 0) {
    return <EmptyState icon={List} title="No tasks found" body="This feature has no tracked tasks." />;
  }

  return (
    <div className="space-y-4">
      {phases.map((phase, i) => {
        const num = phase.phaseNumber ?? i + 1;
        const title = phase.phaseTitle ?? `Phase ${num}`;
        const batches = phase.batches ?? [];

        return (
          <div key={phase.phaseId} className="space-y-1">
            <p className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <span className="font-mono">P{num}</span>
              <span>{title}</span>
              <span className="ml-auto tabular-nums">
                {phase.completedTasks}/{phase.totalTasks}
              </span>
            </p>
            {batches.map(batch => (
              <div
                key={batch.batchId}
                className="rounded-md border border-border/30 bg-surface-1 px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <Dot
                    tone={statusToDotTone(batch.readinessState)}
                    style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0 }}
                  />
                  <span className="flex-1 truncate font-mono text-xs">{batch.batchId}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {batch.taskIds.length} task{batch.taskIds.length !== 1 ? 's' : ''}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {batch.readinessState}
                  </span>
                </div>
                {batch.assignedAgents.length > 0 && (
                  <p className="mt-1 truncate text-xs text-muted-foreground/60">
                    {batch.assignedAgents.join(', ')}
                  </p>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ── Blockers tab ──────────────────────────────────────────────────────────────
// FeaturePlanningContext has blockedBatchIds — derive blocker list from phases.

function BlockersTab({ ctx }: { ctx: FeaturePlanningContext }) {
  const blockedIds = ctx.blockedBatchIds ?? [];
  const phases = ctx.phases ?? [];
  const blockedBatches = phases.flatMap(p =>
    (p.batches ?? []).filter(b => blockedIds.includes(b.batchId))
  );

  if (blockedBatches.length === 0 && blockedIds.length === 0) {
    return <EmptyState icon={AlertCircle} title="No blockers" body="No active blockers for this feature." />;
  }

  return (
    <div className="space-y-2">
      {blockedIds.length > 0 && blockedBatches.length === 0 && (
        <div className="space-y-1">
          {blockedIds.map(id => (
            <div key={id} className="flex items-start gap-3 rounded-md border border-err/20 bg-err/5 px-3 py-3">
              <AlertCircle size={14} className="mt-0.5 shrink-0 text-err" />
              <span className="flex-1 font-mono text-xs text-muted-foreground">{id}</span>
            </div>
          ))}
        </div>
      )}
      {blockedBatches.map(batch => (
        <div key={batch.batchId} className="flex items-start gap-3 rounded-md border border-err/20 bg-err/5 px-3 py-3">
          <AlertCircle size={14} className="mt-0.5 shrink-0 text-err" />
          <div className="flex-1 space-y-1">
            <span className="font-mono text-xs text-muted-foreground">{batch.batchId}</span>
            {batch.taskIds.length > 0 && (
              <p className="text-xs text-muted-foreground/60">
                {batch.taskIds.length} task{batch.taskIds.length !== 1 ? 's' : ''} blocked
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Decisions tab ─────────────────────────────────────────────────────────────
// No dedicated decisions field in FeaturePlanningContext — show linked artifacts
// that are classified as context (CTX) nodes, which typically contain decisions.

function DecisionsTab({ ctx }: { ctx: FeaturePlanningContext }) {
  const ctxNodes = ctx.ctxs ?? [];
  const ctxGraphNodes = (ctx.graph?.nodes ?? []).filter(n => n.type === 'context');
  const allCtx = ctxNodes.length > 0 ? ctxNodes : ctxGraphNodes;

  if (allCtx.length === 0) {
    return <EmptyState icon={FileSearch} title="No decisions recorded" body="Context documents containing decisions will appear here." />;
  }

  return (
    <div className="space-y-2">
      {allCtx.map((item, i) => {
        const path = (item as { filePath?: string; canonicalPath?: string; path?: string }).filePath
          ?? (item as { filePath?: string; canonicalPath?: string; path?: string }).canonicalPath
          ?? (item as { filePath?: string; canonicalPath?: string; path?: string }).path
          ?? `Context ${i + 1}`;
        const label = path.split('/').pop() ?? path;
        const status = (item as { effectiveStatus?: string; status?: string }).effectiveStatus
          ?? (item as { effectiveStatus?: string; status?: string }).status
          ?? null;

        return (
          <div key={i} className="rounded-md border border-border/40 bg-surface-1 px-3 py-3">
            <div className="flex items-center gap-2">
              <span className="flex-1 truncate text-xs font-medium">{label}</span>
              {status && <StatusPill status={status} size="sm" />}
            </div>
            <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground/60">{path}</p>
          </div>
        );
      })}
    </div>
  );
}

// ── Next tab ──────────────────────────────────────────────────────────────────
// Show readyToPromote signal + phases ready to run next.

function NextTab({ ctx }: { ctx: FeaturePlanningContext }) {
  const phases = ctx.phases ?? [];
  const readyPhases = phases.filter(p => p.effectiveStatus === 'ready' || p.effectiveStatus === 'approved');
  const readyToPromote = ctx.readyToPromote ?? false;

  return (
    <div className="space-y-4">
      {readyToPromote && (
        <div className="flex items-center gap-2 rounded-md border border-ok/30 bg-ok/5 px-3 py-3">
          <Zap size={14} className="text-ok" />
          <span className="text-xs font-medium text-ok">Feature is ready to promote</span>
        </div>
      )}

      {readyPhases.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Ready to run
          </p>
          {readyPhases.map((phase, i) => (
            <div
              key={phase.phaseId}
              className="flex items-center gap-3 rounded-md border border-border/40 bg-surface-1 px-3 py-2"
            >
              <span className="font-mono text-xs text-muted-foreground">
                P{phase.phaseNumber ?? i + 1}
              </span>
              <span className="flex-1 text-xs">{phase.phaseTitle}</span>
              <StatusPill status={phase.effectiveStatus ?? phase.rawStatus} />
            </div>
          ))}
        </div>
      ) : (
        !readyToPromote && (
          <EmptyState icon={Zap} title="No next-run preview" body="No phases are ready to run at this time." />
        )
      )}

      {/* Spikes awaiting resolution */}
      {ctx.spikes && ctx.spikes.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Spikes ({ctx.spikes.length})
          </p>
          {ctx.spikes.map(spike => (
            <div key={spike.spikeId} className="flex items-center gap-2 rounded-md border border-border/30 bg-surface-1 px-3 py-2">
              <span className="flex-1 truncate text-xs">{spike.title}</span>
              <StatusPill status={spike.status} size="sm" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Sessions tab ──────────────────────────────────────────────────────────────
// Delegates entirely to PlanningFeatureAgentLane which uses cursor-paginated
// usePlanningFeatureSessionBoardQuery and never bulk-loads transcripts (AC-4).

function SessionsTab({ featureId }: { featureId: string }) {
  return (
    <PlanningFeatureAgentLane featureId={featureId} />
  );
}

// ── Logs tab — same discipline as Sessions ────────────────────────────────────
// Reuses PlanningFeatureAgentLane (cursor-paginated, no bulk transcript loads).

function LogsTab({ featureId }: { featureId: string }) {
  return (
    <PlanningFeatureAgentLane featureId={featureId} />
  );
}

// ── Artifacts tab (P5-007) ────────────────────────────────────────────────────

function ArtifactsTab({ projectId }: { projectId: string; featureId: string }) {
  const { data, isLoading, isError } = useArtifactRankingsQuery({
    projectId,
    params: { limit: 50 },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
        <Loader2 size={16} className="animate-spin" />
        <span className="text-xs">Loading artifacts…</span>
      </div>
    );
  }

  if (isError || !data) {
    return <EmptyState icon={Layers} title="Artifacts unavailable" body="Could not load artifact rankings." />;
  }

  const rows = data.rows ?? [];

  if (rows.length === 0) {
    return <EmptyState icon={Layers} title="No artifacts" body="No ranked artifacts found for this project." />;
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {rows.length} artifact{rows.length !== 1 ? 's' : ''} ranked
        {data.period ? ` · ${data.period}` : ''}
      </p>
      <div className="space-y-1">
        {rows.map((row, i) => (
          <div
            key={row.artifactId ?? row.id ?? i}
            className="flex items-center gap-3 rounded-md border border-border/30 bg-surface-1 px-3 py-2"
          >
            <span className="font-mono text-xs text-muted-foreground/60">#{i + 1}</span>
            <span className="flex-1 truncate text-xs font-medium">
              {row.artifactName ?? row.displayName ?? row.artifactId ?? `Artifact ${i + 1}`}
            </span>
            {row.artifactType && (
              <span className="shrink-0 rounded-sm bg-surface-0 px-1.5 py-0.5 text-xs text-muted-foreground">
                {row.artifactType}
              </span>
            )}
            {typeof row.sessionCount === 'number' && (
              <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
                {row.sessionCount.toLocaleString()} sessions
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Research tab (AC-6) ───────────────────────────────────────────────────────

interface ResearchItem {
  title?: string;
  url?: string;
  summary?: string;
}

interface ResearchResponse {
  enabled: boolean;
  items: ResearchItem[];
}

function ResearchTab({ featureId, enabled }: { featureId: string; enabled: boolean }) {
  const [data, setData] = React.useState<ResearchResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [activated, setActivated] = React.useState(false);

  React.useEffect(() => {
    if (!enabled || activated) return;
    setActivated(true);
    setLoading(true);

    apiRequestJson<ResearchResponse>(
      `/api/integrations/meatywiki/research?feature_id=${encodeURIComponent(featureId)}`,
    )
      .then(setData)
      .catch(() => setData({ enabled: false, items: [] }))
      .finally(() => setLoading(false));
  }, [enabled, featureId, activated]);

  if (!enabled) {
    return (
      <EmptyState
        icon={Telescope}
        title="Research integration not configured"
        body="Enable MeatyWiki integration to surface research results here."
      />
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
        <Loader2 size={16} className="animate-spin" />
        <span className="text-xs">Loading research…</span>
      </div>
    );
  }

  if (!data?.enabled || data.items.length === 0) {
    return (
      <EmptyState
        icon={Telescope}
        title={data?.enabled === false ? 'Research integration not configured' : 'No research results'}
        body={data?.enabled === false
          ? 'Research integration is not configured on the backend.'
          : 'No research results found for this feature.'}
      />
    );
  }

  return (
    <div className="space-y-3">
      {data.items.map((item, i) => (
        <div key={i} className="rounded-lg border border-border/40 bg-surface-1 p-4">
          {item.title && <p className="text-sm font-medium">{item.title}</p>}
          {item.summary && <p className="mt-1 text-xs text-muted-foreground">{item.summary}</p>}
          {item.url && (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 block truncate font-mono text-xs text-brand hover:underline"
            >
              {item.url}
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Council tab (AC-6) ────────────────────────────────────────────────────────

interface CouncilItem {
  title?: string;
  recommendation?: string;
  confidence?: number;
}

interface CouncilResponse {
  enabled: boolean;
  items: CouncilItem[];
}

function CouncilTab({ featureId, enabled }: { featureId: string; enabled: boolean }) {
  const [data, setData] = React.useState<CouncilResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [activated, setActivated] = React.useState(false);

  React.useEffect(() => {
    if (!enabled || activated) return;
    setActivated(true);
    setLoading(true);

    apiRequestJson<CouncilResponse>(
      `/api/agent/features/${encodeURIComponent(featureId)}/council`,
    )
      .then(setData)
      .catch(() => setData({ enabled: false, items: [] }))
      .finally(() => setLoading(false));
  }, [enabled, featureId, activated]);

  if (!enabled) {
    return (
      <EmptyState
        icon={Shield}
        title="Council integration not configured"
        body="Enable ARC (Agent Review Council) integration to surface council results here."
      />
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
        <Loader2 size={16} className="animate-spin" />
        <span className="text-xs">Loading council results…</span>
      </div>
    );
  }

  if (!data?.enabled || data.items.length === 0) {
    return (
      <EmptyState
        icon={Shield}
        title={data?.enabled === false ? 'Council integration not configured' : 'No council results'}
        body={data?.enabled === false
          ? 'Council integration is not configured on the backend.'
          : 'No council results found for this feature.'}
      />
    );
  }

  return (
    <div className="space-y-3">
      {data.items.map((item, i) => (
        <div key={i} className="rounded-lg border border-border/40 bg-surface-1 p-4">
          {item.title && <p className="text-sm font-medium">{item.title}</p>}
          {item.recommendation && (
            <p className="mt-1 text-xs text-muted-foreground">{item.recommendation}</p>
          )}
          {typeof item.confidence === 'number' && (
            <span className="mt-2 block font-mono text-xs text-muted-foreground">
              Confidence: {(item.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

function TabBar({
  activeTab,
  onTabChange,
}: {
  activeTab: FeatureDetailTab;
  onTabChange: (tab: FeatureDetailTab) => void;
}) {
  return (
    <nav
      role="tablist"
      aria-label="Feature detail sections"
      className="flex shrink-0 gap-0.5 overflow-x-auto border-b border-border/50 pb-0 scrollbar-none"
    >
      {TAB_META.map(({ id, label, icon: Icon }) => {
        const isActive = id === activeTab;
        return (
          <button
            key={id}
            id={`tab-${id}`}
            role="tab"
            aria-selected={isActive}
            aria-controls={`tab-panel-${id}`}
            onClick={() => onTabChange(id)}
            className={cn(
              'flex shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-xs font-medium transition-colors',
              isActive
                ? 'border-brand text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon size={12} aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </nav>
  );
}

// ── Main shell ────────────────────────────────────────────────────────────────

export function FeatureDetailShell() {
  const { featureId } = useParams<{ featureId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { activeProject } = useData();
  const projectId = activeProject?.id ?? '';

  // Resolve active tab from URL ?tab= param
  const activeTab = resolveFeatureDetailTab(searchParams);

  // Track which lazy tabs have been activated (mounted at least once)
  const [activatedTabs, setActivatedTabs] = useState<Set<FeatureDetailTab>>(
    () => new Set<FeatureDetailTab>(['overview']),
  );

  // Activate lazy tab on first visit
  useEffect(() => {
    const tabMeta = TAB_META.find(t => t.id === activeTab);
    if (tabMeta?.lazy && !activatedTabs.has(activeTab)) {
      setActivatedTabs(prev => {
        const next = new Set(prev);
        next.add(activeTab);
        return next;
      });
    }
  }, [activeTab, activatedTabs]);

  const handleTabChange = useCallback(
    (tab: FeatureDetailTab) => {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev);
        if (tab === 'overview') {
          next.delete('tab');
        } else {
          next.set('tab', tab);
        }
        return next;
      });
    },
    [setSearchParams],
  );

  // AC-3: shared cache key — same usePlanningFeatureContextQuery keyed by
  // planningKeys.featureContext(projectId, featureId) as in PlanningNodeDetail.
  // Opening either the modal or this route hits the same TQ cache entry.
  const {
    data: ctx,
    isLoading,
    isError,
    error,
  } = usePlanningFeatureContextQuery({
    projectId: projectId || null,
    featureId: featureId ?? null,
  });

  // Capability flags for Research + Council gating (AC-6)
  const { data: caps } = useLaunchCapabilitiesQuery();
  const meatyWikiEnabled = caps?.meatyWikiEnabled ?? false;
  const arcEnabled = caps?.arcEnabled ?? false;

  if (!featureId) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-24 text-muted-foreground">
        <AlertCircle size={24} aria-hidden="true" />
        <p className="text-sm">No feature ID provided.</p>
      </div>
    );
  }

  // ── Header ──────────────────────────────────────────────────────────────────

  const featureTitle = ctx?.featureName ?? ctx?.slug ?? ctx?.featureId ?? featureId;
  const status = ctx?.effectiveStatus ?? ctx?.rawStatus ?? null;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Page header */}
      <div className="shrink-0 border-b border-border/50 bg-surface-0 px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            aria-label="Go back"
          >
            <ArrowLeft size={14} aria-hidden="true" />
          </button>
          <span className="text-muted-foreground/40">/</span>
          <BookOpen size={14} className="text-muted-foreground" aria-hidden="true" />
          <h1 className="truncate text-sm font-semibold">{featureTitle}</h1>
          {status && <StatusPill status={status} />}
        </div>
      </div>

      {/* Tab bar */}
      <div className="shrink-0 bg-surface-0 px-4">
        <TabBar activeTab={activeTab} onTabChange={handleTabChange} />
      </div>

      {/* Tab content */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {/* Loading state for shared-context tabs */}
        {isLoading && SHARED_CONTEXT_TABS.has(activeTab) && (
          <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
            <Loader2 size={16} className="animate-spin" aria-hidden="true" />
            <span className="text-xs">Loading feature context…</span>
          </div>
        )}

        {/* Error state */}
        {isError && SHARED_CONTEXT_TABS.has(activeTab) && (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <AlertCircle size={24} className="text-err" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">
              {error instanceof Error ? error.message : 'Failed to load feature context.'}
            </p>
          </div>
        )}

        {/* ── Shared-context tabs (reuse ctx, no extra fetch) ── */}
        {!isLoading && !isError && ctx && (
          <>
            {activeTab === 'overview' && (
              <div role="tabpanel" id="tab-panel-overview" aria-labelledby="tab-overview">
                <OverviewTab ctx={ctx} />
              </div>
            )}
            {activeTab === 'plan' && (
              <div role="tabpanel" id="tab-panel-plan" aria-labelledby="tab-plan">
                <PlanTab ctx={ctx} />
              </div>
            )}
            {activeTab === 'tasks' && (
              <div role="tabpanel" id="tab-panel-tasks" aria-labelledby="tab-tasks">
                <TasksTab ctx={ctx} />
              </div>
            )}
            {activeTab === 'blockers' && (
              <div role="tabpanel" id="tab-panel-blockers" aria-labelledby="tab-blockers">
                <BlockersTab ctx={ctx} />
              </div>
            )}
            {activeTab === 'decisions' && (
              <div role="tabpanel" id="tab-panel-decisions" aria-labelledby="tab-decisions">
                <DecisionsTab ctx={ctx} />
              </div>
            )}
            {activeTab === 'next' && (
              <div role="tabpanel" id="tab-panel-next" aria-labelledby="tab-next">
                <NextTab ctx={ctx} />
              </div>
            )}
          </>
        )}

        {/* Fallback: ctx missing but not loading/error */}
        {!isLoading && !isError && !ctx && SHARED_CONTEXT_TABS.has(activeTab) && (
          <EmptyState icon={Network} title="Feature context unavailable" body="No data found for this feature." />
        )}

        {/* ── Lazy tabs (conditional mount — first activation only) ── */}

        {/* Sessions (AC-4: cursor-paginated via PlanningFeatureAgentLane) */}
        {activatedTabs.has('sessions') && (
          <div
            role="tabpanel"
            id="tab-panel-sessions"
            aria-labelledby="tab-sessions"
            hidden={activeTab !== 'sessions'}
          >
            <SessionsTab featureId={featureId} />
          </div>
        )}

        {/* Analytics: feature-scoped session usage + planned/observed attribution */}
        {activatedTabs.has('analytics') && (
          <div
            role="tabpanel"
            id="tab-panel-analytics"
            aria-labelledby="tab-analytics"
            hidden={activeTab !== 'analytics'}
          >
            <React.Suspense fallback={<LazyTabFallback label="analytics" />}>
              <FeatureAnalyticsPanel projectId={projectId} featureId={featureId} featureContext={ctx ?? null} />
            </React.Suspense>
          </div>
        )}

        {/* Logs (AC-4: same component, no bulk transcript loads) */}
        {activatedTabs.has('logs') && (
          <div
            role="tabpanel"
            id="tab-panel-logs"
            aria-labelledby="tab-logs"
            hidden={activeTab !== 'logs'}
          >
            <LogsTab featureId={featureId} />
          </div>
        )}

        {/* Artifacts (P5-007: useArtifactRankingsQuery) */}
        {activatedTabs.has('artifacts') && (
          <div
            role="tabpanel"
            id="tab-panel-artifacts"
            aria-labelledby="tab-artifacts"
            hidden={activeTab !== 'artifacts'}
          >
            {projectId ? (
              <ArtifactsTab projectId={projectId} featureId={featureId} />
            ) : (
              <EmptyState icon={Layers} title="No active project" body="Select a project to view artifacts." />
            )}
          </div>
        )}

        {/* Research (AC-6: gate on meatyWikiEnabled) */}
        {activatedTabs.has('research') && (
          <div
            role="tabpanel"
            id="tab-panel-research"
            aria-labelledby="tab-research"
            hidden={activeTab !== 'research'}
          >
            <ResearchTab featureId={featureId} enabled={meatyWikiEnabled} />
          </div>
        )}

        {/* Council (AC-6: gate on arcEnabled) */}
        {activatedTabs.has('council') && (
          <div
            role="tabpanel"
            id="tab-panel-council"
            aria-labelledby="tab-council"
            hidden={activeTab !== 'council'}
          >
            <CouncilTab featureId={featureId} enabled={arcEnabled} />
          </div>
        )}
      </div>
    </div>
  );
}

export default FeatureDetailShell;
