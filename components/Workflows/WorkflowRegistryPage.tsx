import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { Blocks, FolderKanban, RefreshCcw, Sparkles } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';

import { useData } from '../../contexts/DataContext';
import {
  WorkflowRegistryAction,
  WorkflowRegistryCorrelationState,
  WorkflowRegistryDetail,
  WorkflowRegistryListResponse,
} from '../../types';
import { isWorkflowAnalyticsEnabled } from '../../services/agenticIntelligence';
import {
  WorkflowRegistryApiError,
  buildWorkflowRegistryPath,
  decodeWorkflowRegistryRouteParam,
  workflowRegistryService,
} from '../../services/workflows';
import { WorkflowCatalog } from './catalog/WorkflowCatalog';
import { WorkflowDetailPanel } from './detail/WorkflowDetailPanel';
import { formatInteger, runWorkflowRegistryAction } from './workflowRegistryUtils';

const formatLoadError = (err: unknown, fallback: string): string => {
  if (err instanceof WorkflowRegistryApiError) {
    return `${err.message}${err.hint ? ` ${err.hint}` : ''}`.trim();
  }
  return err instanceof Error ? err.message : fallback;
};

const SummaryTile: React.FC<{
  label: string;
  value: string;
  caption: string;
}> = ({ label, value, caption }) => (
  <div className="rounded-2xl border border-slate-800/80 bg-slate-950/50 px-4 py-4">
    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
    <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-100">{value}</div>
    <div className="mt-1 text-xs text-slate-500">{caption}</div>
  </div>
);

