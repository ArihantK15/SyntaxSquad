import React, { useState } from 'react';
import { OCRResult } from '../types';
import { FileText, CheckCircle, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';

interface OCRResultsProps {
  data?: OCRResult;
}

export const OCRResults: React.FC<OCRResultsProps> = ({ data }) => {
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!data) {
    return (
      <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-xs text-slate-500 font-mono">
        No OCR extraction data recorded.
      </div>
    );
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(data.raw_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const fields = [
    { label: 'Full Name', value: data.fields.full_name || '—' },
    { label: 'Document Number', value: data.fields.document_number || '—' },
    { label: 'Nationality', value: data.fields.nationality || '—' },
    { label: 'Country of Issue', value: data.fields.country || '—' },
    { label: 'Date of Birth', value: data.fields.date_of_birth || '—' },
    { label: 'Date of Expiry', value: data.fields.date_of_expiry || '—' },
    { label: 'Sex', value: data.fields.sex || '—' },
  ];

  const confPercent = Math.round(data.confidence * 100);

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 backdrop-blur space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
            Module 1: OCR Extraction
          </h3>
        </div>

        {/* Confidence Meter */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-slate-400">Confidence:</span>
          <span className="text-xs font-mono font-bold text-cyan-300 px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/30">
            {confPercent}%
          </span>
        </div>
      </div>

      {/* Field Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
        {fields.map((f, i) => (
          <div key={i} className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80">
            <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">
              {f.label}
            </span>
            <span className="text-xs font-mono font-medium text-slate-200 truncate block mt-0.5">
              {f.value}
            </span>
          </div>
        ))}
      </div>

      {/* Raw Text Accordion */}
      <div className="pt-2 border-t border-slate-800/80">
        <button
          onClick={() => setShowRaw(!showRaw)}
          className="flex items-center justify-between w-full text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors py-1 cursor-pointer"
        >
          <span>Raw Extracted OCR Buffer ({data.detected_lines.length} lines)</span>
          {showRaw ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        {showRaw && (
          <div className="mt-2 relative">
            <pre className="p-3 rounded-lg bg-slate-950 text-slate-300 font-mono text-[11px] leading-relaxed overflow-x-auto max-h-48 border border-slate-800 select-all">
              {data.raw_text}
            </pre>
            <button
              onClick={handleCopy}
              className="absolute top-2 right-2 p-1.5 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300 text-xs flex items-center gap-1 cursor-pointer"
              title="Copy raw text"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
