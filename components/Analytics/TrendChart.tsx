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

interface TrendChartProps {
    metric: string;
    title: string;
    color?: string;
    valueFormatter?: (val: number) => string;
}

export const TrendChart: React.FC<TrendChartProps> = ({
    metric,
    title,
    color = getChartSeriesColor('primary'),
    valueFormatter = (val) => val.toString(),
}) => {
    const [data, setData] = useState<AnalyticsTrendPoint[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const trends = await analyticsService.getTrends(metric);
                setData(trends);
            } catch (err) {
                console.error('Failed to load trends for', metric, err);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, [metric]);

    if (loading) {
        return <Surface tone="overlay" padding="lg" className="flex h-64 items-center justify-center text-muted-foreground">Loading {title}...</Surface>;
    }

    if (data.length === 0) {
        return <Surface tone="overlay" padding="lg" className="flex h-64 items-center justify-center text-muted-foreground">No data for {title}</Surface>;
    }

    // Transform for chart
    const chartData = data.map(d => ({
        date: new Date(d.captured_at).toLocaleDateString(),
        fullDate: new Date(d.captured_at).toLocaleString(),
        value: d.value,
    }));

    return (
        <Surface tone="panel" padding="lg">
            <h3 className="mb-6 text-lg font-semibold text-panel-foreground">{title}</h3>
            <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                        <defs>
                            <linearGradient id={`gradient-${metric}`} x1="0" y1="0" x2="0" y2="1">
                                {getChartGradientStops(color).map((stop) => (
                                    <stop
                                        key={`${metric}-${stop.offset}`}
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
                            labelFormatter={(label, payload) => payload[0]?.payload.fullDate || label}
                            formatter={(value: number) => [valueFormatter(value), title]}
                        />
                        <Area
                            type="monotone"
                            dataKey="value"
                            stroke={color}
                            fillOpacity={1}
                            fill={`url(#gradient-${metric})`}
                            strokeWidth={2}
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </Surface>
    );
};
