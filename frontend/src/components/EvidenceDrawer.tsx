import React, { useState, useEffect, useMemo } from 'react';
import type { CompanySummary, ExplanationResponse, EvidenceGraphData, EvidencePathNode } from '../types/api';

interface EvidenceDrawerProps {
  company: CompanySummary | null;
  onClose: () => void;
}

type FilterMode = 'all' | 'high_risk' | 'multi_hop';

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({ company, onClose }) => {
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [graphData, setGraphData] = useState<EvidenceGraphData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<FilterMode>('all');
  const [activePathIdx, setActivePathIdx] = useState<number | null>(null);

  useEffect(() => {
    if (!company) return;

    let isMounted = true;
    const controller = new AbortController();

    Promise.all([
      fetch(`/api/companies/${company.ticker}/explanation`, { signal: controller.signal }).then(async (r) => {
        if (!r.ok) throw new Error(`Explanation fetch failed: HTTP ${r.status}`);
        return r.json() as Promise<ExplanationResponse>;
      }),
      fetch(`/api/companies/${company.ticker}/evidence-graph`, { signal: controller.signal }).then(async (r) => {
        if (!r.ok) throw new Error(`Evidence graph fetch failed: HTTP ${r.status}`);
        return r.json() as Promise<EvidenceGraphData>;
      }),
    ])
      .then(([exp, grp]) => {
        if (isMounted) {
          setExplanation(exp);
          setGraphData(grp);
          // Auto-select primary cited node if available
          if (exp?.cited_item_ids && exp.cited_item_ids.length > 0) {
            setSelectedNodeId(exp.cited_item_ids[0]);
          }
          setLoading(false);
        }
      })
      .catch((err: any) => {
        if (err.name === 'AbortError') return;
        if (isMounted) {
          console.error('EvidenceDrawer fetch error:', err);
          setError(err?.message || 'Failed to load graph evidence.');
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [company]);

  const rawNodes = useMemo(() => graphData?.nodes || [], [graphData]);
  const rawEdges = useMemo(() => graphData?.edges || [], [graphData]);

  // Determine multi-hop participant nodes from explanation paths and edge properties
  const multiHopNodeIds = useMemo(() => {
    const ids = new Set<string>();
    if (explanation?.cited_item_ids) {
      explanation.cited_item_ids.forEach((id) => ids.add(id));
    }
    rawEdges.forEach((e) => {
      if (e.properties?.is_recurrence || e.properties?.is_contagion) {
        ids.add(e.source);
        ids.add(e.target);
      }
    });
    // Target company always included
    if (company) {
      ids.add(`comp_${company.ticker}`);
    }
    return ids;
  }, [rawEdges, explanation, company]);

  // Filter nodes based on active filter mode
  const filteredNodes = useMemo(() => {
    if (filterMode === 'high_risk') {
      return rawNodes.filter((n) => {
        if (n.label === 'Company' || n.label === 'Topic' || n.label === 'Regulator') return true;
        const sev = n.properties?.severity ?? 3;
        return sev >= 4 || n.properties?.is_contagion;
      });
    }
    if (filterMode === 'multi_hop') {
      return rawNodes.filter((n) => multiHopNodeIds.has(n.id) || n.label === 'Topic');
    }
    return rawNodes;
  }, [rawNodes, filterMode, multiHopNodeIds]);

  const filteredNodeIdSet = useMemo(() => new Set(filteredNodes.map((n) => n.id)), [filteredNodes]);

  const filteredEdges = useMemo(() => {
    return rawEdges.filter((e) => filteredNodeIdSet.has(e.source) && filteredNodeIdSet.has(e.target));
  }, [rawEdges, filteredNodeIdSet]);

  // Topology Layout Calculation
  const width = 640;
  const height = 380;
  const centerX = width / 2;
  const centerY = height / 2;

  const nodePositions = useMemo(() => {
    const positions: Record<
      string,
      {
        x: number;
        y: number;
        color: string;
        stroke: string;
        r: number;
        label: string;
        subLabel: string;
        isTargetComp: boolean;
      }
    > = {};

    if (!company) return positions;

    // Partition nodes by semantic category
    const targetCompNodes: EvidencePathNode[] = [];
    const peerCompNodes: EvidencePathNode[] = [];
    const directItems: EvidencePathNode[] = [];
    const contagionItems: EvidencePathNode[] = [];
    const topicNodes: EvidencePathNode[] = [];
    const regulatorNodes: EvidencePathNode[] = [];

    filteredNodes.forEach((n) => {
      if (n.label === 'Company') {
        if (n.properties?.is_peer || n.id !== `comp_${company.ticker}`) {
          peerCompNodes.push(n);
        } else {
          targetCompNodes.push(n);
        }
      } else if (n.label === 'Item') {
        if (n.properties?.is_contagion) {
          contagionItems.push(n);
        } else {
          directItems.push(n);
        }
      } else if (n.label === 'Topic') {
        topicNodes.push(n);
      } else if (n.label === 'Regulator') {
        regulatorNodes.push(n);
      }
    });

    // 1. Target Company at anchor center
    targetCompNodes.forEach((n) => {
      positions[n.id] = {
        x: centerX - (peerCompNodes.length > 0 ? 40 : 0),
        y: centerY,
        color: '#0284c7',
        stroke: '#38bdf8',
        r: 26,
        label: n.properties?.ticker || company.ticker,
        subLabel: 'TARGET',
        isTargetComp: true,
      };
    });

    const targetPos = positions[`comp_${company.ticker}`] || { x: centerX, y: centerY };

    // 2. Direct Items in inner orbit around target company
    const itemRadius = 95;
    directItems.forEach((n, idx) => {
      const angle = ((idx + 0.5) / Math.max(directItems.length, 1)) * 2 * Math.PI - Math.PI / 2;
      const sev = n.properties?.severity ?? 3;
      const isSevere = sev >= 4;
      positions[n.id] = {
        x: targetPos.x + itemRadius * Math.cos(angle),
        y: targetPos.y + itemRadius * Math.sin(angle),
        color: isSevere ? '#e11d48' : '#d97706',
        stroke: isSevere ? '#fda4af' : '#fde68a',
        r: isSevere ? 18 : 15,
        label: n.id.replace('cand_', '#').replace('test_', ''),
        subLabel: `Sev ${sev}`,
        isTargetComp: false,
      };
    });

    // 3. Topics in middle orbit
    const topicRadius = 175;
    topicNodes.forEach((n, idx) => {
      const angle = (idx / Math.max(topicNodes.length, 1)) * 2 * Math.PI - Math.PI / 4;
      const rawName = n.properties?.name || n.id.replace('topic_', '').replace(/_/g, ' ');
      const words = rawName.split(' ');
      const shortTopic = words.slice(0, 2).join(' ');
      positions[n.id] = {
        x: targetPos.x + topicRadius * Math.cos(angle),
        y: targetPos.y + topicRadius * Math.sin(angle),
        color: '#7e22ce',
        stroke: '#c084fc',
        r: 16,
        label: shortTopic,
        subLabel: 'TOPIC',
        isTargetComp: false,
      };
    });

    // 4. Regulators in perimeter arc
    regulatorNodes.forEach((n, idx) => {
      const angle = Math.PI * 0.65 + (idx / Math.max(regulatorNodes.length, 1)) * Math.PI * 0.7;
      const regRadius = 160;
      positions[n.id] = {
        x: targetPos.x + regRadius * Math.cos(angle),
        y: targetPos.y + regRadius * Math.sin(angle),
        color: '#059669',
        stroke: '#6ee7b7',
        r: 15,
        label: n.properties?.name || n.id.replace('reg_', ''),
        subLabel: 'REGULATOR',
        isTargetComp: false,
      };
    });

    // 5. Peer Companies on outer right flank for contagion
    peerCompNodes.forEach((n, idx) => {
      const py = centerY - 50 + idx * 80;
      positions[n.id] = {
        x: width - 70,
        y: py,
        color: '#4f46e5',
        stroke: '#818cf8',
        r: 22,
        label: n.properties?.ticker || 'PEER',
        subLabel: 'CONTAGION',
        isTargetComp: false,
      };
    });

    // 6. Contagion Items positioned between topics and peer companies
    contagionItems.forEach((n, idx) => {
      const py = centerY - 60 + idx * 45;
      positions[n.id] = {
        x: width - 150,
        y: py,
        color: '#dc2626',
        stroke: '#fca5a5',
        r: 15,
        label: n.id.replace('cand_', '#').replace('test_', ''),
        subLabel: `${n.properties?.company || 'PEER'}`,
        isTargetComp: false,
      };
    });

    return positions;
  }, [filteredNodes, company, centerX, centerY, width]);

  // Determine active/connected neighbors for interactive focus
  const activeFocusId = hoveredNodeId || selectedNodeId;
  const connectedNeighbors = useMemo(() => {
    if (!activeFocusId) return new Set<string>();
    const neighbors = new Set<string>([activeFocusId]);
    filteredEdges.forEach((e) => {
      if (e.source === activeFocusId) neighbors.add(e.target);
      if (e.target === activeFocusId) neighbors.add(e.source);
    });
    return neighbors;
  }, [activeFocusId, filteredEdges]);

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return rawNodes.find((n) => n.id === selectedNodeId) || null;
  }, [selectedNodeId, rawNodes]);

  if (!company) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/75 backdrop-blur-md flex justify-end animate-fadeIn">
      <div className="w-full max-w-2xl bg-[#080b12]/92 backdrop-blur-2xl border-l border-white/10 h-full overflow-y-auto flex flex-col shadow-2xl p-6 text-slate-200 animate-slideInRight">
        {/* Drawer Header */}
        <div className="flex items-start justify-between pb-4 border-b border-white/10">
          <div>
            <div className="flex items-center gap-3">
              <span className="text-2xl font-black text-white tracking-wide">{company.ticker}</span>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-white/5 text-slate-300 font-semibold border border-white/10">
                {company.top_risk_type.toUpperCase()}
              </span>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-rose-950/70 text-rose-300 font-mono font-bold border border-rose-500/40 neon-border-rose">
                Index: {company.current_index.toFixed(1)} ({company.delta_24h >= 0 ? `+${company.delta_24h.toFixed(1)}` : company.delta_24h.toFixed(1)} 24h)
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1 font-medium">{company.name}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white border border-white/5 transition-all cursor-pointer"
            title="Close Drawer"
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div className="space-y-6 mt-6">
          {/* Grounded Explanation Section */}
          <section className="glass-panel rounded-2xl p-5 border border-white/10 shadow-xl">
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-300 flex items-center gap-2">
                <span>Grounded Multi-Hop Explanation</span>
              </h3>
              <span className="text-[10px] text-emerald-300 font-mono bg-emerald-950/80 px-2.5 py-0.5 rounded-full border border-emerald-500/40 flex items-center gap-1.5 shadow-sm">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Zero-Hallucination Guarded
              </span>
            </div>

            {loading ? (
              <div className="py-6 text-center text-xs text-slate-400 space-y-2">
                <div className="h-2 w-24 bg-sky-500/40 rounded mx-auto animate-pulse"></div>
                <p>Traversing graph neighborhood & validating citations...</p>
              </div>
            ) : error ? (
              <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs flex items-center justify-between">
                <span>{error}</span>
                <button
                  onClick={() => {
                    setLoading(true);
                    setError(null);
                  }}
                  className="px-2 py-1 bg-rose-800/50 hover:bg-rose-700/60 rounded text-[11px]"
                >
                  Retry
                </button>
              </div>
            ) : explanation ? (
              <div>
                <p className="text-sm leading-relaxed text-slate-100 font-medium">
                  {explanation.summary}
                </p>

                {/* Clickable Cited Item Badges */}
                <div className="mt-3.5 flex flex-wrap items-center gap-2 text-xs pt-3 border-t border-slate-800/60">
                  <span className="text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
                    Cited Graph Nodes:
                  </span>
                  {explanation.cited_item_ids && explanation.cited_item_ids.length > 0 ? (
                    explanation.cited_item_ids.map((id) => {
                      const isSelected = selectedNodeId === id;
                      return (
                        <button
                          key={id}
                          onClick={() => setSelectedNodeId(id)}
                          onMouseEnter={() => setHoveredNodeId(id)}
                          onMouseLeave={() => setHoveredNodeId(null)}
                          className={`px-2.5 py-0.5 rounded font-mono text-xs transition-all cursor-pointer flex items-center gap-1 border ${
                            isSelected
                              ? 'bg-sky-500 text-white border-sky-400 shadow-md shadow-sky-500/20 scale-105'
                              : 'bg-sky-950/70 border-sky-800/60 text-sky-300 hover:bg-sky-900/80 hover:border-sky-600'
                          }`}
                          title={`Focus graph item ${id}`}
                        >
                          <span>[{id}]</span>
                          <span className="text-[10px] opacity-75">↗</span>
                        </button>
                      );
                    })
                  ) : (
                    <span className="text-slate-500 text-[11px] italic">Baseline calm state: 0 elevated citations.</span>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400">Baseline calm surveillance: no severe incidents detected.</p>
            )}
          </section>

          {/* Evidence Graph Visualizer */}
          <section className="glass-panel rounded-2xl p-5 border border-white/10 shadow-2xl">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <div>
                <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-300 flex items-center gap-2.5">
                  <span>Evidence Graph Topology</span>
                  <span className="text-[10px] text-sky-300 font-mono glass-pill px-2.5 py-0.5 rounded-full border border-sky-500/30">
                    {filteredNodes.length} Nodes · {filteredEdges.length} Edges
                  </span>
                </h3>
              </div>

              {/* Filter controls */}
              <div className="flex items-center gap-1 glass-pill p-1 rounded-xl text-[11px]">
                <button
                  onClick={() => setFilterMode('all')}
                  className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${
                    filterMode === 'all'
                      ? 'bg-sky-500 text-white font-bold shadow-md shadow-sky-500/25'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  All
                </button>
                <button
                  onClick={() => setFilterMode('high_risk')}
                  className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${
                    filterMode === 'high_risk'
                      ? 'bg-rose-500 text-white font-bold shadow-md shadow-rose-500/25'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Sev 4+
                </button>
                <button
                  onClick={() => setFilterMode('multi_hop')}
                  className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${
                    filterMode === 'multi_hop'
                      ? 'bg-purple-600 text-white font-bold shadow-md shadow-purple-600/25'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Multi-Hop
                </button>
              </div>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap items-center gap-3 text-[10px] mb-3 px-3 py-2 rounded-xl bg-white/[0.03] border border-white/5 backdrop-blur-sm">
              <span className="flex items-center gap-1.5 text-sky-300 font-medium">
                <span className="h-2 w-2 rounded-full bg-sky-400 shadow-sm shadow-sky-400"></span> Target ({company.ticker})
              </span>
              <span className="flex items-center gap-1.5 text-indigo-300 font-medium">
                <span className="h-2 w-2 rounded-full bg-indigo-400 shadow-sm shadow-indigo-400"></span> Peer (Contagion)
              </span>
              <span className="flex items-center gap-1.5 text-rose-300 font-medium">
                <span className="h-2 w-2 rounded-full bg-rose-400 shadow-sm shadow-rose-400"></span> Severe Item (4-5)
              </span>
              <span className="flex items-center gap-1.5 text-amber-300 font-medium">
                <span className="h-2 w-2 rounded-full bg-amber-400 shadow-sm shadow-amber-400"></span> Moderate Item (3)
              </span>
              <span className="flex items-center gap-1.5 text-purple-300 font-medium">
                <span className="h-2 w-2 rounded-full bg-purple-400 shadow-sm shadow-purple-400"></span> Topic
              </span>
              <span className="flex items-center gap-1.5 text-emerald-300 font-medium">
                <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400"></span> Regulator
              </span>
            </div>

            {/* SVG Canvas */}
            <div className="rounded-xl overflow-hidden relative shadow-2xl border border-white/10 bg-gradient-to-b from-[#090d18]/90 via-[#070a13]/95 to-[#04060c]/98">
              <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-76 select-none">
                <defs>
                  {/* Glowing blur filter for selected/severe nodes */}
                  <filter id="glow-neon" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
                    <feMerge>
                      <feMergeNode in="coloredBlur"/>
                      <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                  </filter>
                  <filter id="glow-severe" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
                    <feMerge>
                      <feMergeNode in="coloredBlur"/>
                      <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                  </filter>

                  {/* Arrow markers */}
                  <marker
                    id="arrow-default"
                    viewBox="0 0 10 10"
                    refX="22"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 1 L 9 5 L 0 9 z" fill="#475569" />
                  </marker>
                  <marker
                    id="arrow-active"
                    viewBox="0 0 10 10"
                    refX="22"
                    refY="5"
                    markerWidth="7"
                    markerHeight="7"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 1 L 9 5 L 0 9 z" fill="#38bdf8" />
                  </marker>
                  <marker
                    id="arrow-contagion"
                    viewBox="0 0 10 10"
                    refX="22"
                    refY="5"
                    markerWidth="7"
                    markerHeight="7"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 1 L 9 5 L 0 9 z" fill="#f43f5e" />
                  </marker>
                </defs>

                {/* Subtle background radar circles */}
                <circle cx={centerX - (filteredNodes.some(n => n.label === 'Company' && n.id !== `comp_${company.ticker}`) ? 40 : 0)} cy={centerY} r={95} fill="none" stroke="rgba(255,255,255,0.03)" strokeDasharray="3 4" />
                <circle cx={centerX - (filteredNodes.some(n => n.label === 'Company' && n.id !== `comp_${company.ticker}`) ? 40 : 0)} cy={centerY} r={175} fill="none" stroke="rgba(255,255,255,0.02)" strokeDasharray="2 4" />

                {/* Edges */}
                {filteredEdges.map((edge, i) => {
                  const src = nodePositions[edge.source];
                  const tgt = nodePositions[edge.target];
                  if (!src || !tgt) return null;

                  const isConnected =
                    !activeFocusId ||
                    (activeFocusId === edge.source || activeFocusId === edge.target);

                  const isContagion = Boolean(edge.properties?.is_contagion);
                  const isRecurrence = Boolean(edge.properties?.is_recurrence);

                  let strokeColor = '#334155';
                  let strokeWidth = 1.2;
                  let strokeDasharray: string | undefined = undefined;
                  let markerEnd = 'url(#arrow-default)';

                  if (isContagion) {
                    strokeColor = '#f43f5e';
                    strokeDasharray = '4 3';
                    markerEnd = 'url(#arrow-contagion)';
                    strokeWidth = 1.8;
                  } else if (isRecurrence) {
                    strokeColor = '#a855f7';
                    strokeDasharray = '3 3';
                    strokeWidth = 1.6;
                  } else if (edge.type === 'HAS_TOPIC') {
                    strokeColor = '#8b5cf6';
                    strokeDasharray = '2 2';
                  } else if (edge.type === 'INVOLVES') {
                    strokeColor = '#10b981';
                  }

                  if (isConnected && activeFocusId) {
                    strokeColor = isContagion ? '#fb7185' : '#38bdf8';
                    strokeWidth = 2.4;
                    markerEnd = isContagion ? 'url(#arrow-contagion)' : 'url(#arrow-active)';
                  }

                  return (
                    <g key={`edge-${i}`} opacity={!activeFocusId || isConnected ? 0.9 : 0.15}>
                      <line
                        x1={src.x}
                        y1={src.y}
                        x2={tgt.x}
                        y2={tgt.y}
                        stroke={strokeColor}
                        strokeWidth={strokeWidth}
                        strokeDasharray={strokeDasharray}
                        markerEnd={markerEnd}
                        className="transition-all duration-200"
                      />
                    </g>
                  );
                })}

                {/* Nodes */}
                {filteredNodes.map((node) => {
                  const pos = nodePositions[node.id];
                  if (!pos) return null;

                  const isSelected = selectedNodeId === node.id;
                  const isHovered = hoveredNodeId === node.id;
                  const isNeighbor = connectedNeighbors.has(node.id);
                  const isMuted = activeFocusId && !isNeighbor;
                  const isCited = explanation?.cited_item_ids?.includes(node.id);
                  const isSevere = (node.properties?.severity ?? 0) >= 4;

                  const radius = isSelected ? pos.r + 4 : isHovered ? pos.r + 2 : pos.r;

                  return (
                    <g
                      key={`node-${node.id}`}
                      className="cursor-pointer transition-all duration-150"
                      opacity={isMuted ? 0.25 : 1}
                      onClick={() => setSelectedNodeId(node.id)}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                    >
                      <title>{`${node.label}: ${node.properties?.title || node.properties?.name || node.id}`}</title>

                      {/* Cited node pulse halo */}
                      {isCited && (
                        <circle
                          cx={pos.x}
                          cy={pos.y}
                          r={radius + 7}
                          fill="none"
                          stroke="#38bdf8"
                          strokeWidth="1.5"
                          strokeDasharray="4 3"
                          className="animate-spin"
                          style={{ animationDuration: '8s' }}
                        />
                      )}

                      {/* Selection ring */}
                      {isSelected && (
                        <circle
                          cx={pos.x}
                          cy={pos.y}
                          r={radius + 5}
                          fill="none"
                          stroke="#ffffff"
                          strokeWidth="2.5"
                          filter="url(#glow-neon)"
                        />
                      )}

                      {/* Main node circle */}
                      <circle
                        cx={pos.x}
                        cy={pos.y}
                        r={radius}
                        fill={pos.color}
                        stroke={isSelected ? '#ffffff' : pos.stroke}
                        strokeWidth={isSelected ? 2.5 : 1.5}
                        filter={isSevere ? "url(#glow-severe)" : isSelected ? "url(#glow-neon)" : undefined}
                        className="transition-transform hover:scale-105"
                      />

                      {/* Node Text Label */}
                      <text
                        x={pos.x}
                        y={pos.y + 3.5}
                        textAnchor="middle"
                        fontSize={pos.isTargetComp ? '11' : node.label === 'Topic' ? '8' : '9'}
                        fontWeight="bold"
                        fill="#ffffff"
                        pointerEvents="none"
                      >
                        {pos.label.length > 9 ? pos.label.slice(0, 8) + '…' : pos.label}
                      </text>

                      {/* Sub-label under circle for context */}
                      <text
                        x={pos.x}
                        y={pos.y + radius + 11}
                        textAnchor="middle"
                        fontSize="7.5"
                        fill="#94a3b8"
                        pointerEvents="none"
                        className="font-mono tracking-tight"
                      >
                        {pos.subLabel}
                      </text>
                    </g>
                  );
                })}
              </svg>

              {/* Selected Node Details Popup */}
              {selectedNode && (
                <div className="absolute bottom-3 left-3 right-3 glass-panel rounded-xl p-4 text-xs text-slate-200 shadow-2xl border border-sky-400/40 backdrop-blur-2xl animate-fadeIn">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-sky-400 font-mono">[{selectedNode.label}]</span>
                        <span className="font-semibold text-white">
                          {selectedNode.properties?.title || selectedNode.properties?.name || selectedNode.id}
                        </span>
                        {selectedNode.properties?.severity && (
                          <span
                            className={`px-2 py-0.5 rounded-full font-mono text-[10px] font-bold ${
                              selectedNode.properties.severity >= 4
                                ? 'bg-rose-950 text-rose-300 border border-rose-600/60 neon-border-rose'
                                : 'bg-amber-950 text-amber-300 border border-amber-600/60 neon-border-amber'
                            }`}
                          >
                            Sev {selectedNode.properties.severity}/5
                          </span>
                        )}
                        {selectedNode.properties?.risk_type && (
                          <span className="px-2 py-0.5 rounded-full bg-white/5 text-slate-300 border border-white/10 text-[10px] uppercase font-semibold">
                            {selectedNode.properties.risk_type}
                          </span>
                        )}
                      </div>

                      {selectedNode.properties?.company && (
                        <p className="text-[11px] text-slate-400">
                          Institution: <span className="text-slate-200 font-bold">{selectedNode.properties.company}</span>
                          {selectedNode.properties?.is_contagion && (
                            <span className="ml-2 text-rose-400 font-medium">⚡ Cross-Company Contagion Node</span>
                          )}
                        </p>
                      )}

                      {selectedNode.properties?.source_url && (
                        <a
                          href={selectedNode.properties.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-sky-400 hover:text-sky-300 hover:underline pt-0.5 font-medium"
                        >
                          View Official Source Filing &rarr;
                        </a>
                      )}
                    </div>
                    <button
                      onClick={() => setSelectedNodeId(null)}
                      className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors"
                      title="Deselect node"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Evidence Paths list */}
            {explanation?.evidence_paths && explanation.evidence_paths.length > 0 && (
              <div className="mt-5 pt-4 border-t border-white/10">
                <div className="text-[11px] font-semibold text-slate-300 mb-2.5 flex items-center justify-between">
                  <span>Knowledge Graph Traversal Paths:</span>
                  <span className="text-[10px] text-slate-400 font-mono">Click path to focus</span>
                </div>
                <div className="space-y-2 max-h-36 overflow-y-auto pr-1">
                  {explanation.evidence_paths.map((p, idx) => {
                    const isActive = activePathIdx === idx;
                    return (
                      <div
                        key={idx}
                        onClick={() => setActivePathIdx(isActive ? null : idx)}
                        className={`text-[10px] font-mono px-3 py-2 rounded-xl transition-all cursor-pointer truncate border ${
                          isActive
                            ? 'bg-sky-950/80 border-sky-500/60 text-sky-200 shadow-lg shadow-sky-950/50'
                            : 'glass-pill hover:bg-white/[0.06] text-slate-300 border border-white/5 hover:border-white/10'
                        }`}
                        title={p}
                      >
                        <span className="text-slate-500 mr-2 font-sans font-semibold">Hop {idx + 1}:</span>
                        {p}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </section>

          {/* Mathematical Formula Card */}
          <section className="glass-panel rounded-2xl p-5 border border-white/10 shadow-xl">
            <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-300 mb-2.5 flex items-center gap-2">
              <span>Risk Index Formula Breakdown</span>
            </h3>
            <div className="bg-[#050811]/70 border border-white/5 rounded-xl p-4 font-mono text-xs text-slate-200 space-y-2.5 shadow-inner">
              <div className="text-sky-300 font-bold text-sm tracking-wide bg-sky-950/30 px-3 py-1.5 rounded-lg border border-sky-500/20 inline-block">
                Index = clamp(100 · S / (S + 15) + SpikeBonus, 0, 100)
              </div>
              <div className="text-[11px] text-slate-400 leading-relaxed font-sans space-y-1">
                <div>• <strong className="text-slate-200">Decayed Score:</strong> <code className="text-sky-300 bg-white/5 px-1 py-0.5 rounded">S = Σ (w_type · review_factor · 0.5^(age_days / 7))</code></div>
                <div>• <strong className="text-slate-200">Review Factors:</strong> Agreed/Confirmed = 1.0, Needs Review = 0.5, Dismissed = 0.0</div>
                <div>• <strong className="text-slate-200">Spike Bonus:</strong> <code className="text-rose-300 bg-white/5 px-1 py-0.5 rounded">clamp(z - 1.0, 0, 5)</code> where z is 7d complaint volume z-score</div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
