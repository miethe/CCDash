import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, RefreshCcw, Search, ShieldAlert, Sparkles, Trophy } from 'lucide-react';

import { AnalyticsApiError, analyticsService } from '../../services/analytics';
import {
  ExecutionArtifactReference,
  EffectivenessScopeType,
  FailurePatternRecord,
  WorkflowEffectivenessResponse,
  WorkflowEffectivenessRollup,
} from '../../types';
import { ArtifactContributionPanel } from '../execution/ArtifactContributionPanel';
import { ArtifactReferenceModal } from '../execution/ArtifactReferenceModal';

type PeriodPreset = '7d' | '30d' | '90d';

interface WorkflowEffectivenessSurfaceProps {
  featureId?: string;
  embedded?: boolean;
  title?: string;
  description?: string;
  onOpenSession?: (sessionId: string) => void;
}

interface EffectivenessEvidenceSummary {
  featureIds: string[];
  representativeSessionIds: string[];
  averageQueueOperations: number;
  averageLaterDebugSessions: number;
  averageTestPassRatio: number;
}

const SCOPE_OPTIONS: Array<{ value: EffectivenessScopeType; label: string }> = [
  { value: 'workflow', label: 'Workflow' },
  { value: 'effective_workflow', label: 'Effective Workflow' },
  { value: 'agent', label: 'Agent' },
  { value: 'skill', label: 'Skill' },
  { value: 'context_module', label: 'Context Module' },
  { value: 'bundle', label: 'Bundle Family' },
  { value: 'stack', label: 'Stack' },
];

const PERIOD_OPTIONS: Array<{ value: PeriodPreset; label: string }> = [
  { value: '7d', label: '7d' },
  { value: '30d', label: '30d' },
  { value: '90d', label: '90d' },
];

const formatPercent = (value: number): string => `${Math.round(Math.max(0, Math.min(1, Number(value || 0))) * 100)}%`;
const formatInteger = (value: number): string => Number(value || 0).toLocaleString();

const formatLoadError = (err: unknown): string => {
  if (err instanceof AnalyticsApiError) {
    const suffix = err.hint ? ` ${err.hint}` : '';
    if (err.status === 404) {
      return `Workflow analytics endpoints are unavailable from the current backend.${suffix}`;
    }
    if (err.status === 503) {
      return `${err.message}.${suffix}`.replace(/\.\s*\./g, '.');
    }
    return `${err.message}${suffix ? ` ${err.hint}` : ''}`.trim();
  }
  return err instanceof Error ? err.message : 'Failed to load workflow effectiveness';
};

const buildDateRange = (preset: PeriodPreset): { start: string; end: string } => {
  const days = preset === '7d' ? 7 : preset === '90d' ? 90 : 30;
  const end = new Date();
  const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
  return {
    start: start.toISOString(),
    end: end.toISOString(),
  };
};

const scoreBarClass = (kind: 'success' | 'efficiency' | 'quality' | 'risk'): string => {
  if (kind === 'success') return 'from-emerald-400 to-emerald-500';
  if (kind === 'efficiency') return 'from-sky-400 to-blue-500';
  if (kind === 'quality') return 'from-cyan-400 to-indigo-500';
  return 'from-amber-300 via-orange-400 to-rose-500';
};

const severityClass = (severity: string): string => {
  const normalized = String(severity || '').toLowerCase();
  if (normalized === 'high') return 'border-rose-500/30 bg-rose-500/10 text-rose-100';
  if (normalized === 'low') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100';
  return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
};

const scoreValueClass = (kind: 'success' | 'efficiency' | 'quality' | 'risk'): string => {
  if (kind === 'success') return 'text-emerald-200';
  if (kind === 'efficiency') return 'text-sky-200';
  if (kind === 'quality') return 'text-cyan-200';
  return 'text-amber-200';
};

const asArrayOfStrings = (value: unknown): string[] =>
  Array.isArray(value) ? value.map(item => String(item || '').trim()).filter(Boolean) : [];

const asNumber = (value: unknown, fallback = 0): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const getEvidenceSummary = (summary: Record<string, unknown> | null | undefined): EffectivenessEvidenceSummary => ({
  featureIds: asArrayOfStrings(summary?.featureIds),
  representativeSessionIds: asArrayOfStrings(summary?.representativeSessionIds),
  averageQueueOperations: asNumber(summary?.averageQueueOperations),
  averageLaterDebugSessions: asNumber(summary?.averageLaterDebugSessions),
  averageTestPassRatio: asNumber(summary?.averageTestPassRatio),
});

