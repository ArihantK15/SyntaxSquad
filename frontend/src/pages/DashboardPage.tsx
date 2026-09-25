import React, { useEffect, useState } from 'react';
import { DashboardStats } from '../types';
import { api } from '../services/api';
import { ScrollShadowX } from '../components/ScrollShadowX';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge, type BadgeProps } from '../components/ui/badge';
import { StatCard } from '../components/ui/stat-card';
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

// Maps a case's risk level / decision status onto the Precision Light
// Badge's own variant vocabulary -- distinct from the dark-theme RiskBadge
// component used everywhere else in the app (see components/RiskBadge.tsx),
// since that component's color classes are hand-tuned for the dark
// graphite palette and would clash inside this page's light `.pl-theme`
// scope.
function riskBadgeVariant(text?: string): BadgeProps['variant'] {
  const v = (text || '').toUpperCase();
  if (v === 'LOW' || v === 'CLEARED' || v === 'LOW_RISK' || v === 'MATCH') return 'success-light';
  if (v === 'MEDIUM' || v === 'MEDIUM_RISK') return 'warning-light';
  if (v === 'HIGH' || v === 'HIGH_RISK' || v === 'REQUIRES_REVIEW' || v === 'REQUIRES_INSPECTION') return 'warning';
  if (v === 'CRITICAL' || v === 'ESCALATED') return 'destructive';
  return 'default';
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
      <div className="pl-theme flex items-center justify-center min-h-[60vh] rounded-xl">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
          <span className="text-xs text-muted-foreground">Loading operations stream...</span>
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="pl-theme flex items-center justify-center min-h-[60vh] rounded-xl">
        <div className="flex flex-col items-center gap-3 text-center max-w-sm">
          <AlertTriangle className="w-8 h-8 text-destructive" />
          <p className="text-sm text-foreground font-medium">Couldn't load the operations dashboard</p>
          <p className="text-xs text-muted-foreground">{error || 'No data returned from the server.'}</p>
          <Button onClick={fetchStats} className="mt-1" size="sm">
            Retry
          </Button>
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
    { key: 'screened', label: 'Screened', value: stats.documents_screened, icon: FileCheck2 },
    { key: 'review-queue', label: 'Review queue', value: stats.cases_requiring_review, icon: Inbox },
    { key: 'high-risk', label: 'High risk', value: stats.high_risk_cases, icon: AlertTriangle },
    { key: 'critical', label: 'Critical', value: stats.critical_cases, icon: AlertOctagon },
    { key: 'avg-latency', label: 'Avg latency', value: `${(stats.avg_processing_time_ms / 1000).toFixed(2)}s`, icon: Clock },
  ];

  return (
    <div className="pl-theme space-y-6 rounded-xl p-5 -m-1">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Border screening operations</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Real-time AI identity verification and travel document integrity stream.
          </p>
        </div>
        <Button onClick={onNavigateNewScreening} size="default">
          + New document screening
        </Button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div key={kpi.key} data-testid={`stat-${kpi.key}`}>
              <StatCard label={kpi.label} value={kpi.value} icon={<Icon className="w-4 h-4" />} />
            </div>
          );
        })}
      </div>
      <button
        onClick={onNavigateQueue}
        className="text-xs text-muted-foreground hover:text-primary -mt-4 flex items-center gap-1 cursor-pointer transition-colors"
      >
        Inspect review queue <ArrowRight className="w-2.5 h-2.5" />
      </button>

      {/* Charts -- unequal widths: the actionable list is primary */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <h3 className="text-sm font-semibold text-foreground">Risk level distribution</h3>
            <p className="text-xs text-muted-foreground mt-0.5">{stats.documents_screened} total specimens</p>

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
                    contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#EBEBEB', borderRadius: '8px', fontSize: '12px', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}
                    itemStyle={{ color: '#4C4C4C' }}
                  />
                  <Legend
                    formatter={(val, entry: any) => (
                      <span className="text-xs text-muted-foreground mr-2">
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
                  <span className="text-2xl font-bold text-foreground">{stats.documents_screened}</span>
                  <span className="text-[9px] uppercase text-muted-foreground">Total Specimens</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardContent className="p-5">
            <h3 className="text-sm font-semibold text-foreground">Most frequent risk indicators</h3>
            <p className="text-xs text-muted-foreground mt-0.5">Top detections across all screenings</p>

            <div className="h-56 mt-2">
              {barData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 20 }}>
                    <XAxis type="number" stroke="#B3B3B3" fontSize={11} />
                    <YAxis type="category" dataKey="name" stroke="#8C8C8C" fontSize={10} width={150} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#EBEBEB', borderRadius: '8px', fontSize: '12px', maxWidth: '260px', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}
                      itemStyle={{ color: '#4C4C4C' }}
                      labelFormatter={(_label, payload) => (payload && payload[0] ? (payload[0].payload as any).fullLabel : _label)}
                      wrapperStyle={{ whiteSpace: 'normal' }}
                    />
                    <Bar dataKey="count" fill="#335CFF" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                  Awaiting screening events
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Live queue */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">
                Live screening queue
              </h3>
            </div>
            <button
              onClick={onNavigateQueue}
              className="text-xs text-primary hover:text-primary/70 flex items-center gap-1 cursor-pointer transition-colors"
            >
              <span>View all cases</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <ScrollShadowX>
            <table className="w-full text-left text-xs">
              <thead className="text-muted-foreground border-b border-border">
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
              <tbody className="divide-y divide-border">
                {stats.recent_cases.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => onSelectCase(c.id)}
                    className="hover:bg-accent cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-mono font-semibold text-primary">
                      {c.case_number}
                    </td>
                    <td className="px-4 py-3 text-foreground/80">
                      {c.document_type}
                    </td>
                    <td className="px-4 py-3 text-foreground/80">
                      {c.country}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground">
                          {Math.round(c.risk_score)}
                        </span>
                        <Badge variant={riskBadgeVariant(c.risk_level)} size="sm">{c.risk_level}</Badge>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground truncate max-w-xs">
                      {c.recommendation}
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant={riskBadgeVariant(c.officer_decision !== 'PENDING' ? c.officer_decision : c.status)}
                        size="sm"
                      >
                        {(c.officer_decision !== 'PENDING' ? c.officer_decision : c.status).replace(/_/g, ' ')}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button className="text-primary hover:text-primary/70 font-semibold flex items-center gap-1 ml-auto">
                        <span>Inspect</span>
                        <ChevronRight className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollShadowX>
        </CardContent>
      </Card>
    </div>
  );
};
