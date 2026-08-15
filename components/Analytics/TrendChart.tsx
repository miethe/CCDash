import React, { useEffect, useState } from 'react';
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
} from 'recharts';
import { analyticsService } from '../../services/analytics';
import { chartTheme, getChartGradientStops, getChartSeriesColor } from '../../lib/chartTheme';
import { AnalyticsTrendPoint } from '../../types';
import { Surface } from '../ui/surface';

/** An externally-supplied trend point — used when a caller has already
 * fetched/derived its own weekly-bucketed (or otherwise pre-shaped) series
 * and wants TrendChart's rendering only, skipping its internal
 * analyticsService.getTrends fetch. See are-we-winning-dashboard-v1 M3
 * (lib/areWeWinning.ts's weeklyPointToChartPoint). */
export interface TrendChartExternalPoint {
    date: string;
    fullDate?: string;
    value: number;
    /** Opaque payload handed back to onPointClick, e.g. drill-through bucket coordinates. */
    meta?: unknown;
}

interface TrendChartProps {
    /** Required when `points` is omitted — selects the internally-fetched metric series. */
    metric?: string;
    title: string;
    color?: string;
    valueFormatter?: (val: number) => string;
    /**
     * When supplied (even as an empty array), TrendChart renders this data
     * directly and skips its internal `analyticsService.getTrends` fetch —
     * the caller owns fetching/loading state via `isLoading`.
     */
    points?: TrendChartExternalPoint[];
    /** Loading state for externally-supplied `points`. Ignored when `points` is omitted. */
    isLoading?: boolean;
    /**
     * Fired only from a user click on a rendered point (recharts
     * `activeDot.onClick`) — never from render or an effect. This is the
     * OQ-4 constraint (are-we-winning-dashboard-v1 plan): drill-through must
     * never write navigation/route state outside a click handler.
     */
    onPointClick?: (point: TrendChartExternalPoint) => void;
    /** Overrides the default "No data for {title}" empty-state copy. */
    emptyMessage?: string;
}

export const TrendChart: React.FC<TrendChartProps> = ({
    metric,
    title,
    color = getChartSeriesColor('primary'),
    valueFormatter = (val) => val.toString(),
    points,
    isLoading,
    onPointClick,
    emptyMessage,
}) => {
    const usesExternalData = points !== undefined;
    const [fetchedData, setFetchedData] = useState<AnalyticsTrendPoint[]>([]);
    const [fetchLoading, setFetchLoading] = useState(!usesExternalData);

    useEffect(() => {
        if (usesExternalData) return;
        let cancelled = false;
        const fetchData = async () => {
            try {
                const trends = await analyticsService.getTrends(metric!);
                if (!cancelled) setFetchedData(trends);
            } catch (err) {
                console.error('Failed to load trends for', metric, err);
            } finally {
                if (!cancelled) setFetchLoading(false);
            }
        };
        fetchData();
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [metric, usesExternalData]);

    const loading = usesExternalData ? !!isLoading : fetchLoading;

    if (loading) {
        return <Surface tone="overlay" padding="lg" className="flex h-64 items-center justify-center text-muted-foreground">Loading {title}...</Surface>;
    }

    const chartData = usesExternalData
        ? (points ?? []).map(p => ({
            date: p.date,
            fullDate: p.fullDate ?? p.date,
            value: p.value,
            meta: p.meta,
        }))
        : fetchedData.map(d => ({
            date: new Date(d.captured_at).toLocaleDateString(),
            fullDate: new Date(d.captured_at).toLocaleString(),
            value: d.value,
            meta: undefined as unknown,
        }));

    if (chartData.length === 0) {
        return (
            <Surface tone="overlay" padding="lg" className="flex h-64 items-center justify-center text-muted-foreground">
                {emptyMessage ?? `No data for ${title}`}
            </Surface>
        );
    }

    const gradientId = `gradient-${metric ?? title.replace(/\s+/g, '-').toLowerCase()}`;

    return (
        <Surface tone="panel" padding="lg">
            <h3 className="mb-6 text-lg font-semibold text-panel-foreground">{title}</h3>
            <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                        <defs>
                            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                                {getChartGradientStops(color).map((stop) => (
                                    <stop
                                        key={`${gradientId}-${stop.offset}`}
                                        offset={stop.offset}
                                        stopColor={stop.stopColor}
                                        stopOpacity={stop.stopOpacity}
                                    />
                                ))}
                            </linearGradient>
                        </defs>
                        <CartesianGrid {...chartTheme.grid} vertical={false} />
                        <XAxis
                            dataKey="date"
                            {...chartTheme.axis}
                        />
                        <YAxis
                            {...chartTheme.axis}
                            tickFormatter={valueFormatter}
                        />
                        <Tooltip
                            contentStyle={chartTheme.tooltip.contentStyle}
                            itemStyle={chartTheme.tooltip.itemStyle}
                            labelStyle={chartTheme.tooltip.labelStyle}
                            cursor={chartTheme.tooltip.cursor}
                            labelFormatter={(label, payload) => (payload as any)?.[0]?.payload?.fullDate || label}
                            formatter={(value: number) => [valueFormatter(value), title]}
                        />
                        <Area
                            type="monotone"
                            dataKey="value"
                            stroke={color}
                            fillOpacity={1}
                            fill={`url(#${gradientId})`}
                            strokeWidth={2}
                            isAnimationActive={false}
                            activeDot={onPointClick ? {
                                r: 6,
                                style: { cursor: 'pointer' },
                                // Fired only on a user click — recharts activeDot.onClick is a
                                // click handler, never invoked on render/mount. See OQ-4.
                                // recharts' onClick arg order/shape varies by version, so pull
                                // `.payload` off whichever argument carries it defensively.
                                onClick: (...args: any[]) => {
                                    const original = args
                                        .map((arg) => arg?.payload)
                                        .find((candidate): candidate is TrendChartExternalPoint => !!candidate);
                                    if (original) onPointClick(original);
                                },
                            } as any : undefined}
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </Surface>
    );
};
