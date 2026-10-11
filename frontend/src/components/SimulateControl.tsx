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
    <section className="glass-panel rounded-2xl p-4 md:p-5 border border-white/10 shadow-xl flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="flex h-2.5 w-2.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
          </span>
          <span className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
            Interactive Scenario Sandbox
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Company selector */}
          <div className="relative">
            <select
              value={targetCompany}
              onChange={(e) => setTargetCompany(e.target.value)}
              className="glass-input text-xs text-white rounded-xl px-3 py-1.5 font-semibold font-mono appearance-none pr-8 cursor-pointer"
            >
              <option value="WFC" className="bg-[#0b0e14] text-white">WFC (Wells Fargo)</option>
              <option value="EFX" className="bg-[#0b0e14] text-white">EFX (Equifax)</option>
              <option value="PYPL" className="bg-[#0b0e14] text-white">PYPL (PayPal)</option>
              <option value="COIN" className="bg-[#0b0e14] text-white">COIN (Coinbase)</option>
              <option value="NAVI" className="bg-[#0b0e14] text-white">NAVI (Navient)</option>
            </select>
            <span className="absolute right-2.5 top-2 pointer-events-none text-[10px] text-slate-400">▼</span>
          </div>

          {/* Severity selector */}
          <div className="relative">
            <select
              value={severity}
              onChange={(e) => setSeverity(Number(e.target.value))}
              className="glass-input text-xs text-white rounded-xl px-3 py-1.5 font-medium appearance-none pr-8 cursor-pointer"
            >
              <option value={5} className="bg-[#0b0e14] text-rose-300">Severity 5 (Critical Enforcement Action)</option>
              <option value={4} className="bg-[#0b0e14] text-amber-300">Severity 4 (Major Regulatory Inquiry)</option>
              <option value={3} className="bg-[#0b0e14] text-blue-300">Severity 3 (Consumer Complaint Spike)</option>
            </select>
            <span className="absolute right-2.5 top-2 pointer-events-none text-[10px] text-slate-400">▼</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() =>
            onSimulate(
              targetCompany,
              severity,
              `Simulated Breaking Regulatory Enforcement Action against ${targetCompany}`
            )
          }
          disabled={loading}
          className="glow-btn-rose px-4 py-2 rounded-xl text-white text-xs font-bold tracking-wide shadow-lg disabled:opacity-50 cursor-pointer flex items-center gap-2"
        >
          <span>⚡</span>
          <span>{loading ? 'Simulating...' : 'Inject Spike Incident'}</span>
        </button>

        <button
          onClick={onReset}
          disabled={loading}
          className="glass-pill hover:bg-white/10 px-3.5 py-2 rounded-xl text-slate-300 hover:text-white text-xs font-semibold disabled:opacity-50 transition-all cursor-pointer flex items-center gap-1.5"
        >
          <span>🔄</span>
          <span>Reset Simulation</span>
        </button>
      </div>
    </section>
  );
};