export const WorkflowRegistryPage: React.FC = () => {
  const navigate = useNavigate();
  const params = useParams<{ workflowId?: string }>();
  const { activeProject } = useData();

  const selectedWorkflowId = useMemo(
    () => decodeWorkflowRegistryRouteParam(params.workflowId || ''),
    [params.workflowId],
  );
  const workflowAnalyticsAvailable = isWorkflowAnalyticsEnabled(activeProject);

  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<WorkflowRegistryCorrelationState | 'all'>('all');
  const [catalogPayload, setCatalogPayload] = useState<WorkflowRegistryListResponse | null>(null);
  const [detail, setDetail] = useState<WorkflowRegistryDetail | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [catalogError, setCatalogError] = useState('');
  const [detailError, setDetailError] = useState('');
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const catalogRequestIdRef = useRef(0);
  const detailRequestIdRef = useRef(0);

  const deferredSearch = useDeferredValue(searchQuery.trim());

  const loadCatalog = async () => {
    const requestId = ++catalogRequestIdRef.current;
    setCatalogLoading(true);
    setCatalogError('');
    try {
      const payload = await workflowRegistryService.list({
        search: deferredSearch || undefined,
        offset: 0,
        limit: 200,
      });
      if (requestId !== catalogRequestIdRef.current) return;
      setCatalogPayload(payload);
    } catch (err) {
      if (requestId !== catalogRequestIdRef.current) return;
      setCatalogPayload(null);
      setCatalogError(formatLoadError(err, 'Failed to load workflow registry'));
    } finally {
      if (requestId === catalogRequestIdRef.current) {
        setCatalogLoading(false);
      }
    }
  };

  const loadDetail = async (registryId: string) => {
    const requestId = ++detailRequestIdRef.current;
    setDetailLoading(true);
    setDetailError('');
    try {
      const payload = await workflowRegistryService.getDetail(registryId);
      if (requestId !== detailRequestIdRef.current) return;
      setDetail(payload.item);
    } catch (err) {
      if (requestId !== detailRequestIdRef.current) return;
      setDetail(null);
      setDetailError(formatLoadError(err, 'Failed to load workflow detail'));
    } finally {
      if (requestId === detailRequestIdRef.current) {
        setDetailLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!workflowAnalyticsAvailable || !activeProject?.id) {
      setCatalogLoading(false);
      setDetailLoading(false);
      setCatalogPayload(null);
      setDetail(null);
      setCatalogError('');
      setDetailError('');
      return;
    }
    void loadCatalog();
  }, [activeProject?.id, deferredSearch, workflowAnalyticsAvailable]);

  useEffect(() => {
    if (!selectedWorkflowId || !workflowAnalyticsAvailable || !activeProject?.id) {
      setDetail(null);
      setDetailError('');
      setDetailLoading(false);
      return;
    }
    void loadDetail(selectedWorkflowId);
  }, [activeProject?.id, selectedWorkflowId, workflowAnalyticsAvailable]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTypingTarget = Boolean(
        target &&
          (target.tagName === 'INPUT' ||
            target.tagName === 'TEXTAREA' ||
            target.isContentEditable),
      );
      if (isTypingTarget) return;
      if (event.key === '/' || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k')) {
        event.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const catalogItems = catalogPayload?.items || [];
  const correlationCounts = catalogPayload?.correlationCounts || {
    strong: 0,
    hybrid: 0,
    weak: 0,
    unresolved: 0,
  };
  const visibleCatalogItems = useMemo(
    () => (
      activeFilter === 'all'
        ? catalogItems
        : catalogItems.filter(item => item.correlationState === activeFilter)
    ),
    [activeFilter, catalogItems],
  );
  const catalogFilterCounts = useMemo(
    () => ({
      all: catalogPayload?.total || 0,
      strong: correlationCounts.strong,
      hybrid: correlationCounts.hybrid,
      weak: correlationCounts.weak,
      unresolved: correlationCounts.unresolved,
    }),
    [catalogPayload?.total, correlationCounts.hybrid, correlationCounts.strong, correlationCounts.unresolved, correlationCounts.weak],
  );
  const summary = useMemo(() => {
    const strong = correlationCounts.strong;
    const unresolved = correlationCounts.unresolved;
    const hybrid = correlationCounts.hybrid;
    return {
      strong,
      unresolved,
      hybrid,
    };
  }, [correlationCounts.hybrid, correlationCounts.strong, correlationCounts.unresolved]);

  const handleSelectWorkflow = (registryId: string) => {
    navigate(buildWorkflowRegistryPath(registryId));
  };

  const handleBackToCatalog = () => {
    navigate(buildWorkflowRegistryPath());
  };

  const handleOpenAction = (action: WorkflowRegistryAction) => {
    runWorkflowRegistryAction(action, { navigate });
  };

  const detailTitle = detail?.identity.displayLabel || detail?.identity.observedWorkflowFamilyRef || 'Workflow detail';

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-slate-800/80 bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.18),_rgba(15,23,42,0.96)_42%,_rgba(2,6,23,1)_100%)] px-6 py-6 md:px-7">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/25 bg-indigo-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-100">
              <Sparkles size={12} />
              Workflow Intelligence
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-slate-100 md:text-4xl">
              Workflow Registry
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300 md:text-base">
              Inspect workflow identity across CCDash and SkillMeat, verify correlation strength, and move directly into the evidence or definition that explains each workflow.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-3 xl:min-w-[34rem]">
            <SummaryTile label="Registry" value={formatInteger(catalogPayload?.total || 0)} caption="Workflow entities in the current view" />
            <SummaryTile label="Resolved" value={formatInteger(summary.strong)} caption="Strongly correlated definitions" />
            <SummaryTile label="Attention" value={formatInteger(summary.unresolved + summary.hybrid)} caption="Hybrid or unresolved workflow rows" />
          </div>
        </div>
      </section>

      {!activeProject ? (
        <div className="rounded-[28px] border border-slate-800 bg-slate-950/55 px-5 py-5 text-sm text-slate-400">
          Select an active project to load workflow registry data.
        </div>
      ) : !workflowAnalyticsAvailable ? (
        <div className="rounded-[28px] border border-indigo-500/30 bg-indigo-900/20 px-5 py-5 text-sm text-indigo-100">
          <div className="font-semibold">Workflow analytics disabled</div>
          <p className="mt-2 text-indigo-100/80">
            Enable Workflow Effectiveness in project settings to populate the workflow registry surface for {activeProject.name || activeProject.id}.
          </p>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[400px_minmax(0,1fr)]">
          <div className={selectedWorkflowId ? 'hidden xl:block' : 'block'}>
            <WorkflowCatalog
              searchQuery={searchQuery}
              activeFilter={activeFilter}
              items={visibleCatalogItems}
              counts={catalogFilterCounts}
              total={catalogPayload?.total || 0}
              loading={catalogLoading}
              error={catalogError}
              selectedId={selectedWorkflowId}
              searchInputRef={searchInputRef}
              onSearchQueryChange={setSearchQuery}
              onActiveFilterChange={setActiveFilter}
              onSelect={handleSelectWorkflow}
              onRetry={() => {
                void loadCatalog();
              }}
              onClearFilters={() => {
                setSearchQuery('');
                setActiveFilter('all');
              }}
            />
          </div>

          <div className={selectedWorkflowId ? 'block' : 'hidden xl:block'}>
            <div className="mb-3 flex items-center justify-between gap-3 xl:hidden">
              <button
                type="button"
                onClick={handleBackToCatalog}
                className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-950/70 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-colors hover:border-slate-500"
              >
                <FolderKanban size={12} />
                Catalog
              </button>
              <div className="truncate text-sm text-slate-400">{detailTitle}</div>
            </div>

            {!selectedWorkflowId && (
              <div className="mb-3 hidden items-center justify-between gap-3 xl:flex">
                <div className="text-sm text-slate-500">
                  Choose a workflow from the catalog to inspect the detail panel.
                </div>
                <button
                  type="button"
                  onClick={() => {
                    void loadCatalog();
                  }}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-950/70 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-colors hover:border-slate-500"
                >
                  <RefreshCcw size={12} />
                  Refresh registry
                </button>
              </div>
            )}

            <WorkflowDetailPanel
              detail={detail}
              loading={detailLoading}
              error={detailError}
              showBackButton={Boolean(selectedWorkflowId)}
              onBack={handleBackToCatalog}
              onRetry={() => {
                if (selectedWorkflowId) {
                  void loadDetail(selectedWorkflowId);
                }
              }}
              onOpenAction={handleOpenAction}
            />
          </div>
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/45 px-4 py-4">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <Blocks size={12} />
            Correlation Focus
          </div>
          <div className="mt-2 text-sm leading-6 text-slate-300">
            Strong and weak states are kept explicit so command-backed workflows do not masquerade as fully resolved definitions.
          </div>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/45 px-4 py-4">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <Sparkles size={12} />
            Evidence Bias
          </div>
          <div className="mt-2 text-sm leading-6 text-slate-300">
            Detail views keep SkillMeat metadata and CCDash effectiveness signals side by side instead of flattening them into one score.
          </div>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/45 px-4 py-4">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <FolderKanban size={12} />
            Deep Linking
          </div>
          <div className="mt-2 text-sm leading-6 text-slate-300">
            Workflow detail routes are encoded so hybrid and unresolved registry IDs remain safe for `HashRouter` path segments.
          </div>
        </div>
      </section>
    </div>
  );
};
