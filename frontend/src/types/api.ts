/**
 * This file is AUTO-GENERATED from FastAPI openapi.json.
 * DO NOT EDIT MANUALLY.
 * All API types must strictly mirror backend Pydantic models.
 */

export type RiskType = "legal" | "compliance" | "operational" | "noise";

export type SourceType = "finnhub" | "cfpb" | "edgar";

export type ConsensusStatus = "agreed" | "needs_review" | "confirmed" | "dismissed" | "unflagged";

export type AnalystVerdict = "confirm" | "dismiss";

export interface Neo4jHealth {
  connected: boolean;
  node_count: number;
  relationship_count: number;
  max_nodes: number;
  max_relationships: number;
  node_capacity_pct: number;
  rel_capacity_pct: number;
  capacity_warning: boolean;
  status: string;
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  mock_mode: boolean;
  neo4j: Neo4jHealth;
}

export interface CompanySummary {
  ticker: string;
  name: string;
  current_index: number;
  previous_24h_index: number;
  delta_24h: number;
  top_risk_type: RiskType;
  top_topic: string;
  repeat_issue: boolean;
  contagion: boolean;
  needs_review_count: number;
  one_line_reason: string;
}

export interface ExplanationResponse {
  company: string;
  as_of: string;
  summary: string;
  cited_item_ids: string[];
  evidence_paths?: string[];
}

export interface EvidencePathNode {
  id: string;
  label: string;
  properties: Record<string, any>;
}

export interface EvidencePathEdge {
  source: string;
  target: string;
  type: string;
  properties?: Record<string, any>;
}

export interface EvidenceGraphData {
  nodes: EvidencePathNode[];
  edges: EvidencePathEdge[];
}

export interface ConsensusFlag {
  item_id: string;
  company: string;
  source_url: string;
  date: string;
  risk_type: RiskType;
  primary_severity: number;
  final_severity: number;
  confidence: number;
  status: ConsensusStatus;
  review_factor: number;
  topics: string[];
  regulators: string[];
  reason: string;
  verifier_provider?: string;
  verifier_severity?: number;
  verifier_risk_type?: RiskType;
  analyst_verdict?: AnalystVerdict;
  is_simulated?: boolean;
}

export interface AlertRecord {
  key: string;
  ts: string;
  company: string;
  rule: string;
  subject: string;
  body_html: string;
  body_text: string;
  recipients: string[];
  status: string;
  is_simulated?: boolean;
}

export interface MetricsResponse {
  precision: number;
  recall: number;
  consensus_precision: number;
  consensus_recall: number;
  lift: number;
  agreement_rate: number;
  total_evaluated: number;
}

export interface SimulateRequest {
  company: string;
  severity: number;
  risk_type: RiskType;
  headline: string;
  reason: string;
}

export interface VerdictRequest {
  verdict: AnalystVerdict;
  analyst_notes?: string | null;
}
