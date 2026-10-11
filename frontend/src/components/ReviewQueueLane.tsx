import React from 'react';
import type { ConsensusFlag } from '../types/api';

interface ReviewQueueLaneProps {
  queue: ConsensusFlag[];
  onVerdict: (itemId: string, verdict: 'confirm' | 'dismiss') => Promise<void>;
  loading: boolean;
}

export const ReviewQueueLane: React.FC<ReviewQueueLaneProps> = ({ queue, onVerdict, loading }) => {
  return (
    <section className="bg-[#121620] border border-slate-800 rounded-xl p-5 shadow-lg">
      <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <span className="h-3 w-3 rounded-full bg-blue-500 animate-pulse"></span>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            Human Analyst Review Lane
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-950/80 text-blue-300 border border-blue-800/60 font-mono">
              {queue.length} Pending
            </span>
          </h2>
        </div>
        <div className="text-xs text-slate-400">
          Divergent Dual-LLM items weighted at <span className="font-semibold text-amber-400">0.5x</span> until human verdict
        </div>
      </div>

      {loading && queue.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500 animate-pulse">
          Loading review queue...
        </div>
      ) : queue.length === 0 ? (
        <div className="py-8 text-center bg-[#0d1017] border border-slate-800/50 rounded-lg">
          <p className="text-sm text-slate-400">All high-severity items have reached consensus or been reviewed.</p>
          <span className="text-xs text-emerald-400 mt-1 inline-block">✓ Review Queue Clean</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {queue.map((item) => (
            <div
              key={item.item_id}
              className="bg-[#161c28] border border-slate-800 rounded-lg p-4 flex flex-col justify-between hover:border-slate-700 transition-colors"
            >
              <div>
                {/* Header: Company, Risk Type, Divergence */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-base font-bold text-white font-mono">{item.company}</span>
                    <span className="text-[11px] px-2 py-0.5 rounded font-semibold bg-purple-950/70 text-purple-300 border border-purple-800/50 uppercase">
                      {item.risk_type}
                    </span>
                  </div>
                  <div className="text-[11px] font-mono px-2 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/50">
                    Mistral: Sev {item.primary_severity} ⚡ Verifier: Sev {item.verifier_severity ?? '?'}
                  </div>
                </div>

                {/* Reason */}
                <p className="text-xs text-slate-300 leading-relaxed bg-[#0e121a] p-2.5 rounded border border-slate-800/60 mb-2.5">
                  {item.reason}
                </p>

                {/* Topics & Regulators */}
                <div className="flex flex-wrap gap-1 mb-3">
                  {item.topics.map((t) => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                      #{t}
                    </span>
                  ))}
                  {item.regulators.map((r) => (
                    <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/40 font-mono">
                      {r}
                    </span>
                  ))}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-3 border-t border-slate-800/60">
                <span className="text-[11px] text-slate-400 font-mono">
                  Current Factor: {item.review_factor.toFixed(1)}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onVerdict(item.item_id, 'confirm')}
                    className="px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition-all cursor-pointer flex items-center gap-1"
                  >
                    <span>✓</span> Confirm (1.0)
                  </button>
                  <button
                    onClick={() => onVerdict(item.item_id, 'dismiss')}
                    className="px-3 py-1.5 rounded-md bg-rose-600/80 hover:bg-rose-500 text-white text-xs font-semibold shadow transition-all cursor-pointer flex items-center gap-1"
                  >
                    <span>✕</span> Dismiss (0.0)
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
