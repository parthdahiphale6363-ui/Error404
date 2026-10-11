import React, { useState, useEffect } from 'react';
import type { CompanySummary, ExplanationResponse, EvidenceGraphData } from '../types/api';

interface EvidenceDrawerProps {
  company: CompanySummary | null;
  onClose: () => void;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({ company, onClose }) => {
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [graphData, setGraphData] = useState<EvidenceGraphData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedNode, setSelectedNode] = useState<any | null>(null);

  useEffect(() => {
    if (!company) return;

    let isMounted = true;

    Promise.all([
      fetch(`/api/companies/${company.ticker}/explanation`).then((r) => r.json()).catch(() => null),
      fetch(`/api/companies/${company.ticker}/evidence-graph`).then((r) => r.json()).catch(() => null),
    ]).then(([exp, grp]) => {
      if (isMounted) {
        setExplanation(exp);
        setGraphData(grp);
        setLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [company]);

  if (!company) return null;

  // Simple clean SVG force/circular layout for evidence graph visualization
  const width = 640;
  const height = 360;
  const centerX = width / 2;
  const centerY = height / 2;

  const nodes = graphData?.nodes || [];
  const edges = graphData?.edges || [];

  // Compute node positions: Company at center, others arranged radially by category
  const nodePositions: Record<string, { x: number; y: number; color: string; r: number }> = {};
  
  nodes.forEach((n, idx) => {
    if (n.label === 'Company') {
      nodePositions[n.id] = { x: centerX, y: centerY, color: '#38bdf8', r: 24 };
    } else {
      const angle = (idx / Math.max(nodes.length - 1, 1)) * 2 * Math.PI;
      const radius = n.label === 'Item' ? 120 : 180;
      const x = centerX + radius * Math.cos(angle);
      const y = centerY + radius * Math.sin(angle);
      
      let color = '#94a3b8';
      let r = 16;
      if (n.label === 'Item') {
        const sev = n.properties?.severity ?? 3;
        color = sev >= 4 ? '#f43f5e' : '#f59e0b';
        r = 18;
      } else if (n.label === 'Topic') {
        color = '#a855f7';
        r = 14;
      } else if (n.label === 'Regulator') {
        color = '#10b981';
        r = 14;
      }
      nodePositions[n.id] = { x, y, color, r };
    }
  });

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm flex justify-end animate-fadeIn">
      <div className="w-full max-w-2xl bg-[#0f131c] border-l border-slate-800 h-full overflow-y-auto flex flex-col shadow-2xl p-6 text-slate-200">
        {/* Drawer Header */}
        <div className="flex items-start justify-between pb-4 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-3">
              <span className="text-2xl font-black text-white">{company.ticker}</span>
              <span className="text-sm px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 font-semibold border border-slate-700">
                {company.top_risk_type.toUpperCase()}
              </span>
              <span className="text-sm px-2.5 py-0.5 rounded-full bg-rose-950/60 text-rose-300 font-mono font-bold border border-rose-800/60">
                Index: {company.current_index.toFixed(1)} ({company.delta_24h >= 0 ? `+${company.delta_24h.toFixed(1)}` : company.delta_24h.toFixed(1)} 24h)
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">{company.name}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
            title="Close Drawer"
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div className="space-y-6 mt-6">
          {/* Grounded Explanation Section */}
          <section className="bg-[#141a26] border border-slate-800 rounded-xl p-4">
            <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400 flex items-center justify-between mb-2">
              <span>Grounded Multi-Hop Explanation</span>
              <span className="text-[10px] text-emerald-400 font-mono bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/40">
                Zero-Hallucination Guarded
              </span>
            </h3>

            {loading ? (
              <div className="py-4 text-center text-xs text-slate-500 animate-pulse">
                Traversing knowledge graph & validating citations...
              </div>
            ) : explanation ? (
              <div>
                <p className="text-sm leading-relaxed text-slate-100 font-medium">
                  {explanation.summary}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-slate-400 text-[11px]">Cited Graph Nodes:</span>
                  {explanation.cited_item_ids.map((id) => (
                    <span
                      key={id}
                      className="px-2 py-0.5 rounded bg-sky-950/70 border border-sky-800/60 text-sky-300 font-mono text-[11px]"
                    >
                      [{id}]
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400">Baseline calm surveillance: no severe incidents detected.</p>
            )}
          </section>

          {/* Evidence Graph Visualizer */}
          <section className="bg-[#141a26] border border-slate-800 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400">
                Evidence Graph Topology
              </h3>
              <div className="flex items-center gap-3 text-[10px]">
                <span className="flex items-center gap-1 text-sky-400">
                  <span className="h-2 w-2 rounded-full bg-sky-400"></span> Company
                </span>
                <span className="flex items-center gap-1 text-rose-400">
                  <span className="h-2 w-2 rounded-full bg-rose-400"></span> Item
                </span>
                <span className="flex items-center gap-1 text-purple-400">
                  <span className="h-2 w-2 rounded-full bg-purple-400"></span> Topic
                </span>
                <span className="flex items-center gap-1 text-emerald-400">
                  <span className="h-2 w-2 rounded-full bg-emerald-400"></span> Regulator
                </span>
              </div>
            </div>

            <div className="bg-[#0b0e15] border border-slate-900 rounded-lg overflow-hidden relative">
              <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-64 select-none">
                {/* Edges */}
                {edges.map((edge, i) => {
                  const src = nodePositions[edge.source];
                  const tgt = nodePositions[edge.target];
                  if (!src || !tgt) return null;
                  return (
                    <g key={`edge-${i}`}>
                      <line
                        x1={src.x}
                        y1={src.y}
                        x2={tgt.x}
                        y2={tgt.y}
                        stroke="#334155"
                        strokeWidth="1.5"
                        strokeDasharray={edge.type === 'HAS_TOPIC' ? '3 3' : undefined}
                      />
                    </g>
                  );
                })}

                {/* Nodes */}
                {nodes.map((node) => {
                  const pos = nodePositions[node.id];
                  if (!pos) return null;
                  const isSelected = selectedNode?.id === node.id;
                  return (
                    <g
                      key={`node-${node.id}`}
                      className="cursor-pointer transition-transform hover:scale-110"
                      onClick={() => setSelectedNode(node)}
                    >
                      <circle
                        cx={pos.x}
                        cy={pos.y}
                        r={isSelected ? pos.r + 4 : pos.r}
                        fill={pos.color}
                        stroke={isSelected ? '#ffffff' : '#0f172a'}
                        strokeWidth={isSelected ? '3' : '2'}
                        opacity="0.9"
                      />
                      <text
                        x={pos.x}
                        y={pos.y + 4}
                        textAnchor="middle"
                        fontSize={node.label === 'Company' ? '10' : '8'}
                        fontWeight="bold"
                        fill="#ffffff"
                        pointerEvents="none"
                      >
                        {node.label === 'Company'
                          ? node.properties?.ticker || company.ticker
                          : node.label === 'Topic'
                          ? 'T'
                          : node.label === 'Regulator'
                          ? 'R'
                          : 'I'}
                      </text>
                    </g>
                  );
                })}
              </svg>

              {/* Selected Node Details Popup */}
              {selectedNode && (
                <div className="absolute bottom-2 left-2 right-2 bg-slate-900/95 border border-slate-700/80 rounded p-2 text-xs text-slate-300 flex items-center justify-between">
                  <div>
                    <span className="font-semibold text-white mr-2">[{selectedNode.label}]</span>
                    <span>{selectedNode.properties?.title || selectedNode.properties?.name || selectedNode.id}</span>
                  </div>
                  <button onClick={() => setSelectedNode(null)} className="text-slate-500 hover:text-white ml-2">
                    ✕
                  </button>
                </div>
              )}
            </div>

            {/* Evidence Paths list */}
            {explanation?.evidence_paths && explanation.evidence_paths.length > 0 && (
              <div className="mt-3">
                <div className="text-[11px] font-semibold text-slate-400 mb-1">Graph Traversal Paths:</div>
                <div className="space-y-1 max-h-24 overflow-y-auto">
                  {explanation.evidence_paths.map((p, idx) => (
                    <div key={idx} className="text-[10px] font-mono text-slate-400 bg-slate-900/60 px-2 py-1 rounded truncate">
                      {p}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* Mathematical Formula Card */}
          <section className="bg-[#141a26] border border-slate-800 rounded-xl p-4">
            <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400 mb-2">
              Risk Index Formula Breakdown
            </h3>
            <div className="bg-[#0b0e15] border border-slate-900 rounded p-3 font-mono text-xs text-slate-300 space-y-2">
              <div className="text-sky-300 font-bold">
                Index = clamp(100 · S / (S + 15) + SpikeBonus, 0, 100)
              </div>
              <div className="text-[11px] text-slate-400 leading-relaxed">
                • Decayed Score: S = Σ (w_type · review_factor · 0.5^(age_days / 7))<br />
                • Review Factors: Agreed/Confirmed = 1.0, Needs Review = 0.5, Dismissed = 0.0<br />
                • Spike Bonus: clamp(z - 1.0, 0, 5) where z is 7d complaint volume z-score
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
