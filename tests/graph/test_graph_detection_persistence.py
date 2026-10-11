"""Tests for Graph persistence of Detection results (HAS_TOPIC and INVOLVES edges)."""

from datetime import datetime, timezone
from backend.db.graph_repo import GraphRepo
from backend.schemas import DetectionResult, Item, RiskType, SourceType


def test_detection_creates_topic_and_regulator_edges():
    """Verify upsert_detection creates HAS_TOPIC and INVOLVES edges in graph repo."""
    repo = GraphRepo()

    item = Item(
        id="det_item_01",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://example.com/cfpb-wfc",
        title="CFPB imposes fine on Wells Fargo for account mismanagement",
        text="The CFPB ordered Wells Fargo to pay fines for consumer compliance violations.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_det_01",
    )

    detection = DetectionResult(
        company="WFC",
        source_url=item.source_url,
        date=item.published_at,
        risk_type=RiskType.COMPLIANCE,
        severity=4,
        confidence=0.92,
        topics=["unauthorized accounts or fraud", "enforcement action"],
        regulators=["CFPB"],
        reason="CFPB fine and compliance enforcement order.",
    )

    # Initial health check
    h_before = repo.check_health()

    # Apply detection to graph
    repo.upsert_detection(item, detection)

    h_after = repo.check_health()
    # Edges should include ABOUT (Item->WFC) + HAS_TOPIC (2) + INVOLVES (1)
    assert h_after["relationship_count"] >= h_before["relationship_count"] + 3

    # Check item retrieval
    stored = repo.get_item(item.id)
    assert stored is not None
    assert stored["severity"] == 4
    assert stored["risk_type"] == "compliance"
    assert stored["flagged"] is True  # severity >= 3
    assert "CFPB" in stored.get("regulators", [])
