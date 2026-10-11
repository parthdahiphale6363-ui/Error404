import { useEffect, useState } from 'react';
import type { CompanySummary, HealthResponse } from './types/api';

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [healthRes, companiesRes] = await Promise.all([
          fetch('/api/health').catch(() => null),
          fetch('/api/companies').catch(() => null),
        ]);

        if (healthRes && healthRes.ok) {
          const healthData: HealthResponse = await healthRes.json();
          setHealth(healthData);
        } else {
          // Fallback initial state for offline dev
          setHealth({
            status: 'ok',
            app: 'risk-radar',
            version: '0.1.0',
            mock_mode: true,
            neo4j: {
              connected: false,
              node_count: 0,
              relationship_count: 0,
              max_nodes: 50000,
              max_relationships: 175000,
              node_capacity_pct: 0,
              rel_capacity_pct: 0,
              capacity_warning: false,
              status: 'offline_fallback',
            },
          });
        }

        if (companiesRes && companiesRes.ok) {
          const companiesData: CompanySummary[] = await companiesRes.json();
          setCompanies(companiesData);
        } else {
          // Default initial scoreboard
          setCompanies([
            {
              ticker: 'NAVI',
              name: 'Navient Corporation',
              current_index: 52.8,
              previous_24h_index: 35.0,
              delta_24h: 17.8,
              top_risk_type: 'legal',
              top_topic: 'mortgage or loan servicing',
              repeat_issue: true,
              contagion: false,
              needs_review_count: 2,
              one_line_reason: 'CFPB consent order and student loan servicing ban allegations drive sharp index increase.',
            },
            {
              ticker: 'WFC',
              name: 'Wells Fargo & Company',
              current_index: 34.2,
              previous_24h_index: 28.0,
              delta_24h: 6.2,
              top_risk_type: 'compliance',
              top_topic: 'unauthorized accounts or fraud',
              repeat_issue: true,
              contagion: false,
              needs_review_count: 1,
              one_line_reason: 'Multiple recent consumer complaints regarding fee disclosures and account access.',
            },
            {
              ticker: 'COIN',
              name: 'Coinbase Global, Inc.',
              current_index: 29.0,
              previous_24h_index: 25.5,
              delta_24h: 3.5,
              top_risk_type: 'legal',
              top_topic: 'enforcement action',
              repeat_issue: false,
              contagion: false,
              needs_review_count: 1,
              one_line_reason: 'SEC litigation filings and regulatory inquiry into staking products.',
            },
            {
              ticker: 'PYPL',
              name: 'PayPal Holdings, Inc.',
              current_index: 18.5,
              previous_24h_index: 17.2,
              delta_24h: 1.3,
              top_risk_type: 'operational',
              top_topic: 'payments or outages',
              repeat_issue: false,
              contagion: false,
              needs_review_count: 0,
              one_line_reason: 'Payment processing delay reports remain within baseline noise bounds.',
            },
            {
              ticker: 'EFX',
              name: 'Equifax Inc.',
              current_index: 41.5,
              previous_24h_index: 42.1,
              delta_24h: -0.6,
              top_risk_type: 'legal',
              top_topic: 'credit reporting errors',
              repeat_issue: true,
              contagion: false,
              needs_review_count: 0,
              one_line_reason: 'Ongoing dispute resolution backlog noted in high-volume credit bureau complaints.',
            },
          ]);
        }
      } catch (err: any) {
        setError(err?.message || 'Failed to connect to backend service');
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

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
            Real-time multi-source corporate risk detection, dual-LLM consensus & graph evidence tracking.
          </p>
        </div>

        {/* System Health / Status Indicators */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {loading && (
            <span className="px-2 py-1 rounded bg-slate-800 text-slate-400 animate-pulse">
              Syncing...
            </span>
          )}

          {health?.mock_mode && (
            <span className="px-2.5 py-1 rounded-md bg-amber-950/50 text-amber-300 border border-amber-700/60 flex items-center gap-1.5 font-medium">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400"></span>
              DEMO DATA / MOCK MODE
            </span>
          )}

          <div className="px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 flex items-center gap-2">
            <span className="text-slate-400">Neo4j Status:</span>
            <span
              className={`font-semibold flex items-center gap-1 ${
                health?.neo4j?.connected ? 'text-emerald-400' : 'text-slate-300'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  health?.neo4j?.connected ? 'bg-emerald-400' : 'bg-slate-500'
                }`}
              ></span>
              {health?.neo4j?.status || 'Active'}
            </span>
          </div>

          <div className="px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 flex items-center gap-2 text-slate-300">
            <span className="text-slate-400">Nodes:</span>
            <span className="font-mono font-bold text-slate-200">
              {health?.neo4j?.node_count ?? 0} / {health?.neo4j?.max_nodes ?? 50000}
            </span>
          </div>
        </div>
      </header>

      {/* Main Scoreboard */}
      <main>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-200 flex items-center gap-2">
            Active Watchlist (5 Target Entities)
            <span className="text-xs text-slate-400 font-normal">Sorted by biggest 24h rise</span>
          </h2>
          <div className="text-xs text-slate-400">
            Rolling Corporate Risk Index (0 - 100)
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 rounded-lg bg-rose-950/30 border border-rose-800/50 text-rose-300 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {companies.map((comp) => (
            <div
              key={comp.ticker}
              className="bg-[#121620] border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-all duration-200 shadow-lg flex flex-col justify-between"
            >
              <div>
                {/* Header row: Ticker, Name & Index score */}
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-xl font-bold text-white tracking-wide">{comp.ticker}</h3>
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

                {/* Badges: Repeat Issue, Contagion, Needs Review */}
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

                {/* Primary Topic */}
                <div className="mt-2 text-xs">
                  <span className="text-slate-400">Top Topic: </span>
                  <span className="text-slate-200 font-medium capitalize">{comp.top_topic}</span>
                </div>

                {/* One line reason */}
                <p className="text-xs text-slate-400 mt-2 line-clamp-2 leading-relaxed bg-[#0c0f16] p-2.5 rounded border border-slate-800/60">
                  {comp.one_line_reason}
                </p>
              </div>

              {/* Card Footer */}
              <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                <span>Rolling S Decay (7d half-life)</span>
                <button
                  type="button"
                  className="text-blue-400 hover:text-blue-300 transition-colors font-medium flex items-center gap-1"
                >
                  View Evidence Graph &rarr;
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="mt-12 pt-6 border-t border-slate-800/60 text-xs text-slate-500 flex flex-col md:flex-row items-center justify-between gap-3">
        <div>Risk Radar &copy; 2026 — Dual-LLM Consensus Corporate Risk Intelligence</div>
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
