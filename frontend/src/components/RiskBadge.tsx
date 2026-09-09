import React from 'react';
import { RiskLevel, CaseStatus, OfficerDecision } from '../types';

interface RiskBadgeProps {
  level?: RiskLevel | string;
  status?: CaseStatus | OfficerDecision | string;
  size?: 'sm' | 'md' | 'lg';
}

export const RiskBadge: React.FC<RiskBadgeProps> = ({ level, status, size = 'md' }) => {
  const text = level || status || 'UNKNOWN';

  let colorClasses = 'bg-slate-800/80 text-slate-300 border-slate-700';

  if (text === 'LOW' || text === 'CLEARED' || text === 'LOW_RISK' || text === 'MATCH') {
    colorClasses = 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40 glow-emerald';
  } else if (text === 'MEDIUM' || text === 'MEDIUM_RISK' || text === 'ROUTINE VERIFICATION') {
    colorClasses = 'bg-amber-950/60 text-amber-300 border-amber-500/40 glow-amber';
  } else if (text === 'HIGH' || text === 'HIGH_RISK' || text === 'REQUIRES_REVIEW' || text === 'REQUIRES_INSPECTION' || text === 'REVIEW_REQUIRED') {
    colorClasses = 'bg-orange-950/60 text-orange-300 border-orange-500/40';
  } else if (text === 'CRITICAL' || text === 'ESCALATED' || text === 'REJECT') {
    colorClasses = 'bg-rose-950/60 text-rose-300 border-rose-500/50 glow-red';
  } else if (text === 'PROCESSING') {
    colorClasses = 'bg-cyan-950/60 text-cyan-300 border-cyan-500/40 animate-pulse';
  }

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-xs px-2.5 py-1',
    lg: 'text-sm px-3.5 py-1.5'
  }[size];

  const formatted = text.replace(/_/g, ' ');

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-mono font-semibold tracking-wider uppercase border ${colorClasses} ${sizeClasses}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current"></span>
      {formatted}
    </span>
  );
};
