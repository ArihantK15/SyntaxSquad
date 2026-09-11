import React, { useState, useEffect } from 'react';
import { Settings, Sliders, Shield, Database, Cpu, Check, Info, Loader2, AlertTriangle } from 'lucide-react';
import { api } from '../services/api';

export const SettingsPage: React.FC = () => {
  const [weights, setWeights] = useState({
    mrz: 25,
    tamper: 30,
    face: 30,
    consistency: 10,
    watchlist: 5
  });

  const [thresholds, setThresholds] = useState({
    low: 24,
    medium: 49,
    high: 74
  });

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getPolicy()
      .then((policy) => {
        setWeights({
          mrz: Math.round(policy.weight_mrz * 100),
          tamper: Math.round(policy.weight_tamper * 100),
          face: Math.round(policy.weight_face * 100),
          consistency: Math.round(policy.weight_consistency * 100),
          watchlist: Math.round(policy.weight_watchlist * 100)
        });
        setThresholds({
          low: policy.threshold_low,
          medium: policy.threshold_medium,
          high: policy.threshold_high
        });
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await api.updatePolicy({
        weight_mrz: weights.mrz / 100,
        weight_tamper: weights.tamper / 100,
        weight_face: weights.face / 100,
        weight_consistency: weights.consistency / 100,
        weight_watchlist: weights.watchlist / 100,
        threshold_low: thresholds.low,
        threshold_medium: thresholds.medium,
        threshold_high: thresholds.high
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err: any) {
      setError(err.message || 'Failed to apply policy configuration');
    } finally {
      setSaving(false);
    }
  };

  const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0);

  if (loading) {
    return (
      <div className="p-12 text-center text-xs font-mono text-slate-400 flex items-center justify-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading live policy configuration...
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold font-mono text-slate-100 tracking-wider flex items-center gap-2">
          <Settings className="w-6 h-6 text-cyan-400" />
          SYSTEM CONFIGURATION & POLICY ENGINE
        </h1>
        <p className="text-xs font-mono text-slate-400 mt-1">
          Adjust risk engine intelligence weights, decision thresholds, and view active forensic subsystems
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Risk Engine Weights */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
                1. Central Risk Engine Factor Weights (Total: {totalWeight}%)
              </h3>
            </div>
            <span
              className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
                totalWeight === 100
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/30'
                  : 'bg-rose-950 text-rose-300 border border-rose-500/30'
              }`}
            >
              {totalWeight === 100 ? 'VALID (100%)' : `SUM MUST EQUAL 100% (Currently ${totalWeight}%)`}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
            <div>
              <label className="text-slate-300 block mb-1 flex items-center justify-between">
                <span>MRZ & Validation Rules</span>
                <span className="text-cyan-400 font-bold">{weights.mrz}%</span>
              </label>
              <input
                type="range"
                min="0"
                max="60"
                value={weights.mrz}
                onChange={(e) => setWeights({ ...weights, mrz: parseInt(e.target.value) })}
                className="w-full accent-cyan-500 bg-slate-950 rounded-lg cursor-pointer"
              />
            </div>

            <div>
              <label className="text-slate-300 block mb-1 flex items-center justify-between">
                <span>Forensic Tamper AI (ELA)</span>
                <span className="text-cyan-400 font-bold">{weights.tamper}%</span>
              </label>
              <input
                type="range"
                min="0"
                max="60"
                value={weights.tamper}
                onChange={(e) => setWeights({ ...weights, tamper: parseInt(e.target.value) })}
                className="w-full accent-cyan-500 bg-slate-950 rounded-lg cursor-pointer"
              />
            </div>

            <div>
              <label className="text-slate-300 block mb-1 flex items-center justify-between">
                <span>Biometric Face Verification</span>
                <span className="text-cyan-400 font-bold">{weights.face}%</span>
              </label>
              <input
                type="range"
                min="0"
                max="60"
                value={weights.face}
                onChange={(e) => setWeights({ ...weights, face: parseInt(e.target.value) })}
                className="w-full accent-cyan-500 bg-slate-950 rounded-lg cursor-pointer"
              />
            </div>

            <div>
              <label className="text-slate-300 block mb-1 flex items-center justify-between">
                <span>Data Consistency Crosscheck</span>
                <span className="text-cyan-400 font-bold">{weights.consistency}%</span>
              </label>
              <input
                type="range"
                min="0"
                max="40"
                value={weights.consistency}
                onChange={(e) => setWeights({ ...weights, consistency: parseInt(e.target.value) })}
                className="w-full accent-cyan-500 bg-slate-950 rounded-lg cursor-pointer"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="text-slate-300 block mb-1 flex items-center justify-between">
                <span>Simulated Watchlist Adapter (Demo Sandboxed)</span>
                <span className="text-cyan-400 font-bold">{weights.watchlist}%</span>
              </label>
              <input
                type="range"
                min="0"
                max="20"
                value={weights.watchlist}
                onChange={(e) => setWeights({ ...weights, watchlist: parseInt(e.target.value) })}
                className="w-full accent-cyan-500 bg-slate-950 rounded-lg cursor-pointer"
              />
            </div>
          </div>
        </div>

        {/* Risk Thresholds */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur space-y-4">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
              2. Risk Tier Classification Cutoffs
            </h3>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <span className="text-emerald-400 font-bold block mb-1">LOW RISK TIER</span>
              <span className="text-slate-400 text-[11px] block mb-2">0 to {thresholds.low} Index</span>
              <span className="text-[10px] text-slate-400">Action: Clear for entry</span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <span className="text-amber-400 font-bold block mb-1">MEDIUM RISK TIER</span>
              <span className="text-slate-400 text-[11px] block mb-2">{thresholds.low + 1} to {thresholds.medium} Index</span>
              <span className="text-[10px] text-slate-400">Action: Routine confirmation</span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <span className="text-rose-400 font-bold block mb-1">HIGH & CRITICAL TIER</span>
              <span className="text-slate-400 text-[11px] block mb-2">{thresholds.medium + 1} to 100 Index</span>
              <span className="text-[10px] text-slate-400">Action: Secondary inspection / Detain</span>
            </div>
          </div>
        </div>

        {/* AI Engine Status Overview */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur space-y-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
              3. Connected Subsystem Modules
            </h3>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
              <span className="text-slate-300">OCR Extraction</span>
              <span className="text-emerald-400 font-bold">PyTesseract 5.5 (Active)</span>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
              <span className="text-slate-300">MRZ Parser & Checksums</span>
              <span className="text-emerald-400 font-bold">ICAO 9303 Doc 9303 (Active)</span>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
              <span className="text-slate-300">Tamper AI Model</span>
              <span className="text-emerald-400 font-bold">PyTorch CNN + ELA (Active)</span>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
              <span className="text-slate-300">Face Verification</span>
              <span className="text-emerald-400 font-bold">Cosine Embedding Net (Active)</span>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between sm:col-span-2">
              <span className="text-slate-300">Watchlist Provider</span>
              <span className="text-cyan-400 font-bold">MockWatchlistProvider (Simulated Sandbox)</span>
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex items-center justify-end gap-3">
          {error && (
            <span className="text-xs font-mono text-rose-400 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" /> {error}
            </span>
          )}
          {saved && !error && (
            <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
              <Check className="w-3.5 h-3.5" /> Policy weights updated — takes effect on the next screening
            </span>
          )}
          <button
            type="submit"
            disabled={saving || totalWeight !== 100}
            className="px-6 py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono font-bold tracking-wider uppercase transition-colors shadow-md shadow-cyan-950/40 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Apply Policy Configuration
          </button>
        </div>
      </form>
    </div>
  );
};
