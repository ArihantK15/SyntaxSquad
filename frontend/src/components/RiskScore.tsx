import React from 'react';
import { RiskLevel } from '../types';
import { ShieldAlert, ShieldCheck, AlertTriangle, ShieldX, Info } from 'lucide-react';

interface RiskScoreProps {
  score: number;
  level: RiskLevel;
  recommendation: string;
  size?: 'sm' | 'md' | 'lg';
}

export const RiskScore: React.FC<RiskScoreProps> = ({
  score,
  level,
  recommendation,
  size = 'md'
}) => {
  const getTheme = () => {
    switch (level) {
      case 'LOW':
        return {
          stroke: '#10b981',
          bgRing: 'stroke-emerald-950/40',
          textColor: 'text-emerald-400',
          borderColor: 'border-emerald-500/30',
          icon: ShieldCheck,
          accentBg: 'bg-emerald-950/20'
        };
      case 'MEDIUM':
        return {
          stroke: '#f59e0b',
          bgRing: 'stroke-amber-950/40',
          textColor: 'text-amber-400',
          borderColor: 'border-amber-500/30',
          icon: AlertTriangle,
          accentBg: 'bg-amber-950/20'
        };
      case 'HIGH':
        return {
          stroke: '#f97316',
          bgRing: 'stroke-orange-950/40',
          textColor: 'text-orange-400',
          borderColor: 'border-orange-500/30',
          icon: ShieldAlert,
          accentBg: 'bg-orange-950/20'
        };
      case 'CRITICAL':
      default:
        return {
          stroke: '#f43f5e',
          bgRing: 'stroke-rose-950/40',
          textColor: 'text-rose-400',
          borderColor: 'border-rose-500/40',
          icon: ShieldX,
          accentBg: 'bg-rose-950/25'
        };
    }
  };

  const theme = getTheme();
  const Icon = theme.icon;

  // SVG circular meter calculation
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (Math.min(100, Math.max(0, score)) / 100) * circumference;

  return (
    <div className={`rounded-xl border ${theme.borderColor} ${theme.accentBg} p-5 backdrop-blur-sm`}>
      <div className="flex flex-col sm:flex-row items-center gap-6">
        {/* Circular Gauge */}
        <div className="relative flex items-center justify-center">
          <svg className="w-32 h-32 transform -rotate-90" viewBox="0 0 120 120">
            {/* Background Track */}
            <circle
              cx="60"
              cy="60"
              r={radius}
              stroke="currentColor"
              strokeWidth="10"
              fill="transparent"
              className="text-slate-800/80"
            />
            {/* Progress Arc */}
            <circle
              cx="60"
              cy="60"
              r={radius}
              stroke={theme.stroke}
              strokeWidth="10"
              fill="transparent"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="transition-all duration-1000 ease-out"
            />
          </svg>

          {/* Centered Score */}
          <div className="absolute flex flex-col items-center justify-center text-center">
            <span className={`text-3xl font-bold font-mono tracking-tight ${theme.textColor}`}>
              {Math.round(score)}
            </span>
            <span className="text-[10px] font-mono uppercase text-slate-400 tracking-wider">
              / 100
            </span>
          </div>
        </div>

        {/* Details & Recommendation */}
        <div className="flex-1 text-center sm:text-left space-y-2">
          <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
            <Icon className={`w-5 h-5 ${theme.textColor}`} />
            <span className={`text-xl font-bold font-mono tracking-wider uppercase ${theme.textColor}`}>
              {level} RISK
            </span>
          </div>

          <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">
              Recommended Action
            </p>
            <p className={`text-sm font-medium ${theme.textColor}`}>
              {recommendation}
            </p>
          </div>

          <p className="text-[11px] text-slate-400 flex items-center gap-1.5">
            <Info className="w-3 h-3 shrink-0" /> AI decision-support indicator. Final border determination rests with the screening officer.
          </p>
        </div>
      </div>
    </div>
  );
};
