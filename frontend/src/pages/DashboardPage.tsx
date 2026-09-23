import React, { useEffect, useState } from 'react';
import { DashboardStats, CaseItem } from '../types';
import { api } from '../services/api';
import { RiskBadge } from '../components/RiskBadge';
import { ScrollShadowX } from '../components/ScrollShadowX';
import { SectionHeading } from '../components/SectionHeading';
import {
  FileCheck2,
  AlertTriangle,
  AlertOctagon,
  Clock,
  Inbox,
  ChevronRight,
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getDashboardStats();
      setStats(data);
    } catch (err: any) {
      // A failed fetch never sets `stats` -- without a distinct error state,
      // the `loading || !stats` guard below kept showing the spinner forever
      // even after `loading` itself flipped back to false here.
      setError(err?.message || 'Failed to load dashboard stats');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-brass-400 border-t-transparent animate-spin"></div>
          <span className="text-xs text-graphite-500">Loading operations stream...</span>
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3 text-center max-w-sm">
          <AlertTriangle className="w-8 h-8 text-rose-400" />
          <p className="text-sm text-graphite-200 font-medium">Couldn't load the operations dashboard</p>
          <p className="text-xs text-graphite-500">{error || 'No data returned from the server.'}</p>
          <button
            onClick={fetchStats}
            className="mt-1 px-4 py-2 rounded-lg bg-brass-600 hover:bg-brass-500 text-white text-xs font-semibold transition-colors cursor-pointer"
          >
            Retry
          </button>
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

  // Bar chart data for top risk signals. Many distinct signals share a long
  // common prefix (e.g. "MRZ Checksum Mismatch (Document Number)" vs
  // "...(Date of Birth)") -- the disambiguating part is always the suffix,
  // so truncate wide enough to keep it, and carry the untruncated reason
  // through for the tooltip as a fallback for anything still cut off.
  const barData = stats.top_risk_reasons.map((r) => ({
    name: r.reason.length > 34 ? r.reason.substring(0, 32) + '...' : r.reason,
    fullLabel: r.reason,
    count: r.count
  }));

  const kpis = [
    { label: 'Screened', value: stats.documents_screened, color: 'text-graphite-100', icon: FileCheck2, iconColor: 'text-brass-400' },
    { label: 'Review queue', value: stats.cases_requiring_review, color: 'text-amber-400', icon: Inbox, iconColor: 'text-amber-400' },
    { label: 'High risk', value: stats.high_risk_cases, color: 'text-orange-400', icon: AlertTriangle, iconColor: 'text-orange-400' },
    { label: 'Critical', value: stats.critical_cases, color: 'text-rose-400', icon: AlertOctagon, iconColor: 'text-rose-400' },
    { label: 'Avg latency', value: `${(stats.avg_processing_time_ms / 1000).toFixed(2)}s`, color: 'text-brass-300', icon: Clock, iconColor: 'text-brass-400' },
  ];

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Border screening operations"
        description="Real-time AI identity verification and travel document integrity stream."
        action={
          <button
            onClick={onNavigateNewScreening}
            className="bg-brass-600 hover:bg-brass-500 text-white px-4 py-2 rounded-lg text-xs font-semibold transition-all shadow-md shadow-brass-950/40 flex items-center gap-2 cursor-pointer"
          >
            <span>+ New document screening</span>
          </button>
        }
      />

      {/* KPI strip -- one frame, five columns, not five repeated cards */}
      <div className="rounded-xl bg-graphite-900/80 border border-graphite-800 backdrop-blur grid grid-cols-2 sm:grid-cols-5 divide-x divide-y sm:divide-y-0 divide-graphite-800">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div key={kpi.label} className="p-4">
              <div className="flex items-center justify-between text-graphite-500 mb-2">
                <span className="text-xs">{kpi.label}</span>
                <Icon className={`w-4 h-4 ${kpi.iconColor}`} />
              </div>
              <div className={`text-2xl font-bold ${kpi.color}`}>
                {kpi.value}
              </div>
            </div>
          );
        })}
      </div>
      <button
        onClick={onNavigateQueue}
        className="text-xs text-graphite-500 hover:text-amber-300 -mt-4 flex items-center gap-1 cursor-pointer"
      >
        Inspect review queue <ArrowRight className="w-2.5 h-2.5" />
      </button>

      {/* Charts -- unequal widths: the actionable list is primary */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2 bg-graphite-900/80 border border-graphite-800 rounded-xl p-5 backdrop-blur">
          <SectionHeading level="h3" title="Risk level distribution" description={`${stats.documents_screened} total specimens`} />

          <div className="h-56 relative mt-2">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={75}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#17171A', borderColor: '#3D3933', borderRadius: '8px', fontSize: '12px' }}
                  itemStyle={{ color: '#EBE9E5' }}
                />
                <Legend
                  formatter={(val, entry: any) => (
                    <span className="text-xs text-graphite-300 mr-2">
                      {val}: {entry.payload.value}
                    </span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
            {/* Centered in the donut hole -- offset up from the exact
                midpoint since the Legend row below eats vertical space,
                shifting the pie's true visual center up within this box. */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ top: '-24px' }}>
              <div className="flex flex-col items-center leading-tight">
                <span className="text-2xl font-bold text-graphite-100">{stats.documents_screened}</span>
                <span className="text-[9px] uppercase text-graphite-500">Total Specimens</span>
              </div>
            </div>
          </div>
        </div>

        <div className="lg:col-span-3 bg-graphite-900/80 border border-graphite-800 rounded-xl p-5 backdrop-blur">
          <SectionHeading level="h3" title="Most frequent risk indicators" description="Top detections across all screenings" />

          <div className="h-56 mt-2">
            {barData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 20 }}>
                  <XAxis type="number" stroke="#6B655A" fontSize={11} />
                  <YAxis type="category" dataKey="name" stroke="#8C8579" fontSize={10} width={150} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#17171A', borderColor: '#3D3933', borderRadius: '8px', fontSize: '12px', maxWidth: '260px' }}
                    itemStyle={{ color: '#EBE9E5' }}
                    labelFormatter={(_label, payload) => (payload && payload[0] ? (payload[0].payload as any).fullLabel : _label)}
                    wrapperStyle={{ whiteSpace: 'normal' }}
                  />
                  <Bar dataKey="count" fill="#5C948C" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-graphite-500">
                Awaiting screening events
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Live queue -- a self-framing table already, no outer card too */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-brass-400" />
            <h3 className="text-sm font-semibold text-graphite-200">
              Live screening queue
            </h3>
          </div>
          <button
            onClick={onNavigateQueue}
            className="text-xs text-brass-400 hover:text-brass-300 flex items-center gap-1 cursor-pointer"
          >
            <span>View all cases</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <ScrollShadowX>
          <table className="w-full text-left text-xs">
            <thead className="text-graphite-500 border-b border-graphite-800/80">
              <tr>
                <th className="px-4 py-2.5 font-medium">Case ID</th>
                <th className="px-4 py-2.5 font-medium">Document</th>
                <th className="px-4 py-2.5 font-medium">Jurisdiction</th>
                <th className="px-4 py-2.5 font-medium">Risk score</th>
                <th className="px-4 py-2.5 font-medium">Recommendation</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-graphite-800/60">
              {stats.recent_cases.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => onSelectCase(c.id)}
                  className="hover:bg-graphite-900/60 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-mono font-semibold text-brass-300">
                    {c.case_number}
                  </td>
                  <td className="px-4 py-3 text-graphite-300">
                    {c.document_type}
                  </td>
                  <td className="px-4 py-3 text-graphite-300">
                    {c.country}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-graphite-200">
                        {Math.round(c.risk_score)}
                      </span>
                      <RiskBadge level={c.risk_level} size="sm" />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-graphite-400 truncate max-w-xs">
                    {c.recommendation}
                  </td>
                  <td className="px-4 py-3">
                    <RiskBadge status={c.officer_decision !== 'PENDING' ? c.officer_decision : c.status} size="sm" />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button className="text-brass-400 hover:text-brass-200 font-semibold flex items-center gap-1 ml-auto">
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
