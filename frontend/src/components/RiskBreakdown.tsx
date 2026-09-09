import React from 'react';
import { RiskFactorContribution } from '../types';
import { Sliders, HelpCircle } from 'lucide-react';

interface RiskBreakdownProps {
  breakdown: RiskFactorContribution[];
  totalScore: number;
}

export const RiskBreakdown: React.FC<RiskBreakdownProps> = ({ breakdown, totalScore }) => {
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
            Explainable Risk Breakdown
          </h3>
        </div>
        <span className="text-xs font-mono text-slate-400">
          Total: <strong className="text-slate-100">{Math.round(totalScore)} / 100</strong>
        </span>
      </div>

      <div className="space-y-3">
        {breakdown.map((item, idx) => {
          const percentOfTotal = Math.round(item.weighted_contribution);
          return (
            <div key={idx} className="space-y-1.5">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-300 flex items-center gap-2">
                  <span className="text-cyan-400 font-bold">+{item.weighted_contribution.toFixed(1)}</span>
                  <span>{item.factor}</span>
                  <span className="text-[10px] text-slate-400">({Math.round(item.weight * 100)}% Weight)</span>
                </span>
                <span className="text-slate-400 text-[11px]">
                  Raw Risk: {Math.round(item.raw_risk)}%
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800/80">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all duration-700"
                  style={{ width: `${Math.min(100, Math.max(0, item.raw_risk))}%` }}
                ></div>
              </div>

              {item.top_signals && item.top_signals.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {item.top_signals.map((sig, sIdx) => (
                    <span
                      key={sIdx}
                      className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-950 text-slate-400 border border-slate-800"
                    >
                      {sig}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
