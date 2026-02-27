import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  BookOpen,
  Clipboard,
  Command,
  ExternalLink,
  Layers,
  LineChart,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Terminal,
} from 'lucide-react';

import { useData } from '../contexts/DataContext';
import { FeatureExecutionContext, FeaturePhase } from '../types';
import { getFeatureExecutionContext, trackExecutionEvent } from '../services/execution';

const TERMINAL_PHASE_STATUSES = new Set(['done', 'deferred']);

type WorkbenchTab = 'overview' | 'phases' | 'documents' | 'sessions' | 'analytics';

const TAB_ITEMS: Array<{ id: WorkbenchTab; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: 'overview', label: 'Overview', icon: Layers },
  { id: 'phases', label: 'Phases', icon: Play },
  { id: 'documents', label: 'Documents', icon: BookOpen },
  { id: 'sessions', label: 'Sessions', icon: Terminal },
  { id: 'analytics', label: 'Analytics', icon: LineChart },
];

const formatDateTime = (value?: string): string => {
  if (!value) return '—';
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleString();
};

const formatStatus = (value: string): string => {
  const normalized = (value || 'unknown').replace(/-/g, ' ');
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

const getPhasePendingTasks = (phase: FeaturePhase): number =>
  (phase.tasks || []).filter(task => !TERMINAL_PHASE_STATUSES.has(task.status)).length;

const copyText = async (value: string): Promise<void> => {
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'absolute';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
};

export const FeatureExecutionWorkbench: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { features, refreshFeatures } = useData();

  const [selectedFeatureId, setSelectedFeatureId] = useState<string>(searchParams.get('feature') || '');
  const [query, setQuery] = useState('');
  const [activeTab, setActiveTab] = useState<WorkbenchTab>('overview');
  const [context, setContext] = useState<FeatureExecutionContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [copiedCommand, setCopiedCommand] = useState('');

  useEffect(() => {
    void refreshFeatures();
  }, [refreshFeatures]);

  const filteredFeatures = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = [...features].sort((a, b) => a.name.localeCompare(b.name));
    if (!needle) return rows;
    return rows.filter(feature => {
      const haystack = [feature.id, feature.name, feature.category, ...(feature.tags || [])].join(' ').toLowerCase();
      return haystack.includes(needle);
    });
  }, [features, query]);

  useEffect(() => {
    const fromQuery = searchParams.get('feature') || '';
    if (fromQuery && fromQuery !== selectedFeatureId) {
      setSelectedFeatureId(fromQuery);
      return;
    }
    if (!selectedFeatureId && features.length > 0) {
      const first = [...features].sort((a, b) => a.name.localeCompare(b.name))[0];
      setSelectedFeatureId(first.id);
    }
  }, [features, searchParams, selectedFeatureId]);

  const selectFeature = useCallback(
    (featureId: string) => {
      setSelectedFeatureId(featureId);
      const nextParams = new URLSearchParams(searchParams);
      if (featureId) {
        nextParams.set('feature', featureId);
      } else {
        nextParams.delete('feature');
      }
      setSearchParams(nextParams, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  useEffect(() => {
    if (!selectedFeatureId) {
      setContext(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError('');

    void trackExecutionEvent({
      eventType: 'execution_workbench_opened',
      featureId: selectedFeatureId,
      metadata: { hasQueryFeature: Boolean(searchParams.get('feature')) },
    });

    void getFeatureExecutionContext(selectedFeatureId)
      .then(payload => {
        if (cancelled) return;
        setContext(payload);
        void trackExecutionEvent({
          eventType: 'execution_recommendation_generated',
          featureId: selectedFeatureId,
          recommendationRuleId: payload.recommendations.ruleId,
          command: payload.recommendations.primary.command,
          metadata: { confidence: payload.recommendations.confidence },
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setContext(null);
        setError(err instanceof Error ? err.message : 'Failed to load execution context');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [searchParams, selectedFeatureId]);

  const sourceDocPath = useMemo(
    () => context?.recommendations.evidence.find(item => item.sourcePath)?.sourcePath || '',
    [context],
  );

  const handleCopyCommand = useCallback(
    async (command: string) => {
      try {
        await copyText(command);
        setCopiedCommand(command);
        setTimeout(() => setCopiedCommand(''), 1200);
        void trackExecutionEvent({
          eventType: 'execution_command_copied',
          featureId: context?.feature.id,
          recommendationRuleId: context?.recommendations.ruleId,
          command,
        });
      } catch {
        setCopiedCommand('');
      }
    },
    [context],
  );

  const openSourceDoc = useCallback(() => {
    if (!sourceDocPath) return;
    void trackExecutionEvent({
      eventType: 'execution_source_link_clicked',
      featureId: context?.feature.id,
      recommendationRuleId: context?.recommendations.ruleId,
      metadata: { path: sourceDocPath },
    });
    navigate(`/plans?feature=${encodeURIComponent(context?.feature.id || '')}`);
  }, [context, navigate, sourceDocPath]);

  return (
    <div className="space-y-5">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 md:p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-100">Feature Execution Workbench</h1>
            <p className="text-sm text-slate-400 mt-1">
              Unified context and deterministic next-command guidance for feature delivery.
            </p>
          </div>

          <div className="w-full md:w-[460px] grid grid-cols-1 md:grid-cols-[1fr_180px] gap-2">
            <label className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="Search feature"
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-9 py-2.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
              />
            </label>

            <select
              value={selectedFeatureId}
              onChange={event => selectFeature(event.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            >
              {!selectedFeatureId && <option value="">Select feature</option>}
              {filteredFeatures.map(feature => (
                <option key={feature.id} value={feature.id}>
                  {feature.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          <Link to="/board" className="px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500">Board</Link>
          <Link to="/plans" className="px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500">Plans</Link>
          <Link to="/sessions" className="px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500">Sessions</Link>
          <Link to="/analytics" className="px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500">Analytics</Link>
        </div>
      </div>

      {loading && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-400 flex items-center gap-2">
          <Loader2 size={16} className="animate-spin" />
          Loading execution context...
        </div>
      )}

      {!loading && error && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-4 text-rose-200 text-sm">
          {error}
        </div>
      )}

      {!loading && context && (
        <div className="space-y-4">
          {context.warnings.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 space-y-1">
              {context.warnings.map((warning, idx) => (
                <p key={`${warning.section}-${idx}`} className="text-xs text-amber-200">
                  <span className="font-semibold uppercase mr-2">{warning.section}</span>
                  {warning.message}
                </p>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 xl:grid-cols-[390px_1fr] gap-4">
            <section className="bg-slate-900 border border-slate-800 rounded-xl p-4 h-fit sticky top-0 space-y-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-slate-400">Recommendation</p>
                  <h2 className="text-lg font-semibold text-slate-100 mt-1">Next Command</h2>
                </div>
                <span className="text-[10px] font-bold px-2 py-1 rounded border border-indigo-500/40 text-indigo-200 bg-indigo-500/20">
                  {context.recommendations.ruleId}
                </span>
              </div>

              <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
                <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-2">Primary</p>
                <code className="text-sm text-emerald-300 block whitespace-pre-wrap break-all">{context.recommendations.primary.command}</code>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => handleCopyCommand(context.recommendations.primary.command)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-indigo-500/40 bg-indigo-500/20 text-indigo-100 text-xs font-semibold hover:bg-indigo-500/30"
                >
                  <Clipboard size={14} />
                  {copiedCommand === context.recommendations.primary.command ? 'Copied' : 'Copy Command'}
                </button>
                <button
                  onClick={openSourceDoc}
                  disabled={!sourceDocPath}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-700 text-slate-200 text-xs font-semibold enabled:hover:border-slate-500 disabled:opacity-50"
                >
                  <ExternalLink size={14} />
                  Open Source Doc
                </button>
              </div>

              <p className="text-sm text-slate-300 leading-relaxed">{context.recommendations.explanation}</p>

              {context.recommendations.alternatives.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Alternatives</p>
                  {context.recommendations.alternatives.map(option => (
                    <div key={option.command} className="rounded-lg border border-slate-700/80 p-2.5 bg-slate-950/70">
                      <code className="text-xs text-cyan-200 block whitespace-pre-wrap break-all">{option.command}</code>
                      <div className="mt-2 flex items-center justify-between gap-2">
                        <span className="text-[10px] text-slate-500">{option.ruleId}</span>
                        <button
                          onClick={() => handleCopyCommand(option.command)}
                          className="text-[11px] text-slate-300 hover:text-white"
                        >
                          Copy
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Evidence</p>
                <ul className="space-y-1.5">
                  {context.recommendations.evidence.map(item => (
                    <li key={item.id} className="text-xs text-slate-300 flex items-center justify-between gap-2">
                      <span>{item.value}</span>
                      <span className="text-[10px] uppercase text-slate-500">{item.sourceType}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="bg-slate-900 border border-slate-800 rounded-xl p-4 min-h-[520px]">
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
                {TAB_ITEMS.map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border ${
                      activeTab === tab.id
                        ? 'border-indigo-500/50 bg-indigo-500/20 text-indigo-100'
                        : 'border-slate-700 text-slate-300 hover:border-slate-500'
                    }`}
                  >
                    <tab.icon size={13} />
                    {tab.label}
                  </button>
                ))}
              </div>

              {activeTab === 'overview' && (
                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <p className="text-[11px] text-slate-500 uppercase">Feature</p>
                    <p className="text-sm text-slate-100 font-semibold mt-1">{context.feature.name}</p>
                    <p className="text-xs text-slate-500 mt-1">{context.feature.id}</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <p className="text-[11px] text-slate-500 uppercase">Status</p>
                    <p className="text-sm text-slate-100 font-semibold mt-1">{formatStatus(context.feature.status)}</p>
                    <p className="text-xs text-slate-500 mt-1">Updated {formatDateTime(context.feature.updatedAt)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <p className="text-[11px] text-slate-500 uppercase">Tasks</p>
                    <p className="text-sm text-slate-100 font-semibold mt-1">
                      {context.feature.completedTasks}/{context.feature.totalTasks}
                    </p>
                    <p className="text-xs text-slate-500 mt-1">Across {context.feature.phases.length} phases</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <p className="text-[11px] text-slate-500 uppercase">Generated</p>
                    <p className="text-sm text-slate-100 font-semibold mt-1">{formatDateTime(context.generatedAt)}</p>
                    <p className="text-xs text-slate-500 mt-1">Rule confidence {Math.round(context.recommendations.confidence * 100)}%</p>
                  </div>
                </div>
              )}

              {activeTab === 'phases' && (
                <div className="mt-4 space-y-3">
                  {context.feature.phases.map(phase => {
                    const pendingTasks = getPhasePendingTasks(phase);
                    return (
                      <div key={phase.id || phase.phase} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-slate-100">Phase {phase.phase}: {phase.title || 'Untitled'}</p>
                            <p className="text-xs text-slate-400 mt-1">Status: {formatStatus(phase.status)}</p>
                          </div>
                          <span className="text-xs text-slate-300">
                            {phase.completedTasks}/{phase.totalTasks} complete
                          </span>
                        </div>
                        <div className="mt-2 h-2 rounded bg-slate-800 overflow-hidden">
                          <div className="h-full bg-indigo-500" style={{ width: `${Math.max(0, Math.min(100, phase.progress || 0))}%` }} />
                        </div>
                        <p className="text-xs text-slate-400 mt-2">Next unresolved tasks: {pendingTasks}</p>
                      </div>
                    );
                  })}
                </div>
              )}

              {activeTab === 'documents' && (
                <div className="mt-4 space-y-2">
                  {context.documents.length === 0 && <p className="text-sm text-slate-400">No correlated documents found.</p>}
                  {context.documents.map(doc => (
                    <button
                      key={doc.id}
                      onClick={() => {
                        void trackExecutionEvent({
                          eventType: 'execution_source_link_clicked',
                          featureId: context.feature.id,
                          metadata: { path: doc.filePath },
                        });
                        navigate(`/plans?feature=${encodeURIComponent(context.feature.id)}`);
                      }}
                      className="w-full text-left rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 hover:border-slate-600"
                    >
                      <p className="text-sm text-slate-100 font-medium">{doc.title}</p>
                      <p className="text-xs text-slate-400 mt-1">{doc.docType} · {doc.filePath}</p>
                    </button>
                  ))}
                </div>
              )}

              {activeTab === 'sessions' && (
                <div className="mt-4 space-y-2">
                  {context.sessions.length === 0 && <p className="text-sm text-slate-400">No linked sessions available.</p>}
                  {context.sessions.slice(0, 20).map(session => (
                    <Link
                      key={session.sessionId}
                      to={`/sessions?session=${encodeURIComponent(session.sessionId)}`}
                      className="block rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 hover:border-slate-600"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm text-slate-100 font-medium truncate">{session.title || session.sessionId}</p>
                        <span className="text-[11px] text-slate-400">{Math.round((session.confidence || 0) * 100)}%</span>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        {(session.commands || []).slice(0, 2).join(' · ') || session.sessionType || 'linked session'}
                      </p>
                    </Link>
                  ))}
                </div>
              )}

              {activeTab === 'analytics' && (
                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <p className="text-[11px] text-slate-500 uppercase">Sessions</p>
                    <p className="text-lg text-slate-100 font-semibold mt-1">{context.analytics.sessionCount}</p>
                    <p className="text-xs text-slate-500 mt-1">Primary {context.analytics.primarySessionCount}</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <p className="text-[11px] text-slate-500 uppercase">Session Cost</p>
                    <p className="text-lg text-slate-100 font-semibold mt-1">${context.analytics.totalSessionCost.toFixed(2)}</p>
                    <p className="text-xs text-slate-500 mt-1">Models {context.analytics.modelCount}</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <p className="text-[11px] text-slate-500 uppercase">Telemetry</p>
                    <p className="text-lg text-slate-100 font-semibold mt-1">{context.analytics.artifactEventCount} artifacts</p>
                    <p className="text-xs text-slate-500 mt-1">{context.analytics.commandEventCount} command events</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 md:col-span-2 xl:col-span-3">
                    <p className="text-[11px] text-slate-500 uppercase">Last Event</p>
                    <p className="text-sm text-slate-100 mt-1">{formatDateTime(context.analytics.lastEventAt)}</p>
                  </div>
                </div>
              )}
            </section>
          </div>
        </div>
      )}

      {!loading && !context && !error && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-400 flex items-center gap-2">
          <Command size={16} />
          Select a feature to load execution guidance.
          <button
            onClick={() => void refreshFeatures()}
            className="ml-auto inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-slate-700 text-slate-300 hover:border-slate-500 text-xs"
          >
            <RefreshCw size={13} />
            Refresh
          </button>
        </div>
      )}
    </div>
  );
};
