import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { useData } from '../../contexts/DataContext';
import { TestStatus } from '../../types';
import { SidebarFiltersPortal } from '../SidebarFilters';
import { DomainTreeView } from './DomainTreeView';
import { HealthGauge } from './HealthGauge';
import { TestFilters } from './TestFilters';
import { TestStatusView } from './TestStatusView';
import { useTestStatus } from './hooks';

const getParam = (params: URLSearchParams, camelCase: string, snakeCase: string): string | null => (
  params.get(camelCase) || params.get(snakeCase)
);

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

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchQuery(draftSearchQuery.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [draftSearchQuery]);

  const projectId = activeProject?.id || '';
  const status = useTestStatus(projectId, { enabled: Boolean(projectId) });

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

  const onSelectDomain = useCallback(
    (domainId: string | null) => {
      updateQueryParam('domainId', domainId);
    },
    [updateQueryParam],
  );

  const domainNameById = useMemo(() => {
    const mapping = new Map<string, string>();
    const visit = (nodes: typeof status.domains) => {
      nodes.forEach(node => {
        mapping.set(node.domainId, node.domainName);
        visit(node.children);
      });
    };
    visit(status.domains);
    return mapping;
  }, [status.domains]);

  const totals = useMemo(() => {
    const totalTests = status.domains.reduce((sum, domain) => sum + domain.totalTests, 0);
    const passed = status.domains.reduce((sum, domain) => sum + domain.passed, 0);
    const failed = status.domains.reduce((sum, domain) => sum + domain.failed, 0);
    const skipped = status.domains.reduce((sum, domain) => sum + domain.skipped, 0);
    return {
      totalTests,
      passed,
      failed,
      skipped,
      passRate: totalTests > 0 ? passed / totalTests : 0,
    };
  }, [status.domains]);

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

  const refreshPage = () => {
    status.refresh();
    setRefreshNonce(prev => prev + 1);
  };

  if (!activeProject) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-slate-300">
        Select an active project to view test status.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <header className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Test Visualizer</h1>
            <p className="text-sm text-slate-400">{breadcrumb}</p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <HealthGauge passRate={totals.passRate} size="sm" />
            <div className="text-slate-400">
              <span className="font-medium text-emerald-400">{totals.passed}</span> passing
              {' • '}
              <span className="font-medium text-rose-400">{totals.failed}</span> failing
              {' • '}
              <span className="font-medium text-slate-300">{totals.totalTests}</span> total
              {totals.skipped > 0 && (
                <>
                  {' • '}
                  <span className="font-medium text-amber-300">{totals.skipped}</span> skipped
                </>
              )}
            </div>
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

      <div className="flex min-h-0 flex-1 gap-4">
        <aside className="w-72 shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-3">
          <DomainTreeView
            domains={status.domains}
            selectedDomainId={selectedDomainId}
            onSelectDomain={domain => onSelectDomain(domain?.domainId || null)}
            className="border-0 bg-transparent p-0"
          />
        </aside>

        <div className="min-w-0 flex-1">
          <TestStatusView
            key={`tests-${refreshNonce}-${selectedDomainId || ''}-${selectedFeatureId || ''}-${selectedRunId || ''}`}
            projectId={activeProject.id}
            filter={{
              domainId: selectedDomainId || undefined,
              featureId: selectedFeatureId || undefined,
              runId: selectedRunId || undefined,
            }}
            mode="full"
            hideHeader
            showDomainTree={false}
            uiFilter={{
              statuses: statusFilter,
              searchQuery,
              branch: branchFilter,
              runDateFrom,
              runDateTo,
            }}
          />
        </div>
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
