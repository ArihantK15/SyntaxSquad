import React, { useEffect, useState } from 'react';
import { CaseItem } from '../types';
import { api } from '../services/api';
import { RiskBadge } from '../components/RiskBadge';
import { ScrollShadowX } from '../components/ScrollShadowX';
import { FileText, Search, ChevronRight, RefreshCw } from 'lucide-react';
import { SectionHeading } from '../components/SectionHeading';

interface CasesListPageProps {
  onSelectCase: (caseId: string) => void;
}

export const CasesListPage: React.FC<CasesListPageProps> = ({ onSelectCase }) => {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  useEffect(() => {
    fetchCases();
  }, []);

  const fetchCases = async () => {
    try {
      setLoading(true);
      const data = await api.listCases({ limit: 150 });
      setCases(data);
    } catch (err: any) {
      console.error('Failed to load cases', err);
    } finally {
      setLoading(false);
    }
  };

  const filtered = cases.filter((c) => {
    const matchesStatus =
      statusFilter === 'ALL' ||
      c.status === statusFilter ||
      c.risk_level === statusFilter ||
      c.officer_decision === statusFilter;

    const matchesSearch =
      c.case_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.country.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.recommendation.toLowerCase().includes(searchQuery.toLowerCase());

    return matchesStatus && matchesSearch;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <SectionHeading
          title="Cases archive"
          description="Complete database of screened travel documents and officer determinations."
          icon={<FileText className="w-5 h-5 text-cyan-400" />}
        />

        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search Case ID or Country..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <button
            onClick={fetchCases}
            className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200 cursor-pointer"
            title="Refresh cases"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filter Chips */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-3 flex-wrap text-xs font-mono">
        {['ALL', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'CLEARED', 'REQUIRES_INSPECTION', 'ESCALATED'].map((st) => (
          <button
            key={st}
            onClick={() => setStatusFilter(st)}
            className={`px-3 py-1 rounded-lg transition-colors cursor-pointer ${
              statusFilter === st
                ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-500/40'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            {st.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden backdrop-blur">
        {loading ? (
          <div className="p-12 text-center text-xs font-mono text-slate-400">
            Loading cases...
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-xs font-mono text-slate-400">
            No cases match the query criteria.
          </div>
        ) : (
          <ScrollShadowX>
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="px-4 py-3">Case ID</th>
                  <th className="px-4 py-3">Date Screened</th>
                  <th className="px-4 py-3">Jurisdiction</th>
                  <th className="px-4 py-3">Document</th>
                  <th className="px-4 py-3">Risk Score</th>
                  <th className="px-4 py-3">Recommendation</th>
                  <th className="px-4 py-3">Officer Decision</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filtered.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => onSelectCase(c.id)}
                    className="hover:bg-slate-800/40 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-bold text-cyan-300">
                      {c.case_number}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {c.country}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {c.document_type}
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
                      <RiskBadge status={c.officer_decision} size="sm" />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button className="text-cyan-400 hover:text-cyan-200 font-bold flex items-center gap-1 ml-auto">
                        <span>Inspect</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollShadowX>
        )}
      </div>
    </div>
  );
};
