import React, { useState } from 'react';
import type { AlertRecord } from '../types/api';

interface AlertsPanelProps {
  alerts: AlertRecord[];
  onSendTestAlert: () => Promise<void>;
  sendingTest: boolean;
}

export const AlertsPanel: React.FC<AlertsPanelProps> = ({ alerts, onSendTestAlert, sendingTest }) => {
  const [selectedAlert, setSelectedAlert] = useState<AlertRecord | null>(null);

  return (
    <section className="glass-panel rounded-2xl p-6 border border-white/10 shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 mb-5 border-b border-white/10 gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="flex h-2.5 w-2.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500"></span>
            </span>
            <h2 className="text-lg font-bold text-white tracking-tight">Alert Dispatch Pipeline</h2>
            <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-amber-950/70 text-amber-300 border border-amber-600/50 font-mono font-bold shadow-sm">
              EMAIL_MODE: dry_run
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Rule A (Cross &gt; 60) · Rule B (+15 in 24h) · Rule C (Sev 5 Consensus) & Daily Briefing.
          </p>
        </div>

        <button
          onClick={onSendTestAlert}
          disabled={sendingTest}
          className="glow-btn-sky px-4 py-2 rounded-xl disabled:opacity-50 text-white text-xs font-bold tracking-wide shadow-lg transition-all cursor-pointer flex items-center gap-2 shrink-0"
        >
          <span>📨</span>
          <span>{sendingTest ? 'Dispatching...' : 'Dispatch Test Alert'}</span>
        </button>
      </div>

      {alerts.length === 0 ? (
        <div className="py-8 text-center bg-[#070a10]/50 border border-white/5 rounded-xl shadow-inner">
          <p className="text-xs text-slate-400">No alert dispatches in current session. Trigger a test alert above to inspect outbox rendering.</p>
        </div>
      ) : (
        <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
          {alerts.map((alert) => (
            <div
              key={alert.key}
              className="glass-card rounded-xl p-3.5 flex items-center justify-between border border-white/8 hover:border-sky-500/30 transition-all cursor-pointer shadow-sm group"
              onClick={() => setSelectedAlert(alert)}
            >
              <div className="flex items-center gap-3.5">
                <span className="text-xs font-black font-mono px-2.5 py-1 rounded-lg bg-sky-950/80 text-sky-300 border border-sky-700/60 shadow-sm">
                  {alert.company}
                </span>
                <div>
                  <div className="text-xs font-bold text-slate-100 group-hover:text-sky-300 transition-colors">
                    {alert.subject}
                  </div>
                  <div className="text-[10px] text-slate-400 flex items-center gap-2 mt-0.5">
                    <span className="font-medium text-slate-300">{alert.rule}</span>
                    <span>•</span>
                    <span className="font-mono">{new Date(alert.ts).toLocaleTimeString()}</span>
                    <span>•</span>
                    <span className="text-emerald-400 font-mono font-semibold">[{alert.status}]</span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                className="text-xs text-sky-400 group-hover:text-sky-300 font-semibold flex items-center gap-1 shrink-0 px-2 py-1 rounded hover:bg-white/5 transition-all"
              >
                Preview HTML &rarr;
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Rendered HTML Alert Preview Modal */}
      {selectedAlert && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/75 backdrop-blur-md flex items-center justify-center p-4 animate-fadeIn">
          <div className="glass-panel rounded-2xl max-w-xl w-full p-6 shadow-2xl border border-white/15">
            <div className="flex items-start justify-between pb-4 border-b border-white/10 mb-4">
              <div>
                <h3 className="text-base font-bold text-white tracking-tight">{selectedAlert.subject}</h3>
                <div className="text-xs text-slate-400 mt-1 font-mono">
                  Recipients: <span className="text-slate-200">{selectedAlert.recipients.join(', ')}</span>
                </div>
              </div>
              <button
                onClick={() => setSelectedAlert(null)}
                className="p-1.5 rounded-lg bg-white/5 hover:bg-white/15 text-slate-400 hover:text-white transition-colors"
                title="Close Modal"
              >
                ✕
              </button>
            </div>

            <div className="bg-white text-slate-900 rounded-xl p-5 text-sm max-h-96 overflow-y-auto font-sans shadow-inner">
              <div dangerouslySetInnerHTML={{ __html: selectedAlert.body_html }} />
            </div>

            <div className="mt-5 flex justify-end">
              <button
                onClick={() => setSelectedAlert(null)}
                className="glass-pill hover:bg-white/10 px-5 py-2 rounded-xl text-xs text-slate-200 font-semibold transition-all cursor-pointer"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
