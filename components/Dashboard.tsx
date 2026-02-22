import React, { useState, useEffect, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useData } from '../contexts/DataContext';
import { TrendingUp, AlertTriangle, Zap, DollarSign, Cpu } from 'lucide-react';
import { generateDashboardInsight } from '../services/geminiService';
import { analyticsService } from '../services/analytics';

const StatCard = ({ label, value, sub, icon: Icon, color }: any) => (
  <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl">
    <div className="flex justify-between items-start mb-4">
      <div>
        <p className="text-slate-400 text-sm font-medium">{label}</p>
        <h3 className="text-2xl font-bold text-slate-100 mt-1">{value}</h3>
      </div>
      <div className={`p-2 rounded-lg bg-${color}-500/10 text-${color}-500`}>
        <Icon size={20} />
      </div>
    </div>
    <p className="text-xs text-slate-500">{sub}</p>
  </div>
);

export const Dashboard: React.FC = () => {
  const { sessions, tasks, loading } = useData();
  const [insight, setInsight] = useState<string | null>(null);
  const [loadingInsight, setLoadingInsight] = useState(false);
  const [overview, setOverview] = useState<any | null>(null);
  const [chartData, setChartData] = useState<Array<{ date: string; cost: number; velocity: number }>>([]);
  const [modelData, setModelData] = useState<Array<{ name: string; usage: number }>>([]);

  // Derive analytics from real session data
  const analyticsData = useMemo(() => {
    return sessions.map(s => ({
      date: s.startedAt?.split('T')[0] || 'Unknown',
      cost: s.totalCost,
      featuresShipped: tasks.filter(t => t.status === 'done' || t.status === 'deferred').length,
      avgQuality: s.qualityRating || 4,
    }));
  }, [sessions, tasks]);

  const handleGenerateInsight = async () => {
    setLoadingInsight(true);
    const insightMetrics = (chartData.length > 0 ? chartData : analyticsData).map(point => ({
      name: point.date,
      value: Number(point.cost || 0),
      unit: '$',
    }));
    const result = await generateDashboardInsight(insightMetrics, tasks);
    setInsight(result);
    setLoadingInsight(false);
  };

  useEffect(() => {
    let mounted = true;
    const loadAnalytics = async () => {
      try {
        const [ov, costSeries, velocitySeries] = await Promise.all([
          analyticsService.getOverview(),
          analyticsService.getSeries({ metric: 'session_cost', period: 'daily', limit: 120 }),
          analyticsService.getSeries({ metric: 'task_velocity', period: 'daily', limit: 120 }),
        ]);
        if (!mounted) return;
        setOverview(ov);
        setModelData((ov.topModels || []).slice(0, 6));

        const byDate = new Map<string, { date: string; cost: number; velocity: number }>();
        for (const point of costSeries.items || []) {
          const date = String(point.captured_at || '').slice(0, 10);
          if (!date) continue;
          const current = byDate.get(date) || { date, cost: 0, velocity: 0 };
          current.cost = Number(point.value || 0);
          byDate.set(date, current);
        }
        for (const point of velocitySeries.items || []) {
          const date = String(point.captured_at || '').slice(0, 10);
          if (!date) continue;
          const current = byDate.get(date) || { date, cost: 0, velocity: 0 };
          current.velocity = Number(point.value || 0);
          byDate.set(date, current);
        }
        setChartData(Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date)));
      } catch (err) {
        console.error('Failed to load analytics overview:', err);
      }
    };
    loadAnalytics();
    return () => {
      mounted = false;
    };
  }, [sessions.length, tasks.length]);

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold text-slate-100">Analytics Overview</h2>
          <p className="text-slate-400 mt-2">Performance metrics across all active agents and sessions.</p>
        </div>
        <button
          onClick={handleGenerateInsight}
          disabled={loadingInsight}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          {loadingInsight ? (
            <span className="animate-pulse">Analyzing...</span>
          ) : (
            <>
              <Cpu size={16} />
              AI Insight
            </>
          )}
        </button>
      </div>

      {insight && (
        <div className="bg-indigo-900/20 border border-indigo-500/30 p-4 rounded-xl text-indigo-200 text-sm leading-relaxed flex items-start gap-3">
          <div className="mt-1"><Zap size={16} className="text-indigo-400" /></div>
          <div>{insight}</div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Spend (30d)"
          value={`$${Number(overview?.kpis?.sessionCost || 0).toFixed(2)}`}
          sub="Derived from persisted session totals"
          icon={DollarSign}
          color="emerald"
        />
        <StatCard
          label="Avg. Session Quality"
          value={`${Number(overview?.kpis?.taskCompletionPct || 0).toFixed(1)}%`}
          sub="Task completion across done/deferred/completed"
          icon={TrendingUp}
          color="indigo"
        />
        <StatCard
          label="Tool Success Rate"
          value={`${Number(overview?.kpis?.toolSuccessRate || 0).toFixed(1)}%`}
          sub={`${Number(overview?.kpis?.toolCallCount || 0).toLocaleString()} tool calls tracked`}
          icon={AlertTriangle}
          color="rose"
        />
        <StatCard
          label="Features Shipped"
          value={`${Number(overview?.kpis?.taskVelocity || 0).toLocaleString()}`}
          sub={`${Number(overview?.kpis?.sessionCount || 0).toLocaleString()} sessions in scope`}
          icon={Zap}
          color="amber"
        />
      </div>

      {/* Main Chart Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-6">Cost vs. Velocity</h3>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData.length > 0 ? chartData : analyticsData}>
                <defs>
                  <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorQuality" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(val) => val.slice(5)}
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
                  tickFormatter={(val) => `$${val}`}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f1f5f9' }}
                  itemStyle={{ color: '#e2e8f0' }}
                />
                <Area type="monotone" dataKey="cost" stroke="#6366f1" fillOpacity={1} fill="url(#colorCost)" strokeWidth={2} name="Daily Cost" />
                <Area type="monotone" dataKey="velocity" stroke="#10b981" fillOpacity={1} fill="url(#colorQuality)" strokeWidth={2} name="Task Velocity" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-6">Top Agent Models</h3>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={true} vertical={false} />
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" stroke="#94a3b8" width={80} tick={{ fontSize: 12 }} />
                <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                <Bar dataKey="usage" fill="#3b82f6" radius={[0, 4, 4, 0]} barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};
