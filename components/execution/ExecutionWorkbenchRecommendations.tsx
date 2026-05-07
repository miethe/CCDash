import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, FileText, RefreshCcw, Search } from 'lucide-react';

import { analyticsService, type ArtifactRecommendationItem } from '../../services/analytics';
import { cn } from '../../lib/utils';

interface ExecutionWorkbenchRecommendationsProps {
  projectId?: string | null;
}

type EvidenceEntry = {
  key: string;
  value: string;
};

const isFiniteNumber = (value: unknown): value is number => (
  typeof value === 'number' && Number.isFinite(value)
);

const coerceText = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed || null;
};

export const formatRecommendationLabel = (value: string | null | undefined): string => {
  const raw = coerceText(value);
  if (!raw) return 'Recommendation';
  return raw
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

export const formatConfidence = (value: number | null | undefined): string => {
  if (!isFiniteNumber(value)) return 'n/a';
  return `${Math.round(value * 100)}%`;
};

const formatEvidenceValue = (value: unknown): string => {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    return value.map(item => formatEvidenceValue(item)).filter(Boolean).join(', ');
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

export const normalizeEvidenceEntries = (
  evidence: ArtifactRecommendationItem['evidence'],
): EvidenceEntry[] => {
  if (!evidence) return [];
  if (Array.isArray(evidence)) {
    return evidence
      .map((value, index) => ({ key: `Evidence ${index + 1}`, value: formatEvidenceValue(value) }))
      .filter(entry => entry.value);
  }
  return Object.entries(evidence)
    .map(([key, value]) => ({
      key: formatRecommendationLabel(key),
      value: formatEvidenceValue(value),
    }))
    .filter(entry => entry.value);
};

export const hasStaleSnapshotWarning = (recommendation: ArtifactRecommendationItem): boolean => {
  if (recommendation.rationaleCode === 'stale_snapshot') return true;
  const evidence = recommendation.evidence;
  return Boolean(
    evidence
    && !Array.isArray(evidence)
    && (evidence.snapshotFetchedAt || evidence.suppressedType),
  );
};

export const resolveAffectedArtifactLabel = (recommendation: ArtifactRecommendationItem): string => {
  const affected = recommendation.affectedArtifactIds?.find(value => coerceText(value));
  return affected || coerceText(recommendation.scope) || 'Project artifact set';
};

const recommendationToneClass = (type: string | null | undefined): string => {
  if (type === 'disable_candidate' || type === 'version_regression') {
    return 'border-danger-border bg-danger/10 text-danger-foreground';
  }
  if (type === 'optimization_target' || type === 'identity_reconciliation') {
    return 'border-warning-border bg-warning/10 text-warning-foreground';
  }
  if (type === 'load_on_demand' || type === 'workflow_specific_swap') {
    return 'border-info-border bg-info/10 text-info-foreground';
  }
  return 'border-panel-border bg-surface-muted text-muted-foreground';
};

const buildScopeLabels = (recommendation: ArtifactRecommendationItem): string[] => {
  const labels = ['Project advisory'];
  if (recommendation.workflowId) labels.push('Workflow-level');
  if (recommendation.collectionId) labels.push('Collection scope');
  if (recommendation.userScope) labels.push('User scope');
  if (recommendation.period) labels.push(recommendation.period);
  return labels;
};

const RecommendationSkeleton: React.FC = () => (
  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
    {Array.from({ length: 4 }).map((_, index) => (
      <div key={index} className="rounded-lg border border-panel-border bg-surface-overlay/60 p-3">
        <div className="h-4 w-32 animate-pulse rounded bg-surface-muted" />
        <div className="mt-3 h-3 w-full animate-pulse rounded bg-surface-muted" />
        <div className="mt-2 h-3 w-3/4 animate-pulse rounded bg-surface-muted" />
      </div>
    ))}
  </div>
);

export const ExecutionWorkbenchRecommendations: React.FC<ExecutionWorkbenchRecommendationsProps> = ({ projectId }) => {
  const [recommendations, setRecommendations] = useState<ArtifactRecommendationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const queryProject = projectId || undefined;

  const loadRecommendations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await analyticsService.fetchArtifactRecommendations({
        project: queryProject,
        minConfidence: 0.7,
        limit: 6,
        period: '30d',
      });
      setRecommendations(Array.isArray(payload.recommendations) ? payload.recommendations : []);
    } catch (fetchError) {
      console.error('Failed to load artifact recommendations', fetchError);
      setRecommendations([]);
      setError(fetchError instanceof Error ? fetchError.message : 'Failed to load artifact recommendations.');
    } finally {
      setLoading(false);
    }
  }, [queryProject]);

  useEffect(() => {
    void loadRecommendations();
  }, [loadRecommendations]);

  const staleCount = useMemo(
    () => recommendations.filter(hasStaleSnapshotWarning).length,
    [recommendations],
  );

  return (
    <section className="rounded-xl border border-panel-border bg-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-primary" />
            <h3 className="text-sm font-semibold text-panel-foreground">Artifact Recommendations</h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Advisory project and workflow-level recommendations from the last 30 days.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {staleCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full border border-warning-border bg-warning/10 px-2 py-1 text-[11px] font-semibold text-warning-foreground">
              <AlertTriangle size={12} />
              Stale snapshot
            </span>
          )}
          <button
            type="button"
            onClick={() => void loadRecommendations()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-md border border-panel-border px-2.5 py-1.5 text-xs font-semibold text-panel-foreground hover:border-hover disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCcw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div className="mt-4">
        {loading && <RecommendationSkeleton />}

        {!loading && error && (
          <div className="rounded-lg border border-danger-border bg-danger/10 px-3 py-2 text-sm text-danger-foreground">
            <p className="font-semibold">Recommendations unavailable</p>
            <p className="mt-1 text-xs opacity-85">{error}</p>
          </div>
        )}

        {!loading && !error && recommendations.length === 0 && (
          <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-4 text-center">
            <Search size={18} className="mx-auto text-muted-foreground" />
            <p className="mt-2 text-sm font-semibold text-panel-foreground">No recommendations</p>
          </div>
        )}

        {!loading && !error && recommendations.length > 0 && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {recommendations.map((recommendation, index) => {
              const evidence = normalizeEvidenceEntries(recommendation.evidence).slice(0, 4);
              const isStale = hasStaleSnapshotWarning(recommendation);
              const artifactLabel = resolveAffectedArtifactLabel(recommendation);
              const recommendationKey = [
                recommendation.type || 'recommendation',
                artifactLabel,
                recommendation.workflowId || '',
                index,
              ].join(':');

              return (
                <article key={recommendationKey} className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <span className={cn(
                      'inline-flex items-center rounded-full border px-2 py-1 text-[11px] font-semibold',
                      recommendationToneClass(recommendation.type),
                    )}>
                      {formatRecommendationLabel(recommendation.type)}
                    </span>
                    <span className="rounded-full border border-panel-border bg-surface-muted px-2 py-1 font-mono text-[11px] text-muted-foreground">
                      {formatConfidence(recommendation.confidence)}
                    </span>
                  </div>

                  <div className="mt-3 min-w-0">
                    <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Affected artifact</div>
                    <div className="mt-1 truncate font-mono text-xs text-panel-foreground" title={artifactLabel}>
                      {artifactLabel}
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {buildScopeLabels(recommendation).map(label => (
                      <span key={label} className="rounded-full border border-panel-border bg-surface-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                        {label}
                      </span>
                    ))}
                  </div>

                  {recommendation.rationaleCode && (
                    <p className="mt-3 text-xs text-muted-foreground">
                      <span className="font-semibold text-panel-foreground">Rationale:</span> {formatRecommendationLabel(recommendation.rationaleCode)}
                    </p>
                  )}

                  {recommendation.nextAction && (
                    <p className="mt-2 text-sm leading-5 text-panel-foreground">{recommendation.nextAction}</p>
                  )}

                  {evidence.length > 0 && (
                    <dl className="mt-3 space-y-1.5 rounded-md border border-panel-border/70 bg-surface-muted/60 p-2">
                      {evidence.map(entry => (
                        <div key={`${entry.key}:${entry.value}`} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 text-[11px]">
                          <dt className="truncate text-muted-foreground" title={entry.key}>{entry.key}</dt>
                          <dd className="min-w-0 truncate font-mono text-panel-foreground" title={entry.value}>{entry.value}</dd>
                        </div>
                      ))}
                    </dl>
                  )}

                  {isStale && (
                    <div className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-warning-border bg-warning/10 px-2 py-1 text-[11px] font-semibold text-warning-foreground">
                      <AlertTriangle size={12} />
                      Snapshot may be stale
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
};
