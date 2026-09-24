import React from 'react';
import { FaceVerificationResult } from '../types';
import { UserCheck, UserX, ScanFace, CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react';
import { RiskBadge } from './RiskBadge';
import { SectionHeading } from './SectionHeading';

interface FaceVerificationProps {
  faceResult?: FaceVerificationResult;
}

export const FaceVerification: React.FC<FaceVerificationProps> = ({ faceResult }) => {
  if (!faceResult) {
    return (
      <div className="bg-graphite-900/80 border border-graphite-800 rounded-xl p-5 text-center text-xs text-graphite-500">
        No face verification biometric data available.
      </div>
    );
  }

  const simPercent = Math.round(faceResult.similarity * 100);
  const isMatch = faceResult.status === 'MATCH';
  const quality = faceResult.quality_checks || {};

  return (
    <div className="bg-graphite-900/80 border border-graphite-800 rounded-xl p-5 backdrop-blur space-y-4">
      {/* Header */}
      <SectionHeading
        level="h3"
        title="Biometric face verification"
        icon={<ScanFace className="w-4 h-4 text-graphite-500" />}
        action={
          <div className="flex items-center gap-2">
            <RiskBadge status={faceResult.status} size="sm" />
            <span className="text-xs font-semibold text-graphite-200 px-2 py-0.5 rounded bg-graphite-800">
              Similarity: {simPercent}%
            </span>
          </div>
        }
      />

      {/* Side-by-Side Face Comparison */}
      <div className="grid grid-cols-2 gap-4">
        {/* Document Portrait */}
        <div className="flex flex-col items-center p-3 rounded-xl bg-graphite-950 border border-graphite-800">
          <span className="text-[10px] text-graphite-400 mb-2 uppercase tracking-wider">
            Document Portrait Crop
          </span>
          <div className="w-full max-w-xs mx-auto aspect-[3/4] rounded-lg overflow-hidden bg-graphite-900 border border-graphite-700 flex items-center justify-center shadow-md">
            {faceResult.document_face_url ? (
              <img
                src={faceResult.document_face_url}
                alt="Document Portrait"
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-[11px] text-graphite-500">Portrait Crop</span>
            )}
          </div>
          <span className="text-[10px] text-graphite-400 mt-2">ICAO Photo Region</span>
        </div>

        {/* Live Subject Capture */}
        <div className="flex flex-col items-center p-3 rounded-xl bg-graphite-950 border border-graphite-800">
          <span className="text-[10px] text-graphite-400 mb-2 uppercase tracking-wider">
            Live Subject Capture
          </span>
          <div className="w-full max-w-xs mx-auto aspect-[3/4] rounded-lg overflow-hidden bg-graphite-900 border border-graphite-700 flex items-center justify-center shadow-md">
            {faceResult.live_face_url ? (
              <img
                src={faceResult.live_face_url}
                alt="Live Subject"
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-[11px] text-graphite-500">Live Webcam</span>
            )}
          </div>
          <span className="text-[10px] text-graphite-400 mt-2 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-brass-400"></span> Live Frame
          </span>
        </div>
      </div>

      {/* Similarity Progress Bar */}
      <div className="p-3 rounded-xl bg-graphite-950/70 border border-graphite-800 space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-graphite-400">Biometric Cosine Similarity:</span>
          <span className={`font-bold ${isMatch ? 'text-emerald-400' : 'text-rose-400'}`}>
            {simPercent}% (Threshold: {(faceResult.match_threshold * 100).toFixed(1)}%)
          </span>
        </div>

        <div className="w-full bg-graphite-900 h-2.5 rounded-full overflow-hidden border border-graphite-800">
          <div
            className={`h-full transition-all duration-1000 ${isMatch ? 'bg-emerald-500' : 'bg-rose-500'}`}
            style={{ width: `${Math.min(100, Math.max(0, simPercent))}%` }}
          ></div>
        </div>
      </div>

      {/* Quality Checks & Anti-Spoofing */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        <div className="p-2 rounded-lg bg-graphite-950 border border-graphite-800 text-[11px]">
          <span className="text-graphite-400 block text-[10px]">Sharpness</span>
          <span className="font-semibold text-graphite-200">
            {quality.laplacian_sharpness ? `${quality.laplacian_sharpness} (Good)` : 'Adequate'}
          </span>
        </div>

        <div className="p-2 rounded-lg bg-graphite-950 border border-graphite-800 text-[11px]">
          <span className="text-graphite-400 block text-[10px]">Lighting</span>
          <span className="font-semibold text-graphite-200">
            {quality.is_dark ? 'Underexposed' : quality.is_overexposed ? 'Overexposed' : 'Balanced'}
          </span>
        </div>

        <div
          className="p-2 rounded-lg bg-graphite-950 border border-graphite-800 text-[11px]"
          title="Heuristic indicator (blur/brightness + FFT moire/halftone check), not certified Presentation Attack Detection (PAD)"
        >
          <span className="text-graphite-400 block text-[10px]">Liveness Heuristic</span>
          <span className="font-semibold text-graphite-200">
            {Math.round((faceResult.anti_spoofing_score || 0.95) * 100)}%
          </span>
          <span className="text-graphite-500 block text-[9px] leading-tight mt-0.5">
            Heuristic only — not certified PAD
          </span>
        </div>

        <div className="p-2 rounded-lg bg-graphite-950 border border-graphite-800 text-[11px]">
          <span className="text-graphite-400 block text-[10px]">Decision</span>
          <span className={`font-bold ${isMatch ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isMatch ? 'BIOMETRIC MATCH' : 'REVIEW REQUIRED'}
          </span>
        </div>
      </div>
    </div>
  );
};