const summarizeScope = (item: WorkflowEffectivenessRollup): string => {
  if (item.scopeLabel && item.scopeLabel !== item.scopeId) return item.scopeId;
  return item.scopeType.replace(/_/g, ' ');
};

const topPerformerFor = (items: WorkflowEffectivenessRollup[]): WorkflowEffectivenessRollup | null => {
  if (items.length === 0) return null;
  return [...items].sort((a, b) => {
    const aScore = a.successScore + a.efficiencyScore + a.qualityScore - a.riskScore;
    const bScore = b.successScore + b.efficiencyScore + b.qualityScore - b.riskScore;
    if (bScore !== aScore) return bScore - aScore;
    return b.sampleSize - a.sampleSize;
  })[0] || null;
};

const weightedAverage = (items: WorkflowEffectivenessRollup[], key: keyof WorkflowEffectivenessRollup): number => {
  const totalWeight = items.reduce((sum, item) => sum + Math.max(1, Number(item.sampleSize || 0)), 0);
  if (totalWeight <= 0) return 0;
  return items.reduce(
    (sum, item) => sum + (Number(item[key] || 0) * Math.max(1, Number(item.sampleSize || 0))),
    0,
  ) / totalWeight;
};

const scopeLabelFor = (scopeType: EffectivenessScopeType): string =>
  SCOPE_OPTIONS.find(option => option.value === scopeType)?.label || scopeType.replace(/_/g, ' ');

const supportsArtifactContributions = (item: WorkflowEffectivenessRollup): boolean =>
  item.scopeType === 'workflow' || item.scopeType === 'effective_workflow';

const ScoreBar: React.FC<{ label: string; value: number; kind: 'success' | 'efficiency' | 'quality' | 'risk' }> = ({
  label,
  value,
  kind,
}) => (
  <div className="space-y-2">
    <div className="flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.16em] text-slate-500">
      <span>{label}</span>
      <span className={`font-mono text-sm ${scoreValueClass(kind)}`}>{formatPercent(value)}</span>
    </div>
    <div className="h-2 overflow-hidden rounded-full bg-slate-900">
      <div
        className={`h-full rounded-full bg-gradient-to-r ${scoreBarClass(kind)}`}
        style={{ width: `${Math.max(8, Math.round(Math.max(0, Math.min(1, value)) * 100))}%` }}
      />
    </div>
  </div>
);

const SummaryCard: React.FC<{ label: string; value: string; caption?: string }> = ({ label, value, caption }) => (
  <div className="rounded-2xl border border-slate-800/80 bg-slate-950/55 px-4 py-4">
    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
    <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-100 md:text-3xl [overflow-wrap:anywhere]">{value}</div>
    {caption && <div className="mt-1 text-xs text-slate-500">{caption}</div>}
  </div>
);

const EvidenceMetric: React.FC<{ label: string; value: string; tone?: 'default' | 'positive' | 'warning' }> = ({
  label,
  value,
  tone = 'default',
}) => (
  <div className="rounded-xl border border-slate-800 bg-slate-950/75 px-3 py-3">
    <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{label}</div>
    <div
      className={`mt-1 font-mono text-base ${
        tone === 'positive' ? 'text-emerald-200' : tone === 'warning' ? 'text-amber-200' : 'text-slate-200'
      }`}
    >
      {value}
    </div>
  </div>
);

