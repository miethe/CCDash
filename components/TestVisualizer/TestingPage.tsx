import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { useData } from '../../contexts/DataContext';
import { getTestMetricsSummary, getTestRun, invalidateTestVisualizerProjectCache, listRunResults } from '../../services/testVisualizer';
import { DomainHealthRollup, TestDefinition, TestResult, TestRun, TestRunDetail, TestStatus } from '../../types';
import { SidebarFiltersPortal } from '../SidebarFilters';
import { DomainTreeView } from './DomainTreeView';
import { HealthGauge } from './HealthGauge';
import { HealthSummaryBar } from './HealthSummaryBar';
import { TestFilters } from './TestFilters';
import { TestResultTable } from './TestResultTable';
import { TestStatusBadge } from './TestStatusBadge';
import { useTestRuns, useTestStatus, useTestVisualizerConfig } from './hooks';

const getParam = (params: URLSearchParams, camelCase: string, snakeCase: string): string | null => (
  params.get(camelCase) || params.get(snakeCase)
);

const normalizeRunStatus = (status: TestRun['status']): TestStatus => {
  if (status === 'failed') return 'failed';
  if (status === 'running') return 'running';
  return 'passed';
};

const findDomainById = (domains: DomainHealthRollup[], domainId: string): DomainHealthRollup | null => {
  for (const domain of domains) {
    if (domain.domainId === domainId) return domain;
    const child = findDomainById(domain.children, domainId);
    if (child) return child;
  }
  return null;
};

const collectDomainNameMap = (domains: DomainHealthRollup[]): Map<string, string> => {
  const map = new Map<string, string>();
  const visit = (nodes: DomainHealthRollup[]) => {
    nodes.forEach(node => {
      map.set(node.domainId, node.domainName);
      visit(node.children);
    });
  };
  visit(domains);
  return map;
};

const summarizeRoots = (domains: DomainHealthRollup[]) => {
  const totalTests = domains.reduce((sum, domain) => sum + domain.totalTests, 0);
  const passed = domains.reduce((sum, domain) => sum + domain.passed, 0);
  const failed = domains.reduce((sum, domain) => sum + domain.failed, 0);
  const skipped = domains.reduce((sum, domain) => sum + domain.skipped, 0);
  return {
    totalTests,
    passed,
    failed,
    skipped,
    passRate: totalTests > 0 ? passed / totalTests : 0,
  };
};

const toRunLabel = (run: TestRun): string => {
  const stamp = new Date(run.timestamp).toLocaleString();
  return `${stamp} • ${run.failedTests} failed • ${run.passedTests} passed • ${run.runId.slice(0, 10)}`;
};

