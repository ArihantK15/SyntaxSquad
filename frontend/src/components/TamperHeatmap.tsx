import React, { useState } from 'react';
import { TamperResult } from '../types';
import { Layers, Eye, Flame, AlertOctagon, ScanSearch } from 'lucide-react';
import { RiskBadge } from './RiskBadge';

interface TamperHeatmapProps {
  originalImageUrl?: string;
  tamperResult?: TamperResult;
}

export const TamperHeatmap: React.FC<TamperHeatmapProps> = ({
  originalImageUrl,
  tamperResult
}) => {
  const [viewMode, setViewMode] = useState<'original' | 'heatmap' | 'split'>('heatmap');

  if (!tamperResult) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 text-center text-xs text-slate-500 font-mono">
        No tamper forensic analysis conducted yet.
      </div>
    );
  }

  const tamperRiskPercent = Math.round(tamperResult.tamper_risk * 100);

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-slate-500" />
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
            Module 3: Tamper AI & Error Level Analysis (ELA)
          </h3>
        </div>

        <div className="flex items-center gap-2">
          <RiskBadge level={tamperResult.risk_level} size="sm" />
          <span className="text-xs font-mono font-bold text-slate-200 px-2 py-0.5 rounded bg-slate-800">
            Risk: {tamperRiskPercent}%
          </span>
        </div>
      </div>

      {/* View Toggle Tabs */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <span className="text-[11px] font-mono text-slate-400">
          Forensic Visualizer Mode:
        </span>
        <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
          <button
            onClick={() => setViewMode('original')}
            className={`px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center gap-1.5 ${
              viewMode === 'original'
                ? 'bg-slate-800 text-slate-200 font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Eye className="w-3 h-3" />
            Original
          </button>
          <button
            onClick={() => setViewMode('heatmap')}
            className={`px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center gap-1.5 ${
              viewMode === 'heatmap'
                ? 'bg-slate-800 text-slate-200 border border-slate-700 font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Flame className="w-3 h-3" />
            ELA Heatmap
          </button>
          <button
            onClick={() => setViewMode('split')}
            className={`px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center gap-1.5 ${
              viewMode === 'split'
                ? 'bg-slate-800 text-slate-200 font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <ScanSearch className="w-3 h-3" />
            Side-by-Side
          </button>
        </div>
      </div>

      {/* Image Preview Area */}
      <div className="rounded-xl overflow-hidden bg-slate-950 border border-slate-800 p-2">
        {viewMode === 'split' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <span className="text-[10px] font-mono text-slate-400 mb-1 block uppercase">
                Original Specimen
              </span>
              <div className="relative rounded-lg overflow-hidden bg-black/40 border border-slate-800 aspect-[16/10] flex items-center justify-center">
                {originalImageUrl ? (
                  <img src={originalImageUrl} alt="Original Document" className="w-full h-full object-contain" />
                ) : (
                  <span className="text-xs text-slate-500 font-mono">No Image</span>
                )}
              </div>
            </div>
            <div>
              <span className="text-[10px] font-mono text-slate-400 mb-1 block uppercase flex items-center gap-1">
                <Flame className="w-3 h-3" /> ELA Thermal Heatmap Overlay
              </span>
              <div className="relative rounded-lg overflow-hidden bg-black/40 border border-slate-800 aspect-[16/10] flex items-center justify-center">
                {tamperResult.heatmap_url ? (
                  <img src={tamperResult.heatmap_url} alt="ELA Heatmap" className="w-full h-full object-contain" />
                ) : (
                  <span className="text-xs text-slate-500 font-mono">Heatmap Processing</span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="relative rounded-lg overflow-hidden bg-black/40 border border-slate-800 max-h-80 flex items-center justify-center">
            <img
              src={viewMode === 'original' ? originalImageUrl : tamperResult.heatmap_url || originalImageUrl}
              alt="Document Forensic View"
              className="max-h-80 w-auto object-contain"
            />
          </div>
        )}
      </div>

      {/* Forensic Signal Breakdown */}
      <div>
        <h4 className="text-[11px] font-mono text-slate-400 uppercase tracking-wider mb-2">
          Forensic Multi-Signal Indicators ({tamperResult.signals.length} Detected)
        </h4>

        {tamperResult.signals.length === 0 ? (
          <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-500/30 text-emerald-300 text-xs font-mono flex items-center gap-2">
            <span>✓</span> No significant image manipulation or recompression anomalies detected.
          </div>
        ) : (
          <div className="space-y-2">
            {tamperResult.signals.map((sig, idx) => (
              <div
                key={idx}
                className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-xs font-mono space-y-1"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-orange-300 capitalize flex items-center gap-1.5">
                    <AlertOctagon className="w-3.5 h-3.5 text-orange-400" />
                    {sig.type.replace(/_/g, ' ')}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-orange-950 text-orange-300 border border-orange-500/40 font-bold">
                    Confidence: {Math.round(sig.confidence * 100)}%
                  </span>
                </div>
                <p className="text-slate-400 text-[11px]">{sig.explanation}</p>
                {sig.region && sig.region.length === 4 && (
                  <span className="text-[10px] text-slate-400 block font-mono">
                    Region Box: [x:{sig.region[0]}, y:{sig.region[1]}, w:{sig.region[2]}, h:{sig.region[3]}]
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
