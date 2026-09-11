import React, { useEffect, useState } from 'react';
import { AuditLog, ChainVerificationResult } from '../types';
import { api } from '../services/api';
import { ScrollShadowX } from '../components/ScrollShadowX';
import {
  ShieldCheck,
  ShieldAlert,
  Search,
  RefreshCw,
  ChevronRight,
  Lock
} from 'lucide-react';

interface AuditTrailPageProps {
  onSelectCase: (caseId: string) => void;
}

export const AuditTrailPage: React.FC<AuditTrailPageProps> = ({ onSelectCase }) => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState<string>('ALL');

  // Blockchain Ledger Verification State
  const [verification, setVerification] = useState<ChainVerificationResult | null>(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    fetchLogsAndVerify();
  }, []);

  const fetchLogsAndVerify = async () => {
    try {
      setLoading(true);
      const [logsData, verifyData] = await Promise.all([
        api.getAuditLogs({ limit: 100 }),
        api.verifyAuditChain().catch(() => null)
      ]);
      setLogs(logsData);
      if (verifyData) setVerification(verifyData);
    } catch (err: any) {
      console.error('Failed to load audit logs', err);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyChain = async () => {
    try {
      setVerifying(true);
      const res = await api.verifyAuditChain();
      setVerification(res);
    } catch (err: any) {
      alert(`Verification error: ${err.message}`);
    } finally {
      setVerifying(false);
    }
  };

  const filtered = logs.filter((l) => {
    const matchesSearch =
      l.action.toLowerCase().includes(search.toLowerCase()) ||
      l.actor.toLowerCase().includes(search.toLowerCase()) ||
      (l.case_id && l.case_id.toLowerCase().includes(search.toLowerCase())) ||
      (l.entry_hash && l.entry_hash.toLowerCase().includes(search.toLowerCase()));

    if (!matchesSearch) return false;

    if (filterType === 'OFFICER') return l.actor.includes('OFFICER');
    if (filterType === 'PURGED') return l.action.includes('PURGE');
    if (filterType === 'AI') return l.actor.startsWith('AI');
    return true;
  });

  return (
    <div className="space-y-5">
      {/* Header: title + chain status + actions, one row */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">Audit trail</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Every screening event, AI evaluation, and officer action — chained with SHA-256 so nothing can be altered after the fact.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleVerifyChain}
            disabled={verifying}
            className="px-3 py-1.5 rounded-lg border border-slate-800 text-slate-300 text-xs font-medium flex items-center gap-1.5 hover:border-slate-700 hover:text-slate-100 transition-colors cursor-pointer disabled:opacity-50"
            title="Re-run mathematical hash verification across every block"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>{verifying ? 'Verifying…' : 'Re-verify chain'}</span>
          </button>

          <button
            onClick={fetchLogsAndVerify}
            className="p-1.5 rounded-lg border border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700 transition-colors cursor-pointer"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Chain integrity — one quiet line, not a banner */}
      {verification && (
        <div className={`flex flex-wrap items-center gap-2 text-sm ${
          verification.valid ? 'text-emerald-400' : 'text-rose-400'
        }`}>
          {verification.valid ? <Lock className="w-4 h-4 shrink-0" /> : <ShieldAlert className="w-4 h-4 shrink-0" />}
          <span className="font-medium">
            {verification.valid ? 'Chain intact' : 'Tamper detected'}
          </span>
          <span className="text-slate-500 font-normal">
            — {verification.total_records} blocks verified
          </span>
          {verification.head_hash && (
            <span className="text-slate-600 font-mono text-xs ml-auto truncate">
              head {verification.head_hash.substring(0, 10)}…{verification.head_hash.substring(56)}
            </span>
          )}
        </div>
      )}

      {/* Filters + search — plain row, no card */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1">
          {(['ALL', 'OFFICER', 'AI', 'PURGED'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                filterType === t
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {t === 'ALL' && 'All'}
              {t === 'OFFICER' && 'Officer actions'}
              {t === 'AI' && 'AI forensics'}
              {t === 'PURGED' && 'Biometrics purged'}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search action, actor, hash…"
            className="w-full bg-slate-900/60 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-600"
          />
        </div>
      </div>

      {/* Logs table — the one real surface on this page */}
      <div className="border border-slate-800/80 rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-sm text-slate-500">Loading audit blocks…</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-sm text-slate-500">No audit records match this search.</div>
        ) : (
          <ScrollShadowX>
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500 text-xs border-b border-slate-800/80">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Time</th>
                  <th className="px-4 py-2.5 font-medium">Event</th>
                  <th className="px-4 py-2.5 font-medium">Actor</th>
                  <th className="px-4 py-2.5 font-medium">Case</th>
                  <th className="px-4 py-2.5 font-medium">Hash</th>
                  <th className="px-4 py-2.5 font-medium">Details</th>
                  <th className="px-4 py-2.5 font-medium text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {filtered.map((item, idx) => {
                  const dateStr = new Date(item.timestamp).toLocaleString([], {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                  });
                  const isOfficer = item.actor.includes('OFFICER');
                  const isPurge = item.action.includes('PURGE');

                  return (
                    <tr key={item.id || idx} className="hover:bg-slate-900/40 transition-colors">
                      <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap font-mono text-xs">
                        {dateStr}
                      </td>

                      <td className={`px-4 py-2.5 font-medium whitespace-nowrap ${isPurge ? 'text-amber-400' : 'text-slate-200'}`}>
                        {item.action.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase())}
                      </td>

                      <td className="px-4 py-2.5">
                        <span
                          className={`px-2 py-0.5 rounded text-xs ${
                            isOfficer
                              ? 'text-cyan-300 bg-cyan-500/10'
                              : isPurge
                              ? 'text-amber-300 bg-amber-500/10'
                              : 'text-slate-400 bg-slate-800/60'
                          }`}
                        >
                          {item.actor}
                        </span>
                      </td>

                      <td className="px-4 py-2.5 text-slate-400 font-mono text-xs">
                        {item.case_id ? item.case_id.substring(0, 8) : '—'}
                      </td>

                      <td className="px-4 py-2.5">
                        {item.entry_hash ? (
                          <span
                            className="text-xs font-mono text-slate-500"
                            title={`Full SHA-256: ${item.entry_hash}\nPrev: ${item.previous_hash || 'GENESIS'}`}
                          >
                            {item.entry_hash.substring(0, 8)}…{item.entry_hash.substring(60)}
                          </span>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>

                      <td className="px-4 py-2.5 text-slate-500 text-xs max-w-xs truncate">
                        {item.metadata_json ? JSON.stringify(item.metadata_json) : '—'}
                      </td>

                      <td className="px-4 py-2.5 text-right">
                        {item.case_id && (
                          <button
                            onClick={() => onSelectCase(item.case_id!)}
                            className="text-slate-500 hover:text-cyan-400 flex items-center gap-0.5 ml-auto cursor-pointer transition-colors"
                          >
                            <span className="text-xs">Case</span>
                            <ChevronRight className="w-3 h-3" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </ScrollShadowX>
        )}
      </div>
    </div>
  );
};
