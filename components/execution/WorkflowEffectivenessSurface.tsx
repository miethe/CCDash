import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, RefreshCcw, Search, ShieldAlert, Sparkles, Trophy } from 'lucide-react';

import { AnalyticsApiError, analyticsService } from '../../services/analytics';
import {
  EffectivenessScopeType,
  FailurePatternRecord,
  WorkflowEffectivenessResponse,
  WorkflowEffectivenessRollup,
} from '../../types';

type PeriodPreset = '7d' | '30d' | '90d';

interface WorkflowEffectivenessSurfaceProps {
  featureId?: string;
  embedded?: boolean;
  title?: string;
  description?: string;
  onOpenSession?: (sessionId: string) => void;
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
const formatDecimal = (value: number): string => Number(value || 0).toFixed(2);
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
  if (kind === 'quality') return 'from-fuchsia-400 to-violet-500';
  return 'from-rose-400 via-amber-400 to-yellow-500';
};

const severityClass = (severity: string): string => {
  const normalized = String(severity || '').toLowerCase();
  if (normalized === 'high') return 'border-rose-500/40 bg-rose-500/10 text-rose-100';
  if (normalized === 'low') return 'border-emerald-500/35 bg-emerald-500/10 text-emerald-100';
  return 'border-amber-500/40 bg-amber-500/10 text-amber-100';
};

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

