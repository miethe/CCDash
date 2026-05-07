import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCcw, Search, SlidersHorizontal } from 'lucide-react';

import { analyticsService } from '../../services/analytics';
import type { ArtifactRankingRow, ArtifactRecommendation, ArtifactRecommendationType } from '../../types';
import { formatTokenCount } from '../../lib/tokenMetrics';
import { cn } from '../../lib/utils';
import { AlertSurface, Surface } from '../ui/surface';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Select } from '../ui/select';

type RankingFilters = {
    project: string;
    collection: string;
    user: string;
    period: string;
    artifactType: string;
    workflow: string;
    recommendationType: string;
};

type RankingRowWithBackendFields = ArtifactRankingRow & {
    avgConfidence?: number | null;
    recommendationTypes?: ArtifactRecommendationType[];
    evidence?: Record<string, unknown>;
};

const PERIOD_OPTIONS = [
    { value: '7d', label: '7 days' },
    { value: '30d', label: '30 days' },
    { value: '90d', label: '90 days' },
    { value: 'all', label: 'All time' },
];

const RECOMMENDATION_OPTIONS: Array<{ value: ArtifactRecommendationType; label: string }> = [
    { value: 'disable_candidate', label: 'Disable' },
    { value: 'load_on_demand', label: 'On demand' },
    { value: 'workflow_specific_swap', label: 'Workflow swap' },
    { value: 'optimization_target', label: 'Optimize' },
    { value: 'version_regression', label: 'Regression' },
    { value: 'identity_reconciliation', label: 'Identity' },
    { value: 'insufficient_data', label: 'Insufficient data' },
];

const emptyFilters = (projectId?: string | null): RankingFilters => ({
    project: projectId || '',
    collection: '',
    user: '',
    period: '30d',
    artifactType: '',
    workflow: '',
    recommendationType: '',
});

const isFiniteNumber = (value: unknown): value is number => (
    typeof value === 'number' && Number.isFinite(value)
);

const coerceString = (value: unknown): string | null => {
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    return trimmed || null;
};

export const formatNullableScore = (value: number | null | undefined): string => {
    if (!isFiniteNumber(value)) return '—';
    return `${Math.round(value * 100)}%`;
};

export const resolveArtifactLabel = (row: ArtifactRankingRow): string => (
    coerceString(row.displayName)
    || coerceString(row.artifactName)
    || coerceString(row.externalId)
    || coerceString(row.artifactUuid)
    || coerceString(row.artifactId)
    || 'Unknown artifact'
);

export const resolveRecommendationTypes = (row: ArtifactRankingRow): ArtifactRecommendationType[] => {
    const backendRow = row as RankingRowWithBackendFields;
    const values = [
        backendRow.recommendation?.type,
        ...(backendRow.recommendations || []).map(item => item?.type),
        ...(backendRow.recommendationTypes || []),
    ];
    return Array.from(new Set(values.filter((value): value is ArtifactRecommendationType => Boolean(value))));
};

const formatCurrency = (value: number | null | undefined): string => {
    if (!isFiniteNumber(value)) return '—';
    return `$${value.toFixed(4)}`;
};

const formatNumber = (value: number | null | undefined): string => {
    if (!isFiniteNumber(value)) return '—';
    return Math.round(value).toLocaleString();
};

const formatDate = (value: string | null | undefined): string => {
    const raw = coerceString(value);
    if (!raw) return '—';
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? raw : parsed.toLocaleString();
};

