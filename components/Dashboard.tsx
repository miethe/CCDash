import React, { useState, useEffect, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useData } from '../contexts/DataContext';
import { TrendingUp, AlertTriangle, Zap, DollarSign, Cpu } from 'lucide-react';
import { generateDashboardInsight } from '../services/geminiService';

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

  // Derive analytics from real session data
  const analyticsData = useMemo(() => {
    return sessions.map(s => ({
      date: s.startedAt?.split('T')[0] || 'Unknown',
      cost: s.totalCost,
      featuresShipped: tasks.filter(t => t.status === 'done').length,
      avgQuality: s.qualityRating || 4,
    }));
  }, [sessions, tasks]);

  const handleGenerateInsight = async () => {
    setLoadingInsight(true);
    const result = await generateDashboardInsight(analyticsData, tasks);
    setInsight(result);
    setLoadingInsight(false);
  };

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
          value="$142.50"
          sub="+12% from last month"
          icon={DollarSign}
          color="emerald"
        />
        <StatCard
          label="Avg. Session Quality"
          value="4.2/5.0"
          sub="Based on 42 reviews"
          icon={TrendingUp}
          color="indigo"
        />
        <StatCard
          label="Hallucination Rate"
          value="3.2%"
          sub="Inferred from tool rejections"
          icon={AlertTriangle}
          color="rose"
        />
        <StatCard
          label="Features Shipped"
          value="12"
          sub="Last 7 days"
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
              <AreaChart data={analyticsData}>
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
                <Area type="monotone" dataKey="avgQuality" stroke="#10b981" fillOpacity={1} fill="url(#colorQuality)" strokeWidth={2} name="Quality Score" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-6">Top Agent Models</h3>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[
                { name: 'Claude 3.7', usage: 65 },
                { name: 'Claude 3.5', usage: 25 },
                { name: 'Gemini Pro', usage: 10 },
              ]} layout="vertical">
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