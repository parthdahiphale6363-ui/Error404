"""Phase 5 Graph Explain Gate Tests.

Verifies:
1. Evidence retrieval from graph (same-company recurrence, cross-company contagion, graph paths).
2. Grounded 2-line explanation citing retrieved Item IDs.
3. Anti-hallucination validation: 0 unsourced claims on 20 samples; every cited ID exists.
4. Rejection of unsourced claims.
5. Endpoints GET /companies/{ticker}/explanation and GET /companies/{ticker}/evidence-graph.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import Item, SourceType, RiskType, DetectionResult
from backend.db.graph_repo import graph_repo
from backend.explain.engine import ExplainEngine, AntiHallucinationError


@pytest.fixture
def explain_client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_graph_data():
    """Seed known items into graph for testing."""
    items = [
        Item(
            id="test_wfc_01",
            company="WFC",
            source=SourceType.CFPB,
            source_url="https://cfpb.gov/test1",
            title="Unauthorized Checking Account Fee Charges",
            text="Consumer charged repeated unauthorized fees on checking account without consent.",
            published_at=datetime.now(timezone.utc),
            content_hash="hash_wfc_01",
        ),
        Item(
            id="test_wfc_02",
            company="WFC",
            source=SourceType.EDGAR,
            source_url="https://sec.gov/test2",
            title="Form 8-K: Regulatory Inquiry into Account Practices",
            text="Disclosure of ongoing regulatory scrutiny regarding fee disclosures and account practices.",
            published_at=datetime.now(timezone.utc),
            content_hash="hash_wfc_02",
        ),
        Item(
            id="test_efx_01",
            company="EFX",
            source=SourceType.CFPB,
            source_url="https://cfpb.gov/test3",
            title="Dispute Investigation Backlog in Credit Reporting",
            text="Credit reporting dispute remained unresolved past statutory 30-day window.",
            published_at=datetime.now(timezone.utc),
            content_hash="hash_efx_01",
        ),
        Item(
            id="test_navi_01",
            company="NAVI",
            source=SourceType.CFPB,
            source_url="https://cfpb.gov/test4",
            title="Student Loan Forbearance Steering Allegations",
            text="Borrowers steered into costly forbearance without adequate disclosure of repayment options.",
            published_at=datetime.now(timezone.utc),
            content_hash="hash_navi_01",
        ),
    ]

    for item in items:
        graph_repo.upsert_item(item)

    # Upsert detections with topics to create graph edges
    graph_repo.upsert_detection(
        items[0],
        DetectionResult(
            company="WFC",
            source_url=items[0].source_url,
            date=items[0].published_at,
            risk_type=RiskType.COMPLIANCE,
            severity=4,
            confidence=0.92,
            topics=["unauthorized accounts or fraud"],
            regulators=["CFPB"],
            reason="Unauthorized account fee complaints.",
        ),
    )
    graph_repo.upsert_detection(
        items[1],
        DetectionResult(
            company="WFC",
            source_url=items[1].source_url,
            date=items[1].published_at,
            risk_type=RiskType.LEGAL,
            severity=4,
            confidence=0.88,
            topics=["enforcement action", "unauthorized accounts or fraud"],
            regulators=["SEC", "CFPB"],
            reason="8-K disclosure of regulatory scrutiny.",
        ),
    )
    graph_repo.upsert_detection(
        items[2],
        DetectionResult(
            company="EFX",
            source_url=items[2].source_url,
            date=items[2].published_at,
            risk_type=RiskType.LEGAL,
            severity=4,
            confidence=0.90,
            topics=["credit reporting errors"],
            regulators=["CFPB"],
            reason="Credit dispute resolution delays.",
        ),
    )
    graph_repo.upsert_detection(
        items[3],
        DetectionResult(
            company="NAVI",
            source_url=items[3].source_url,
            date=items[3].published_at,
            risk_type=RiskType.LEGAL,
            severity=5,
            confidence=0.95,
            topics=["mortgage or loan servicing", "enforcement action"],
            regulators=["CFPB"],
            reason="Student loan servicing enforcement action.",
        ),
    )


def test_evidence_retrieval_recurrence_and_contagion():
    engine = ExplainEngine(repo=graph_repo)
    evidence = engine.retrieve_evidence("WFC")

    assert evidence is not None
    assert "items" in evidence
    assert len(evidence["items"]) >= 1
    # Check recurrence paths: WFC has multiple items with unauthorized accounts or enforcement action
    assert "paths" in evidence
    assert len(evidence["paths"]) >= 1


def test_grounded_explanation_cites_existing_items():
    engine = ExplainEngine(repo=graph_repo)
    resp = engine.generate_explanation("WFC")

    assert resp.company == "WFC"
    assert resp.summary is not None
    assert len(resp.cited_item_ids) >= 1

    # Verify every cited ID exists in graph
    for item_id in resp.cited_item_ids:
        item = graph_repo.get_item(item_id)
        assert item is not None, f"Cited ID {item_id} not found in graph!"


def test_anti_hallucination_rejects_unsourced_claims():
    engine = ExplainEngine(repo=graph_repo)
    evidence = engine.retrieve_evidence("WFC")
    valid_ids = {i["id"] for i in evidence["items"]}

    # A fabricated summary citing a non-existent item ID
    hallucinated_summary = "Risk is rising due to unauthorized fees [test_wfc_01] and fraud [hallucinated_item_999]."

    with pytest.raises(AntiHallucinationError):
        engine.verify_citations(hallucinated_summary, valid_ids)


def test_gate_20_sample_eval_zero_unsourced_claims():
    """Gate requirement: 0 unsourced claims on 20 samples; every cited ID exists."""
    engine = ExplainEngine(repo=graph_repo)
    tickers = ["WFC", "EFX", "NAVI", "COIN", "PYPL"]

    samples_tested = 0
    unsourced_count = 0

    for i in range(20):
        ticker = tickers[i % len(tickers)]
        resp = engine.generate_explanation(ticker)
        samples_tested += 1

        # Check citations
        evidence = engine.retrieve_evidence(ticker)
        evidence_ids = {item["id"] for item in evidence["items"]}
        for r in evidence.get("recurrence", []):
            evidence_ids.add(r["related_item_id"])
        for c in evidence.get("contagion", []):
            evidence_ids.add(c["related_item_id"])

        for cited_id in resp.cited_item_ids:
            if cited_id not in evidence_ids:
                unsourced_count += 1

    assert samples_tested == 20
    assert unsourced_count == 0, f"Found {unsourced_count} unsourced claims! Must be 0."


def test_api_explanation_and_evidence_graph_endpoints(explain_client):
    res_exp = explain_client.get("/companies/WFC/explanation")
    assert res_exp.status_code == 200
    data_exp = res_exp.json()
    assert data_exp["company"] == "WFC"
    assert len(data_exp["cited_item_ids"]) >= 1
    assert len(data_exp["evidence_paths"]) >= 1

    res_graph = explain_client.get("/companies/WFC/evidence-graph")
    assert res_graph.status_code == 200
    data_graph = res_graph.json()
    assert "nodes" in data_graph
    assert "edges" in data_graph
    assert len(data_graph["nodes"]) >= 2
    assert len(data_graph["edges"]) >= 1
