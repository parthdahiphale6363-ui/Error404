"""E2E Test for FastAPI application health."""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify application boots and /health returns 200 OK with Neo4j status and counts."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "risk-radar"
    assert "version" in data
    assert "mock_mode" in data

    # Verify Neo4j health block
    assert "neo4j" in data
    neo4j_data = data["neo4j"]
    assert "status" in neo4j_data
    assert "node_count" in neo4j_data
    assert "relationship_count" in neo4j_data
    assert "max_nodes" in neo4j_data
    assert neo4j_data["max_nodes"] == 50000
    assert "max_relationships" in neo4j_data
    assert neo4j_data["max_relationships"] == 175000
    assert "capacity_warning" in neo4j_data
    assert isinstance(neo4j_data["capacity_warning"], bool)


def test_root_redirects_to_frontend():
    """Verify visiting root / on port 8000 redirects to frontend UI on port 3000."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers.get("location") == "http://localhost:3000"


def test_favicon_returns_no_content():
    """Verify /favicon.ico returns 204 No Content without 404 error."""
    response = client.get("/favicon.ico")
    assert response.status_code == 204

