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
    <section className="bg-[#121620] border border-slate-800 rounded-xl p-5 shadow-lg">
      <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-rose-500"></span>
            <h2 className="text-lg font-bold text-white">Alert Dispatch & History</h2>
            <span className="text-[11px] px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-mono">
              EMAIL_MODE: dry_run
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Rules A (Cross &gt; 60), B (+15 in 24h), C (Sev 5 Agreed/Confirmed) & Daily Briefing.
          </p>
        </div>

        <button
          onClick={onSendTestAlert}
          disabled={sendingTest}
          className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold shadow transition-all cursor-pointer flex items-center gap-1.5"
        >
          {sendingTest ? 'Sending...' : '📨 Send Test Alert'}
        </button>
      </div>

      {alerts.length === 0 ? (
        <div className="py-6 text-center bg-[#0d1017] border border-slate-800/50 rounded-lg">
          <p className="text-xs text-slate-400">No alert dispatches in current session. Trigger a test alert above.</p>
        </div>
      ) : (
        <div className="space-y-2.5 max-h-60 overflow-y-auto">
          {alerts.map((alert) => (
            <div
              key={alert.key}
              className="bg-[#161c28] border border-slate-800/80 rounded-lg p-3 flex items-center justify-between hover:border-slate-700 transition-colors cursor-pointer"
              onClick={() => setSelectedAlert(alert)}
            >
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-slate-800 text-white">
                  {alert.company}
                </span>
                <div>
                  <div className="text-xs font-medium text-slate-200">{alert.subject}</div>
                  <div className="text-[10px] text-slate-400 flex items-center gap-2 mt-0.5">
                    <span>{alert.rule}</span>
                    <span>•</span>
                    <span>{new Date(alert.ts).toLocaleTimeString()}</span>
                    <span>•</span>
                    <span className="text-emerald-400 font-mono">[{alert.status}]</span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                className="text-xs text-blue-400 hover:text-blue-300 font-medium"
              >
                Preview HTML &rarr;
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Rendered HTML Alert Preview Modal */}
      {selectedAlert && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#121620] border border-slate-700 rounded-xl max-w-xl w-full p-6 shadow-2xl">
            <div className="flex items-start justify-between pb-3 border-b border-slate-800 mb-4">
              <div>
                <h3 className="text-base font-bold text-white">{selectedAlert.subject}</h3>
                <div className="text-xs text-slate-400 mt-1">To: {selectedAlert.recipients.join(', ')}</div>
              </div>
              <button
                onClick={() => setSelectedAlert(null)}
                className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="bg-white text-slate-900 rounded p-4 text-sm max-h-96 overflow-y-auto font-sans">
              <div dangerouslySetInnerHTML={{ __html: selectedAlert.body_html }} />
            </div>

            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setSelectedAlert(null)}
                className="px-4 py-1.5 rounded bg-slate-800 text-xs text-slate-200 hover:bg-slate-700"
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
