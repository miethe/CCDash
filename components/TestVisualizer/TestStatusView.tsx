import React, { useEffect, useMemo, useState } from 'react';
import { Activity, AlertCircle, ArrowRight, RefreshCw } from 'lucide-react';

import { FeatureTestTimeline, TestRunDetail } from '../../types';
import { getFeatureTimeline, getIntegrityAlerts, getTestRun } from '../../services/testVisualizer';
import { DomainTreeView } from './DomainTreeView';
import { HealthGauge } from './HealthGauge';
import { IntegrityAlertCard } from './IntegrityAlertCard';
import { TestResultTable } from './TestResultTable';
import { TestRunCard } from './TestRunCard';
import { TestTimeline } from './TestTimeline';
import { useLiveTestUpdates, useTestRuns, useTestStatus } from './hooks';

interface TestStatusViewProps {
  projectId: string;
  filter?: {
    featureId?: string;
    sessionId?: string;
    domainId?: string;
    runId?: string;
  };
  mode: 'full' | 'compact' | 'tab';
  isLive?: boolean;
  onNavigateToTestingPage?: () => void;
}

export const TestStatusView: React.FC<TestStatusViewProps> = ({
  projectId,
  filter,
  mode,
  isLive = false,
  onNavigateToTestingPage,
}) => {
  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(filter?.domainId ?? null);
  const [selectedRunDetail, setSelectedRunDetail] = useState<TestRunDetail | null>(null);
  const [timeline, setTimeline] = useState<FeatureTestTimeline | null>(null);
  const [timelineError, setTimelineError] = useState<Error | null>(null);
  const [alerts, setAlerts] = useState<Awaited<ReturnType<typeof getIntegrityAlerts>>['items']>([]);

  const status = useTestStatus(projectId, { enabled: Boolean(projectId) });
  const runs = useTestRuns(projectId, {
    featureId: filter?.featureId,
    agentSessionId: filter?.sessionId,
    limit: mode === 'compact' ? 3 : 12,
  });
  const live = useLiveTestUpdates(
    projectId,
    {
      runId: filter?.runId,
      featureId: filter?.featureId,
      sessionId: filter?.sessionId,
    },
    {
      enabled: isLive,
    },
  );

  const topDomain = useMemo(() => {
    const roots = status.domains;
    if (roots.length === 0) return null;
    const total = roots.reduce((sum, domain) => sum + domain.totalTests, 0);
    const passed = roots.reduce((sum, domain) => sum + domain.passed, 0);
    const integrity = roots.reduce((sum, domain) => sum + domain.integrityScore, 0) / roots.length;
    return {
      passRate: total > 0 ? passed / total : 0,
      integrityScore: Number.isFinite(integrity) ? integrity : 0,
      totalTests: total,
    };
  }, [status.domains]);

  useEffect(() => {
    let alive = true;

    const runId = filter?.runId || runs.runs[0]?.runId;
    if (!runId) {
      setSelectedRunDetail(null);
      return;
    }

    const loadDetail = async () => {
      try {
        const detail = await getTestRun(runId, projectId);
        if (!alive) return;
        setSelectedRunDetail(detail);
      } catch {
        if (!alive) return;
        setSelectedRunDetail(null);
      }
    };

    loadDetail();
    return () => {
      alive = false;
    };
  }, [filter?.runId, projectId, runs.runs]);

  useEffect(() => {
    let alive = true;

    const loadAlerts = async () => {
      try {
        const payload = await getIntegrityAlerts(projectId, {
          agentSessionId: filter?.sessionId,
          limit: mode === 'compact' ? 3 : 6,
        });
        if (!alive) return;
        setAlerts(payload.items);
      } catch {
        if (!alive) return;
        setAlerts([]);
      }
    };

    loadAlerts();
    return () => {
      alive = false;
    };
  }, [filter?.sessionId, mode, projectId]);

  useEffect(() => {
    let alive = true;

    const loadTimeline = async () => {
      if (!filter?.featureId) {
        setTimeline(null);
        setTimelineError(null);
        return;
      }

      try {
        const payload = await getFeatureTimeline(filter.featureId, projectId, { includeSignals: true });
        if (!alive) return;
        setTimeline(payload);
        setTimelineError(null);
      } catch (err) {
        if (!alive) return;
        setTimeline(null);
        setTimelineError(err instanceof Error ? err : new Error('Failed to load timeline'));
      }
    };

    loadTimeline();
    return () => {
      alive = false;
    };
  }, [filter?.featureId, projectId]);

  return (
    <section className="space-y-4">
      <header className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Test Status</h2>
            <p className="text-sm text-slate-400">Shared status panel for features, sessions, and the testing page.</p>
          </div>
          <div className="flex items-center gap-2">
            {isLive && (
              <span className="inline-flex items-center gap-1 rounded border border-indigo-500/40 bg-indigo-500/10 px-2 py-1 text-xs font-semibold text-indigo-300">
                <Activity size={12} />
                LIVE
              </span>
            )}
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 hover:border-slate-600"
              onClick={status.refresh}
            >
              <RefreshCw size={12} /> Refresh
            </button>
            {onNavigateToTestingPage && (
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded border border-indigo-500/35 bg-indigo-500/10 px-3 py-2 text-xs font-semibold text-indigo-300 hover:bg-indigo-500/20"
                onClick={onNavigateToTestingPage}
              >
                Open Testing Page <ArrowRight size={12} />
              </button>
            )}
          </div>
        </div>
      </header>

      {status.error && (
        <div className="rounded-xl border border-rose-500/35 bg-rose-500/10 p-3 text-sm text-rose-200">
          <p className="inline-flex items-center gap-2">
            <AlertCircle size={14} /> {status.error.message}
          </p>
        </div>
      )}

      <div className={`grid gap-4 ${mode === 'full' ? 'lg:grid-cols-[320px_1fr]' : 'grid-cols-1'}`}>
        <aside className="space-y-4">
          {topDomain && (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-500">Global Health</p>
              <div className="mt-3 flex items-center justify-between">
                <HealthGauge passRate={topDomain.passRate} integrityScore={topDomain.integrityScore} size="md" />
                <div className="text-right text-xs text-slate-400">
                  <p>{topDomain.totalTests.toLocaleString()} tests</p>
                  {live.lastUpdated && <p>Updated {live.lastUpdated.toLocaleTimeString()}</p>}
                </div>
              </div>
            </div>
          )}

          <DomainTreeView
            domains={status.domains}
            selectedDomainId={selectedDomainId}
            onSelectDomain={domain => setSelectedDomainId(domain?.domainId ?? null)}
          />
        </aside>

        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-300">Recent Runs</h3>
              {runs.runs.map(run => (
                <TestRunCard key={run.runId} run={run} showSession compact={mode === 'compact'} />
              ))}
              {runs.error && <p className="text-sm text-rose-300">{runs.error.message}</p>}
              {runs.hasMore && mode !== 'compact' && (
                <button
                  type="button"
                  onClick={runs.loadMore}
                  className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 hover:border-slate-600"
                >
                  Load more
                </button>
              )}
            </div>

            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-300">Integrity Alerts</h3>
              {alerts.length === 0 && <p className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">No alerts.</p>}
              {alerts.map(signal => (
                <IntegrityAlertCard key={signal.signalId} signal={signal} />
              ))}
            </div>
          </div>

          {mode !== 'compact' && (
            <>
              <TestResultTable
                results={selectedRunDetail?.results || []}
                definitions={selectedRunDetail?.definitions || {}}
                isLoading={runs.isLoading || status.isLoading}
              />
              {filter?.featureId && <TestTimeline timeline={timeline} />}
              {timelineError && <p className="text-sm text-rose-300">{timelineError.message}</p>}
            </>
          )}
        </div>
      </div>
    </section>
  );
};

export type { TestStatusViewProps };
