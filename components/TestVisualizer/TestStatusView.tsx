import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertCircle, ArrowRight, RefreshCw } from 'lucide-react';

import { FeatureTestTimeline, TestDefinition, TestRun, TestRunDetail, TestStatus } from '../../types';
import { getFeatureTimeline, getIntegrityAlerts, getTestRun, listRunResults } from '../../services/testVisualizer';
import { DomainTreeView } from './DomainTreeView';
import { HealthGauge } from './HealthGauge';
import { HealthSummaryBar } from './HealthSummaryBar';
import { IntegrityAlertCard } from './IntegrityAlertCard';
import { TestResultTable } from './TestResultTable';
import { TestRunCard } from './TestRunCard';
import { TestStatusBadge } from './TestStatusBadge';
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
  onRunSelect?: (runId: string) => void;
  onRunSelectionChange?: (selection: {
    run: TestRun | null;
    detail: TestRunDetail | null;
    isLoading: boolean;
  }) => void;
  hideHeader?: boolean;
  showDomainTree?: boolean;
  uiFilter?: {
    statuses?: TestStatus[];
    searchQuery?: string;
    branch?: string;
    runDateFrom?: string;
    runDateTo?: string;
  };
}

const EMPTY_STATUSES: TestStatus[] = [];

export const TestStatusView: React.FC<TestStatusViewProps> = ({
  projectId,
  filter,
  mode,
  isLive = false,
  onNavigateToTestingPage,
  onRunSelect,
  onRunSelectionChange,
  hideHeader = false,
  showDomainTree = true,
  uiFilter,
}) => {
  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(filter?.domainId ?? null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(filter?.runId ?? null);
  const [selectedRunDetail, setSelectedRunDetail] = useState<TestRunDetail | null>(null);
  const [isRunDetailLoading, setIsRunDetailLoading] = useState(false);
  const [timeline, setTimeline] = useState<FeatureTestTimeline | null>(null);
  const [timelineError, setTimelineError] = useState<Error | null>(null);
  const [alerts, setAlerts] = useState<Awaited<ReturnType<typeof getIntegrityAlerts>>['items']>([]);
  const [runResults, setRunResults] = useState<TestRunDetail['results']>([]);
  const [runResultDefinitions, setRunResultDefinitions] = useState<Record<string, TestDefinition>>({});
  const [resultsNextCursor, setResultsNextCursor] = useState<string | null>(null);
  const [resultsTotal, setResultsTotal] = useState(0);
  const [isRunResultsLoading, setIsRunResultsLoading] = useState(false);
  const [isRunResultsLoadingMore, setIsRunResultsLoadingMore] = useState(false);
  const [runResultsError, setRunResultsError] = useState<string | null>(null);
  const [resultSortKey, setResultSortKey] = useState<'status' | 'duration' | 'name' | 'test_id'>('status');
  const [resultSortOrder, setResultSortOrder] = useState<'asc' | 'desc'>('asc');
  const runResultsRequestIdRef = useRef(0);

  const shouldFetchStatus = showDomainTree || !hideHeader;
  const status = useTestStatus(projectId, { enabled: Boolean(projectId && shouldFetchStatus) });
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

  useEffect(() => {
    setSelectedDomainId(filter?.domainId ?? null);
  }, [filter?.domainId]);

  useEffect(() => {
    setSelectedRunDetail(null);
    setSelectedRunId(null);
    setRunResults([]);
    setRunResultDefinitions({});
    setResultsNextCursor(null);
    setResultsTotal(0);
    setRunResultsError(null);
    setResultSortKey('status');
    setResultSortOrder('asc');
  }, [projectId]);

  const selectedStatuses = uiFilter?.statuses ?? EMPTY_STATUSES;
  const selectedStatusesKey = useMemo(
    () => [...selectedStatuses].sort().join(','),
    [selectedStatuses],
  );
  const selectedStatusesParam = useMemo(
    () => (selectedStatusesKey ? selectedStatusesKey.split(',') : undefined),
    [selectedStatusesKey],
  );
  const searchQuery = (uiFilter?.searchQuery || '').trim().toLowerCase();
  const branchFilter = (uiFilter?.branch || '').trim().toLowerCase();
  const runDateFrom = (uiFilter?.runDateFrom || '').trim();
  const runDateTo = (uiFilter?.runDateTo || '').trim();

  const filteredRuns = useMemo(() => {
    const runDateFromEpoch = runDateFrom ? Date.parse(`${runDateFrom}T00:00:00`) : Number.NEGATIVE_INFINITY;
    const runDateToEpoch = runDateTo ? Date.parse(`${runDateTo}T23:59:59.999`) : Number.POSITIVE_INFINITY;

    return runs.runs.filter(run => {
      const normalizedStatus: TestStatus = run.status === 'failed'
        ? 'failed'
        : run.status === 'running'
          ? 'running'
          : 'passed';
      if (selectedStatuses.length > 0 && !selectedStatuses.includes(normalizedStatus)) {
        return false;
      }

      const runEpoch = Date.parse(run.timestamp || '');
      if (Number.isFinite(runEpoch)) {
        if (runEpoch < runDateFromEpoch || runEpoch > runDateToEpoch) {
          return false;
        }
      }

      if (branchFilter && !String(run.branch || '').toLowerCase().includes(branchFilter)) {
        return false;
      }

      if (!searchQuery) return true;
      const haystack = [
        run.runId,
        run.gitSha,
        run.branch,
        run.agentSessionId,
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(searchQuery);
    });
  }, [branchFilter, runDateFrom, runDateTo, runs.runs, searchQuery, selectedStatuses]);

  useEffect(() => {
    if (filter?.runId) {
      setSelectedRunId(filter.runId);
      return;
    }

    if (filteredRuns.length === 0) {
      setSelectedRunId(null);
      return;
    }

    if (selectedRunId && filteredRuns.some(run => run.runId === selectedRunId)) {
      return;
    }
    setSelectedRunId(filteredRuns[0].runId);
  }, [filter?.runId, filteredRuns, selectedRunId]);

  const activeRunId = filter?.runId ?? selectedRunId ?? filteredRuns[0]?.runId ?? null;

  const activeRun = useMemo(() => {
    if (!activeRunId) return null;
    return filteredRuns.find(run => run.runId === activeRunId)
      || runs.runs.find(run => run.runId === activeRunId)
      || null;
  }, [activeRunId, filteredRuns, runs.runs]);
  const resolvedActiveRun = activeRun || selectedRunDetail?.run || null;

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

    if (!activeRunId) {
      setSelectedRunDetail(null);
      setIsRunDetailLoading(false);
      return;
    }

    const loadDetail = async () => {
      setIsRunDetailLoading(true);
      setSelectedRunDetail(null);
      try {
        const detail = await getTestRun(activeRunId, projectId, { includeResults: false });
        if (!alive) return;
        setSelectedRunDetail(detail);
      } catch {
        if (!alive) return;
        setSelectedRunDetail(null);
      } finally {
        if (alive) {
          setIsRunDetailLoading(false);
        }
      }
    };

    void loadDetail();
    return () => {
      alive = false;
    };
  }, [activeRunId, projectId]);

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

  useEffect(() => {
    if (!activeRunId || !projectId) {
      runResultsRequestIdRef.current += 1;
      setRunResults([]);
      setRunResultDefinitions({});
      setResultsNextCursor(null);
      setResultsTotal(0);
      setRunResultsError(null);
      setIsRunResultsLoading(false);
      setIsRunResultsLoadingMore(false);
      return;
    }

    const requestId = runResultsRequestIdRef.current + 1;
    runResultsRequestIdRef.current = requestId;

    setIsRunResultsLoading(true);
    setRunResultsError(null);
    setRunResults([]);
    setRunResultDefinitions({});
    setResultsNextCursor(null);

    const loadFirstPage = async () => {
      try {
        const payload = await listRunResults({
          runId: activeRunId,
          projectId,
          statuses: selectedStatusesParam,
          query: searchQuery || undefined,
          sortBy: resultSortKey,
          sortOrder: resultSortOrder,
          limit: 150,
        });
        if (runResultsRequestIdRef.current !== requestId) return;
        setRunResults(payload.items || []);
        setRunResultDefinitions(payload.definitions || {});
        setResultsNextCursor(payload.nextCursor || null);
        setResultsTotal(payload.total || 0);
      } catch (err) {
        if (runResultsRequestIdRef.current !== requestId) return;
        setRunResults([]);
        setRunResultDefinitions({});
        setResultsNextCursor(null);
        setResultsTotal(0);
        setRunResultsError(err instanceof Error ? err.message : 'Failed to load run results');
      } finally {
        if (runResultsRequestIdRef.current === requestId) {
          setIsRunResultsLoading(false);
        }
      }
    };

    void loadFirstPage();
  }, [activeRunId, projectId, resultSortKey, resultSortOrder, searchQuery, selectedStatusesParam]);

  const loadMoreRunResults = async () => {
    if (!activeRunId || !projectId || !resultsNextCursor || isRunResultsLoadingMore) {
      return;
    }

    const requestId = runResultsRequestIdRef.current;
    setIsRunResultsLoadingMore(true);
    setRunResultsError(null);
    try {
      const payload = await listRunResults({
        runId: activeRunId,
        projectId,
        statuses: selectedStatusesParam,
        query: searchQuery || undefined,
        sortBy: resultSortKey,
        sortOrder: resultSortOrder,
        cursor: resultsNextCursor,
        limit: 150,
      });
      if (runResultsRequestIdRef.current !== requestId) return;
      setRunResults(prev => [...prev, ...(payload.items || [])]);
      setRunResultDefinitions(prev => ({ ...prev, ...(payload.definitions || {}) }));
      setResultsNextCursor(payload.nextCursor || null);
      setResultsTotal(payload.total || 0);
    } catch (err) {
      if (runResultsRequestIdRef.current !== requestId) return;
      setRunResultsError(err instanceof Error ? err.message : 'Failed to load more run results');
    } finally {
      if (runResultsRequestIdRef.current === requestId) {
        setIsRunResultsLoadingMore(false);
      }
    }
  };

  useEffect(() => {
    onRunSelectionChange?.({
      run: resolvedActiveRun,
      detail: selectedRunDetail,
      isLoading: isRunDetailLoading,
    });
  }, [resolvedActiveRun, isRunDetailLoading, onRunSelectionChange, selectedRunDetail]);

  const showSplitLayout = mode === 'full' && showDomainTree;

  return (
    <section className="space-y-4">
      {!hideHeader && (
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
      )}

      {status.error && (
        <div className="rounded-xl border border-rose-500/35 bg-rose-500/10 p-3 text-sm text-rose-200">
          <p className="inline-flex items-center gap-2">
            <AlertCircle size={14} /> {status.error.message}
          </p>
        </div>
      )}

      <div className={`grid gap-4 ${showSplitLayout ? 'lg:grid-cols-[320px_1fr]' : 'grid-cols-1'}`}>
        {showDomainTree && (
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
        )}

        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-300">Recent Runs</h3>
              {resolvedActiveRun && (
                <p className="text-xs text-indigo-300">
                  Viewing run <span className="font-mono">{resolvedActiveRun.runId}</span>
                </p>
              )}
              {filteredRuns.map(run => (
                <TestRunCard
                  key={run.runId}
                  run={run}
                  showSession
                  compact={mode === 'compact'}
                  selected={activeRunId === run.runId}
                  onSelect={nextRun => {
                    setSelectedRunId(nextRun.runId);
                    onRunSelect?.(nextRun.runId);
                  }}
                />
              ))}
              {filteredRuns.length === 0 && (
                <p className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
                  No runs match the current filters.
                </p>
              )}
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
              <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-slate-200">Run Details</h3>
                  {isRunDetailLoading && (
                    <span className="text-xs text-indigo-300">Loading selected run...</span>
                  )}
                </div>
                {resolvedActiveRun ? (
                  <div className="mt-3 space-y-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      <TestStatusBadge
                        status={resolvedActiveRun.status === 'failed' ? 'failed' : resolvedActiveRun.status === 'running' ? 'running' : 'passed'}
                        size="sm"
                      />
                      <span className="font-mono text-slate-200">{resolvedActiveRun.runId}</span>
                      <span>{new Date(resolvedActiveRun.timestamp).toLocaleString()}</span>
                      {resolvedActiveRun.gitSha && (
                        <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                          {resolvedActiveRun.gitSha.slice(0, 12)}
                        </span>
                      )}
                      {resolvedActiveRun.branch && (
                        <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                          {resolvedActiveRun.branch}
                        </span>
                      )}
                    </div>
                    <HealthSummaryBar
                      passed={resolvedActiveRun.passedTests}
                      failed={resolvedActiveRun.failedTests}
                      skipped={resolvedActiveRun.skippedTests}
                      total={resolvedActiveRun.totalTests}
                      className="pt-1"
                    />
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-slate-500">Select a run to view details.</p>
                )}
              </div>
              <TestResultTable
                results={runResults}
                definitions={runResultDefinitions}
                isLoading={isRunResultsLoading || isRunDetailLoading}
                isLoadingMore={isRunResultsLoadingMore}
                total={resultsTotal}
                error={runResultsError}
                hasMore={Boolean(resultsNextCursor)}
                onLoadMore={loadMoreRunResults}
                sortKey={resultSortKey}
                sortOrder={resultSortOrder}
                onSortChange={(sortKey, sortOrder) => {
                  setResultSortKey(sortKey);
                  setResultSortOrder(sortOrder);
                }}
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
