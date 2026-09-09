import React, { useEffect, useState } from 'react';
import { DashboardStats } from '../types';
import { api } from '../services/api';
import { BarChart3, Activity, Clock, ShieldCheck, Zap } from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend
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
      <div className="p-12 text-center text-xs font-mono text-slate-400">
        Loading analytics engine...
      </div>
    );
  }

  const pieData = [
    { name: 'Low Risk', value: stats.risk_distribution.LOW || 0, color: '#10b981' },
    { name: 'Medium Risk', value: stats.risk_distribution.MEDIUM || 0, color: '#f59e0b' },
    { name: 'High Risk', value: stats.risk_distribution.HIGH || 0, color: '#f97316' },
    { name: 'Critical Risk', value: stats.risk_distribution.CRITICAL || 0, color: '#f43f5e' },
  ];

  const docTypeData = Object.entries(stats.document_types || {}).map(([k, v]) => ({
    type: k,
    count: v
  }));

  const latencyBreakdown = [
    { module: 'Normalization', time: 140 },
    { module: 'OCR Extraction', time: 520 },
    { module: 'MRZ Checksums', time: 90 },
    { module: 'Tamper AI (ELA)', time: 820 },
    { module: 'Face Verification', time: 480 },
    { module: 'Risk Engine', time: 50 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold font-mono text-slate-100 tracking-wider flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-cyan-400" />
          SYSTEM ANALYTICS & FORENSIC INTELLIGENCE
        </h1>
        <p className="text-xs font-mono text-slate-400 mt-1">
          Deep-dive telemetry into AI module triggers, latency profiles, and border security distributions
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-mono uppercase">Average Pipeline Latency</span>
            <Zap className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-cyan-300">
            {(stats.avg_processing_time_ms / 1000).toFixed(2)} seconds
          </div>
          <span className="text-[10px] text-emerald-400 font-mono mt-1 block">
            Target: &lt; 5.0s (Sub-second GPU acceleration compatible)
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-mono uppercase">Risk Mitigation Rate</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400">
            {stats.documents_screened > 0
              ? Math.round((stats.cleared_cases / stats.documents_screened) * 100)
              : 0}
            %
          </div>
          <span className="text-[10px] text-slate-400 font-mono mt-1 block">
            Admitted without secondary inspection
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-mono uppercase">Anomaly Detection Yield</span>
            <Activity className="w-4 h-4 text-orange-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-orange-400">
            {stats.documents_screened > 0
              ? Math.round(((stats.high_risk_cases + stats.critical_cases) / stats.documents_screened) * 100)
              : 0}
            %
          </div>
          <span className="text-[10px] text-slate-400 font-mono mt-1 block">
            Cases escalated for manual inspection
          </span>
        </div>
      </div>

      {/* Latency by Module & Document Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur">
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200 mb-4">
            Component Processing Latency (Milliseconds)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={latencyBreakdown} layout="vertical">
                <XAxis type="number" stroke="#64748b" fontSize={11} fontFamily="monospace" />
                <YAxis type="category" dataKey="module" stroke="#94a3b8" fontSize={11} fontFamily="monospace" width={140} />
                <Tooltip contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', borderRadius: '8px', fontSize: '12px', fontFamily: 'monospace' }} />
                <Bar dataKey="time" fill="#06b6d4" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur">
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200 mb-4">
            Document Types Screened
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={docTypeData}>
                <XAxis dataKey="type" stroke="#64748b" fontSize={11} fontFamily="monospace" />
                <YAxis stroke="#94a3b8" fontSize={11} fontFamily="monospace" />
                <Tooltip contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', borderRadius: '8px', fontSize: '12px', fontFamily: 'monospace' }} />
                <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};
