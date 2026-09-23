import React, { useState } from 'react';
import { RiskSignal } from '../types';
import { ShieldAlert } from 'lucide-react';
import { RiskBadge } from './RiskBadge';
import { SectionHeading } from './SectionHeading';

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
    <div className="bg-graphite-900/80 border border-graphite-800 rounded-xl p-5 backdrop-blur space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <SectionHeading
          level="h3"
          title={`Forensic evidence & signals (${signals.length})`}
          icon={<ShieldAlert className="w-4 h-4 text-graphite-500" />}
        />

        {/* Severity Filter Chips */}
        <div className="flex items-center gap-1 bg-graphite-950 p-1 rounded-lg border border-graphite-800 text-[11px]">
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((lvl) => (
            <button
              key={lvl}
              onClick={() => setFilter(lvl)}
              className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${
                filter === lvl
                  ? 'bg-graphite-800 text-graphite-200 font-bold border border-graphite-700'
                  : 'text-graphite-400 hover:text-graphite-200'
              }`}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="p-4 rounded-lg bg-graphite-950/60 border border-graphite-800 text-center text-xs text-graphite-400">
          No signals matching the selected criteria.
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((sig, idx) => (
            <div
              key={idx}
              className="p-3 rounded-lg bg-graphite-950/70 border border-graphite-800/80 hover:border-graphite-700 transition-all flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs"
            >
              <div className="space-y-1 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2 py-0.5 rounded bg-graphite-800 text-graphite-300 font-bold text-[10px]">
                    {sig.module}
                  </span>
                  <RiskBadge level={sig.severity} size="sm" />
                  <span className="font-semibold text-graphite-200">{sig.signal}</span>
                </div>
                <p className="text-graphite-400 text-[11px] leading-relaxed">
                  {sig.explanation}
                </p>
              </div>

              <div className="flex sm:flex-col items-end justify-between sm:justify-center shrink-0 w-full sm:w-auto pt-2 sm:pt-0 border-t sm:border-t-0 border-graphite-800 text-right">
                <span className="text-rose-400 font-bold">
                  +{sig.score_impact > 0 ? sig.score_impact.toFixed(1) : '0'} pts
                </span>
                <span className="text-[10px] text-graphite-400">
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
