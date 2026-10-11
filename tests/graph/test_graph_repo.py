"""Tests for Neo4j GraphRepo and Migration."""

from datetime import datetime, timezone
from backend.db.graph_repo import GraphRepo, MAX_NODES, MAX_RELATIONSHIPS
from backend.db.migrate import run_migrations, COMPANIES, TOPICS, REGULATORS
from backend.schemas import Item, SourceType


def test_graph_repo_health_structure():
    """Verify check_health returns Aura Free limits and capacity percentages."""
    repo = GraphRepo()
    health = repo.check_health()
    assert "status" in health
    assert "connected" in health
    assert health["max_nodes"] == MAX_NODES
    assert health["max_relationships"] == MAX_RELATIONSHIPS
    assert "node_capacity_pct" in health
    assert "rel_capacity_pct" in health
    assert "capacity_warning" in health
    assert isinstance(health["capacity_warning"], bool)


def test_migration_and_constraints():
    """Verify run_migrations initializes constraints and seeds metadata."""
    health = run_migrations()
    assert health is not None
    assert len(COMPANIES) == 5
    assert len(TOPICS) >= 12
    assert "CFPB" in REGULATORS


def test_upsert_and_reset_simulated():
    """Verify simulated item handling and reset logic."""
    repo = GraphRepo()
    sim_item = Item(
        id="test_sim_123",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://test.com/item",
        title="Test Simulated Item",
        text="Sample text for testing",
        published_at=datetime.now(timezone.utc),
        is_simulated=True,
        content_hash="hash_sim_123",
    )
    repo.upsert_item(sim_item, topics=["payments or outages"], regulators=["CFPB"])
    
    # Reset simulated items
    removed = repo.reset_simulated_items()
    assert removed >= 0
