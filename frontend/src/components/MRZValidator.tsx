import React from 'react';
import { MRZResult, ValidationResult } from '../types';
import { Binary, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';

interface MRZValidatorProps {
  mrz?: MRZResult;
  validation?: ValidationResult;
}

export const MRZValidator: React.FC<MRZValidatorProps> = ({ mrz, validation }) => {
  if (!mrz) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur text-center">
        <div className="flex items-center gap-2 mb-2 text-xs font-mono font-bold text-amber-400">
          <AlertTriangle className="w-4 h-4" />
          <span>Module 2: MRZ Extraction</span>
        </div>
        <p className="text-xs text-slate-400 font-mono">
          No Machine Readable Zone (MRZ) detected or parsed.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Binary className="w-4 h-4 text-slate-500" />
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
            Module 2: ICAO 9303 MRZ Validation
          </h3>
        </div>

        <span
          className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-full border ${
            mrz.is_valid
              ? 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40'
              : 'bg-rose-950/60 text-rose-300 border-rose-500/40'
          }`}
        >
          {mrz.is_valid ? 'ALL CHECKSUMS VALID' : 'CHECKSUM MISMATCH'}
        </span>
      </div>

      {/* Raw MRZ Lines Display */}
      <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
        <span className="text-[10px] font-mono text-slate-400 block mb-1 uppercase tracking-wider">
          Format: {mrz.format} (2 lines x 44 chars)
        </span>
        <div className="font-mono text-xs sm:text-sm tracking-widest text-slate-200 break-all select-all font-semibold">
          {mrz.line1}
        </div>
        <div className="font-mono text-xs sm:text-sm tracking-widest text-slate-200 break-all select-all font-semibold">
          {mrz.line2}
        </div>
      </div>

      {/* Checksums Matrix */}
      <div>
        <h4 className="text-[11px] font-mono text-slate-400 uppercase tracking-wider mb-2">
          ICAO 9303 7-3-1 Checksum Matrix
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {mrz.checksums.map((cs, idx) => {
            const isValid = cs.valid;
            return (
              <div
                key={idx}
                className={`p-2.5 rounded-lg border flex items-center justify-between ${
                  isValid
                    ? 'bg-slate-950/50 border-slate-800/80 text-slate-200'
                    : 'bg-rose-950/30 border-rose-500/40 text-rose-200'
                }`}
              >
                <div className="flex items-center gap-2">
                  {isValid ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                  )}
                  <div>
                    <span className="text-xs font-mono font-medium block">
                      {cs.field}
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      Found: '{cs.check_digit}' | Calc: '{cs.calculated_check_digit}'
                    </span>
                  </div>
                </div>

                <span
                  className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                    isValid
                      ? 'bg-emerald-950/80 text-emerald-300'
                      : 'bg-rose-950/80 text-rose-300'
                  }`}
                >
                  {isValid ? 'MATCH' : 'FAIL'}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Document Rules Engine Summary if available */}
      {validation && (
        <div className="pt-2 border-t border-slate-800/80">
          <div className="flex items-center justify-between text-xs font-mono text-slate-400 mb-2">
            <span>Rules Engine Consistency:</span>
            <span>
              <strong className="text-emerald-400">{validation.passed_count} Passed</strong> /{' '}
              <strong className={validation.failed_count > 0 ? 'text-rose-400' : 'text-slate-400'}>
                {validation.failed_count} Failed
              </strong>
            </span>
          </div>

          <div className="space-y-1.5">
            {validation.rules_detail.map((rule, idx) => (
              <div
                key={idx}
                className={`text-[11px] font-mono p-2 rounded flex items-center justify-between ${
                  rule.passed ? 'bg-slate-950/40 text-slate-400' : 'bg-rose-950/40 border border-rose-900/60 text-rose-300'
                }`}
              >
                <span>{rule.explanation}</span>
                <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${rule.passed ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {rule.passed ? 'PASS' : 'FAIL'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
