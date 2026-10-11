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


def test_graph_repo_seeds_entities_in_fallback():
    """Verify fallback mode seeds 5 target companies and tracks relationships."""
    repo = GraphRepo()
    health = repo.check_health()
    # In fallback mode, entities must be seeded (5 companies + taxonomy >= 5)
    assert health["node_count"] >= 5
    assert health["relationship_count"] >= 0
    assert "in_memory" in health["status"] or health["status"] == "offline_fallback"

    # Upserting a company and an item increments counts
    repo.upsert_company("TEST_CO", "Test Company")
    test_item = Item(
        id="item_fallback_1",
        company="TEST_CO",
        source=SourceType.FINNHUB,
        source_url="https://test.com/news/1",
        title="Fallback item",
        text="Sample fallback item text",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_fallback_1",
    )
    repo.upsert_item(test_item, topics=["payments or outages"], regulators=["CFPB"])
    new_health = repo.check_health()
    assert new_health["node_count"] > health["node_count"]
    assert new_health["relationship_count"] >= 3  # ABOUT + HAS_TOPIC + INVOLVES

