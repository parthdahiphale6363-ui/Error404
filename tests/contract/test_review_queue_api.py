"""Contract tests for Review Queue and Verdict API."""

from fastapi.testclient import TestClient
from backend.main import app
from backend.schemas import AnalystVerdict, ConsensusStatus

client = TestClient(app)


def test_get_review_queue_endpoint():
    """Verify GET /review-queue returns items requiring review with valid ConsensusFlag schema."""
    resp = client.get("/review-queue")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "item_id" in item
        assert "company" in item
        assert "status" in item
        assert item["status"] in ("needs_review", "agreed", "confirmed", "dismissed")
        assert "review_factor" in item
        assert 0.0 <= item["review_factor"] <= 1.0


def test_submit_verdict_confirm_and_dismiss():
    """Verify POST /items/{id}/verdict updates status to confirmed/dismissed and adjusts review_factor."""
    # Confirm
    resp_confirm = client.post(
        "/items/test_item_queue_01/verdict",
        json={"verdict": "confirm"},
    )
    assert resp_confirm.status_code == 200
    data_confirm = resp_confirm.json()
    assert data_confirm["status"] == "confirmed"
    assert data_confirm["review_factor"] == 1.0
    assert data_confirm["analyst_verdict"] == "confirm"

    # Dismiss
    resp_dismiss = client.post(
        "/items/test_item_queue_01/verdict",
        json={"verdict": "dismiss"},
    )
    assert resp_dismiss.status_code == 200
    data_dismiss = resp_dismiss.json()
    assert data_dismiss["status"] == "dismissed"
    assert data_dismiss["review_factor"] == 0.0
    assert data_dismiss["analyst_verdict"] == "dismiss"
