import React, { useEffect, useState } from 'react';
import { CaseItem } from '../types';
import { api } from '../services/api';
import { RiskBadge } from '../components/RiskBadge';
import { Inbox, Search, Filter, ChevronRight, AlertTriangle, ShieldCheck } from 'lucide-react';

interface ReviewQueuePageProps {
  onSelectCase: (caseId: string) => void;
}

export const ReviewQueuePage: React.FC<ReviewQueuePageProps> = ({ onSelectCase }) => {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterLevel, setFilterLevel] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchQueue();
  }, []);

  const fetchQueue = async () => {
    try {
      setLoading(true);
      const data = await api.listCases({ limit: 100 });
      // Queue prioritizes cases needing officer attention
      setCases(data);
    } catch (err: any) {
      console.error('Failed to load queue', err);
    } finally {
      setLoading(false);
    }
  };

  const filtered = cases.filter((c) => {
    const matchesFilter =
      filterLevel === 'ALL'
        ? c.officer_decision === 'PENDING'
        : filterLevel === 'CLEARED'
        ? c.officer_decision === 'CLEARED'
        : c.risk_level === filterLevel;

    const matchesSearch =
      c.case_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.country.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.recommendation.toLowerCase().includes(searchQuery.toLowerCase());

    return matchesFilter && matchesSearch;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-mono text-slate-100 tracking-wider flex items-center gap-2">
            <Inbox className="w-6 h-6 text-cyan-400" />
            OFFICER REVIEW QUEUE
          </h1>
          <p className="text-xs font-mono text-slate-400 mt-1">
            Cases flagged by AI risk engine requiring human immigration officer review and disposition
          </p>
        </div>

        {/* Search Bar */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search Case ID or Country..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-3 flex-wrap">
        {[
          { id: 'ALL', label: 'All Pending Review' },
          { id: 'CRITICAL', label: 'Critical Risk' },
          { id: 'HIGH', label: 'High Risk' },
          { id: 'MEDIUM', label: 'Medium Risk' },
          { id: 'CLEARED', label: 'Cleared Archive' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setFilterLevel(tab.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all cursor-pointer ${
              filterLevel === tab.id
                ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-500/40 shadow-inner'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Queue Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden backdrop-blur">
        {loading ? (
          <div className="p-12 text-center text-xs font-mono text-slate-400">
            Loading queue cases...
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-xs font-mono text-slate-400">
            No screening cases in this queue view.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="px-4 py-3">Case ID</th>
                  <th className="px-4 py-3">Jurisdiction</th>
                  <th className="px-4 py-3">Document</th>
                  <th className="px-4 py-3">Risk Level</th>
                  <th className="px-4 py-3">Recommendation</th>
                  <th className="px-4 py-3">Officer Status</th>
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
          </div>
        )}
      </div>
    </div>
  );
};
