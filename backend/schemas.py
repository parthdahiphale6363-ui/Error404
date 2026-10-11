"""Data contracts and Pydantic models for Risk Radar."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class RiskType(str, Enum):
    LEGAL = "legal"
    COMPLIANCE = "compliance"
    OPERATIONAL = "operational"
    NOISE = "noise"


class SourceType(str, Enum):
    FINNHUB = "finnhub"
    CFPB = "cfpb"
    EDGAR = "edgar"


class ConsensusStatus(str, Enum):
    AGREED = "agreed"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    UNFLAGGED = "unflagged"


class AnalystVerdict(str, Enum):
    CONFIRM = "confirm"
    DISMISS = "dismiss"


# Fixed Topic Taxonomy (max 20)
TOPIC_TAXONOMY = [
    "unauthorized accounts or fraud",
    "data breach or cybersecurity",
    "debt collection practices",
    "mortgage or loan servicing",
    "credit reporting errors",
    "payments or outages",
    "account access or customer service",
    "enforcement action",
    "litigation or class action",
    "AML or sanctions",
    "governance or executive",
    "financial distress",
    "other",
]

# Fixed Regulators
REGULATORS = [
    "CFPB",
    "SEC",
    "DOJ",
    "FTC",
    "OCC",
    "FDIC",
    "Federal Reserve",
    "FINRA",
    "State AG",
    "other",
]


class Item(BaseModel):
    """Normalized ingested document."""
    id: str = Field(..., description="Unique deterministic item hash / ID")
    company: str = Field(..., min_length=1, description="Company ticker")
    source: SourceType = Field(..., description="Data source provider")
    source_url: str = Field(..., description="Original URL or canonical reference")
    title: str = Field(..., description="Headline or title")
    text: str = Field(..., description="Full text or complaint narrative")
    published_at: datetime = Field(..., description="Timestamp of publication or receipt")
    is_simulated: bool = Field(default=False, description="Flag for simulated demo items")
    content_hash: str = Field(..., min_length=8, description="Content hash for deduplication")


class DetectionResult(BaseModel):
    """Mistral structured classification output."""
    company: str = Field(...)
    source_url: str = Field(...)
    date: datetime = Field(...)
    risk_type: RiskType = Field(...)
    severity: int = Field(..., ge=0, le=5)
    confidence: float = Field(..., ge=0.0, le=1.0)
    topics: List[str] = Field(default_factory=list)
    regulators: List[str] = Field(default_factory=list)
    reason: str = Field(..., min_length=5)


class VerificationResult(BaseModel):
    """Blind verifier classification output."""
    provider: str = Field(..., description="gemini or groq")
    risk_type: RiskType = Field(...)
    severity: int = Field(..., ge=0, le=5)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., min_length=5)


class ConsensusFlag(BaseModel):
    """Aggregated consensus flag with review factor."""
    item_id: str = Field(...)
    company: str = Field(...)
    source_url: str = Field(...)
    date: datetime = Field(...)
    risk_type: RiskType = Field(...)
    primary_severity: int = Field(..., ge=0, le=5)
    final_severity: int = Field(..., ge=0, le=5)
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: ConsensusStatus = Field(...)
    review_factor: float = Field(..., ge=0.0, le=1.0)
    topics: List[str] = Field(default_factory=list)
    regulators: List[str] = Field(default_factory=list)
    reason: str = Field(...)
    verifier_provider: Optional[str] = None
    verifier_severity: Optional[int] = None
    verifier_risk_type: Optional[RiskType] = None
    analyst_verdict: Optional[AnalystVerdict] = None
    is_simulated: bool = Field(default=False)


class ItemContribution(BaseModel):
    item_id: str
    risk_type: RiskType
    severity: int
    review_factor: float
    age_days: float
    weight: float
    decayed_score: float


class ScorePoint(BaseModel):
    """Corporate Risk Index evaluation point."""
    company: str = Field(...)
    as_of: datetime = Field(...)
    index_score: float = Field(..., ge=0.0, le=100.0)
    raw_s: float = Field(..., ge=0.0)
    z_score: float = Field(default=0.0)
    complaint_spike_bonus: float = Field(default=0.0, ge=0.0, le=5.0)
    top_items_json: str = Field(default="[]", description="JSON array of top contributing items")
    is_simulated: bool = Field(default=False)


class AlertRecord(BaseModel):
    """Generated alert event."""
    key: str = Field(..., description="Idempotency key: company+rule+bucket")
    ts: datetime = Field(...)
    company: str = Field(...)
    rule: str = Field(..., description="Rule A, B, C or Daily Briefing")
    subject: str = Field(...)
    body_html: str = Field(...)
    body_text: str = Field(...)
    recipients: List[str] = Field(...)
    status: str = Field(default="sent", description="sent or dry_run_saved")
    is_simulated: bool = Field(default=False)


class CompanySummary(BaseModel):
    ticker: str
    name: str
    current_index: float
    previous_24h_index: float
    delta_24h: float
    top_risk_type: RiskType
    top_topic: str
    repeat_issue: bool = False
    contagion: bool = False
    needs_review_count: int = 0
    one_line_reason: str


class EvidencePathNode(BaseModel):
    id: str
    label: str
    properties: Dict[str, Any]


class EvidencePathEdge(BaseModel):
    source: str
    target: str
    type: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphData(BaseModel):
    nodes: List[EvidencePathNode]
    edges: List[EvidencePathEdge]


class ExplanationResponse(BaseModel):
    company: str
    as_of: datetime
    summary: str
    cited_item_ids: List[str]
    evidence_paths: List[str] = Field(default_factory=list)
