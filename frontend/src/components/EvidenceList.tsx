import React, { useState } from 'react';
import { RiskSignal } from '../types';
import { AlertCircle, Filter, ShieldAlert } from 'lucide-react';
import { RiskBadge } from './RiskBadge';

interface EvidenceListProps {
  signals: RiskSignal[];
}

export const EvidenceList: React.FC<EvidenceListProps> = ({ signals }) => {
  const [filter, setFilter] = useState<string>('ALL');

  const filtered = signals.filter((s) => {
    if (filter === 'ALL') return true;
    return s.severity === filter;
  });

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-slate-500" />
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
            Forensic Evidence & Signals ({signals.length})
          </h3>
        </div>

        {/* Severity Filter Chips */}
        <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-[11px] font-mono">
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((lvl) => (
            <button
              key={lvl}
              onClick={() => setFilter(lvl)}
              className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${
                filter === lvl
                  ? 'bg-slate-800 text-slate-200 font-bold border border-slate-700'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800 text-center text-xs text-slate-400 font-mono">
          No signals matching the selected criteria.
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((sig, idx) => (
            <div
              key={idx}
              className="p-3 rounded-lg bg-slate-950/70 border border-slate-800/80 hover:border-slate-700 transition-all flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs font-mono"
            >
              <div className="space-y-1 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-bold text-[10px]">
                    {sig.module}
                  </span>
                  <RiskBadge level={sig.severity} size="sm" />
                  <span className="font-semibold text-slate-200">{sig.signal}</span>
                </div>
                <p className="text-slate-400 text-[11px] leading-relaxed">
                  {sig.explanation}
                </p>
              </div>

              <div className="flex sm:flex-col items-end justify-between sm:justify-center shrink-0 w-full sm:w-auto pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-800 text-right">
                <span className="text-rose-400 font-bold font-mono">
                  +{sig.score_impact > 0 ? sig.score_impact.toFixed(1) : '0'} pts
                </span>
                <span className="text-[10px] text-slate-400">
                  Conf: {Math.round((sig.confidence || 0.9) * 100)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
