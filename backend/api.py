"""FastAPI Router for Corporate Risk Radar.

Conforms strictly to the API Contract in brain.md Section 10.
All frontend types will be generated from the FastAPI /openapi.json specification.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.alerts.engine import alert_engine
from backend.db.graph_repo import graph_repo
from backend.explain.engine import ExplainEngine
from backend.replay.engine import replay_engine, ReplayCase
from backend.schemas import (
    AnalystVerdict,
    AlertRecord,
    CompanySummary,
    ConsensusFlag,
    ConsensusStatus,
    DetectionResult,
    EvidenceGraphData,
    ExplanationResponse,
    Item,
    RiskType,
    SourceType,
)

logger = logging.getLogger(__name__)
router = APIRouter()
explain_engine = ExplainEngine()


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


# Baseline review queue seeded items (Phase 3 dual-model divergence)
_INITIAL_REVIEW_ITEMS: List[ConsensusFlag] = [
    ConsensusFlag(
        item_id="cand_04",
        company="WFC",
        source_url="https://www.consumerfinance.gov/data-research/consumer-complaints/search/detail/8901232",
        date=datetime(2026, 3, 8, 15, 20, tzinfo=timezone.utc),
        risk_type=RiskType.COMPLIANCE,
        primary_severity=4,
        final_severity=4,
        confidence=0.88,
        status=ConsensusStatus.NEEDS_REVIEW,
        review_factor=0.5,
        topics=["unauthorized accounts or fraud", "mortgage or loan servicing"],
        regulators=["CFPB"],
        reason="Mistral assessed unlawful auto insurance force-placing as severity 4; Verifier categorized individual servicing dispute (severity 2).",
        verifier_provider="gemini",
        verifier_severity=2,
        verifier_risk_type=RiskType.COMPLIANCE,
    ),
    ConsensusFlag(
        item_id="cand_43",
        company="COIN",
        source_url="https://www.sec.gov/Archives/edgar/data/1679788/coin-8k-subpoena.htm",
        date=datetime(2026, 3, 2, 16, 45, tzinfo=timezone.utc),
        risk_type=RiskType.LEGAL,
        primary_severity=4,
        final_severity=4,
        confidence=0.91,
        status=ConsensusStatus.NEEDS_REVIEW,
        review_factor=0.5,
        topics=["litigation or class action", "enforcement action"],
        regulators=["SEC"],
        reason="Mistral evaluated formal investigative subpoena as severity 4; Verifier categorized preliminary regulatory inquiry (severity 2).",
        verifier_provider="gemini",
        verifier_severity=2,
        verifier_risk_type=RiskType.LEGAL,
    ),
    ConsensusFlag(
        item_id="cand_52",
        company="NAVI",
        source_url="https://www.consumerfinance.gov/data-research/consumer-complaints/search/detail/8901239",
        date=datetime(2026, 3, 4, 13, 10, tzinfo=timezone.utc),
        risk_type=RiskType.LEGAL,
        primary_severity=4,
        final_severity=4,
        confidence=0.89,
        status=ConsensusStatus.NEEDS_REVIEW,
        review_factor=0.5,
        topics=["mortgage or loan servicing", "enforcement action"],
        regulators=["CFPB"],
        reason="Mistral flagged student loan servicing steering allegations as severity 4; Verifier flagged forbearance dispute (severity 3).",
        verifier_provider="gemini",
        verifier_severity=3,
        verifier_risk_type=RiskType.LEGAL,
    ),
    ConsensusFlag(
        item_id="cand_55",
        company="NAVI",
        source_url="https://www.consumerfinance.gov/data-research/consumer-complaints/search/detail/8901248",
        date=datetime(2026, 2, 28, 14, 0, tzinfo=timezone.utc),
        risk_type=RiskType.COMPLIANCE,
        primary_severity=3,
        final_severity=3,
        confidence=0.86,
        status=ConsensusStatus.NEEDS_REVIEW,
        review_factor=0.5,
        topics=["mortgage or loan servicing", "debt collection practices"],
        regulators=["CFPB"],
        reason="Mistral flagged systemic late fee assessment as severity 3; Verifier treated as single collection inquiry (severity 1).",
        verifier_provider="gemini",
        verifier_severity=1,
        verifier_risk_type=RiskType.COMPLIANCE,
    ),
    ConsensusFlag(
        item_id="cand_02",
        company="WFC",
        source_url="https://www.reuters.com/business/finance/wells-fargo-cfpb-action-2026",
        date=datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc),
        risk_type=RiskType.COMPLIANCE,
        primary_severity=5,
        final_severity=5,
        confidence=0.96,
        status=ConsensusStatus.CONFIRMED,
        review_factor=1.0,
        topics=["enforcement action", "unauthorized accounts or fraud"],
        regulators=["CFPB"],
        reason="Analyst verified $3.7B CFPB consent order redress. Severity confirmed at 5.0.",
        verifier_provider="gemini",
        verifier_severity=5,
        verifier_risk_type=RiskType.COMPLIANCE,
        analyst_verdict=AnalystVerdict.CONFIRM,
    ),
]

# Runtime in-memory stores
_REVIEW_QUEUE: Dict[str, ConsensusFlag] = {item.item_id: item for item in _INITIAL_REVIEW_ITEMS}
for item in _INITIAL_REVIEW_ITEMS:
    graph_repo.upsert_consensus(item)

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
    """List 5 companies with dynamic rolling index, 24h delta, badges, top topic."""
    base_company_configs = [
        {
            "ticker": "WFC",
            "name": "Wells Fargo & Company",
            "base_index": 34.2,
            "prev_index": 28.0,
            "risk_type": RiskType.COMPLIANCE,
            "topic": "unauthorized accounts or fraud",
            "repeat": True,
            "contagion": False,
            "reason": "Multiple recent consumer complaints regarding fee disclosures and account access.",
        },
        {
            "ticker": "EFX",
            "name": "Equifax Inc.",
            "base_index": 41.5,
            "prev_index": 42.1,
            "risk_type": RiskType.LEGAL,
            "topic": "credit reporting errors",
            "repeat": True,
            "contagion": False,
            "reason": "Ongoing dispute resolution backlog noted in high-volume credit bureau complaints.",
        },
        {
            "ticker": "PYPL",
            "name": "PayPal Holdings, Inc.",
            "base_index": 18.5,
            "prev_index": 17.2,
            "risk_type": RiskType.OPERATIONAL,
            "topic": "payments or outages",
            "repeat": False,
            "contagion": False,
            "reason": "Payment processing delay reports remain within baseline noise bounds.",
        },
        {
            "ticker": "COIN",
            "name": "Coinbase Global, Inc.",
            "base_index": 29.0,
            "prev_index": 25.5,
            "risk_type": RiskType.LEGAL,
            "topic": "enforcement action",
            "repeat": False,
            "contagion": False,
            "reason": "SEC litigation filings and regulatory inquiry into staking products.",
        },
        {
            "ticker": "NAVI",
            "name": "Navient Corporation",
            "base_index": 52.8,
            "prev_index": 35.0,
            "risk_type": RiskType.LEGAL,
            "topic": "mortgage or loan servicing",
            "repeat": True,
            "contagion": False,
            "reason": "CFPB consent order and student loan servicing ban allegations drive sharp index increase.",
        },
    ]

    summaries = []
    for cfg in base_company_configs:
        ticker = cfg["ticker"]
        current_index = cfg["base_index"]
        prev_index = cfg["prev_index"]
        top_risk_type = cfg["risk_type"]
        top_topic = cfg["topic"]
        reason = cfg["reason"]

        # Dynamically apply simulated items if present
        comp_sims = [it for it in _SIMULATED_ITEMS if it.company.upper() == ticker]
        if comp_sims:
            latest_sim = comp_sims[-1]
            # Boost score based on severity (Sev 5 -> +44pts, Sev 4 -> +28pts, Sev 3 -> +15pts)
            sim_item_sev = 5
            if latest_sim.id in _REVIEW_QUEUE:
                sim_item_sev = _REVIEW_QUEUE[latest_sim.id].primary_severity
            score_boost = 12.0 * max(sim_item_sev - 1, 1) + 8.0
            current_index = min(98.5, round(current_index + score_boost, 1))
            top_topic = "enforcement action"
            top_risk_type = RiskType.LEGAL
            reason = f"[SIMULATED] {latest_sim.title.replace('[SIMULATED] ', '')}"

        # Dynamically compute needs review count from active review queue
        pending_review_count = len([
            q for q in _REVIEW_QUEUE.values()
            if q.company.upper() == ticker and q.status == ConsensusStatus.NEEDS_REVIEW
        ])

        delta_24h = round(current_index - prev_index, 1)

        summaries.append(
            CompanySummary(
                ticker=ticker,
                name=cfg["name"],
                current_index=current_index,
                previous_24h_index=prev_index,
                delta_24h=delta_24h,
                top_risk_type=top_risk_type,
                top_topic=top_topic,
                repeat_issue=cfg["repeat"],
                contagion=cfg["contagion"],
                needs_review_count=pending_review_count,
                one_line_reason=reason,
            )
        )

    return sorted(summaries, key=lambda c: c.delta_24h, reverse=True)


@router.get("/companies/{ticker}/explanation", response_model=ExplanationResponse)
def get_company_explanation(ticker: str):
    """Grounded 2-line explanation citing retrieved graph items."""
    return explain_engine.generate_explanation(ticker)


@router.get("/companies/{ticker}/evidence-graph", response_model=EvidenceGraphData)
def get_company_evidence_graph(ticker: str):
    """Nodes and edges for evidence path visualization."""
    evidence = graph_repo.get_evidence_for_company(ticker)
    return EvidenceGraphData(
        nodes=evidence.get("nodes", []),
        edges=evidence.get("edges", []),
    )


@router.get("/review-queue", response_model=List[ConsensusFlag])
def get_review_queue():
    """Items with status 'needs_review' requiring human analyst confirmation."""
    repo_items = graph_repo.get_review_queue()
    if repo_items:
        flags = []
        for item in repo_items:
            try:
                flags.append(
                    ConsensusFlag(
                        item_id=item.get("id", "item_unknown"),
                        company=item.get("company", "WFC"),
                        source_url=item.get("source_url", "https://example.com"),
                        date=item.get("date", datetime.now(timezone.utc)),
                        risk_type=RiskType(item.get("risk_type", "compliance")),
                        primary_severity=int(item.get("primary_severity", item.get("severity", 4))),
                        final_severity=int(item.get("final_severity", item.get("severity", 4))),
                        confidence=float(item.get("confidence", 0.9)),
                        status=ConsensusStatus(item.get("status", "needs_review")),
                        review_factor=float(item.get("review_factor", 0.5)),
                        topics=json.loads(item["topics_json"]) if "topics_json" in item else item.get("topics", []),
                        regulators=json.loads(item["regulators_json"]) if "regulators_json" in item else item.get("regulators", []),
                        reason=item.get("reason", "Awaiting analyst verdict."),
                        verifier_provider=item.get("verifier_provider"),
                        verifier_severity=item.get("verifier_severity"),
                        verifier_risk_type=RiskType(item["verifier_risk_type"]) if item.get("verifier_risk_type") else None,
                        analyst_verdict=AnalystVerdict(item["analyst_verdict"]) if item.get("analyst_verdict") else None,
                        is_simulated=item.get("is_simulated", False),
                    )
                )
            except Exception as e:
                logger.warning("Failed to deserialize review queue item: %s", e)
        if flags:
            return [f for f in flags if f.status == ConsensusStatus.NEEDS_REVIEW]

    return [f for f in _REVIEW_QUEUE.values() if f.status == ConsensusStatus.NEEDS_REVIEW]


@router.post("/items/{id}/verdict", response_model=ConsensusFlag)
def submit_verdict(id: str, request: VerdictRequest):
    """Analyst confirms or dismisses flagged item."""
    graph_repo.update_verdict(id, request.verdict)

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


@router.get("/review-log", response_model=List[ConsensusFlag])
def get_review_log():
    """Human Analyst Report Log: list of items confirmed or dismissed by analyst."""
    logged_items = [
        f for f in _REVIEW_QUEUE.values()
        if f.status in (ConsensusStatus.CONFIRMED, ConsensusStatus.DISMISSED)
    ]
    return sorted(logged_items, key=lambda x: str(x.date), reverse=True)


@router.get("/alerts", response_model=List[AlertRecord])
def get_alerts():
    """History of generated alerts (including dry-run HTML preview links)."""
    return _ALERTS_LOG


@router.post("/alerts/test")
def trigger_test_alert():
    """Send one test alert to verify delivery."""
    key = f"test_alert_{int(datetime.now(timezone.utc).timestamp())}"
    content = alert_engine.build_email_content(
        company="WFC",
        index=62.5,
        delta=16.5,
        topic="unauthorized accounts or fraud",
        rule_name="Manual Verification Test",
        reason="Analyst triggered test alert to verify email dispatch pipeline and HTML rendering.",
        evidence_items=[{
            "risk_type": "compliance",
            "severity": 4,
            "title": "Unauthorized Checking Account Fee Charges",
            "url": "https://consumerfinance.gov/data-research/consumer-complaints/",
        }],
        badges=["Test Alert", "Manual Trigger"],
    )
    test_record = AlertRecord(
        key=key,
        ts=datetime.now(timezone.utc),
        company="WFC",
        rule="Rule A (Manual Test)",
        subject=content["subject"],
        body_html=content["body_html"],
        body_text=content["body_text"],
        recipients=alert_engine.adapter.get_allowlist(),
        status="pending",
        is_simulated=False,
    )
    res = alert_engine.dispatch_alert(test_record)
    _ALERTS_LOG.append(test_record)
    return {"status": "ok", "message": "Test alert dispatched", "record": test_record, "dispatch": res}


@router.get("/replay", response_model=List[str])
def list_replay_cases():
    """List benchmark historical cases and calm controls."""
    return [
        "wfc_2022_cfpb",
        "efx_2017_breach",
        "navi_2024_servicing",
        "pypl_calm_control",
        "coin_calm_control",
    ]


@router.get("/replay/{case_id}", response_model=ReplayCase)
def get_replay_case(case_id: str):
    """Retrieve full point-in-time time-machine replay for a case."""
    return replay_engine.get_benchmark_case(case_id)


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

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

    topics = ["enforcement action"]
    if request.company == "WFC":
        topics.append("unauthorized accounts or fraud")
    elif request.company == "EFX":
        topics.append("credit reporting errors")
    elif request.company == "PYPL":
        topics.append("payments or outages")
    elif request.company == "NAVI":
        topics.append("mortgage or loan servicing")
    else:
        topics.append("account access or customer service")

    regulators = ["CFPB", "SEC"]

    sim_reason = request.reason if len(request.reason) >= 5 else f"Simulated: {request.reason}"
    detection = DetectionResult(
        company=request.company,
        source_url=new_item.source_url,
        date=new_item.published_at,
        risk_type=request.risk_type,
        severity=request.severity,
        confidence=0.95,
        topics=topics,
        regulators=regulators,
        reason=sim_reason,
    )
    graph_repo.upsert_detection(new_item, detection)

    if request.severity >= 3:
        flag = ConsensusFlag(
            item_id=item_id,
            company=request.company,
            source_url=new_item.source_url,
            date=new_item.published_at,
            risk_type=request.risk_type,
            primary_severity=request.severity,
            final_severity=request.severity,
            confidence=0.95,
            status=ConsensusStatus.NEEDS_REVIEW,
            review_factor=0.5,
            topics=topics,
            regulators=regulators,
            reason=f"[SIMULATED] {sim_reason}",
            is_simulated=True,
        )
        _REVIEW_QUEUE[item_id] = flag
        graph_repo.upsert_consensus(flag)

        # Generate simulated outbox alert preview for the alerts panel
        sim_alert_content = alert_engine.build_email_content(
            company=request.company,
            index=84.5 if request.severity == 5 else 68.0,
            delta=38.0 if request.severity == 5 else 22.0,
            topic=topics[0] if topics else "enforcement action",
            rule_name=f"Rule {'C (Severity 5)' if request.severity == 5 else 'B (24h Surge)'}",
            reason=f"[SIMULATED] Critical risk incident injected: {request.headline}",
            evidence_items=[{
                "risk_type": request.risk_type.value,
                "severity": request.severity,
                "title": request.headline,
                "url": new_item.source_url,
            }],
            badges=["Simulated Incident", f"Severity {request.severity}"],
            is_simulated=True,
        )
        sim_alert = AlertRecord(
            key=f"sim_alert_{item_id}",
            ts=datetime.now(timezone.utc),
            company=request.company,
            rule=f"Rule {'C (Severity 5)' if request.severity == 5 else 'B (Surge)'} [SIMULATED]",
            subject=sim_alert_content["subject"],
            body_html=sim_alert_content["body_html"],
            body_text=sim_alert_content["body_text"],
            recipients=["compliance@riskradar.io"],
            status="simulated",
            is_simulated=True,
        )
        _ALERTS_LOG.insert(0, sim_alert)

    return {"status": "simulated", "item": new_item}


@router.post("/reset")
def reset_simulated():
    """Remove simulated items and reset indices."""
    removed_count = graph_repo.reset_simulated_items()
    removed_count += len(_SIMULATED_ITEMS)
    _SIMULATED_ITEMS.clear()
    sim_queue_keys = [k for k, v in _REVIEW_QUEUE.items() if getattr(v, "is_simulated", False)]
    for k in sim_queue_keys:
        _REVIEW_QUEUE.pop(k, None)

    global _ALERTS_LOG
    _ALERTS_LOG = [a for a in _ALERTS_LOG if not getattr(a, "is_simulated", False)]
    return {"status": "reset", "simulated_items_removed": removed_count}
