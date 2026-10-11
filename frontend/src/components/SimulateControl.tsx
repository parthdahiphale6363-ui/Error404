import React, { useState } from 'react';

interface SimulateControlProps {
  onSimulate: (company: string, severity: number, headline: string) => Promise<void>;
  onReset: () => Promise<void>;
  loading: boolean;
}

export const SimulateControl: React.FC<SimulateControlProps> = ({ onSimulate, onReset, loading }) => {
  const [targetCompany, setTargetCompany] = useState<string>('WFC');
  const [severity, setSeverity] = useState<number>(5);

  return (
    <section className="bg-[#121620] border border-slate-800 rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          🎮 Interactive Demo Sandbox:
        </span>
        <select
          value={targetCompany}
          onChange={(e) => setTargetCompany(e.target.value)}
          className="bg-slate-900 border border-slate-700 text-xs text-white rounded px-2.5 py-1"
        >
          <option value="WFC">WFC (Wells Fargo)</option>
          <option value="EFX">EFX (Equifax)</option>
          <option value="PYPL">PYPL (PayPal)</option>
          <option value="COIN">COIN (Coinbase)</option>
          <option value="NAVI">NAVI (Navient)</option>
        </select>

        <select
          value={severity}
          onChange={(e) => setSeverity(Number(e.target.value))}
          className="bg-slate-900 border border-slate-700 text-xs text-white rounded px-2.5 py-1"
        >
          <option value={5}>Severity 5 (Critical Enforcement)</option>
          <option value={4}>Severity 4 (Major Regulatory Inquiry)</option>
          <option value={3}>Severity 3 (Material Consumer Backlog)</option>
        </select>
      </div>

      <div className="flex items-center gap-2.5">
        <button
          onClick={() =>
            onSimulate(
              targetCompany,
              severity,
              `Simulated Breaking Enforcement Action against ${targetCompany}`
            )
          }
          disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white text-xs font-semibold shadow transition-all cursor-pointer flex items-center gap-1.5"
        >
          ⚡ Inject Spike Item
        </button>
        <button
          onClick={onReset}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 text-xs font-medium border border-slate-700 transition-all cursor-pointer"
        >
          🔄 Reset Simulation
        </button>
      </div>
    </section>
  );
};
