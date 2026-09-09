import React from 'react';
import { CheckCircle2, Loader2, Circle, AlertCircle } from 'lucide-react';

export interface PipelineStage {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  latencyMs?: number;
  detail?: string;
}

interface ProcessingPipelineProps {
  stages: PipelineStage[];
  title?: string;
}

export const ProcessingPipeline: React.FC<ProcessingPipelineProps> = ({
  stages,
  title = 'AI Screening Pipeline'
}) => {
  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
      <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-800">
        <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-cyan-400"></span>
          {title}
        </h3>
        <span className="text-[11px] font-mono text-slate-400">
          REAL-TIME MULTI-MODEL EXECUTION
        </span>
      </div>

      <div className="space-y-3">
        {stages.map((st, index) => {
          return (
            <div
              key={st.id}
              className={`flex items-center justify-between p-2.5 rounded-lg border transition-all ${
                st.status === 'running'
                  ? 'bg-cyan-950/40 border-cyan-500/40 text-cyan-200'
                  : st.status === 'completed'
                  ? 'bg-slate-950/60 border-slate-800/80 text-slate-300'
                  : st.status === 'error'
                  ? 'bg-rose-950/40 border-rose-500/40 text-rose-200'
                  : 'bg-slate-950/20 border-slate-900 text-slate-400'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="shrink-0">
                  {st.status === 'completed' && (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  )}
                  {st.status === 'running' && (
                    <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
                  )}
                  {st.status === 'error' && (
                    <AlertCircle className="w-4 h-4 text-rose-400" />
                  )}
                  {st.status === 'pending' && (
                    <Circle className="w-4 h-4 text-slate-400" />
                  )}
                </div>

                <div>
                  <div className="text-xs font-mono font-medium flex items-center gap-2">
                    <span>{st.name}</span>
                    {st.status === 'running' && (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300 animate-pulse font-mono">
                        ANALYZING...
                      </span>
                    )}
                  </div>
                  {st.detail && (
                    <p className="text-[11px] text-slate-400 mt-0.5">{st.detail}</p>
                  )}
                </div>
              </div>

              <div className="text-right font-mono text-xs">
                {st.latencyMs !== undefined ? (
                  <span className="text-slate-400">{Math.round(st.latencyMs)} ms</span>
                ) : st.status === 'completed' ? (
                  <span className="text-emerald-400">DONE</span>
                ) : st.status === 'running' ? (
                  <span className="text-cyan-400">ACTIVE</span>
                ) : (
                  <span className="text-slate-400">QUEUED</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