export const TestingPage: React.FC = () => {
  const { activeProject } = useData();
  const [searchParams, setSearchParams] = useSearchParams();

  const selectedDomainId = getParam(searchParams, 'domainId', 'domain_id');
  const selectedFeatureId = getParam(searchParams, 'featureId', 'feature_id');
  const selectedRunId = getParam(searchParams, 'runId', 'run_id');

  const [statusFilter, setStatusFilter] = useState<TestStatus[]>([]);
  const [branchFilter, setBranchFilter] = useState('');
  const [runDateFrom, setRunDateFrom] = useState('');
  const [runDateTo, setRunDateTo] = useState('');
  const [draftSearchQuery, setDraftSearchQuery] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [metricTotal, setMetricTotal] = useState(0);

  const [selectedRunDetail, setSelectedRunDetail] = useState<TestRunDetail | null>(null);
  const [isRunDetailLoading, setIsRunDetailLoading] = useState(false);

  const [runResults, setRunResults] = useState<TestResult[]>([]);
  const [runResultDefinitions, setRunResultDefinitions] = useState<Record<string, TestDefinition>>({});
  const [resultsNextCursor, setResultsNextCursor] = useState<string | null>(null);
  const [resultsTotal, setResultsTotal] = useState(0);
  const [isRunResultsLoading, setIsRunResultsLoading] = useState(false);
  const [isRunResultsLoadingMore, setIsRunResultsLoadingMore] = useState(false);
  const [runResultsError, setRunResultsError] = useState<string | null>(null);
  const [resultSortKey, setResultSortKey] = useState<'status' | 'duration' | 'name' | 'test_id'>('status');
  const [resultSortOrder, setResultSortOrder] = useState<'asc' | 'desc'>('asc');
  const runResultsRequestIdRef = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchQuery(draftSearchQuery.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [draftSearchQuery]);

  const projectId = activeProject?.id || '';
  const testConfig = useTestVisualizerConfig(projectId, Boolean(projectId));
  const visualizerEnabled = Boolean(testConfig.config?.effectiveFlags?.testVisualizerEnabled);
  const status = useTestStatus(projectId, { enabled: Boolean(projectId && visualizerEnabled) });
  const runs = useTestRuns(
    projectId,
    {
      featureId: selectedFeatureId || undefined,
      domainId: selectedDomainId || undefined,
      limit: 50,
    },
    {
      enabled: Boolean(projectId && visualizerEnabled),
      refreshToken: refreshNonce,
    },
  );

  useEffect(() => {
    setSelectedRunDetail(null);
    setRunResults([]);
    setRunResultDefinitions({});
    setResultsNextCursor(null);
    setResultsTotal(0);
    setRunResultsError(null);
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !visualizerEnabled) {
      setMetricTotal(0);
      return;
    }
    let alive = true;
    const load = async () => {
      try {
        const summary = await getTestMetricsSummary(projectId);
        if (!alive) return;
        setMetricTotal(summary.totalMetrics || 0);
      } catch {
        if (!alive) return;
        setMetricTotal(0);
      }
    };
    void load();
    return () => {
      alive = false;
    };
  }, [projectId, refreshNonce, visualizerEnabled]);

  const updateQueryParam = useCallback(
    (key: 'domainId' | 'featureId' | 'runId', value: string | null) => {
      const next = new URLSearchParams(searchParams);
      next.delete(key);
      next.delete(key.replace(/[A-Z]/g, match => `_${match.toLowerCase()}`));
      if (value) {
        next.set(key, value);
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const selectedStatusesKey = useMemo(
    () => [...statusFilter].sort().join(','),
    [statusFilter],
  );

  const selectedStatusesParam = useMemo(
    () => (selectedStatusesKey ? selectedStatusesKey.split(',') : undefined),
    [selectedStatusesKey],
  );

  const filteredRuns = useMemo(() => {
    const runDateFromEpoch = runDateFrom ? Date.parse(`${runDateFrom}T00:00:00`) : Number.NEGATIVE_INFINITY;
    const runDateToEpoch = runDateTo ? Date.parse(`${runDateTo}T23:59:59.999`) : Number.POSITIVE_INFINITY;

    return [...runs.runs]
      .sort((a, b) => Date.parse(b.timestamp || '') - Date.parse(a.timestamp || ''))
      .filter(run => {
        const normalizedStatus = normalizeRunStatus(run.status);
        if (statusFilter.length > 0 && !statusFilter.includes(normalizedStatus)) {
          return false;
        }

        const runEpoch = Date.parse(run.timestamp || '');
        if (Number.isFinite(runEpoch) && (runEpoch < runDateFromEpoch || runEpoch > runDateToEpoch)) {
          return false;
        }

        if (branchFilter && !String(run.branch || '').toLowerCase().includes(branchFilter.toLowerCase())) {
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

        return haystack.includes(searchQuery.toLowerCase());
      });
  }, [branchFilter, runDateFrom, runDateTo, runs.runs, searchQuery, statusFilter]);

  useEffect(() => {
    if (runs.isLoading && runs.runs.length === 0) {
      return;
    }
    const nextRunId = filteredRuns[0]?.runId || null;
    if (selectedRunId && filteredRuns.some(run => run.runId === selectedRunId)) {
      return;
    }
    if (selectedRunId === nextRunId) {
      return;
    }
    updateQueryParam('runId', nextRunId);
  }, [filteredRuns, runs.isLoading, runs.runs.length, selectedRunId, updateQueryParam]);

  const activeRunId = selectedRunId || filteredRuns[0]?.runId || null;

  const activeRun = useMemo(() => {
    if (!activeRunId) return null;
    return filteredRuns.find(run => run.runId === activeRunId)
      || runs.runs.find(run => run.runId === activeRunId)
      || selectedRunDetail?.run
      || null;
  }, [activeRunId, filteredRuns, runs.runs, selectedRunDetail]);

  useEffect(() => {
    let alive = true;

    if (!activeRunId || !projectId) {
      setSelectedRunDetail(null);
      setIsRunDetailLoading(false);
      return;
    }

    const loadDetail = async () => {
      setIsRunDetailLoading(true);
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
  }, [activeRunId, projectId, refreshNonce]);

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
          domainId: selectedDomainId || undefined,
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
  }, [
    activeRunId,
    projectId,
    resultSortKey,
    resultSortOrder,
    searchQuery,
    selectedDomainId,
    selectedStatusesParam,
    refreshNonce,
  ]);

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
        domainId: selectedDomainId || undefined,
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

  const domainNameById = useMemo(() => collectDomainNameMap(status.domains), [status.domains]);
  const selectedDomain = useMemo(
    () => (selectedDomainId ? findDomainById(status.domains, selectedDomainId) : null),
    [selectedDomainId, status.domains],
  );

  const totals = useMemo(() => summarizeRoots(status.domains), [status.domains]);

  const viewingRunTotals = useMemo(() => {
    if (!activeRun) return totals;
    const totalTests = activeRun.totalTests;
    const passed = activeRun.passedTests;
    const failed = activeRun.failedTests;
    const skipped = activeRun.skippedTests;
    return {
      totalTests,
      passed,
      failed,
      skipped,
      passRate: totalTests > 0 ? passed / totalTests : 0,
    };
  }, [activeRun, totals]);

  const focusScopeTotals = useMemo(() => {
    if (selectedDomain) {
      return {
        totalTests: selectedDomain.totalTests,
        passed: selectedDomain.passed,
        failed: selectedDomain.failed,
        skipped: selectedDomain.skipped,
        passRate: selectedDomain.passRate,
      };
    }
    return totals;
  }, [selectedDomain, totals]);

  const breadcrumb = useMemo(() => {
    const parts = ['Testing'];
    if (selectedDomainId && domainNameById.has(selectedDomainId)) {
      parts.push(domainNameById.get(selectedDomainId) || selectedDomainId);
    }
    if (selectedFeatureId) {
      parts.push(selectedFeatureId);
    }
    return parts.join(' > ');
  }, [domainNameById, selectedDomainId, selectedFeatureId]);

  const viewingDomainLabel = selectedDomain ? selectedDomain.domainName : 'All mapped domains';

  const refreshPage = () => {
    invalidateTestVisualizerProjectCache(projectId, 'testing_page_refresh');
    testConfig.refresh();
    status.refresh();
    runs.refresh();
    setRefreshNonce(prev => prev + 1);
  };

  if (!activeProject) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-slate-300">
        Select an active project to view test status.
      </div>
    );
  }

  if (testConfig.isLoading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-slate-300">
        Loading test visualizer configuration...
      </div>
    );
  }

  if (testConfig.error) {
    return (
      <div className="rounded-xl border border-rose-600/40 bg-rose-600/10 p-6 text-rose-200">
        Failed to load test visualizer configuration: {testConfig.error.message}
      </div>
    );
  }

  if (!visualizerEnabled) {
    return (
      <div className="rounded-xl border border-amber-500/35 bg-amber-500/10 p-6 text-amber-100">
        <p className="text-sm font-semibold">Test Visualizer is disabled for this project.</p>
        <p className="mt-2 text-sm text-amber-200/90">
          Enable it in Settings - Projects - Testing, then click Refresh.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Test Visualizer</h1>
            <p className="text-sm text-slate-400">{breadcrumb}</p>
            {activeRun && (
              <p className="mt-1 text-xs text-indigo-300">
                Viewing run <span className="font-mono">{activeRun.runId}</span>
                {' • '}
                {new Date(activeRun.timestamp).toLocaleString()}
                {isRunDetailLoading ? ' • loading details...' : ''}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <span className="uppercase tracking-wider text-slate-500">Recent Run</span>
              <select
                value={activeRunId || ''}
                onChange={event => updateQueryParam('runId', event.target.value || null)}
                className="max-w-[420px] rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                disabled={filteredRuns.length === 0}
              >
                {filteredRuns.length === 0 && <option value="">No runs available</option>}
                {filteredRuns.map(run => (
                  <option key={run.runId} value={run.runId}>
                    {toRunLabel(run)}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              onClick={refreshPage}
              className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 hover:border-slate-600"
            >
              <RefreshCw size={13} />
              Refresh
            </button>
          </div>
        </div>
      </header>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(280px,1fr)]">
        <article className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-slate-200">Run Details</h2>
            {runs.isLoading && <span className="text-xs text-slate-500">Refreshing runs...</span>}
          </div>

          {!activeRun && (
            <p className="mt-3 text-sm text-slate-500">
              No runs match the current filters. Adjust filters or refresh to load the latest run.
            </p>
          )}

          {activeRun && (
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <TestStatusBadge status={normalizeRunStatus(activeRun.status)} size="sm" />
                <span className="font-mono text-slate-200">{activeRun.runId}</span>
                <span>{new Date(activeRun.timestamp).toLocaleString()}</span>
                {activeRun.gitSha && (
                  <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                    {activeRun.gitSha.slice(0, 12)}
                  </span>
                )}
                {activeRun.branch && (
                  <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                    {activeRun.branch}
                  </span>
                )}
                {activeRun.agentSessionId && (
                  <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                    session: {activeRun.agentSessionId}
                  </span>
                )}
              </div>
              <HealthSummaryBar
                passed={activeRun.passedTests}
                failed={activeRun.failedTests}
                skipped={activeRun.skippedTests}
                total={activeRun.totalTests}
                className="pt-1"
              />
              {runs.error && <p className="text-xs text-rose-300">{runs.error.message}</p>}
            </div>
          )}
        </article>

        <aside className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Test Health Metrics</p>
          <div className="mt-3 flex items-center justify-between gap-4">
            <HealthGauge passRate={viewingRunTotals.passRate} size="sm" />
            <div className="text-right text-xs text-slate-400">
              <p>
                <span className="font-medium text-emerald-400">{viewingRunTotals.passed}</span> passing
              </p>
              <p>
                <span className="font-medium text-rose-400">{viewingRunTotals.failed}</span> failing
              </p>
              <p>
                <span className="font-medium text-amber-300">{viewingRunTotals.skipped}</span> skipped
              </p>
              <p>
                <span className="font-medium text-slate-200">{viewingRunTotals.totalTests}</span> tests in scope
              </p>
              <p>
                <span className="font-medium text-indigo-300">{metricTotal}</span> collected metrics
              </p>
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Scope: <span className="text-slate-300">{viewingDomainLabel}</span>
          </p>
        </aside>
      </section>

      {status.error && (
        <div className="rounded-xl border border-rose-500/35 bg-rose-500/10 p-3 text-sm text-rose-200">
          <p className="inline-flex items-center gap-2">
            <AlertCircle size={14} /> {status.error.message}
          </p>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="h-[38rem] overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-3">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Mapped Domains</h2>
          <DomainTreeView
            domains={status.domains}
            selectedDomainId={selectedDomainId}
            onSelectDomain={domain => updateQueryParam('domainId', domain?.domainId || null)}
            className="border-0 bg-transparent p-0"
          />
        </aside>

        <section className="min-w-0 space-y-4">
          <article className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-slate-200">
                  {selectedDomain ? `Domain Status: ${selectedDomain.domainName}` : 'Overall App Status'}
                </h2>
                <p className="text-xs text-slate-400">
                  {selectedDomain
                    ? `Tier: ${selectedDomain.tier}. Drill into mapped sub-domains below.`
                    : 'Select a mapped domain to focus on domain-specific test health and results.'}
                </p>
              </div>
              {status.lastFetchedAt && (
                <p className="text-xs text-slate-500">Updated {status.lastFetchedAt.toLocaleTimeString()}</p>
              )}
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-[auto_minmax(0,1fr)]">
              <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                <HealthGauge
                  passRate={focusScopeTotals.passRate}
                  integrityScore={selectedDomain?.integrityScore}
                  size="md"
                />
              </div>

              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-4">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-400">
                    <p className="text-slate-500">Total</p>
                    <p className="text-sm font-semibold text-slate-100">{focusScopeTotals.totalTests}</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-400">
                    <p className="text-slate-500">Passing</p>
                    <p className="text-sm font-semibold text-emerald-400">{focusScopeTotals.passed}</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-400">
                    <p className="text-slate-500">Failing</p>
                    <p className="text-sm font-semibold text-rose-400">{focusScopeTotals.failed}</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-400">
                    <p className="text-slate-500">Skipped</p>
                    <p className="text-sm font-semibold text-amber-300">{focusScopeTotals.skipped}</p>
                  </div>
                </div>

                <HealthSummaryBar
                  passed={focusScopeTotals.passed}
                  failed={focusScopeTotals.failed}
                  skipped={focusScopeTotals.skipped}
                  total={focusScopeTotals.totalTests}
                />
              </div>
            </div>
          </article>

          <article className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-200">Domain Drilldown</h3>
              <span className="text-xs text-slate-500">
                {selectedDomain ? `${selectedDomain.children.length} sub-domains` : `${status.domains.length} top-level domains`}
              </span>
            </div>

            {!selectedDomain && (
              <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {status.domains.map(domain => (
                  <button
                    key={domain.domainId}
                    type="button"
                    onClick={() => updateQueryParam('domainId', domain.domainId)}
                    className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-left text-xs text-slate-300 hover:border-slate-700"
                  >
                    <p className="font-medium text-slate-200">{domain.domainName}</p>
                    <p className="mt-1 text-slate-500">{domain.totalTests} tests • {Math.round(domain.passRate * 100)}% pass rate</p>
                  </button>
                ))}
                {status.domains.length === 0 && <p className="text-sm text-slate-500">No mapped domains found.</p>}
              </div>
            )}

            {selectedDomain && (
              <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {selectedDomain.children.map(child => (
                  <button
                    key={child.domainId}
                    type="button"
                    onClick={() => updateQueryParam('domainId', child.domainId)}
                    className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-left text-xs text-slate-300 hover:border-slate-700"
                  >
                    <p className="font-medium text-slate-200">{child.domainName}</p>
                    <p className="mt-1 text-slate-500">{child.totalTests} tests • {Math.round(child.passRate * 100)}% pass rate</p>
                  </button>
                ))}
                {selectedDomain.children.length === 0 && (
                  <p className="text-sm text-slate-500">No mapped sub-domains for this selection.</p>
                )}
              </div>
            )}
          </article>

          <section className="space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-slate-200">Test Details</h2>
                <p className="text-xs text-slate-400">
                  Viewing domain: <span className="text-slate-200">{viewingDomainLabel}</span>
                  {activeRun && (
                    <>
                      {' • '}run <span className="font-mono text-slate-200">{activeRun.runId}</span>
                    </>
                  )}
                </p>
              </div>
              <div className="text-xs text-slate-500">
                {runResults.length} loaded / {resultsTotal} total
                {' '}
                (out of {activeRun?.totalTests || totals.totalTests} total tests)
              </div>
            </div>

            <div className="h-[38rem] overflow-y-auto">
              <TestResultTable
                results={runResults}
                definitions={runResultDefinitions}
                isLoading={isRunResultsLoading || isRunDetailLoading}
                isLoadingMore={isRunResultsLoadingMore}
                total={resultsTotal}
                totalTestsOverall={activeRun?.totalTests || totals.totalTests}
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
            </div>
          </section>
        </section>
      </div>

      <SidebarFiltersPortal>
        <TestFilters
          statusFilter={statusFilter}
          onStatusChange={setStatusFilter}
          searchQuery={draftSearchQuery}
          onSearchChange={setDraftSearchQuery}
          branchFilter={branchFilter}
          onBranchFilterChange={setBranchFilter}
          runDateFrom={runDateFrom}
          onRunDateFromChange={setRunDateFrom}
          runDateTo={runDateTo}
          onRunDateToChange={setRunDateTo}
        />
      </SidebarFiltersPortal>
    </div>
  );
};
