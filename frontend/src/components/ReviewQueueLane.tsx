import React, { useState } from 'react';
import type { ConsensusFlag } from '../types/api';

interface ReviewQueueLaneProps {
  queue: ConsensusFlag[];
  reportLog?: ConsensusFlag[];
  onVerdict: (itemId: string, verdict: 'confirm' | 'dismiss') => Promise<void>;
  loading: boolean;
}

export const ReviewQueueLane: React.FC<ReviewQueueLaneProps> = ({
  queue,
  reportLog = [],
  onVerdict,
  loading,
}) => {
  const [activeTab, setActiveTab] = useState<'queue' | 'log'>('queue');
  const [lastActionToast, setLastActionToast] = useState<{
    itemId: string;
    verdict: 'confirm' | 'dismiss';
    company: string;
  } | null>(null);
  const [logFilter, setLogFilter] = useState<'all' | 'confirm' | 'dismiss'>('all');

  const handleAction = async (itemId: string, verdict: 'confirm' | 'dismiss', company: string) => {
    setLastActionToast({ itemId, verdict, company });
    await onVerdict(itemId, verdict);
  };

  const filteredLog = reportLog.filter((item) => {
    if (logFilter === 'confirm') return item.analyst_verdict === 'confirm' || item.status === 'confirmed';
    if (logFilter === 'dismiss') return item.analyst_verdict === 'dismiss' || item.status === 'dismissed';
    return true;
  });

  const confirmedCount = reportLog.filter(
    (i) => i.analyst_verdict === 'confirm' || i.status === 'confirmed'
  ).length;
  const dismissedCount = reportLog.filter(
    (i) => i.analyst_verdict === 'dismiss' || i.status === 'dismissed'
  ).length;

  return (
    <section className="glass-panel rounded-2xl p-6 border border-white/10 shadow-xl relative overflow-hidden">
      {/* Header & View Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 mb-5 border-b border-white/10 gap-4">
        <div className="flex items-center gap-3">
          <div className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-sky-500"></span>
          </div>
          <div>
            <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2.5">
              Human Analyst Review Lane
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Dual-model divergence verification and official audit trail
            </p>
          </div>
        </div>

        {/* Tab Controls: Pending Queue vs Human Analyst Report Log */}
        <div className="flex items-center p-1 rounded-xl bg-black/60 border border-white/10">
          <button
            onClick={() => setActiveTab('queue')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'queue'
                ? 'bg-sky-500/20 text-sky-200 border border-sky-400/30 shadow-sm shadow-sky-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>Pending Review</span>
            <span
              className={`text-[10px] px-2 py-0.2 rounded-full font-mono ${
                queue.length > 0
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'bg-white/5 text-slate-400'
              }`}
            >
              {queue.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('log')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'log'
                ? 'bg-emerald-500/20 text-emerald-200 border border-emerald-400/30 shadow-sm shadow-emerald-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>Human Analyst Report Log</span>
            <span
              className={`text-[10px] px-2 py-0.2 rounded-full font-mono ${
                reportLog.length > 0
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                  : 'bg-white/5 text-slate-400'
              }`}
            >
              {reportLog.length}
            </span>
          </button>
        </div>
      </div>

      {/* Confirmation Toast Notification */}
      {lastActionToast && (
        <div className="mb-5 p-3.5 rounded-xl bg-emerald-950/50 border border-emerald-500/40 flex items-center justify-between text-xs text-emerald-200 animate-fadeIn shadow-lg shadow-emerald-950/40">
          <div className="flex items-center gap-2.5">
            <span className="h-5 w-5 rounded-full bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-300 font-bold">
              ✓
            </span>
            <span>
              Item <strong>{lastActionToast.itemId}</strong> ({lastActionToast.company}) successfully{' '}
              <strong className="text-white">
                {lastActionToast.verdict === 'confirm' ? 'CONFIRMED' : 'DISMISSED'}
              </strong>{' '}
              and added to the{' '}
              <strong className="underline decoration-emerald-400 underline-offset-2">
                Human Analyst Report Log
              </strong>
              .
            </span>
          </div>
          <div className="flex items-center gap-2">
            {activeTab !== 'log' && (
              <button
                onClick={() => setActiveTab('log')}
                className="px-2.5 py-1 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 font-semibold border border-emerald-400/30 cursor-pointer"
              >
                View in Report Log &rarr;
              </button>
            )}
            <button
              onClick={() => setLastActionToast(null)}
              className="text-emerald-400/80 hover:text-white px-1.5"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* VIEW 1: PENDING QUEUE */}
      {activeTab === 'queue' && (
        <>
          <div className="flex items-center justify-between text-xs text-slate-400 mb-4">
            <span>
              Items flagged with Dual-LLM divergence (Mistral vs Blind Verifier)
            </span>
            <span className="font-mono text-[11px] glass-pill px-2.5 py-0.5 rounded-md">
              Default Pre-Review Factor: <strong className="text-amber-400">0.5x</strong>
            </span>
          </div>

          {loading && queue.length === 0 ? (
            <div className="py-10 text-center text-xs text-slate-400 animate-pulse space-y-2">
              <div className="h-2 w-28 bg-sky-500/30 rounded mx-auto"></div>
              <p>Polling Dual-LLM consensus review lane...</p>
            </div>
          ) : queue.length === 0 ? (
            <div className="py-12 text-center bg-[#070a10]/50 border border-white/5 rounded-xl shadow-inner">
              <div className="h-10 w-10 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center mx-auto mb-3 text-lg font-bold">
                ✓
              </div>
              <p className="text-sm text-slate-200 font-medium">
                All high-severity items have reached consensus or been reviewed.
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Zero pending items. Confirmed cases are recorded in the Human Analyst Report Log.
              </p>
              {reportLog.length > 0 && (
                <button
                  onClick={() => setActiveTab('log')}
                  className="mt-4 px-4 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-sky-300 text-xs font-semibold border border-sky-400/20 transition-all cursor-pointer"
                >
                  Inspect Human Analyst Report Log ({reportLog.length}) &rarr;
                </button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {queue.map((item) => (
                <div
                  key={item.item_id}
                  className="glass-card rounded-xl p-5 flex flex-col justify-between border border-white/8 hover:border-sky-500/30 shadow-lg transition-all"
                >
                  <div>
                    {/* Header: Company, Risk Type, Divergence */}
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2.5">
                        <span className="text-lg font-black text-white font-mono tracking-wide">
                          {item.company}
                        </span>
                        <span className="text-[10px] px-2.5 py-0.5 rounded-md font-bold bg-purple-950/70 text-purple-300 border border-purple-700/60 uppercase tracking-wider">
                          {item.risk_type}
                        </span>
                        <span className="text-[11px] font-mono text-slate-400">
                          ID: {item.item_id}
                        </span>
                      </div>
                      <div className="text-[11px] font-mono px-2.5 py-1 rounded-lg bg-amber-950/70 text-amber-300 border border-amber-600/50 shadow-sm flex items-center gap-1.5">
                        <span>Mistral: Sev {item.primary_severity}</span>
                        <span className="text-amber-400">⚡</span>
                        <span>Verifier: Sev {item.verifier_severity ?? '?'}</span>
                      </div>
                    </div>

                    {/* Reason description */}
                    <p className="text-xs text-slate-300 leading-relaxed bg-[#080b11]/70 p-3 rounded-xl border border-white/5 mb-3 shadow-inner">
                      {item.reason}
                    </p>

                    {/* Topics & Regulators tags */}
                    <div className="flex flex-wrap gap-1.5 mb-4">
                      {item.topics.map((t) => (
                        <span
                          key={t}
                          className="text-[10px] px-2 py-0.5 rounded-md bg-white/5 text-slate-300 border border-white/5"
                        >
                          #{t}
                        </span>
                      ))}
                      {item.regulators.map((r) => (
                        <span
                          key={r}
                          className="text-[10px] px-2 py-0.5 rounded-md bg-emerald-950/80 text-emerald-300 border border-emerald-700/50 font-mono font-semibold"
                        >
                          {r}
                        </span>
                      ))}
                      {item.source_url && (
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[10px] px-2 py-0.5 rounded-md bg-sky-950/60 text-sky-300 hover:text-white border border-sky-800/40 flex items-center gap-1 transition-colors"
                        >
                          Source ↗
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center justify-between pt-3.5 border-t border-white/10">
                    <span className="text-[11px] text-slate-400 font-mono">
                      Weight Factor: <strong className="text-white">{item.review_factor.toFixed(1)}x</strong>
                    </span>
                    <div className="flex items-center gap-2.5">
                      <button
                        onClick={() => handleAction(item.item_id, 'confirm', item.company)}
                        className="glow-btn-emerald px-3.5 py-1.5 rounded-lg text-white text-xs font-bold shadow transition-all cursor-pointer flex items-center gap-1.5 hover:scale-[1.02] active:scale-[0.98]"
                        title="Confirm item: apply 1.0 weight factor and add to Report Log"
                      >
                        <span>✓</span> Confirm (1.0)
                      </button>
                      <button
                        onClick={() => handleAction(item.item_id, 'dismiss', item.company)}
                        className="glass-pill hover:bg-rose-950/60 hover:border-rose-500/50 text-rose-300 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 active:scale-[0.98]"
                        title="Dismiss item: apply 0.0 weight factor and archive to Report Log"
                      >
                        <span>✕</span> Dismiss (0.0)
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* VIEW 2: HUMAN ANALYST REPORT LOG */}
      {activeTab === 'log' && (
        <div className="space-y-4 animate-fadeIn">
          {/* Summary Audit Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
            <div className="p-3 rounded-xl bg-black/50 border border-white/8 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
                  Total Audited
                </div>
                <div className="text-xl font-bold font-mono text-white mt-0.5">
                  {reportLog.length}
                </div>
              </div>
              <span className="text-xs px-2 py-1 rounded bg-white/5 text-slate-300 font-mono">
                Log Total
              </span>
            </div>

            <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-500/20 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-emerald-400 uppercase tracking-wider font-semibold">
                  Confirmed (1.0x)
                </div>
                <div className="text-xl font-bold font-mono text-emerald-200 mt-0.5">
                  {confirmedCount}
                </div>
              </div>
              <span className="text-xs px-2 py-1 rounded bg-emerald-950/60 text-emerald-300 font-mono border border-emerald-600/30">
                Applied
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-700/30 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
                  Dismissed (0.0x)
                </div>
                <div className="text-xl font-bold font-mono text-slate-300 mt-0.5">
                  {dismissedCount}
                </div>
              </div>
              <span className="text-xs px-2 py-1 rounded bg-white/5 text-slate-400 font-mono">
                Neutralized
              </span>
            </div>
          </div>

          {/* Filter Bar */}
          <div className="flex items-center justify-between pt-1 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 font-medium">Filter Log:</span>
              <button
                onClick={() => setLogFilter('all')}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer ${
                  logFilter === 'all'
                    ? 'bg-white/10 text-white border border-white/20'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                All ({reportLog.length})
              </button>
              <button
                onClick={() => setLogFilter('confirm')}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer ${
                  logFilter === 'confirm'
                    ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/40'
                    : 'text-slate-400 hover:text-emerald-300'
                }`}
              >
                Confirmed ({confirmedCount})
              </button>
              <button
                onClick={() => setLogFilter('dismiss')}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer ${
                  logFilter === 'dismiss'
                    ? 'bg-rose-950/80 text-rose-300 border border-rose-500/40'
                    : 'text-slate-400 hover:text-rose-300'
                }`}
              >
                Dismissed ({dismissedCount})
              </button>
            </div>

            <div className="text-[11px] text-slate-500 font-mono">
              Audit trail verified with tamper-free graph persistence
            </div>
          </div>

          {/* Log List / Table */}
          {filteredLog.length === 0 ? (
            <div className="py-12 text-center bg-[#070a10]/50 border border-white/5 rounded-xl">
              <p className="text-sm text-slate-300 font-medium">
                No items match the selected report log filter.
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Confirm items from the Pending Review tab to populate this audit log.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredLog.map((log) => {
                const isConfirmed = log.analyst_verdict === 'confirm' || log.status === 'confirmed';
                return (
                  <div
                    key={log.item_id}
                    className="p-4 rounded-xl bg-[#090d16]/80 border border-white/8 hover:border-white/15 transition-all shadow-md flex flex-col sm:flex-row sm:items-start justify-between gap-4"
                  >
                    <div className="space-y-1.5 flex-1">
                      {/* Company, Status, Verdict Badge */}
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span className="text-base font-black text-white font-mono tracking-wide">
                          {log.company}
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold text-slate-300 bg-white/5 border border-white/10">
                          {log.item_id}
                        </span>

                        {isConfirmed ? (
                          <span className="text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 neon-border-emerald flex items-center gap-1 shadow-sm">
                            <span>✓</span> CONFIRMED · Weight 1.0x
                          </span>
                        ) : (
                          <span className="text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-rose-950/80 text-rose-300 border border-rose-500/40 flex items-center gap-1 shadow-sm">
                            <span>✕</span> DISMISSED · Weight 0.0x
                          </span>
                        )}

                        <span className="text-[10px] px-2 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40 uppercase font-semibold">
                          {log.risk_type}
                        </span>

                        <span className="text-[10px] text-slate-500 font-mono ml-auto">
                          Audited: {new Date(log.date).toLocaleDateString()}
                        </span>
                      </div>

                      {/* Reason Description */}
                      <p className="text-xs text-slate-300 leading-relaxed pt-1">
                        {log.reason}
                      </p>

                      {/* Metadata tags */}
                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        {log.topics.map((t) => (
                          <span
                            key={t}
                            className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-400 border border-white/5 font-sans"
                          >
                            #{t}
                          </span>
                        ))}
                        {log.regulators.map((r) => (
                          <span
                            key={r}
                            className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/50 text-emerald-300 border border-emerald-700/40 font-mono font-semibold"
                          >
                            {r}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Right column: Severity Breakdown & Source Link */}
                    <div className="sm:text-right shrink-0 flex flex-col justify-between sm:items-end gap-2 pt-1 border-t sm:border-t-0 border-white/5">
                      <div className="text-[11px] font-mono text-slate-300 bg-black/40 px-2.5 py-1 rounded-lg border border-white/5">
                        <div>
                          Primary Sev: <strong className="text-white">{log.primary_severity}</strong>
                        </div>
                        {log.verifier_severity !== undefined && (
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            Verifier Sev: <strong>{log.verifier_severity}</strong>
                          </div>
                        )}
                      </div>

                      {log.source_url && (
                        <a
                          href={log.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1 transition-colors self-start sm:self-end"
                        >
                          Source Document &rarr;
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
