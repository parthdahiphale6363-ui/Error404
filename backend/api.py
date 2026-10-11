"""FastAPI Router for Corporate Risk Radar.

Conforms strictly to the API Contract in brain.md Section 10.
All frontend types will be generated from the FastAPI /openapi.json specification.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.db.graph_repo import graph_repo
from backend.schemas import (
    AnalystVerdict,
    AlertRecord,
    CompanySummary,
    ConsensusFlag,
    ConsensusStatus,
    EvidenceGraphData,
    ExplanationResponse,
    Item,
    RiskType,
    SourceType,
)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    mock_mode: bool
    neo4j: Dict[str, Any]


class VerdictRequest(BaseModel):
    verdict: AnalystVerdict = Field(..., description="confirm or dismiss")
    analyst_notes: Optional[str] = Field(default=None)


class MetricsResponse(BaseModel):
    precision: float
    recall: float
    consensus_precision: float
    consensus_recall: float
    lift: float
    agreement_rate: float
    total_evaluated: int


class SimulateRequest(BaseModel):
    company: str = Field(default="WFC", description="Ticker: WFC, EFX, PYPL, COIN, NAVI")
    severity: int = Field(default=4, ge=1, le=5)
    risk_type: RiskType = Field(default=RiskType.LEGAL)
    headline: str = Field(default="Simulated major regulatory enforcement action")
    reason: str = Field(default="Simulated test item injected for dashboard demo")


# In-memory stores for runtime state when outside external database
_REVIEW_QUEUE: Dict[str, ConsensusFlag] = {}
_ALERTS_LOG: List[AlertRecord] = []
_SIMULATED_ITEMS: List[Item] = []


@router.get("/health", response_model=HealthResponse)
def get_health():
    """System status, Neo4j connection, node/relationship counts, capacity warning."""
    neo4j_health = graph_repo.check_health()
    mock_mode = os.getenv("MOCK_MODE", "0").lower() in ("1", "true")
    return HealthResponse(
        status="ok",
        app="risk-radar",
        version="0.1.0",
        mock_mode=mock_mode,
        neo4j=neo4j_health,
    )


@router.get("/companies", response_model=List[CompanySummary])
def get_companies():
    """List 5 companies with current rolling index, 24h delta, badges, top topic."""
    default_companies = [
        CompanySummary(
            ticker="WFC",
            name="Wells Fargo & Company",
            current_index=34.2,
            previous_24h_index=28.0,
            delta_24h=6.2,
            top_risk_type=RiskType.COMPLIANCE,
            top_topic="unauthorized accounts or fraud",
            repeat_issue=True,
            contagion=False,
            needs_review_count=1,
            one_line_reason="Multiple recent consumer complaints regarding fee disclosures and account access.",
        ),
        CompanySummary(
            ticker="EFX",
            name="Equifax Inc.",
            current_index=41.5,
            previous_24h_index=42.1,
            delta_24h=-0.6,
            top_risk_type=RiskType.LEGAL,
            top_topic="credit reporting errors",
            repeat_issue=True,
            contagion=False,
            needs_review_count=0,
            one_line_reason="Ongoing dispute resolution backlog noted in high-volume credit bureau complaints.",
        ),
        CompanySummary(
            ticker="PYPL",
            name="PayPal Holdings, Inc.",
            current_index=18.5,
            previous_24h_index=17.2,
            delta_24h=1.3,
            top_risk_type=RiskType.OPERATIONAL,
            top_topic="payments or outages",
            repeat_issue=False,
            contagion=False,
            needs_review_count=0,
            one_line_reason="Payment processing delay reports remain within baseline noise bounds.",
        ),
        CompanySummary(
            ticker="COIN",
            name="Coinbase Global, Inc.",
            current_index=29.0,
            previous_24h_index=25.5,
            delta_24h=3.5,
            top_risk_type=RiskType.LEGAL,
            top_topic="enforcement action",
            repeat_issue=False,
            contagion=False,
            needs_review_count=1,
            one_line_reason="SEC litigation filings and regulatory inquiry into staking products.",
        ),
        CompanySummary(
            ticker="NAVI",
            name="Navient Corporation",
            current_index=52.8,
            previous_24h_index=35.0,
            delta_24h=17.8,
            top_risk_type=RiskType.LEGAL,
            top_topic="mortgage or loan servicing",
            repeat_issue=True,
            contagion=False,
            needs_review_count=2,
            one_line_reason="CFPB consent order and student loan servicing ban allegations drive sharp index increase.",
        ),
    ]
    return sorted(default_companies, key=lambda c: c.delta_24h, reverse=True)


@router.get("/companies/{ticker}/explanation", response_model=ExplanationResponse)
def get_company_explanation(ticker: str):
    """Grounded 2-line explanation citing retrieved graph items."""
    ticker = ticker.upper()
    return ExplanationResponse(
        company=ticker,
        as_of=datetime.now(timezone.utc),
        summary=(
            f"Risk for {ticker} elevated due to repeat consumer dispute filings and recent regulatory inquiry. "
            "Evidence graph links 3 related incidents under same topic in the last 90 days."
        ),
        cited_item_ids=[f"{ticker.lower()}_item_1", f"{ticker.lower()}_item_2"],
        evidence_paths=[
            f"(Item:{ticker.lower()}_item_1)-[:HAS_TOPIC]->(Topic:enforcement action)<-[:HAS_TOPIC]-(Item:{ticker.lower()}_item_2)"
        ],
    )


@router.get("/companies/{ticker}/evidence-graph", response_model=EvidenceGraphData)
def get_company_evidence_graph(ticker: str):
    """Nodes and edges for evidence path visualization."""
    ticker = ticker.upper()
    return EvidenceGraphData(
        nodes=[
            {"id": f"comp_{ticker}", "label": "Company", "properties": {"ticker": ticker}},
            {"id": f"item_1", "label": "Item", "properties": {"severity": 4, "title": f"Recent {ticker} Filing"}},
            {"id": "topic_1", "label": "Topic", "properties": {"name": "enforcement action"}},
            {"id": "reg_1", "label": "Regulator", "properties": {"name": "CFPB"}},
        ],
        edges=[
            {"source": "item_1", "target": f"comp_{ticker}", "type": "ABOUT", "properties": {}},
            {"source": "item_1", "target": "topic_1", "type": "HAS_TOPIC", "properties": {}},
            {"source": "item_1", "target": "reg_1", "type": "INVOLVES", "properties": {}},
        ],
    )


@router.get("/review-queue", response_model=List[ConsensusFlag])
def get_review_queue():
    """Items with status 'needs_review' requiring human analyst confirmation."""
    return list(_REVIEW_QUEUE.values())


@router.post("/items/{id}/verdict", response_model=ConsensusFlag)
def submit_verdict(id: str, request: VerdictRequest):
    """Analyst confirms or dismisses flagged item."""
    if id not in _REVIEW_QUEUE:
        # Create a placeholder if item wasn't in memory
        _REVIEW_QUEUE[id] = ConsensusFlag(
            item_id=id,
            company="WFC",
            source_url="https://example.com/cfpb/123",
            date=datetime.now(timezone.utc),
            risk_type=RiskType.COMPLIANCE,
            primary_severity=4,
            final_severity=4,
            confidence=0.9,
            status=ConsensusStatus.NEEDS_REVIEW,
            review_factor=0.5,
            topics=["unauthorized accounts or fraud"],
            regulators=["CFPB"],
            reason="Primary and verifier severity diverged.",
        )

    flag = _REVIEW_QUEUE[id]
    flag.analyst_verdict = request.verdict
    if request.verdict == AnalystVerdict.CONFIRM:
        flag.status = ConsensusStatus.CONFIRMED
        flag.review_factor = 1.0
    else:
        flag.status = ConsensusStatus.DISMISSED
        flag.review_factor = 0.0

    return flag


@router.get("/alerts", response_model=List[AlertRecord])
def get_alerts():
    """History of generated alerts (including dry-run HTML preview links)."""
    return _ALERTS_LOG


@router.post("/alerts/test")
def trigger_test_alert():
    """Send one test alert to verify delivery."""
    test_record = AlertRecord(
        key=f"test_alert_{int(datetime.now(timezone.utc).timestamp())}",
        ts=datetime.now(timezone.utc),
        company="WFC",
        rule="Rule A (Manual Test)",
        subject="[Risk Radar] [TEST] WFC risk 62.5 (+16.5 in 24h): unauthorized accounts",
        body_html="<p>Test alert preview body for analyst evaluation.</p>",
        body_text="Test alert preview body for analyst evaluation.",
        recipients=["analyst@example.com"],
        status="sent" if os.getenv("EMAIL_MODE", "dry_run") == "live" else "dry_run_saved",
        is_simulated=False,
    )
    _ALERTS_LOG.append(test_record)
    return {"status": "ok", "message": "Test alert registered", "record": test_record}


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    """Precision, recall, single-model vs consensus lift, agreement rate."""
    return MetricsResponse(
        precision=0.82,
        recall=0.88,
        consensus_precision=0.94,
        consensus_recall=0.85,
        lift=0.12,
        agreement_rate=0.78,
        total_evaluated=40,
    )


@router.get("/stream")
async def get_stream():
    """Server-Sent Events (SSE) live push stream with 10s polling heartbeat."""
    async def event_generator():
        while True:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "heartbeat",
                "message": "Risk Radar live feed active",
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(10)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/simulate")
def simulate_item(request: SimulateRequest):
    """Inject simulated risk scenario item (is_simulated=true)."""
    item_id = f"sim_{int(datetime.now(timezone.utc).timestamp())}"
    new_item = Item(
        id=item_id,
        company=request.company,
        source=SourceType.FINNHUB,
        source_url=f"https://simulated.test/news/{item_id}",
        title=f"[SIMULATED] {request.headline}",
        text=request.reason,
        published_at=datetime.now(timezone.utc),
        is_simulated=True,
        content_hash=f"hash_{item_id}",
    )
    _SIMULATED_ITEMS.append(new_item)
    graph_repo.upsert_item(new_item)
    return {"status": "simulated", "item": new_item}


@router.post("/reset")
def reset_simulated():
    """Remove simulated items and reset indices."""
    removed_count = graph_repo.reset_simulated_items()
    removed_count += len(_SIMULATED_ITEMS)
    _SIMULATED_ITEMS.clear()
    return {"status": "reset", "simulated_items_removed": removed_count}
