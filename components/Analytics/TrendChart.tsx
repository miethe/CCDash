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
import { AnalyticsTrendPoint } from '../../types';

interface TrendChartProps {
    metric: string;
    title: string;
    color?: string;
    valueFormatter?: (val: number) => string;
}

export const TrendChart: React.FC<TrendChartProps> = ({
    metric,
    title,
    color = '#6366f1',
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
        return <div className="h-64 flex items-center justify-center text-slate-500">Loading {title}...</div>;
    }

    if (data.length === 0) {
        return <div className="h-64 flex items-center justify-center text-slate-500">No data for {title}</div>;
    }

    // Transform for chart
    const chartData = data.map(d => ({
        date: new Date(d.captured_at).toLocaleDateString(),
        fullDate: new Date(d.captured_at).toLocaleString(),
        value: d.value,
    }));

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <h3 className="text-lg font-semibold text-slate-200 mb-6">{title}</h3>
            <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                        <defs>
                            <linearGradient id={`gradient-${metric}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                                <stop offset="95%" stopColor={color} stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                        <XAxis
                            dataKey="date"
                            stroke="#475569"
                            tick={{ fill: '#64748b', fontSize: 12 }}
                            axisLine={false}
                            tickLine={false}
                        />
                        <YAxis
                            stroke="#475569"
                            tick={{ fill: '#64748b', fontSize: 12 }}
                            axisLine={false}
                            tickLine={false}
                            tickFormatter={valueFormatter}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f1f5f9' }}
                            itemStyle={{ color: '#e2e8f0' }}
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
        </div>
    );
};
