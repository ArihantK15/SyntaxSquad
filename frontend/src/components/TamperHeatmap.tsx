import React, { useState } from 'react';
import { TamperResult } from '../types';
import { Layers, Eye, Flame, AlertOctagon, ScanSearch } from 'lucide-react';
import { RiskBadge } from './RiskBadge';
import { SectionHeading } from './SectionHeading';

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
      <div className="bg-graphite-900/80 border border-graphite-800 rounded-xl p-5 text-center text-xs text-graphite-500">
        No tamper forensic analysis conducted yet.
      </div>
    );
  }

  const tamperRiskPercent = Math.round(tamperResult.tamper_risk * 100);

  return (
    <div className="bg-graphite-900/80 border border-graphite-800 rounded-xl p-5 backdrop-blur space-y-4">
      {/* Header */}
      <SectionHeading
        level="h3"
        title="Tamper AI & error level analysis"
        icon={<Layers className="w-4 h-4 text-graphite-500" />}
        action={
          <div className="flex items-center gap-2">
            <RiskBadge level={tamperResult.risk_level} size="sm" />
            <span className="text-xs font-semibold text-graphite-200 px-2 py-0.5 rounded bg-graphite-800">
              Risk: {tamperRiskPercent}%
            </span>
          </div>
        }
      />

      {/* View Toggle Tabs */}
      <div className="flex items-center justify-between border-b border-graphite-800 pb-2">
        <span className="text-[11px] text-graphite-400">
          Forensic Visualizer Mode:
        </span>
        <div className="flex items-center gap-1 bg-graphite-950 p-1 rounded-lg border border-graphite-800 text-xs">
          <button
            onClick={() => setViewMode('original')}
            className={`px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center gap-1.5 ${
              viewMode === 'original'
                ? 'bg-graphite-800 text-graphite-200 font-semibold'
                : 'text-graphite-400 hover:text-graphite-200'
            }`}
          >
            <Eye className="w-3 h-3" />
            Original
          </button>
          <button
            onClick={() => setViewMode('heatmap')}
            className={`px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center gap-1.5 ${
              viewMode === 'heatmap'
                ? 'bg-graphite-800 text-graphite-200 border border-graphite-700 font-semibold'
                : 'text-graphite-400 hover:text-graphite-200'
            }`}
          >
            <Flame className="w-3 h-3" />
            ELA Heatmap
          </button>
          <button
            onClick={() => setViewMode('split')}
            className={`px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center gap-1.5 ${
              viewMode === 'split'
                ? 'bg-graphite-800 text-graphite-200 font-semibold'
                : 'text-graphite-400 hover:text-graphite-200'
            }`}
          >
            <ScanSearch className="w-3 h-3" />
            Side-by-Side
          </button>
        </div>
      </div>

      {/* Image Preview Area -- the evidence is the hero of this view: large,
          minimal framing, everything else here is secondary. */}
      <div className="rounded-xl overflow-hidden bg-graphite-950 border border-graphite-800 p-2">
        {viewMode === 'split' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <span className="text-[10px] text-graphite-400 mb-1 block uppercase">
                Original Specimen
              </span>
              <div className="relative rounded-lg overflow-hidden bg-black/40 border border-graphite-800 aspect-[3/4] sm:aspect-[4/5] flex items-center justify-center">
                {originalImageUrl ? (
                  <img src={originalImageUrl} alt="Original Document" className="w-full h-full object-contain" />
                ) : (
                  <span className="text-xs text-graphite-500">No Image</span>
                )}
              </div>
            </div>
            <div>
              <span className="text-[10px] text-graphite-400 mb-1 block uppercase flex items-center gap-1">
                <Flame className="w-3 h-3" /> ELA Thermal Heatmap Overlay
              </span>
              <div className="relative rounded-lg overflow-hidden bg-black/40 border border-graphite-800 aspect-[3/4] sm:aspect-[4/5] flex items-center justify-center">
                {tamperResult.heatmap_url ? (
                  <img src={tamperResult.heatmap_url} alt="ELA Heatmap" className="w-full h-full object-contain" />
                ) : (
                  <span className="text-xs text-graphite-500">Heatmap Processing</span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="relative rounded-lg overflow-hidden bg-black/40 border border-graphite-800 min-h-[420px] max-h-[70vh] flex items-center justify-center">
            <img
              src={viewMode === 'original' ? originalImageUrl : tamperResult.heatmap_url || originalImageUrl}
              alt="Document Forensic View"
              className="max-h-[70vh] w-auto object-contain"
            />
          </div>
        )}
      </div>

      {/* Forensic Signal Breakdown -- secondary to the evidence image above */}
      <div>
        <h4 className="text-[11px] font-medium text-graphite-500 mb-2">
          Forensic multi-signal indicators ({tamperResult.signals.length} detected)
        </h4>

        {tamperResult.signals.length === 0 ? (
          <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
            <span>✓</span> No significant image manipulation or recompression anomalies detected.
          </div>
        ) : (
          <div className="space-y-2">
            {tamperResult.signals.map((sig, idx) => (
              <div
                key={idx}
                className="p-3 rounded-lg bg-graphite-950/70 border border-graphite-800 text-xs space-y-1"
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
                <p className="text-graphite-400 text-[11px]">{sig.explanation}</p>
                {sig.region && sig.region.length === 4 && (
                  <span className="text-[10px] text-graphite-400 block font-mono">
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