export const WorkflowEffectivenessSurface: React.FC<WorkflowEffectivenessSurfaceProps> = ({
  featureId,
  embedded = false,
  title = 'Workflow Effectiveness',
  description = 'Compare observed workflows, agents, skills, and stacks against real outcomes.',
  onOpenSession,
}) => {
  const [scopeType, setScopeType] = useState<EffectivenessScopeType>('workflow');
  const [periodPreset, setPeriodPreset] = useState<PeriodPreset>('30d');
  const [search, setSearch] = useState('');
  const [payload, setPayload] = useState<WorkflowEffectivenessResponse | null>(null);
  const [failurePatterns, setFailurePatterns] = useState<FailurePatternRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeScopeDetail, setActiveScopeDetail] = useState<{
    item: WorkflowEffectivenessRollup;
    reference: ExecutionArtifactReference;
  } | null>(null);
  const requestIdRef = useRef(0);
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

  const loadSurface = async (recompute = false) => {
    const requestId = ++requestIdRef.current;
    const { start, end } = buildDateRange(periodPreset);
    setLoading(true);
    setError('');
    try {
      const [effectiveness, patterns] = await Promise.all([
        analyticsService.getWorkflowEffectiveness({
          period: 'all',
          scopeType,
          featureId,
          start,
          end,
          recompute,
          offset: 0,
          limit: 100,
        }),
        analyticsService.getFailurePatterns({
          scopeType,
          featureId,
          start,
          end,
          offset: 0,
          limit: 12,
        }),
      ]);
      if (requestId !== requestIdRef.current) return;
      setPayload(effectiveness);
      setFailurePatterns(patterns.items || []);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setPayload(null);
      setFailurePatterns([]);
      setError(formatLoadError(err));
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void loadSurface(false);
  }, [featureId, periodPreset, scopeType]);

  const filteredItems = useMemo(() => {
    const rows = payload?.items || [];
    if (!deferredSearch) return rows;
    return rows.filter(item => {
      const evidence = getEvidenceSummary(item.evidenceSummary);
      const haystack = [
        item.scopeLabel,
        item.scopeId,
        item.scopeType,
        ...evidence.featureIds,
        ...evidence.representativeSessionIds,
      ].join(' ').toLowerCase();
      return haystack.includes(deferredSearch);
    });
  }, [deferredSearch, payload?.items]);

  const summary = useMemo(() => {
    const topPerformer = topPerformerFor(filteredItems);
    return {
      overallSuccess: weightedAverage(filteredItems, 'successScore'),
      avgEfficiency: weightedAverage(filteredItems, 'efficiencyScore'),
      attributedTokens: filteredItems.reduce((sum, item) => sum + Number(item.attributedTokens || 0), 0),
      attributedCost: filteredItems.reduce((sum, item) => sum + Number(item.attributedCostUsdModelIO || 0), 0),
      attributionCoverage: weightedAverage(filteredItems, 'attributionCoverage'),
      attributionCacheShare: weightedAverage(filteredItems, 'attributionCacheShare'),
      topPerformer,
      flaggedPatterns: failurePatterns.length,
    };
  }, [failurePatterns.length, filteredItems]);

  const shellClass = embedded
    ? 'rounded-[24px] border border-slate-800/80 bg-slate-900/75 p-4 md:p-5 shadow-[inset_0_1px_0_rgba(148,163,184,0.06)]'
    : 'rounded-[28px] border border-slate-800/80 bg-slate-900/80 p-5 md:p-6 shadow-[0_28px_90px_rgba(2,6,23,0.22)]';
  const contentGridClass = embedded
    ? 'mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.88fr)]'
    : 'mt-5 grid gap-4 2xl:grid-cols-[minmax(0,1fr)_320px]';
  const itemsColumnClass = 'space-y-4';
  const failurePatternsBodyClass = 'space-y-3 px-4 py-4';
  const failurePatternsAsideClass = 'min-w-0 overflow-hidden rounded-[24px] border border-slate-800/80 bg-slate-950/50';

  return (
    <section className={shellClass}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-100">
            <Sparkles size={12} />
            Intelligence View
          </div>
          <h3 className="mt-3 text-xl font-semibold tracking-tight text-slate-100 md:text-2xl">{title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
        </div>
        <button
          onClick={() => { void loadSurface(true); }}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs font-semibold text-slate-200 transition-colors hover:border-slate-600 hover:bg-slate-950 disabled:opacity-60"
        >
          <RefreshCcw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="mt-5 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(12rem,1fr))]">
        <label className="rounded-2xl border border-slate-800/80 bg-slate-950/55 px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Scope</span>
          <select
            value={scopeType}
            onChange={event => setScopeType(event.target.value as EffectivenessScopeType)}
            className="mt-2 w-full bg-transparent text-base font-medium text-slate-100 outline-none"
          >
            {SCOPE_OPTIONS.map(option => (
              <option key={option.value} value={option.value} className="bg-slate-950 text-slate-100">
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="rounded-2xl border border-slate-800/80 bg-slate-950/55 px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Period</span>
          <select
            value={periodPreset}
            onChange={event => setPeriodPreset(event.target.value as PeriodPreset)}
            className="mt-2 w-full bg-transparent text-base font-medium text-slate-100 outline-none"
          >
            {PERIOD_OPTIONS.map(option => (
              <option key={option.value} value={option.value} className="bg-slate-950 text-slate-100">
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="rounded-2xl border border-slate-800/80 bg-slate-950/55 px-4 py-3">
          <span className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <Search size={12} />
            Search
          </span>
          <input
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Filter scopes, features, sessions"
            className="mt-2 w-full bg-transparent text-base text-slate-100 outline-none placeholder:text-slate-500"
          />
        </label>
      </div>

      {featureId && (
        <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-indigo-500/25 bg-indigo-500/10 px-3 py-1 text-[11px] text-indigo-100">
          Feature-scoped view
          <span className="font-mono text-indigo-200">{featureId}</span>
        </div>
      )}

      <div className="mt-5 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(13rem,1fr))]">
        <SummaryCard label="Overall Success" value={formatPercent(summary.overallSuccess)} caption="Weighted across visible scopes" />
        <SummaryCard label="Avg Efficiency" value={formatPercent(summary.avgEfficiency)} caption="Duration, cost, token, and queue pressure" />
        <SummaryCard label="Attributed Tokens" value={formatInteger(summary.attributedTokens)} caption={`${formatPercent(summary.attributionCoverage)} model-IO coverage`} />
        <SummaryCard label="Attributed Cost" value={`$${summary.attributedCost.toFixed(2)}`} caption={`${formatPercent(summary.attributionCacheShare)} cache share`} />
        <SummaryCard
          label="Top Performer"
          value={summary.topPerformer?.scopeLabel || summary.topPerformer?.scopeId || 'n/a'}
          caption={summary.topPerformer ? `${scopeLabelFor(summary.topPerformer.scopeType)} • ${summary.topPerformer.sampleSize} sessions` : 'No scored rows'}
        />
        <SummaryCard label="Flagged Patterns" value={formatInteger(summary.flaggedPatterns)} caption="Low-yield patterns in this window" />
      </div>

      {error && (
        <div className="mt-5 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {error}
        </div>
      )}

      <div className={contentGridClass}>
        <div className={itemsColumnClass}>
          {!loading && !error && filteredItems.length > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800/80 bg-slate-950/45 px-4 py-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Visible rollups</div>
                <div className="mt-1 text-sm text-slate-300">
                  {formatInteger(filteredItems.length)} scope{filteredItems.length === 1 ? '' : 's'} ranked by delivery outcome.
                </div>
              </div>
              {payload?.metricDefinitions?.length ? (
                <div className="text-xs text-slate-500">
                  Metrics: {payload.metricDefinitions.map(metric => metric.label).join(' / ')}
                </div>
              ) : null}
            </div>
          )}

          {loading && (
            <div className="rounded-2xl border border-slate-800/80 bg-slate-950/45 px-4 py-8 text-sm text-slate-400">
              Loading workflow effectiveness...
            </div>
          )}

          {!loading && !error && filteredItems.length === 0 && (
            <div className="rounded-2xl border border-slate-800/80 bg-slate-950/45 px-4 py-10 text-sm text-slate-500">
              No effectiveness rows matched the current filters.
            </div>
          )}

          {!loading && !error && filteredItems.map(item => {
            const evidence = getEvidenceSummary(item.evidenceSummary);
            const scopeTypeLabel = scopeLabelFor(item.scopeType);
            const representativeSessions = evidence.representativeSessionIds.slice(0, 4);
            const featureIds = evidence.featureIds.slice(0, 4);

            return (
              <article
                key={`${item.scopeType}-${item.scopeId}`}
                className="min-w-0 rounded-[24px] border border-slate-800/80 bg-slate-950/50 p-4 transition-colors hover:border-slate-700"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                        {scopeTypeLabel}
                      </span>
                      <span className="inline-flex items-center rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300">
                        {formatInteger(item.sampleSize)} sessions
                      </span>
                    </div>
                    {item.scopeRef ? (
                      <button
                        onClick={() => setActiveScopeDetail({ item, reference: item.scopeRef! })}
                        className="mt-3 text-left text-lg font-semibold leading-tight text-sky-200 underline decoration-slate-600 underline-offset-4 [overflow-wrap:anywhere]"
                      >
                        {item.scopeLabel || item.scopeId}
                      </button>
                    ) : (
                      <h4 className="mt-3 text-lg font-semibold leading-tight text-slate-100 [overflow-wrap:anywhere]">
                        {item.scopeLabel || item.scopeId}
                      </h4>
                    )}
                    <p className="mt-1 text-sm text-slate-500 [overflow-wrap:anywhere]">
                      {summarizeScope(item)}
                    </p>
                    {(item.relatedRefs || []).length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(item.relatedRefs || []).slice(0, 4).map(reference => (
                          <button
                            key={`${item.scopeType}-${item.scopeId}-${reference.kind}-${reference.key}`}
                            onClick={() => setActiveScopeDetail({ item, reference })}
                            className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300 transition-colors hover:border-slate-600"
                          >
                            {reference.label || reference.key}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {summary.topPerformer?.scopeType === item.scopeType && summary.topPerformer?.scopeId === item.scopeId && (
                    <div className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/25 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-100">
                      <Trophy size={13} className="text-amber-300" />
                      Top performer
                    </div>
                  )}
                </div>

                <div className="mt-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(9rem,1fr))]">
                  <ScoreBar label="Success" value={item.successScore} kind="success" />
                  <ScoreBar label="Efficiency" value={item.efficiencyScore} kind="efficiency" />
                  <ScoreBar label="Quality" value={item.qualityScore} kind="quality" />
                  <ScoreBar label="Risk" value={item.riskScore} kind="risk" />
                </div>

                <div className="mt-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(9rem,1fr))]">
                  <EvidenceMetric label="Attributed Tokens" value={formatInteger(Number(item.attributedTokens || 0))} />
                  <EvidenceMetric label="Attributed Cost" value={`$${Number(item.attributedCostUsdModelIO || 0).toFixed(2)}`} />
                  <EvidenceMetric label="Coverage" value={formatPercent(Number(item.attributionCoverage || 0))} tone={Number(item.attributionCoverage || 0) >= 0.75 ? 'positive' : 'warning'} />
                  <EvidenceMetric label="Cache Share" value={formatPercent(Number(item.attributionCacheShare || 0))} />
                </div>

                <div className="mt-4 grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))]">
                  <div className="min-w-0 rounded-2xl border border-slate-800/80 bg-slate-950/75 p-4">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Evidence Snapshot</div>
                    <div className="mt-3 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(9rem,1fr))]">
                      <EvidenceMetric
                        label="Avg Test Pass"
                        value={formatPercent(evidence.averageTestPassRatio)}
                        tone={evidence.averageTestPassRatio >= 0.75 ? 'positive' : evidence.averageTestPassRatio > 0 ? 'default' : 'warning'}
                      />
                      <EvidenceMetric
                        label="Avg Queue Ops"
                        value={evidence.averageQueueOperations.toFixed(2)}
                        tone={evidence.averageQueueOperations > 3 ? 'warning' : 'default'}
                      />
                      <EvidenceMetric
                        label="Later Debug"
                        value={evidence.averageLaterDebugSessions.toFixed(2)}
                        tone={evidence.averageLaterDebugSessions > 0.5 ? 'warning' : 'default'}
                      />
                      <EvidenceMetric
                        label="Features"
                        value={formatInteger(evidence.featureIds.length)}
                        tone={evidence.featureIds.length > 0 ? 'positive' : 'default'}
                      />
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      {featureIds.length > 0 ? featureIds.map(id => (
                        <span
                          key={`${item.scopeType}-${item.scopeId}-feature-${id}`}
                          className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] font-mono text-slate-300"
                        >
                          {id}
                        </span>
                      )) : (
                        <span className="text-xs text-slate-500">No feature coverage metadata was attached.</span>
                      )}
                    </div>
                  </div>

                  {supportsArtifactContributions(item) && (
                    <ArtifactContributionPanel
                      workflowId={item.scopeId}
                      period={periodPreset}
                    />
                  )}

                  <div className="min-w-0 rounded-2xl border border-slate-800/80 bg-slate-950/75 p-4">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Representative Sessions</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {representativeSessions.length > 0 ? representativeSessions.map(sessionId => (
                        <button
                          key={`${item.scopeType}-${item.scopeId}-session-${sessionId}`}
                          onClick={() => onOpenSession?.(sessionId)}
                          disabled={!onOpenSession}
                          className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-[11px] font-mono text-sky-200 transition-colors hover:border-slate-600 hover:text-sky-100 disabled:cursor-default disabled:text-slate-400"
                        >
                          {sessionId}
                        </button>
                      )) : (
                        <div className="text-sm text-slate-500">No representative sessions were attached to this rollup.</div>
                      )}
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>

        <aside className={failurePatternsAsideClass}>
          <div className="border-b border-slate-800 px-4 py-4">
            <div className="flex items-center gap-2 text-lg font-semibold text-slate-100">
              <ShieldAlert size={18} className="text-amber-300" />
              Failure Patterns
            </div>
            <p className="mt-2 text-sm text-slate-500">
              Common ways this scope drifts into slow or low-confidence execution.
            </p>
          </div>
          <div className={failurePatternsBodyClass}>
            {!loading && !error && failurePatterns.length === 0 && (
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-5 text-sm text-slate-500">
                No low-yield patterns were flagged for this scope and time window.
              </div>
            )}

            {!error && failurePatterns.map((pattern, index) => {
              const evidence = getEvidenceSummary(pattern.evidenceSummary);
              return (
                <div
                  key={pattern.id}
                  className={`rounded-2xl border px-4 py-4 ${severityClass(pattern.severity)}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 rounded-full border border-current/25 px-2 py-1 text-[11px] font-semibold">
                      {index + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <AlertTriangle size={15} />
                        <div className="text-base font-semibold">{pattern.title}</div>
                      </div>

                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.16em] text-current/80">
                        <span>{pattern.occurrenceCount} hits</span>
                        <span>{formatPercent(pattern.confidence)} confidence</span>
                        <span>{formatPercent(pattern.averageRiskScore)} avg risk</span>
                      </div>

                      <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                        <div className="rounded-xl border border-current/15 bg-slate-950/35 px-3 py-2">
                          <div className="text-current/70">Scope</div>
                          <div className="mt-1 font-mono text-slate-100 [overflow-wrap:anywhere]">
                            {pattern.scopeId || scopeLabelFor(pattern.scopeType as EffectivenessScopeType)}
                          </div>
                        </div>
                        <div className="rounded-xl border border-current/15 bg-slate-950/35 px-3 py-2">
                          <div className="text-current/70">Missing validation</div>
                          <div className="mt-1 font-mono text-slate-100">{formatInteger(asNumber(pattern.evidenceSummary?.missingValidationSessions))}</div>
                        </div>
                        <div className="rounded-xl border border-current/15 bg-slate-950/35 px-3 py-2">
                          <div className="text-current/70">Avg queue ops</div>
                          <div className="mt-1 font-mono text-slate-100">{evidence.averageQueueOperations.toFixed(2)}</div>
                        </div>
                        <div className="rounded-xl border border-current/15 bg-slate-950/35 px-3 py-2">
                          <div className="text-current/70">Later debug</div>
                          <div className="mt-1 font-mono text-slate-100">{evidence.averageLaterDebugSessions.toFixed(2)}</div>
                        </div>
                      </div>

                      {evidence.featureIds.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {evidence.featureIds.slice(0, 3).map(feature => (
                            <span
                              key={`${pattern.id}-${feature}`}
                              className="rounded-full border border-current/20 bg-slate-950/35 px-2.5 py-1 text-[11px] font-mono text-slate-100"
                            >
                              {feature}
                            </span>
                          ))}
                        </div>
                      )}

                      {pattern.sessionIds.length > 0 && onOpenSession && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {pattern.sessionIds.slice(0, 2).map(sessionId => (
                            <button
                              key={`${pattern.id}-${sessionId}`}
                              onClick={() => onOpenSession(sessionId)}
                              className="rounded-full border border-current/20 bg-slate-950/35 px-3 py-1.5 text-[11px] font-mono text-slate-100 underline decoration-current/30 underline-offset-4"
                            >
                              {sessionId}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </aside>
      </div>

      {activeScopeDetail && (
        <ArtifactReferenceModal
          reference={activeScopeDetail.reference}
          title={`${scopeLabelFor(activeScopeDetail.item.scopeType)} Reference`}
          subtitle={`Observed across ${formatInteger(activeScopeDetail.item.sampleSize)} session${activeScopeDetail.item.sampleSize === 1 ? '' : 's'} in the current window.`}
          metrics={[
            { label: 'Success', value: formatPercent(activeScopeDetail.item.successScore) },
            { label: 'Quality', value: formatPercent(activeScopeDetail.item.qualityScore) },
            { label: 'Risk', value: formatPercent(activeScopeDetail.item.riskScore) },
            { label: 'Sessions', value: formatInteger(activeScopeDetail.item.sampleSize) },
          ]}
          relatedRefs={activeScopeDetail.item.relatedRefs || []}
          onOpenReference={(reference) => setActiveScopeDetail({ item: activeScopeDetail.item, reference })}
          onClose={() => setActiveScopeDetail(null)}
        />
      )}
    </section>
  );
};
