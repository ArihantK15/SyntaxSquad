import React, { useState, useEffect } from 'react';
import { Settings, Sliders, Check, Loader2, AlertTriangle } from 'lucide-react';
import { api } from '../services/api';
import { SectionHeading } from '../components/SectionHeading';

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
      <div className="p-12 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading live policy configuration...
      </div>
    );
  }

  const subsystems = [
    { name: 'OCR extraction', value: 'PyTesseract 5.5 (active)' },
    { name: 'MRZ parser & checksums', value: 'ICAO 9303 (active)' },
    { name: 'Tamper AI model', value: 'PyTorch CNN + ELA (active)' },
    { name: 'Face verification', value: 'Cosine embedding net (active)' },
    { name: 'Watchlist provider', value: 'MockWatchlistProvider (simulated sandbox)', accent: true },
  ];

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <SectionHeading
        title="Settings"
        description="Adjust risk engine weights, decision thresholds, and view connected subsystems."
        icon={<Settings className="w-5 h-5 text-cyan-400" />}
      />

      <form onSubmit={handleSave} className="space-y-6">
        {/* Risk Engine Weights -- the one real interactive control, keeps a card */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 backdrop-blur space-y-4">
          <SectionHeading
            level="h3"
            title="Risk engine factor weights"
            icon={<Sliders className="w-4 h-4 text-cyan-400" />}
            action={
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded ${
                  totalWeight === 100
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/30'
                    : 'bg-rose-950 text-rose-300 border border-rose-500/30'
                }`}
              >
                {totalWeight === 100 ? 'Valid — 100%' : `Must total 100% — currently ${totalWeight}%`}
              </span>
            }
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="text-slate-300 block mb-1 flex items-center justify-between">
                <span>MRZ & validation rules</span>
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
                <span>Forensic tamper AI (ELA)</span>
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
                <span>Biometric face verification</span>
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
                <span>Data consistency crosscheck</span>
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
                <span>Simulated watchlist adapter (demo sandboxed)</span>
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

        {/* Risk tier cutoffs -- read-only reference data, a plain row not a card */}
        <div>
          <h3 className="text-sm font-semibold text-slate-200 mb-3">Risk tier classification cutoffs</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <span className="text-emerald-400 font-semibold block mb-1">Low risk</span>
              <span className="text-slate-500 block mb-1">0–{thresholds.low}</span>
              <span className="text-slate-500">Clear for entry</span>
            </div>
            <div>
              <span className="text-amber-400 font-semibold block mb-1">Medium risk</span>
              <span className="text-slate-500 block mb-1">{thresholds.low + 1}–{thresholds.medium}</span>
              <span className="text-slate-500">Routine confirmation</span>
            </div>
            <div>
              <span className="text-rose-400 font-semibold block mb-1">High & critical</span>
              <span className="text-slate-500 block mb-1">{thresholds.medium + 1}–100</span>
              <span className="text-slate-500">Secondary inspection / detain</span>
            </div>
          </div>
        </div>

        {/* Connected subsystems -- plain label/value list, not a grid of boxes */}
        <div>
          <h3 className="text-sm font-semibold text-slate-200 mb-3">Connected subsystem modules</h3>
          <div className="divide-y divide-slate-800/80 border-t border-b border-slate-800/80">
            {subsystems.map((sub) => (
              <div key={sub.name} className="flex items-center justify-between py-2.5 text-xs">
                <span className="text-slate-300">{sub.name}</span>
                <span className={`font-semibold ${sub.accent ? 'text-cyan-400' : 'text-emerald-400'}`}>
                  {sub.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Save Button */}
        <div className="flex items-center justify-end gap-3">
          {error && (
            <span className="text-xs text-rose-400 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" /> {error}
            </span>
          )}
          {saved && !error && (
            <span className="text-xs text-emerald-400 flex items-center gap-1">
              <Check className="w-3.5 h-3.5" /> Policy weights updated — takes effect on the next screening
            </span>
          )}
          <button
            type="submit"
            disabled={saving || totalWeight !== 100}
            className="px-6 py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold transition-colors shadow-md shadow-cyan-950/40 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Apply policy configuration
          </button>
        </div>
      </form>
    </div>
  );
};
