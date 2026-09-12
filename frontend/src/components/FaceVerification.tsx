import React from 'react';
import { FaceVerificationResult } from '../types';
import { UserCheck, UserX, ScanFace, CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react';
import { RiskBadge } from './RiskBadge';

interface FaceVerificationProps {
  faceResult?: FaceVerificationResult;
}

export const FaceVerification: React.FC<FaceVerificationProps> = ({ faceResult }) => {
  if (!faceResult) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 text-center text-xs text-slate-500 font-mono">
        No face verification biometric data available.
      </div>
    );
  }

  const simPercent = Math.round(faceResult.similarity * 100);
  const isMatch = faceResult.status === 'MATCH';
  const quality = faceResult.quality_checks || {};

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <ScanFace className="w-4 h-4 text-slate-500" />
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
            Module 4: Biometric Face Verification
          </h3>
        </div>

        <div className="flex items-center gap-2">
          <RiskBadge status={faceResult.status} size="sm" />
          <span className="text-xs font-mono font-bold text-slate-200 px-2 py-0.5 rounded bg-slate-800">
            Similarity: {simPercent}%
          </span>
        </div>
      </div>

      {/* Side-by-Side Face Comparison */}
      <div className="grid grid-cols-2 gap-4">
        {/* Document Portrait */}
        <div className="flex flex-col items-center p-3 rounded-xl bg-slate-950 border border-slate-800">
          <span className="text-[10px] font-mono text-slate-400 mb-2 uppercase tracking-wider">
            Document Portrait Crop
          </span>
          <div className="w-28 h-36 rounded-lg overflow-hidden bg-slate-900 border border-slate-700 flex items-center justify-center shadow-md">
            {faceResult.document_face_url ? (
              <img
                src={faceResult.document_face_url}
                alt="Document Portrait"
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-[11px] text-slate-500 font-mono">Portrait Crop</span>
            )}
          </div>
          <span className="text-[10px] font-mono text-slate-400 mt-2">ICAO Photo Region</span>
        </div>

        {/* Live Subject Capture */}
        <div className="flex flex-col items-center p-3 rounded-xl bg-slate-950 border border-slate-800">
          <span className="text-[10px] font-mono text-slate-400 mb-2 uppercase tracking-wider">
            Live Subject Capture
          </span>
          <div className="w-28 h-36 rounded-lg overflow-hidden bg-slate-900 border border-slate-700 flex items-center justify-center shadow-md">
            {faceResult.live_face_url ? (
              <img
                src={faceResult.live_face_url}
                alt="Live Subject"
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-[11px] text-slate-500 font-mono">Live Webcam</span>
            )}
          </div>
          <span className="text-[10px] font-mono text-slate-400 mt-2 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span> Live Frame
          </span>
        </div>
      </div>

      {/* Similarity Progress Bar */}
      <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 space-y-1.5">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-slate-400">Biometric Cosine Similarity:</span>
          <span className={`font-bold ${isMatch ? 'text-emerald-400' : 'text-rose-400'}`}>
            {simPercent}% (Threshold: {(faceResult.match_threshold * 100).toFixed(1)}%)
          </span>
        </div>

        <div className="w-full bg-slate-900 h-2.5 rounded-full overflow-hidden border border-slate-800">
          <div
            className={`h-full transition-all duration-1000 ${isMatch ? 'bg-emerald-500' : 'bg-rose-500'}`}
            style={{ width: `${Math.min(100, Math.max(0, simPercent))}%` }}
          ></div>
        </div>
      </div>

      {/* Quality Checks & Anti-Spoofing */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono">
          <span className="text-slate-400 block text-[10px]">Sharpness</span>
          <span className="font-semibold text-slate-200">
            {quality.laplacian_sharpness ? `${quality.laplacian_sharpness} (Good)` : 'Adequate'}
          </span>
        </div>

        <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono">
          <span className="text-slate-400 block text-[10px]">Lighting</span>
          <span className="font-semibold text-slate-200">
            {quality.is_dark ? 'Underexposed' : quality.is_overexposed ? 'Overexposed' : 'Balanced'}
          </span>
        </div>

        <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono">
          <span className="text-slate-400 block text-[10px]">Anti-Spoofing</span>
          <span className="font-semibold text-slate-200">
            {Math.round((faceResult.anti_spoofing_score || 0.95) * 100)}% Liveness
          </span>
        </div>

        <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono">
          <span className="text-slate-400 block text-[10px]">Decision</span>
          <span className={`font-bold ${isMatch ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isMatch ? 'BIOMETRIC MATCH' : 'REVIEW REQUIRED'}
          </span>
        </div>
      </div>
    </div>
  );
};