const formatRecommendationLabel = (value: string): string => (
    value
        .split('_')
        .filter(Boolean)
        .map(part => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
);

const pickRecommendationConfidence = (
    row: RankingRowWithBackendFields,
    type: ArtifactRecommendationType,
): number | null | undefined => {
    const matchesType = (recommendation?: ArtifactRecommendation | null) => recommendation?.type === type;
    if (matchesType(row.recommendation)) return row.recommendation?.confidence;
    const match = (row.recommendations || []).find(matchesType);
    return match?.confidence ?? row.confidence ?? row.avgConfidence ?? row.averageConfidence;
};

const buildQuery = (filters: RankingFilters) => {
    const trimmed = {
        project: filters.project.trim(),
        collection: filters.collection.trim(),
        user: filters.user.trim(),
        period: filters.period,
        artifactType: filters.artifactType.trim(),
        workflow: filters.workflow.trim(),
        recommendationType: filters.recommendationType,
    };
    return {
        project: trimmed.project || undefined,
        collection: trimmed.collection || undefined,
        user: trimmed.user || undefined,
        period: trimmed.period || undefined,
        artifactType: trimmed.artifactType || undefined,
        workflow: trimmed.workflow || undefined,
        recommendationType: trimmed.recommendationType || undefined,
        limit: 100,
    };
};

const recommendationToneClass = (type: string): string => {
    if (type === 'disable_candidate' || type === 'version_regression') return 'danger';
    if (type === 'optimization_target' || type === 'identity_reconciliation') return 'warning';
    if (type === 'load_on_demand' || type === 'workflow_specific_swap') return 'info';
    return 'muted';
};

const badgeClass = (tone: string, mono = false): string => cn(
    'inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-semibold whitespace-nowrap',
    mono && 'font-mono',
    tone === 'info' && 'border-info-border bg-info/10 text-info-foreground',
    tone === 'warning' && 'border-warning-border bg-warning/10 text-warning-foreground',
    tone === 'danger' && 'border-danger-border bg-danger/10 text-danger-foreground',
    tone === 'muted' && 'border-panel-border bg-surface-muted text-muted-foreground',
    tone === 'neutral' && 'border-panel-border bg-surface-overlay/80 text-panel-foreground',
);

const FilterField: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
    <label className="min-w-0 space-y-1">
        <span className="block text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        {children}
    </label>
);

const LoadingRows: React.FC = () => (
    <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="grid grid-cols-[1.5fr_0.8fr_0.7fr_0.7fr_1fr] gap-3 rounded-lg border border-panel-border bg-surface-overlay/60 p-3">
                {Array.from({ length: 5 }).map((__, innerIndex) => (
                    <div key={`${index}-${innerIndex}`} className="h-4 animate-pulse rounded bg-surface-muted" />
                ))}
            </div>
        ))}
    </div>
);

export interface ArtifactRankingsViewProps {
    defaultProjectId?: string | null;
}

