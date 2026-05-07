import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, RefreshCcw, Sparkles } from 'lucide-react';

import { analyticsService } from '../../services/analytics';
import type { ArtifactRankingRow, ArtifactRecommendation, ArtifactRecommendationType } from '../../types';
import { formatTokenCount } from '../../lib/tokenMetrics';
import {
  formatNullableScore,
  resolveArtifactLabel,
  resolveRecommendationTypes,
} from '../Analytics/ArtifactRankingsView';

interface ArtifactContributionPanelProps {
  workflowId: string;
  period?: string;
  defaultLimit?: number;
  expandedLimit?: number;
}

type RankingRowWithBackendFields = ArtifactRankingRow & {
  avgConfidence?: number | null;
  recommendationTypes?: ArtifactRecommendationType[];
};

const isFiniteNumber = (value: unknown): value is number => (
  typeof value === 'number' && Number.isFinite(value)
);

const formatRecommendationLabel = (value: string): string => (
  value
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
);

const recommendationToneClass = (type: string): string => {
  if (type === 'disable_candidate' || type === 'version_regression') {
    return 'border-rose-500/30 bg-rose-500/10 text-rose-100';
  }
  if (type === 'optimization_target' || type === 'identity_reconciliation') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
  }
  if (type === 'load_on_demand' || type === 'workflow_specific_swap') {
    return 'border-sky-500/30 bg-sky-500/10 text-sky-100';
  }
  return 'border-slate-700 bg-slate-900 text-slate-300';
};

const pickTopRecommendation = (row: RankingRowWithBackendFields): ArtifactRecommendation | null => {
  if (row.recommendation?.type) return row.recommendation;
  return (row.recommendations || []).find(recommendation => recommendation?.type) || null;
};

const pickRecommendationConfidence = (
  row: RankingRowWithBackendFields,
  recommendation: ArtifactRecommendation,
): number | null | undefined => (
  recommendation.confidence
  ?? row.confidence
  ?? row.avgConfidence
  ?? row.averageConfidence
);

const contributionTokensFor = (row: ArtifactRankingRow): number => {
  const attributedTokens = Number(row.attributedTokens || 0);
  if (attributedTokens > 0) return attributedTokens;
  return Number(row.exclusiveTokens || 0) + Number(row.supportingTokens || 0);
};

const NoArtifactData: React.FC<{ onRetry?: () => void; loading?: boolean }> = ({ onRetry, loading = false }) => (
  <div className="rounded-2xl border border-slate-800/80 bg-slate-950/70 px-4 py-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Artifact Contributions</div>
        <div className="mt-1 text-sm text-slate-500">No artifact data</div>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[11px] font-semibold text-slate-300 transition-colors hover:border-slate-600 disabled:opacity-60"
        >
          <RefreshCcw size={12} className={loading ? 'animate-spin' : ''} />
          Retry
        </button>
      )}
    </div>
  </div>
);

export const ArtifactContributionPanel: React.FC<ArtifactContributionPanelProps> = ({
  workflowId,
  period = '30d',
  defaultLimit = 3,
  expandedLimit = 10,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [rows, setRows] = useState<ArtifactRankingRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const limit = expanded ? expandedLimit : defaultLimit;

  const loadRows = useCallback(async () => {
    const workflow = workflowId.trim();
    if (!workflow) {
      setRows([]);
      setTotal(0);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const payload = await analyticsService.fetchArtifactRankings({
        workflow,
        period,
        limit,
      });
      setRows(Array.isArray(payload.rows) ? payload.rows : []);
      setTotal(Number.isFinite(payload.total) ? payload.total : 0);
    } catch (error) {
      console.warn('Failed to load workflow artifact contributions', error);
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [limit, period, workflowId]);

  useEffect(() => {
    void loadRows();
  }, [loadRows]);

  const canExpand = useMemo(() => (
    !expanded && (total > defaultLimit || rows.length >= defaultLimit)
  ), [defaultLimit, expanded, rows.length, total]);

  if (loading && rows.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-800/80 bg-slate-950/70 px-4 py-4">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
          <RefreshCcw size={12} className="animate-spin" />
          Artifact Contributions
        </div>
        <div className="mt-3 space-y-2">
          {Array.from({ length: defaultLimit }).map((_, index) => (
            <div key={index} className="h-10 animate-pulse rounded-xl bg-slate-900/80" />
          ))}
        </div>
      </div>
    );
  }

  if (rows.length === 0) {
    return <NoArtifactData onRetry={() => void loadRows()} loading={loading} />;
  }

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-slate-950/70 px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
          <Sparkles size={13} className="text-cyan-300" />
          Artifact Contributions
        </div>
        <div className="font-mono text-[11px] text-slate-500">
          Top {Math.min(rows.length, limit)}{total > 0 ? ` of ${total}` : ''}
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {rows.map((row, index) => {
          const backendRow = row as RankingRowWithBackendFields;
          const artifactKey = row.artifactUuid || row.artifactId || row.externalId || String(row.id || index);
          const tokens = contributionTokensFor(row);
          const recommendation = pickTopRecommendation(backendRow);
          const recommendationTypes = resolveRecommendationTypes(row);
          const fallbackRecommendationType = recommendationTypes[0];
          const recommendationType = recommendation?.type || fallbackRecommendationType;
          const recommendationConfidence = recommendation
            ? pickRecommendationConfidence(backendRow, recommendation)
            : backendRow.confidence ?? backendRow.avgConfidence ?? backendRow.averageConfidence;
          const effectivenessScore = isFiniteNumber(row.successScore)
            ? row.successScore
            : row.efficiencyScore;

          return (
            <div
              key={`${artifactKey}-${index}`}
              className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/55 px-3 py-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] text-slate-500">#{index + 1}</span>
                    <div className="truncate text-sm font-semibold text-slate-100" title={resolveArtifactLabel(row)}>
                      {resolveArtifactLabel(row)}
                    </div>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
                    {row.artifactType && (
                      <span className="rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5">
                        {row.artifactType}
                      </span>
                    )}
                    {row.versionId && (
                      <span className="rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5 font-mono">
                        {row.versionId}
                      </span>
                    )}
                    <span className="max-w-[16rem] truncate font-mono" title={artifactKey}>
                      {artifactKey}
                    </span>
                  </div>
                </div>

                {recommendationType && (
                  <span
                    className={`inline-flex items-center rounded-full border px-2 py-1 text-[10px] font-semibold ${recommendationToneClass(recommendationType)}`}
                    title={`Confidence ${formatNullableScore(recommendationConfidence)}`}
                  >
                    {formatRecommendationLabel(recommendationType)}
                    <span className="ml-1 opacity-75">{formatNullableScore(recommendationConfidence)}</span>
                  </span>
                )}
              </div>

              <div className="mt-3 grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(7rem,1fr))]">
                <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Usage Tokens</div>
                  <div className="mt-1 font-mono text-sm text-cyan-100">{formatTokenCount(tokens)}</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Success</div>
                  <div className="mt-1 font-mono text-sm text-emerald-100">{formatNullableScore(row.successScore)}</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Effectiveness</div>
                  <div className="mt-1 font-mono text-sm text-sky-100">{formatNullableScore(effectivenessScore)}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {(canExpand || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded(value => !value)}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[11px] font-semibold text-slate-300 transition-colors hover:border-slate-600"
        >
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          {expanded ? 'Show fewer' : 'Show more'}
        </button>
      )}
    </div>
  );
};
