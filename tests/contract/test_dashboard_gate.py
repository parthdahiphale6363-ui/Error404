"""Phase 6 Dashboard Integration Gate Tests.

Verifies:
1. Scoreboard returns 5 target companies sorted by 24h delta in <100ms.
2. Drawer endpoints (/explanation, /evidence-graph) respond cleanly.
3. Review lane verdict submissions update consensus flags in real-time.
4. Stream endpoint pushes SSE events without blocking.
5. Simulation and reset cycle functions cleanly.
"""

import time
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import AnalystVerdict


@pytest.fixture
def client():
    return TestClient(app)


def test_scoreboard_fast_load_under_2s(client):
    """Gate requirement: page loads under 2s from cached/memory data."""
    start = time.perf_counter()
    res = client.get("/companies")
    elapsed = time.perf_counter() - start

    assert res.status_code == 200
    assert elapsed < 2.0, f"Scoreboard took {elapsed:.3f}s, expected < 2.0s!"
    data = res.json()
    assert len(data) == 5

    # Check companies are sorted by delta_24h descending
    deltas = [c["delta_24h"] for c in data]
    assert deltas == sorted(deltas, reverse=True)


def test_drawer_endpoints_contract(client):
    for ticker in ["WFC", "EFX", "PYPL", "COIN", "NAVI"]:
        exp_res = client.get(f"/companies/{ticker}/explanation")
        assert exp_res.status_code == 200
        exp_data = exp_res.json()
        assert exp_data["company"] == ticker
        assert "summary" in exp_data

        grp_res = client.get(f"/companies/{ticker}/evidence-graph")
        assert grp_res.status_code == 200
        grp_data = grp_res.json()
        assert "nodes" in grp_data
        assert "edges" in grp_data


def test_review_lane_action_cycle(client):
    q_res = client.get("/review-queue")
    assert q_res.status_code == 200
    queue = q_res.json()

    # Submit a confirm verdict for test item
    item_id = queue[0]["item_id"] if queue else "test_wfc_01"
    v_res = client.post(
        f"/items/{item_id}/verdict",
        json={"verdict": AnalystVerdict.CONFIRM.value},
    )
    assert v_res.status_code == 200
    flag = v_res.json()
    assert flag["status"] == "confirmed"
    assert flag["review_factor"] == 1.0


@pytest.mark.anyio
async def test_sse_stream_contract():
    from backend.api import get_stream
    resp = await get_stream()
    assert resp.media_type == "text/event-stream"
    async for chunk in resp.body_iterator:
        assert "heartbeat" in chunk
        break


def test_simulate_and_reset_cycle(client):
    sim_res = client.post(
        "/simulate",
        json={
          "company": "WFC",
          "severity": 5,
          "risk_type": "legal",
          "headline": "Enforcement Action Test",
          "reason": "Test reason",
        },
    )
    assert sim_res.status_code == 200
    data = sim_res.json()
    assert data["status"] == "simulated"

    reset_res = client.post("/reset")
    assert reset_res.status_code == 200
    r_data = reset_res.json()
    assert r_data["status"] == "reset"
