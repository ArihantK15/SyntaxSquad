import React, { useEffect, useState } from 'react';
import { DashboardStats, CaseItem } from '../types';
import { api } from '../services/api';
import { RiskBadge } from '../components/RiskBadge';
import { ScrollShadowX } from '../components/ScrollShadowX';
import {
  FileCheck2,
  AlertTriangle,
  AlertOctagon,
  Clock,
  Inbox,
  ShieldCheck,
  ChevronRight,
  TrendingUp,
  Activity,
  ArrowRight
} from 'lucide-react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend
} from 'recharts';

interface DashboardPageProps {
  onSelectCase: (caseId: string) => void;
  onNavigateNewScreening: () => void;
  onNavigateQueue: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  onSelectCase,
  onNavigateNewScreening,
  onNavigateQueue
}) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const data = await api.getDashboardStats();
      setStats(data);
    } catch (err: any) {
      console.error('Failed to load dashboard stats', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !stats) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-cyan-400 border-t-transparent animate-spin"></div>
          <span className="text-xs font-mono text-slate-400">Loading operations stream...</span>
        </div>
      </div>
    );
  }

  // Pie chart data for risk distribution
  const pieData = [
    { name: 'Low Risk', value: stats.risk_distribution.LOW || 0, color: '#10b981' },
    { name: 'Medium Risk', value: stats.risk_distribution.MEDIUM || 0, color: '#f59e0b' },
    { name: 'High Risk', value: stats.risk_distribution.HIGH || 0, color: '#f97316' },
    { name: 'Critical Risk', value: stats.risk_distribution.CRITICAL || 0, color: '#f43f5e' },
  ];

  // Bar chart data for top risk signals
  const barData = stats.top_risk_reasons.map((r) => ({
    name: r.reason.length > 22 ? r.reason.substring(0, 20) + '...' : r.reason,
    count: r.count
  }));

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-mono text-slate-100 tracking-wider">
            BORDER SCREENING OPERATIONS
          </h1>
          <p className="text-xs font-mono text-slate-400 mt-1">
            Real-Time AI Identity Verification & Travel Document Integrity Stream
          </p>
        </div>

        <button
          onClick={onNavigateNewScreening}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded-lg text-xs font-mono font-bold tracking-wider uppercase transition-all shadow-md shadow-cyan-950/40 flex items-center gap-2 cursor-pointer"
        >
          <span>+ New Document Screening</span>
        </button>
      </div>

      {/* Top 5 Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">Screened</span>
            <FileCheck2 className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100">
            {stats.documents_screened}
          </div>
          <span className="text-[10px] text-emerald-400 font-mono mt-1 block">
            ✓ 100% automated parsing
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">Review Queue</span>
            <Inbox className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-amber-400">
            {stats.cases_requiring_review}
          </div>
          <button
            onClick={onNavigateQueue}
            className="text-[10px] text-slate-400 hover:text-amber-300 font-mono mt-1 flex items-center gap-1 cursor-pointer"
          >
            Inspect queue <ArrowRight className="w-2.5 h-2.5" />
          </button>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">High Risk</span>
            <AlertTriangle className="w-4 h-4 text-orange-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-orange-400">
            {stats.high_risk_cases}
          </div>
          <span className="text-[10px] text-slate-400 font-mono mt-1 block">
            Secondary inspection
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">Critical</span>
            <AlertOctagon className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-rose-400">
            {stats.critical_cases}
          </div>
          <span className="text-[10px] text-rose-400/80 font-mono mt-1 block">
            Immediate escalation
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">Avg Latency</span>
            <Clock className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-cyan-300">
            {(stats.avg_processing_time_ms / 1000).toFixed(2)}s
          </div>
          <span className="text-[10px] text-cyan-400/80 font-mono mt-1 block">
            Sub-5s SIH benchmark
          </span>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk Distribution Donut */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
              Risk Level Distribution
            </h3>
            <span className="text-[11px] font-mono text-slate-400">
              {stats.documents_screened} Total Specimens
            </span>
          </div>

          <div className="h-64 flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', borderRadius: '8px', fontSize: '12px', fontFamily: 'monospace' }}
                  itemStyle={{ color: '#e2e8f0' }}
                />
                <Legend
                  formatter={(val, entry: any) => (
                    <span className="text-xs font-mono text-slate-300 mr-2">
                      {val}: {entry.payload.value}
                    </span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Top Forensic Trigger Reasons */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
              Most Frequent Risk Indicators
            </h3>
            <span className="text-[11px] font-mono text-slate-400">Top Detections</span>
          </div>

          <div className="h-64">
            {barData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 20 }}>
                  <XAxis type="number" stroke="#64748b" fontSize={11} fontFamily="monospace" />
                  <YAxis type="category" dataKey="name" stroke="#94a3b8" fontSize={10} fontFamily="monospace" width={110} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', borderRadius: '8px', fontSize: '12px', fontFamily: 'monospace' }}
                  />
                  <Bar dataKey="count" fill="#06b6d4" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs font-mono text-slate-500">
                Awaiting screening events
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Operational Queue Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden backdrop-blur">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
              Live Screening Queue (Recent Cases)
            </h3>
          </div>
          <button
            onClick={onNavigateQueue}
            className="text-xs font-mono text-cyan-400 hover:text-cyan-300 flex items-center gap-1 cursor-pointer"
          >
            <span>View All Cases</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <ScrollShadowX>
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Case ID</th>
                <th className="px-4 py-3">Document</th>
                <th className="px-4 py-3">Jurisdiction</th>
                <th className="px-4 py-3">Risk Score</th>
                <th className="px-4 py-3">Recommendation</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {stats.recent_cases.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => onSelectCase(c.id)}
                  className="hover:bg-slate-800/40 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-bold text-cyan-300">
                    {c.case_number}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {c.document_type}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {c.country}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-200">
                        {Math.round(c.risk_score)}
                      </span>
                      <RiskBadge level={c.risk_level} size="sm" />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-400 truncate max-w-xs">
                    {c.recommendation}
                  </td>
                  <td className="px-4 py-3">
                    <RiskBadge status={c.officer_decision !== 'PENDING' ? c.officer_decision : c.status} size="sm" />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button className="text-cyan-400 hover:text-cyan-200 font-bold flex items-center gap-1 ml-auto">
                      <span>Inspect</span>
                      <ChevronRight className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollShadowX>
      </div>
    </div>
  );
};