export const ArtifactRankingsView: React.FC<ArtifactRankingsViewProps> = ({ defaultProjectId }) => {
    const [filters, setFilters] = useState<RankingFilters>(() => emptyFilters(defaultProjectId));
    const [rows, setRows] = useState<ArtifactRankingRow[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setFilters(prev => (prev.project ? prev : { ...prev, project: defaultProjectId || '' }));
    }, [defaultProjectId]);

    const loadRankings = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const payload = await analyticsService.fetchArtifactRankings(buildQuery(filters));
            setRows(Array.isArray(payload.rows) ? payload.rows : []);
            setTotal(Number.isFinite(payload.total) ? payload.total : 0);
        } catch (fetchError) {
            console.error('Failed to load artifact rankings', fetchError);
            setRows([]);
            setTotal(0);
            setError(fetchError instanceof Error ? fetchError.message : 'Failed to load artifact rankings.');
        } finally {
            setLoading(false);
        }
    }, [filters]);

    useEffect(() => {
        void loadRankings();
    }, [loadRankings]);

    const summary = useMemo(() => {
        let tokens = 0;
        let cost = 0;
        let recommendations = 0;
        rows.forEach(row => {
            tokens += Number(row.exclusiveTokens || 0) + Number(row.supportingTokens || 0);
            cost += Number(row.costUsd || row.costUsdModelIO || 0);
            recommendations += resolveRecommendationTypes(row).length;
        });
        return { tokens, cost, recommendations };
    }, [rows]);

    const updateFilter = (key: keyof RankingFilters, value: string) => {
        setFilters(prev => ({ ...prev, [key]: value }));
    };

    const clearFilters = () => {
        setFilters(emptyFilters(defaultProjectId));
    };

    return (
        <div className="space-y-5">
            <Surface tone="panel" padding="lg">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <div className="flex items-center gap-2">
                            <SlidersHorizontal size={18} className="text-primary" />
                            <h3 className="text-lg font-semibold text-panel-foreground">Artifact Rankings</h3>
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Rank artifacts by usage, cost, outcome scores, context pressure, and advisory recommendations.
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={clearFilters}>
                            Clear
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => void loadRankings()} disabled={loading}>
                            <RefreshCcw size={15} />
                            Retry
                        </Button>
                    </div>
                </div>

                <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-7">
                    <FilterField label="Project">
                        <Input fieldSize="sm" value={filters.project} onChange={event => updateFilter('project', event.target.value)} placeholder="active project" />
                    </FilterField>
                    <FilterField label="Collection">
                        <Input fieldSize="sm" value={filters.collection} onChange={event => updateFilter('collection', event.target.value)} placeholder="any" />
                    </FilterField>
                    <FilterField label="User">
                        <Input fieldSize="sm" value={filters.user} onChange={event => updateFilter('user', event.target.value)} placeholder="all" />
                    </FilterField>
                    <FilterField label="Period">
                        <Select fieldSize="sm" value={filters.period} onChange={event => updateFilter('period', event.target.value)}>
                            {PERIOD_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </Select>
                    </FilterField>
                    <FilterField label="Type">
                        <Input fieldSize="sm" value={filters.artifactType} onChange={event => updateFilter('artifactType', event.target.value)} placeholder="skill" />
                    </FilterField>
                    <FilterField label="Workflow">
                        <Input fieldSize="sm" value={filters.workflow} onChange={event => updateFilter('workflow', event.target.value)} placeholder="workflow id" />
                    </FilterField>
                    <FilterField label="Recommendation">
                        <Select fieldSize="sm" value={filters.recommendationType} onChange={event => updateFilter('recommendationType', event.target.value)}>
                            <option value="">Any</option>
                            {RECOMMENDATION_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </Select>
                    </FilterField>
                </div>
            </Surface>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <Surface tone="overlay" padding="md">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Ranked Artifacts</div>
                    <div className="mt-2 text-2xl font-semibold text-panel-foreground">{formatNumber(total || rows.length)}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{formatNumber(rows.length)} loaded</div>
                </Surface>
                <Surface tone="overlay" padding="md">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Attributed Tokens</div>
                    <div className="mt-2 text-2xl font-semibold text-info-foreground">{formatTokenCount(summary.tokens)}</div>
                    <div className="mt-1 text-xs text-muted-foreground">exclusive plus supporting</div>
                </Surface>
                <Surface tone="overlay" padding="md">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Recommendations</div>
                    <div className="mt-2 text-2xl font-semibold text-warning-foreground">{formatNumber(summary.recommendations)}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{formatCurrency(summary.cost)} visible cost</div>
                </Surface>
            </div>

            {loading && <LoadingRows />}

            {!loading && error && (
                <AlertSurface intent="danger" className="flex flex-wrap items-center justify-between gap-3">
                    <span>{error}</span>
                    <Button variant="outline" size="sm" onClick={() => void loadRankings()}>
                        <RefreshCcw size={15} />
                        Retry
                    </Button>
                </AlertSurface>
            )}

            {!loading && !error && rows.length === 0 && (
                <Surface tone="panel" padding="lg" className="text-center">
                    <Search size={22} className="mx-auto text-muted-foreground" />
                    <p className="mt-3 font-semibold text-panel-foreground">No artifact rankings available</p>
                    <p className="mt-1 text-sm text-muted-foreground">Adjust the filters or refresh after ranking data has been generated.</p>
                </Surface>
            )}

            {!loading && !error && rows.length > 0 && (
                <Surface tone="panel" padding="none" className="overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full min-w-[1120px] text-sm">
                            <thead>
                                <tr className="border-b border-panel-border text-muted-foreground">
                                    <th className="px-4 py-3 text-left">Artifact</th>
                                    <th className="px-4 py-3 text-left">Scope</th>
                                    <th className="px-4 py-3 text-right">Tokens</th>
                                    <th className="px-4 py-3 text-right">Cost</th>
                                    <th className="px-4 py-3 text-right">Success</th>
                                    <th className="px-4 py-3 text-right">Efficiency</th>
                                    <th className="px-4 py-3 text-left">Context</th>
                                    <th className="px-4 py-3 text-left">Recommendations</th>
                                    <th className="px-4 py-3 text-left">Observed</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((row, index) => {
                                    const backendRow = row as RankingRowWithBackendFields;
                                    const artifactKey = coerceString(row.artifactUuid) || coerceString(row.artifactId) || String(row.id || index);
                                    const tokens = Number(row.exclusiveTokens || 0) + Number(row.supportingTokens || 0);
                                    const contextPressure = isFiniteNumber(row.contextPressure) ? Math.max(0, Math.min(1, row.contextPressure)) : null;
                                    const recommendationTypes = resolveRecommendationTypes(row);
                                    return (
                                        <tr key={`${artifactKey}-${index}`} className="border-b border-panel-border/80 text-foreground">
                                            <td className="px-4 py-3 align-top">
                                                <div className="font-medium text-panel-foreground">{resolveArtifactLabel(row)}</div>
                                                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                                    {row.artifactType && <span className={badgeClass('neutral')}>{row.artifactType}</span>}
                                                    {row.versionId && <span className={badgeClass('muted', true)}>{row.versionId}</span>}
                                                </div>
                                                <div className="mt-1 max-w-[280px] truncate font-mono text-[11px] text-muted-foreground" title={artifactKey}>
                                                    {artifactKey}
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 align-top text-xs">
                                                <div className="text-panel-foreground">{row.projectId || 'active project'}</div>
                                                <div className="mt-1 text-muted-foreground">collection {row.collectionId || 'any'}</div>
                                                <div className="mt-1 text-muted-foreground">user {row.userScope || 'all'}</div>
                                                {row.workflowId && <div className="mt-1 font-mono text-muted-foreground">{row.workflowLabel || row.workflowId}</div>}
                                            </td>
                                            <td className="px-4 py-3 text-right align-top font-mono">
                                                <div>{formatTokenCount(tokens)}</div>
                                                <div className="mt-1 text-[11px] text-muted-foreground">{formatTokenCount(row.exclusiveTokens || 0)} exclusive</div>
                                            </td>
                                            <td className="px-4 py-3 text-right align-top font-mono">{formatCurrency(row.costUsd ?? row.costUsdModelIO)}</td>
                                            <td className="px-4 py-3 text-right align-top font-mono">{formatNullableScore(row.successScore)}</td>
                                            <td className="px-4 py-3 text-right align-top font-mono">{formatNullableScore(row.efficiencyScore)}</td>
                                            <td className="px-4 py-3 align-top">
                                                <div className="font-mono text-sm text-panel-foreground">{formatNullableScore(row.contextPressure)}</div>
                                                {contextPressure !== null && (
                                                    <div className="mt-2 h-1.5 w-28 overflow-hidden rounded-full bg-surface-muted">
                                                        <div
                                                            className={cn(
                                                                'h-full rounded-full',
                                                                contextPressure > 0.75 ? 'bg-danger' : contextPressure > 0.5 ? 'bg-warning' : 'bg-success',
                                                            )}
                                                            style={{ width: `${Math.round(contextPressure * 100)}%` }}
                                                        />
                                                    </div>
                                                )}
                                                <div className="mt-1 text-[11px] text-muted-foreground">identity {formatNullableScore(row.identityConfidence)}</div>
                                            </td>
                                            <td className="px-4 py-3 align-top">
                                                {recommendationTypes.length === 0 ? (
                                                    <span className="text-muted-foreground">None</span>
                                                ) : (
                                                    <div className="flex max-w-[300px] flex-wrap gap-1.5">
                                                        {recommendationTypes.map(type => (
                                                            <span
                                                                key={type}
                                                                className={badgeClass(recommendationToneClass(type))}
                                                                title={`Confidence ${formatNullableScore(pickRecommendationConfidence(backendRow, type))}`}
                                                            >
                                                                {formatRecommendationLabel(type)}
                                                                <span className="ml-1 opacity-75">{formatNullableScore(pickRecommendationConfidence(backendRow, type))}</span>
                                                            </span>
                                                        ))}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 align-top text-xs text-muted-foreground">
                                                <div>{formatDate(row.lastObservedAt)}</div>
                                                <div className="mt-1">{formatNumber(row.sessionCount)} sessions</div>
                                                <div className="mt-1">{formatNumber(row.sampleSize)} samples</div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </Surface>
            )}
        </div>
    );
};
