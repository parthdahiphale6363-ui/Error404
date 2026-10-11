import { useEffect, useState, useCallback } from 'react';
import type { CompanySummary, HealthResponse, ConsensusFlag, AlertRecord } from './types/api';
import { EvidenceDrawer } from './components/EvidenceDrawer';
import { ReviewQueueLane } from './components/ReviewQueueLane';
import { AlertsPanel } from './components/AlertsPanel';
import { SimulateControl } from './components/SimulateControl';
import { CelestialBackground } from './components/CelestialBackground';
import './App.css';

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ConsensusFlag[]>([]);
  const [analystReportLog, setAnalystReportLog] = useState<ConsensusFlag[]>([]);
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<CompanySummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [sendingTestAlert, setSendingTestAlert] = useState<boolean>(false);
  const [simulating, setSimulating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  const refreshData = useCallback(async () => {
    try {
      const [healthRes, compRes, queueRes, logRes, alertsRes] = await Promise.all([
        fetch('/api/health').catch(() => null),
        fetch('/api/companies').catch(() => null),
        fetch('/api/review-queue').catch(() => null),
        fetch('/api/review-log').catch(() => null),
        fetch('/api/alerts').catch(() => null),
      ]);

      if (healthRes && healthRes.ok) {
        setHealth(await healthRes.json());
      }

      if (compRes && compRes.ok) {
        const compData: CompanySummary[] = await compRes.json();
        setCompanies(compData);
      }

      if (queueRes && queueRes.ok) {
        const queueData: ConsensusFlag[] = await queueRes.json();
        setReviewQueue(queueData);
      }

      if (logRes && logRes.ok) {
        const logData: ConsensusFlag[] = await logRes.json();
        setAnalystReportLog(logData);
      }

      if (alertsRes && alertsRes.ok) {
        const alertsData: AlertRecord[] = await alertsRes.json();
        setAlerts(alertsData);
      }

      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err: any) {
      console.warn('Refresh polling error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initTimer = setTimeout(() => {
      void refreshData();
    }, 0);

    // Setup live SSE stream with 10s polling fallback
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource('/api/stream');
      eventSource.onmessage = () => {
        refreshData();
      };
      eventSource.onerror = () => {
        if (eventSource) eventSource.close();
      };
    } catch {
      // Fallback
    }

    const interval = setInterval(refreshData, 10000);

    return () => {
      clearTimeout(initTimer);
      clearInterval(interval);
      if (eventSource) eventSource.close();
    };
  }, [refreshData]);

  const handleVerdict = async (itemId: string, verdict: 'confirm' | 'dismiss') => {
    try {
      const target = reviewQueue.find((i) => i.item_id === itemId);
      // Optimistic UI updates
      setReviewQueue((prev) => prev.filter((item) => item.item_id !== itemId));
      if (target) {
        const optimisticLog: ConsensusFlag = {
          ...target,
          status: verdict === 'confirm' ? 'confirmed' : 'dismissed',
          analyst_verdict: verdict,
          review_factor: verdict === 'confirm' ? 1.0 : 0.0,
        };
        setAnalystReportLog((prev) => [optimisticLog, ...prev.filter((p) => p.item_id !== itemId)]);
      }

      const res = await fetch(`/api/items/${itemId}/verdict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ verdict }),
      });

      if (res.ok) {
        const updatedFlag: ConsensusFlag = await res.json();
        setAnalystReportLog((prev) => [updatedFlag, ...prev.filter((p) => p.item_id !== itemId)]);
      }

      refreshData();
    } catch (err: any) {
      setError(`Failed to submit analyst verdict: ${err?.message}`);
    }
  };

  const handleSendTestAlert = async () => {
    try {
      setSendingTestAlert(true);
      const res = await fetch('/api/alerts/test', { method: 'POST' });
      if (res.ok) {
        await refreshData();
      }
    } catch (err: any) {
      setError(`Failed to dispatch test alert: ${err?.message}`);
    } finally {
      setSendingTestAlert(false);
    }
  };

  const handleSimulate = async (company: string, severity: number, headline: string) => {
    try {
      setSimulating(true);
      await fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company,
          severity,
          risk_type: 'legal',
          headline,
          reason: 'Injected high-severity regulatory incident for live demonstration.',
        }),
      });
      await refreshData();
    } catch (err: any) {
      setError(`Failed to inject simulation: ${err?.message}`);
    } finally {
      setSimulating(false);
    }
  };

  const handleReset = async () => {
    try {
      setSimulating(true);
      await fetch('/api/reset', { method: 'POST' });
      await refreshData();
    } catch (err: any) {
      setError(`Failed to reset simulation: ${err?.message}`);
    } finally {
      setSimulating(false);
    }
  };

  const getScoreBadgeClass = (score: number) => {
    if (score >= 60) return 'text-rose-300 bg-rose-950/60 border-rose-500/40 neon-border-rose shadow-lg shadow-rose-950/50';
    if (score >= 35) return 'text-amber-300 bg-amber-950/60 border-amber-500/40 neon-border-amber shadow-lg shadow-amber-950/50';
    return 'text-emerald-300 bg-emerald-950/60 border-emerald-500/40 neon-border-emerald shadow-lg shadow-emerald-950/50';
  };

  const getCardTopStripe = (score: number) => {
    if (score >= 60) return 'from-rose-500 via-rose-400 to-amber-500';
    if (score >= 35) return 'from-amber-500 via-amber-400 to-sky-400';
    return 'from-emerald-400 via-teal-400 to-sky-400';
  };

  const getRiskTypeBadge = (type: string) => {
    switch (type) {
      case 'legal':
        return 'bg-purple-950/70 text-purple-300 border border-purple-700/60 shadow-sm shadow-purple-950/40';
      case 'compliance':
        return 'bg-blue-950/70 text-blue-300 border border-blue-700/60 shadow-sm shadow-blue-950/40';
      case 'operational':
        return 'bg-amber-950/70 text-amber-300 border border-amber-700/60 shadow-sm shadow-amber-950/40';
      default:
        return 'bg-slate-800 text-slate-300 border border-slate-700';
    }
  };

  return (
    <div className="min-h-screen relative bg-black text-slate-100 selection:bg-sky-500/30 selection:text-sky-200 overflow-x-hidden">
      {/* Celestial Deep Space Sky with Moving Stars, Shooting Meteors & Luminous Orbiting Moon */}
      <CelestialBackground />

      {/* Main Content Layer */}
      <div className="relative z-10 px-4 py-8 max-w-7xl mx-auto font-sans">
        {/* Ambient Lighting Orbs */}
        <div className="ambient-glow-1"></div>
        <div className="ambient-glow-2"></div>
        <div className="ambient-glow-3"></div>

      {/* Header */}
      <header className="glass-panel rounded-2xl p-6 mb-8 relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6 border border-white/10 shadow-2xl">
        <div className="flex items-start gap-4">
          {/* Animated Radar Pulse Icon */}
          <div className="relative h-12 w-12 rounded-xl bg-gradient-to-tr from-sky-500/20 via-indigo-500/20 to-purple-500/20 border border-sky-400/30 flex items-center justify-center overflow-hidden shrink-0 shadow-lg shadow-sky-500/10">
            <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-sky-400/15 to-transparent animate-radar origin-center"></div>
            <div className="h-4 w-4 rounded-full border border-sky-400/60 flex items-center justify-center">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse"></span>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white flex items-center gap-2.5">
                <span className="bg-gradient-to-r from-white via-slate-100 to-sky-200 bg-clip-text text-transparent">
                  Corporate Risk Radar
                </span>
                <span className="text-[11px] uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-sky-950/80 text-sky-300 font-semibold border border-sky-700/60 shadow-sm">
                  Fintech PS 01
                </span>
              </h1>
            </div>
            <p className="text-xs md:text-sm text-slate-400 mt-1 max-w-2xl leading-relaxed">
              Autonomous multi-source continuous surveillance, Dual-LLM consensus (<span className="text-slate-200 font-medium">Mistral</span> + <span className="text-slate-200 font-medium">Blind Verifier</span>) & Neo4j knowledge graph topology.
            </p>
          </div>
        </div>

        {/* System Health / Status Indicators */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {lastUpdated && (
            <div className="glass-pill px-3 py-1.5 rounded-lg text-[11px] text-slate-400 font-mono flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Live: <span className="text-slate-200">{lastUpdated}</span>
            </div>
          )}

          {health?.mock_mode && (
            <span className="px-3 py-1.5 rounded-lg bg-amber-950/60 text-amber-300 border border-amber-600/60 flex items-center gap-1.5 font-medium shadow-sm">
              <span className="h-2 w-2 rounded-full bg-amber-400 animate-ping"></span>
              DEMO DATA MODE
            </span>
          )}

          <div
            className="glass-pill px-3.5 py-1.5 rounded-lg flex items-center gap-2 cursor-help"
            title={
              health?.neo4j?.connected
                ? 'Connected to live Neo4j AuraDB instance'
                : 'Active in-memory knowledge graph fallback'
            }
          >
            <span className="text-slate-400">Graph:</span>
            <span
              className={`font-semibold flex items-center gap-1.5 ${
                health?.neo4j?.connected ? 'text-emerald-400' : 'text-sky-300'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  health?.neo4j?.connected ? 'bg-emerald-400 shadow-sm shadow-emerald-400' : 'bg-sky-400 shadow-sm shadow-sky-400'
                }`}
              ></span>
              {health?.neo4j?.connected ? 'AuraDB' : 'In-Memory'}
            </span>
          </div>

          <div className="glass-pill px-3 py-1.5 rounded-lg flex items-center gap-2 text-slate-300 font-mono">
            <span className="text-slate-400 font-sans">Nodes:</span>
            <span className="font-bold text-white">
              {health?.neo4j?.node_count ?? 0}
            </span>
          </div>

          <div className="glass-pill px-3 py-1.5 rounded-lg flex items-center gap-2 text-slate-300 font-mono">
            <span className="text-slate-400 font-sans">Edges:</span>
            <span className="font-bold text-white">
              {health?.neo4j?.relationship_count ?? 0}
            </span>
          </div>
        </div>
      </header>

      {/* Interactive Sandbox Simulator */}
      <div className="mb-8 relative z-10">
        <SimulateControl
          onSimulate={handleSimulate}
          onReset={handleReset}
          loading={simulating}
        />
      </div>

      {error && (
        <div className="mb-6 p-4 rounded-xl glass-panel bg-rose-950/40 border border-rose-500/50 text-rose-300 text-sm flex items-center justify-between shadow-xl">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-white p-1">✕</button>
        </div>
      )}

      {/* Main Scoreboard */}
      <main className="space-y-10 relative z-10">
        <div>
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2.5">
                Corporate Risk Scoreboard
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800/80 text-slate-300 font-normal border border-slate-700/60">
                  Ranked by 24h delta surge
                </span>
              </h2>
            </div>
            <div className="text-xs text-slate-400 font-mono glass-pill px-3 py-1 rounded-lg">
              0 - 100 Index · 7d Half-Life Decay
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {companies.map((comp) => (
              <div
                key={comp.ticker}
                onClick={() => setSelectedCompany(comp)}
                className="glass-card rounded-2xl p-6 relative overflow-hidden flex flex-col justify-between cursor-pointer group hover:border-sky-400/40"
              >
                {/* Top Glowing Gradient Accent Bar */}
                <div
                  className={`absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r ${getCardTopStripe(
                    comp.current_index
                  )} opacity-80 group-hover:opacity-100 transition-opacity`}
                ></div>

                <div>
                  {/* Top row: Ticker, Name, Index */}
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <div className="flex items-center gap-2.5">
                        <h3 className="text-2xl font-black text-white tracking-wide group-hover:text-sky-300 transition-colors">
                          {comp.ticker}
                        </h3>
                        <span className={`text-[11px] px-2.5 py-0.5 rounded-md font-semibold tracking-wider ${getRiskTypeBadge(comp.top_risk_type)}`}>
                          {comp.top_risk_type.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1 font-medium">{comp.name}</p>
                    </div>

                    <div className={`text-right px-3.5 py-2 rounded-xl border ${getScoreBadgeClass(comp.current_index)}`}>
                      <div className="text-2xl font-black font-mono leading-none tracking-tight">
                        {comp.current_index.toFixed(1)}
                      </div>
                      <div className="text-[10px] font-semibold mt-1 font-mono tracking-tight">
                        {comp.delta_24h >= 0 ? `+${comp.delta_24h.toFixed(1)}` : comp.delta_24h.toFixed(1)} 24h
                      </div>
                    </div>
                  </div>

                  {/* Badges */}
                  <div className="flex flex-wrap gap-1.5 my-3.5">
                    {comp.repeat_issue && (
                      <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-rose-950/60 text-rose-300 border border-rose-800/50 font-medium shadow-sm">
                        ⚠️ Repeat Issue (3+ in 90d)
                      </span>
                    )}
                    {comp.contagion && (
                      <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-amber-950/60 text-amber-300 border border-amber-800/50 font-medium shadow-sm">
                        ⚡ Contagion (2+ Cos)
                      </span>
                    )}
                    {comp.needs_review_count > 0 && (
                      <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-blue-950/60 text-blue-300 border border-blue-800/50 font-medium shadow-sm">
                        🔍 Needs Review: {comp.needs_review_count}
                      </span>
                    )}
                  </div>

                  {/* Topic & One-line reason */}
                  <div className="mt-3 text-xs flex items-center gap-1.5">
                    <span className="text-slate-400">Top Topic:</span>
                    <span className="text-slate-200 font-semibold capitalize bg-white/5 px-2 py-0.5 rounded border border-white/5">
                      {comp.top_topic}
                    </span>
                  </div>

                  <p className="text-xs text-slate-400 mt-2.5 line-clamp-2 leading-relaxed bg-[#080b11]/60 p-3 rounded-xl border border-white/5 shadow-inner">
                    {comp.one_line_reason}
                  </p>
                </div>

                {/* Footer action */}
                <div className="mt-5 pt-3.5 border-t border-white/10 flex items-center justify-between text-xs text-slate-400">
                  <span className="font-mono text-[11px]">Half-life decay: 7d</span>
                  <span className="text-sky-400 group-hover:text-sky-300 font-semibold flex items-center gap-1 transition-transform group-hover:translate-x-1">
                    Explore Evidence Topology &rarr;
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Human Analyst Review Lane & Report Log */}
        <ReviewQueueLane
          queue={reviewQueue}
          reportLog={analystReportLog}
          onVerdict={handleVerdict}
          loading={loading}
        />

        {/* Alerts Dispatch & History Panel */}
        <AlertsPanel
          alerts={alerts}
          onSendTestAlert={handleSendTestAlert}
          sendingTest={sendingTestAlert}
        />
      </main>

      {/* Slide-over Evidence Drawer */}
      <EvidenceDrawer
        key={selectedCompany?.ticker || 'empty'}
        company={selectedCompany}
        onClose={() => setSelectedCompany(null)}
      />

      {/* Footer */}
      <footer className="mt-16 pt-8 border-t border-white/10 text-xs text-slate-500 flex flex-col md:flex-row items-center justify-between gap-4 relative z-10">
        <div>Corporate Risk Radar &copy; 2026 — Dual-LLM Consensus Corporate Risk Intelligence</div>
        <div className="flex items-center gap-4 text-slate-400">
          <span>FastAPI Backend</span>
          <span>&bull;</span>
          <span>Neo4j AuraDB Knowledge Graph</span>
          <span>&bull;</span>
          <span>Glassmorphic Architecture</span>
        </div>
      </footer>
    </div>
  </div>
);
}

export default App;
