import React, { useEffect, useState } from 'react';
import { DashboardStats } from '../types';
import { api } from '../services/api';
import { SectionHeading } from '../components/SectionHeading';
import { BarChart3, Activity, ShieldCheck, Zap } from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip
} from 'recharts';

export const AnalyticsPage: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const data = await api.getDashboardStats();
      setStats(data);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !stats) {
    return (
      <div className="p-12 text-center text-xs text-slate-500">
        Loading analytics engine...
      </div>
    );
  }

  const docTypeData = Object.entries(stats.document_types || {}).map(([k, v]) => ({
    type: k,
    count: v
  }));

  // Real per-module averages computed server-side from each case's own audit
  // trail timestamps (see backend/app/api/routes/dashboard.py) -- a module
  // with zero completed cases so far reports 0ms rather than a guess.
  const latencyBreakdown = stats.latency_breakdown.map((entry) => ({
    module: entry.module,
    time: entry.time_ms
  }));

  const kpis = [
    {
      label: 'Average pipeline latency',
      value: `${(stats.avg_processing_time_ms / 1000).toFixed(2)}s`,
      color: 'text-cyan-300',
      icon: Zap,
      iconColor: 'text-cyan-400',
      note: 'Target: under 5.0s'
    },
    {
      label: 'Risk mitigation rate',
      value: `${stats.documents_screened > 0 ? Math.round((stats.cleared_cases / stats.documents_screened) * 100) : 0}%`,
      color: 'text-emerald-400',
      icon: ShieldCheck,
      iconColor: 'text-emerald-400',
      note: 'Admitted without secondary inspection'
    },
    {
      label: 'Anomaly detection yield',
      value: `${stats.documents_screened > 0 ? Math.round(((stats.high_risk_cases + stats.critical_cases) / stats.documents_screened) * 100) : 0}%`,
      color: 'text-orange-400',
      icon: Activity,
      iconColor: 'text-orange-400',
      note: 'Cases escalated for manual inspection'
    },
  ];

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Analytics"
        description="Deep-dive telemetry into AI module triggers, latency profiles, and risk distributions."
        icon={<BarChart3 className="w-5 h-5 text-cyan-400" />}
      />

      {/* KPI strip */}
      <div className="rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur grid grid-cols-1 sm:grid-cols-3 divide-x-0 sm:divide-x divide-y sm:divide-y-0 divide-slate-800">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div key={kpi.label} className="p-4">
              <div className="flex items-center justify-between text-slate-500 mb-2">
                <span className="text-xs">{kpi.label}</span>
                <Icon className={`w-4 h-4 ${kpi.iconColor}`} />
              </div>
              <div className={`text-2xl font-bold ${kpi.color}`}>
                {kpi.value}
              </div>
              <span className="text-xs text-slate-500 mt-1 block">{kpi.note}</span>
            </div>
          );
        })}
      </div>

      {/* Latency by Module & Document Breakdown -- asymmetric: latency has
          more rows, so it gets more room. */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur">
          <SectionHeading level="h3" title="Component processing latency" description="Milliseconds per pipeline module" />
          <div className="h-64 mt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={latencyBreakdown} layout="vertical">
                <XAxis type="number" stroke="#64748b" fontSize={11} />
                <YAxis type="category" dataKey="module" stroke="#94a3b8" fontSize={11} width={140} />
                <Tooltip contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', borderRadius: '8px', fontSize: '12px' }} />
                <Bar dataKey="time" fill="#06b6d4" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="lg:col-span-2 bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur">
          <SectionHeading level="h3" title="Document types screened" />
          <div className="h-64 mt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={docTypeData}>
                <XAxis dataKey="type" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', borderRadius: '8px', fontSize: '12px' }} />
                <Bar dataKey="count" fill="#0e7490" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};