const ScoreBar: React.FC<{ label: string; value: number; kind: 'success' | 'efficiency' | 'quality' | 'risk' }> = ({
  label,
  value,
  kind,
}) => (
  <div className="space-y-1.5">
    <div className="flex items-center justify-between gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
      <span>{label}</span>
      <span className="font-semibold text-slate-300">{formatPercent(value)}</span>
    </div>
    <div className="h-2 rounded-full bg-slate-800/90 overflow-hidden">
      <div
        className={`h-full rounded-full bg-gradient-to-r ${scoreBarClass(kind)}`}
        style={{ width: `${Math.max(6, Math.round(Math.max(0, Math.min(1, value)) * 100))}%` }}
      />
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
      const haystack = [
        item.scopeLabel,
        item.scopeId,
        item.scopeType,
        String(item.evidenceSummary?.featureId || ''),
      ].join(' ').toLowerCase();
      return haystack.includes(deferredSearch);
    });
  }, [deferredSearch, payload?.items]);

  const summary = useMemo(() => {
    const topPerformer = topPerformerFor(filteredItems);
    return {
      overallSuccess: weightedAverage(filteredItems, 'successScore'),
      avgEfficiency: weightedAverage(filteredItems, 'efficiencyScore'),
      topPerformer,
      flaggedPatterns: failurePatterns.length,
    };
  }, [failurePatterns.length, filteredItems]);

  const shellClass = embedded
    ? 'rounded-[24px] border border-slate-800 bg-[radial-gradient(circle_at_top,_rgba(37,99,235,0.18),_rgba(15,23,42,0.92)_42%,_rgba(2,6,23,0.96)_100%)] p-4 md:p-5'
    : 'rounded-[28px] border border-slate-800 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.2),_rgba(15,23,42,0.94)_42%,_rgba(2,6,23,0.98)_100%)] p-5 md:p-6 shadow-[0_28px_90px_rgba(15,23,42,0.38)]';

  return (
    <section className={shellClass}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.28em] text-sky-100">
            <Sparkles size={12} />
            Intelligence View
          </div>
          <h3 className="mt-3 font-mono text-2xl text-slate-100">{title}</h3>
          <p className="mt-2 max-w-3xl text-sm text-slate-400">{description}</p>
        </div>
        <button
          onClick={() => { void loadSurface(true); }}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-xs font-semibold text-slate-200 transition-colors hover:border-slate-500 disabled:opacity-60"
        >
          <RefreshCcw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px_320px]">
        <label className="rounded-2xl border border-slate-700/80 bg-slate-950/45 px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Scope</span>
          <select
            value={scopeType}
            onChange={event => setScopeType(event.target.value as EffectivenessScopeType)}
            className="mt-2 w-full bg-transparent font-mono text-lg text-slate-100 outline-none"
          >
            {SCOPE_OPTIONS.map(option => (
              <option key={option.value} value={option.value} className="bg-slate-950 text-slate-100">
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="rounded-2xl border border-slate-700/80 bg-slate-950/45 px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Period</span>
          <select
            value={periodPreset}
            onChange={event => setPeriodPreset(event.target.value as PeriodPreset)}
            className="mt-2 w-full bg-transparent font-mono text-lg text-slate-100 outline-none"
          >
            {PERIOD_OPTIONS.map(option => (
              <option key={option.value} value={option.value} className="bg-slate-950 text-slate-100">
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="rounded-2xl border border-slate-700/80 bg-slate-950/45 px-4 py-3">
          <span className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <Search size={12} />
            Search
          </span>
          <input
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Filter names or IDs"
            className="mt-2 w-full bg-transparent font-mono text-lg text-slate-100 outline-none placeholder:text-slate-500"
          />
        </label>
      </div>

      {featureId && (
        <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-indigo-500/25 bg-indigo-500/10 px-3 py-1 text-[11px] text-indigo-100">
          Feature-scoped view
          <span className="font-mono text-indigo-200">{featureId}</span>
        </div>
      )}

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-700/80 bg-slate-950/50 px-4 py-4">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Overall Success</div>
          <div className="mt-2 font-mono text-4xl text-slate-100">{formatPercent(summary.overallSuccess)}</div>
        </div>
        <div className="rounded-2xl border border-slate-700/80 bg-slate-950/50 px-4 py-4">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Avg Efficiency</div>
          <div className="mt-2 font-mono text-4xl text-slate-100">{formatDecimal(summary.avgEfficiency)}</div>
        </div>
        <div className="rounded-2xl border border-slate-700/80 bg-slate-950/50 px-4 py-4">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Top Performer</div>
          <div className="mt-2 flex items-start gap-3">
            <Trophy size={18} className="mt-1 text-amber-300" />
            <div>
              <div className="font-mono text-2xl text-slate-100">
                {summary.topPerformer?.scopeLabel || summary.topPerformer?.scopeId || 'n/a'}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {summary.topPerformer ? `${summary.topPerformer.sampleSize} sessions` : 'No scored rows'}
              </div>
            </div>
          </div>
        </div>
        <div className="rounded-2xl border border-slate-700/80 bg-slate-950/50 px-4 py-4">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Flagged Patterns</div>
          <div className="mt-2 font-mono text-4xl text-slate-100">{formatInteger(summary.flaggedPatterns)}</div>
        </div>
      </div>

      {error && (
        <div className="mt-5 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {error}
        </div>
      )}

      <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="overflow-hidden rounded-[24px] border border-slate-700/80 bg-slate-950/45">
          <div className="grid grid-cols-[minmax(220px,1.3fr)_repeat(4,minmax(120px,1fr))_84px] gap-4 border-b border-slate-800/90 px-4 py-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <div>Name</div>
            <div>Success</div>
            <div>Efficiency</div>
            <div>Quality</div>
            <div>Risk</div>
            <div>Sessions</div>
          </div>

          {loading && (
            <div className="px-4 py-8 text-sm text-slate-400">Loading workflow effectiveness...</div>
          )}

          {!loading && !error && filteredItems.length === 0 && (
            <div className="px-4 py-10 text-sm text-slate-500">
              No effectiveness rows matched the current filters.
            </div>
          )}

          {!loading && !error && filteredItems.map(item => (
            <div
              key={`${item.scopeType}-${item.scopeId}`}
              className="grid grid-cols-[minmax(220px,1.3fr)_repeat(4,minmax(120px,1fr))_84px] gap-4 border-b border-slate-900/80 px-4 py-4 last:border-b-0"
            >
              <div className="min-w-0">
                <div className="truncate font-mono text-lg text-slate-100">
                  {item.scopeLabel || item.scopeId}
                </div>
                <div className="mt-1 truncate text-sm text-slate-500">
                  {summarizeScope(item)}
                </div>
              </div>
              <ScoreBar label="Success" value={item.successScore} kind="success" />
              <ScoreBar label="Efficiency" value={item.efficiencyScore} kind="efficiency" />
              <ScoreBar label="Quality" value={item.qualityScore} kind="quality" />
              <ScoreBar label="Risk" value={item.riskScore} kind="risk" />
              <div className="font-mono text-2xl text-slate-200">{formatInteger(item.sampleSize)}</div>
            </div>
          ))}
        </div>

        <aside className="overflow-hidden rounded-[24px] border border-slate-700/80 bg-slate-950/45">
          <div className="border-b border-slate-800/90 px-4 py-4">
            <div className="flex items-center gap-2 font-mono text-2xl text-slate-100">
              <ShieldAlert size={18} className="text-amber-300" />
              Failure Patterns
            </div>
          </div>
          <div className="space-y-3 px-4 py-4">
            {!loading && !error && failurePatterns.length === 0 && (
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-5 text-sm text-slate-500">
                No low-yield patterns were flagged for this scope and time window.
              </div>
            )}

            {!error && failurePatterns.map((pattern, index) => (
              <div
                key={pattern.id}
                className={`rounded-2xl border px-4 py-4 ${severityClass(pattern.severity)}`}
              >
                <div className="flex items-start gap-3">
                  <div className="font-mono text-lg text-slate-300">{index + 1}.</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <AlertTriangle size={15} />
                      <div className="font-mono text-base">{pattern.title}</div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.16em] text-slate-300/75">
                      <span>{pattern.occurrenceCount} hits</span>
                      <span>{formatPercent(pattern.confidence)} confidence</span>
                      <span>{formatPercent(pattern.averageRiskScore)} avg risk</span>
                    </div>
                    {pattern.sessionIds.length > 0 && onOpenSession && (
                      <button
                        onClick={() => onOpenSession(pattern.sessionIds[0])}
                        className="mt-3 text-xs text-sky-200 underline decoration-slate-500 underline-offset-4 hover:text-sky-100"
                      >
                        Open sample session
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
};
