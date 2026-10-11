"""Phase 9 Full Offline Demo Gate Test.

Verifies:
Full demo runs end-to-end with every external API switched off (MOCK_MODE=1, EMAIL_MODE=dry_run).
No crashes, no unhandled exceptions, zero network dependencies.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def mock_client(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setenv("EMAIL_MODE", "dry_run")
    return TestClient(app)


def test_full_offline_demo_walkthrough(mock_client):
    # 1. Health check with mock_mode=true
    health_res = mock_client.get("/health")
    assert health_res.status_code == 200
    health = health_res.json()
    assert health["status"] == "ok"
    assert health["mock_mode"] is True

    # 2. Watchlist scoreboard
    comp_res = mock_client.get("/companies")
    assert comp_res.status_code == 200
    companies = comp_res.json()
    assert len(companies) == 5

    # 3. Drawer Explanation
    exp_res = mock_client.get("/companies/WFC/explanation")
    assert exp_res.status_code == 200
    exp = exp_res.json()
    assert exp["company"] == "WFC"
    assert "summary" in exp

    # 4. Drawer Evidence Graph
    graph_res = mock_client.get("/companies/WFC/evidence-graph")
    assert graph_res.status_code == 200
    graph = graph_res.json()
    assert len(graph["nodes"]) >= 1

    # 5. Review queue
    q_res = mock_client.get("/review-queue")
    assert q_res.status_code == 200

    # 6. Verdict action
    v_res = mock_client.post("/items/demo_test_01/verdict", json={"verdict": "confirm"})
    assert v_res.status_code == 200
    flag = v_res.json()
    assert flag["status"] == "confirmed"

    # 7. Test alert dispatch (dry-run)
    alert_res = mock_client.post("/alerts/test")
    assert alert_res.status_code == 200
    alert_data = alert_res.json()
    assert alert_data["status"] == "ok"

    # 8. Time-machine replay
    replay_list = mock_client.get("/replay")
    assert replay_list.status_code == 200
    assert "wfc_2022_cfpb" in replay_list.json()

    case_res = mock_client.get("/replay/wfc_2022_cfpb")
    assert case_res.status_code == 200
    case = case_res.json()
    assert case["lead_time_days"] >= 14
    assert case["false_alarms"] == 0

    # 9. Metrics
    metrics_res = mock_client.get("/metrics")
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert metrics["precision"] > 0
    assert metrics["agreement_rate"] > 0

    # 10. Simulate & Reset cycle
    sim_res = mock_client.post("/simulate", json={"company": "WFC", "severity": 4, "risk_type": "legal", "headline": "Test Spike", "reason": "Test"})
    assert sim_res.status_code == 200

    reset_res = mock_client.post("/reset")
    assert reset_res.status_code == 200
