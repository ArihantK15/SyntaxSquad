import React from 'react';
import { RiskFactorContribution } from '../types';
import { Sliders } from 'lucide-react';
import { SectionHeading } from './SectionHeading';

interface RiskBreakdownProps {
  breakdown: RiskFactorContribution[];
  totalScore: number;
}

export const RiskBreakdown: React.FC<RiskBreakdownProps> = ({ breakdown, totalScore }) => {
  return (
    <div className="bg-graphite-900/80 border border-graphite-800 rounded-xl p-5 backdrop-blur space-y-4">
      <SectionHeading
        level="h3"
        title="Explainable risk breakdown"
        icon={<Sliders className="w-4 h-4 text-graphite-500" />}
        action={
          <span className="text-xs text-graphite-400">
            Total: <strong className="text-graphite-100">{Math.round(totalScore)} / 100</strong>
          </span>
        }
      />

      <div className="space-y-3">
        {breakdown.map((item, idx) => {
          const percentOfTotal = Math.round(item.weighted_contribution);
          return (
            <div key={idx} className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-graphite-300 flex items-center gap-2">
                  <span className="text-graphite-200 font-bold">+{item.weighted_contribution.toFixed(1)}</span>
                  <span>{item.factor}</span>
                  <span className="text-[10px] text-graphite-400">({Math.round(item.weight * 100)}% Weight)</span>
                </span>
                <span className="text-graphite-400 text-[11px]">
                  Raw Risk: {Math.round(item.raw_risk)}%
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-graphite-950 h-2 rounded-full overflow-hidden border border-graphite-800/80">
                <div
                  className="h-full bg-graphite-500 rounded-full transition-all duration-700"
                  style={{ width: `${Math.min(100, Math.max(0, item.raw_risk))}%` }}
                ></div>
              </div>

              {item.top_signals && item.top_signals.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {item.top_signals.map((sig, sIdx) => (
                    <span
                      key={sIdx}
                      className="text-[10px] px-1.5 py-0.2 rounded bg-graphite-950 text-graphite-400 border border-graphite-800"
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
