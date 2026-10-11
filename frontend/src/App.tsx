import { useEffect, useState, useCallback } from 'react';
import type { CompanySummary, HealthResponse, ConsensusFlag, AlertRecord } from './types/api';
import { EvidenceDrawer } from './components/EvidenceDrawer';
import { ReviewQueueLane } from './components/ReviewQueueLane';
import { AlertsPanel } from './components/AlertsPanel';
import { SimulateControl } from './components/SimulateControl';

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ConsensusFlag[]>([]);
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<CompanySummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [sendingTestAlert, setSendingTestAlert] = useState<boolean>(false);
  const [simulating, setSimulating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  const refreshData = useCallback(async () => {
    try {
      const [healthRes, compRes, queueRes, alertsRes] = await Promise.all([
        fetch('/api/health').catch(() => null),
        fetch('/api/companies').catch(() => null),
        fetch('/api/review-queue').catch(() => null),
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
      // Optimistic UI update
      setReviewQueue((prev) => prev.filter((item) => item.item_id !== itemId));

      await fetch(`/api/items/${itemId}/verdict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ verdict }),
      });

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

  const getScoreColor = (score: number) => {
    if (score >= 60) return 'text-rose-400 bg-rose-950/40 border-rose-800/60';
    if (score >= 35) return 'text-amber-400 bg-amber-950/40 border-amber-800/60';
    return 'text-emerald-400 bg-emerald-950/40 border-emerald-800/60';
  };

  const getRiskTypeBadge = (type: string) => {
    switch (type) {
      case 'legal':
        return 'bg-purple-950/70 text-purple-300 border border-purple-800/50';
      case 'compliance':
        return 'bg-blue-950/70 text-blue-300 border border-blue-800/50';
      case 'operational':
        return 'bg-amber-950/70 text-amber-300 border border-amber-800/50';
      default:
        return 'bg-slate-800 text-slate-300 border border-slate-700';
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0c10] text-slate-100 px-4 py-8 max-w-7xl mx-auto font-sans">
      {/* Header */}
      <header className="border-b border-slate-800 pb-6 mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 rounded-full bg-emerald-500 animate-pulse"></span>
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              Corporate Risk Radar
              <span className="text-xs uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-semibold border border-slate-700">
                Fintech PS 01
              </span>
            </h1>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Continuous multi-source surveillance, dual-LLM consensus (Mistral + Blind Verifier) & Neo4j graph explainability.
          </p>
        </div>

        {/* System Health / Status Indicators */}
        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          {lastUpdated && (
            <span className="text-[11px] text-slate-500 font-mono">
              Live: {lastUpdated}
            </span>
          )}

          {health?.mock_mode && (
            <span className="px-2.5 py-1 rounded-md bg-amber-950/50 text-amber-300 border border-amber-700/60 flex items-center gap-1.5 font-medium">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400"></span>
              DEMO DATA / MOCK MODE
            </span>
          )}

          <div
            className="px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 flex items-center gap-2 cursor-help"
            title={
              health?.neo4j?.connected
                ? 'Connected to live Neo4j AuraDB instance'
                : 'Active in-memory graph repository fallback'
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
                  health?.neo4j?.connected ? 'bg-emerald-400' : 'bg-sky-400'
                }`}
              ></span>
              {health?.neo4j?.connected ? 'AuraDB' : 'In-Memory'}
            </span>
          </div>

          <div className="px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 flex items-center gap-2 text-slate-300 font-mono">
            <span className="text-slate-400 font-sans">Nodes:</span>
            <span className="font-bold text-slate-200">
              {health?.neo4j?.node_count ?? 0}
            </span>
          </div>

          <div className="px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 flex items-center gap-2 text-slate-300 font-mono">
            <span className="text-slate-400 font-sans">Edges:</span>
            <span className="font-bold text-slate-200">
              {health?.neo4j?.relationship_count ?? 0}
            </span>
          </div>
        </div>
      </header>

      {/* Interactive Sandbox Simulator */}
      <div className="mb-6">
        <SimulateControl
          onSimulate={handleSimulate}
          onReset={handleReset}
          loading={simulating}
        />
      </div>

      {error && (
        <div className="mb-6 p-4 rounded-lg bg-rose-950/30 border border-rose-800/50 text-rose-300 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Main Scoreboard */}
      <main className="space-y-8">
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-200 flex items-center gap-2">
              Corporate Risk Scoreboard (Watchlist)
              <span className="text-xs text-slate-400 font-normal">Ranked by 24h delta surge</span>
            </h2>
            <div className="text-xs text-slate-400">
              0 - 100 Index with 7-Day Exponential Decay
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {companies.map((comp) => (
              <div
                key={comp.ticker}
                onClick={() => setSelectedCompany(comp)}
                className="bg-[#121620] border border-slate-800 rounded-xl p-5 hover:border-sky-500/50 hover:shadow-sky-500/5 transition-all duration-200 shadow-lg flex flex-col justify-between cursor-pointer group"
              >
                <div>
                  {/* Top row: Ticker, Name, Index */}
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-xl font-bold text-white tracking-wide group-hover:text-sky-300 transition-colors">
                          {comp.ticker}
                        </h3>
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${getRiskTypeBadge(comp.top_risk_type)}`}>
                          {comp.top_risk_type.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">{comp.name}</p>
                    </div>

                    <div className={`text-right px-3 py-1.5 rounded-lg border ${getScoreColor(comp.current_index)}`}>
                      <div className="text-2xl font-black font-mono leading-none">
                        {comp.current_index.toFixed(1)}
                      </div>
                      <div className="text-[10px] font-semibold mt-1">
                        {comp.delta_24h >= 0 ? `+${comp.delta_24h.toFixed(1)}` : comp.delta_24h.toFixed(1)} 24h
                      </div>
                    </div>
                  </div>

                  {/* Badges */}
                  <div className="flex flex-wrap gap-1.5 my-3">
                    {comp.repeat_issue && (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800/50 font-medium">
                        ⚠️ Repeat Issue (3+ in 90d)
                      </span>
                    )}
                    {comp.contagion && (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/50 font-medium">
                        ⚡ Contagion (2+ Cos)
                      </span>
                    )}
                    {comp.needs_review_count > 0 && (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-blue-950/60 text-blue-300 border border-blue-800/50 font-medium">
                        🔍 Needs Review: {comp.needs_review_count}
                      </span>
                    )}
                  </div>

                  {/* Topic & One-line reason */}
                  <div className="mt-2 text-xs">
                    <span className="text-slate-400">Top Topic: </span>
                    <span className="text-slate-200 font-medium capitalize">{comp.top_topic}</span>
                  </div>

                  <p className="text-xs text-slate-400 mt-2 line-clamp-2 leading-relaxed bg-[#0c0f16] p-2.5 rounded border border-slate-800/60">
                    {comp.one_line_reason}
                  </p>
                </div>

                {/* Footer action */}
                <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                  <span>Rolling S Decay (7d half-life)</span>
                  <span className="text-sky-400 group-hover:text-sky-300 font-medium flex items-center gap-1">
                    Open Evidence Drawer &rarr;
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Human Analyst Review Lane */}
        <ReviewQueueLane
          queue={reviewQueue}
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
        company={selectedCompany}
        onClose={() => setSelectedCompany(null)}
      />

      {/* Footer */}
      <footer className="mt-12 pt-6 border-t border-slate-800/60 text-xs text-slate-500 flex flex-col md:flex-row items-center justify-between gap-3">
        <div>Corporate Risk Radar &copy; 2026 — Dual-LLM Consensus Corporate Risk Intelligence</div>
        <div className="flex items-center gap-4">
          <span>FastAPI Backend</span>
          <span>&bull;</span>
          <span>Neo4j AuraDB Knowledge Graph</span>
          <span>&bull;</span>
          <span>Tailwind v4 UI</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
