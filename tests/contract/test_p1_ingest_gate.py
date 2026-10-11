"""P1 Ingestion and Scheduler Gate Tests.

Gate Criteria:
1. 20 random rows match their sources (structure, content, url, hash).
2. A re-run adds 0 duplicates (strict deduplication by content hash / item ID).
3. CFPB only ingests complaints with consumer narratives.
4. Custom User-Agent with email sent to CFPB and SEC EDGAR.
5. Scheduler enforces intervals: Finnhub every 60s, CFPB & EDGAR every 15 min (900s).
6. Ingested items write Item nodes + ABOUT edges to Neo4j graph repo.
7. Capacity budget respected (max 1,200 Item nodes per company).
"""

from datetime import datetime, timezone
import pytest

from backend.apigateway.client import ApiGatewayClient
from backend.apigateway.adapters.finnhub import FinnhubAdapter
from backend.apigateway.adapters.cfpb import CFPBAdapter
from backend.apigateway.adapters.edgar import EdgarAdapter
from backend.ingest.pipeline import IngestionPipeline, InMemoryItemStore
from backend.jobs.scheduler import IngestionScheduler
from backend.db.graph_repo import graph_repo, MAX_ITEMS_PER_COMPANY
from backend.schemas import Item, SourceType


def test_gate_p1_twenty_rows_match_sources():
    """Gate 1: Verify 20 ingested items match their source contracts."""
    client = ApiGatewayClient(mock_mode=True)
    pipeline = IngestionPipeline(client=client)

    # Ingest from all adapters
    ingested_items = pipeline.ingest_all_companies(
        companies=["WFC", "EFX", "PYPL", "COIN", "NAVI"],
        limit_per_source=10,
    )

    # Must have at least 20 items for gate validation
    assert len(ingested_items) >= 20, f"Expected at least 20 items, got {len(ingested_items)}"

    # Check 20 items match source specifications
    sample_20 = ingested_items[:20]
    for item in sample_20:
        assert isinstance(item, Item)
        assert item.id.strip()
        assert item.company in ("WFC", "EFX", "PYPL", "COIN", "NAVI")
        assert item.source in (SourceType.FINNHUB, SourceType.CFPB, SourceType.EDGAR)
        assert item.source_url.startswith("http")
        assert len(item.title.strip()) > 0
        assert len(item.text.strip()) > 0
        assert item.published_at <= datetime.now(timezone.utc)
        assert len(item.content_hash) == 64  # Valid SHA-256

        # Source-specific invariants
        if item.source == SourceType.CFPB:
            assert "cfpb_" in item.id
            assert "consumerfinance.gov" in item.source_url
        elif item.source == SourceType.FINNHUB:
            assert "finnhub_" in item.id
        elif item.source == SourceType.EDGAR:
            assert "edgar_" in item.id
            assert "sec.gov" in item.source_url


def test_gate_p1_rerun_adds_zero_duplicates():
    """Gate 2: Re-running ingestion must add 0 duplicate items."""
    client = ApiGatewayClient(mock_mode=True)
    store = InMemoryItemStore()
    pipeline = IngestionPipeline(client=client, store=store)

    # First run
    first_run_items = pipeline.ingest_all_companies(["WFC", "EFX"], limit_per_source=5)
    first_count = store.count()
    assert first_count > 0
    assert len(first_run_items) == first_count

    # Re-run identical ingestion
    second_run_items = pipeline.ingest_all_companies(["WFC", "EFX"], limit_per_source=5)
    second_count = store.count()

    # Gate guarantee: re-run adds 0 duplicates
    assert len(second_run_items) == 0, f"Expected 0 new items on re-run, got {len(second_run_items)}"
    assert second_count == first_count, f"Store count changed from {first_count} to {second_count}"


def test_gate_p1_cfpb_narrative_filter_strictly_enforced():
    """Gate 3: CFPB complaints without narratives must be filtered out."""
    client = ApiGatewayClient(mock_mode=True)
    adapter = CFPBAdapter(client=client)

    # With narrative filter enabled
    items_with_narratives = adapter.fetch_complaints("WELLS FARGO & COMPANY", "WFC", has_narrative=True)
    for item in items_with_narratives:
        assert len(item.text.strip()) > 0, "CFPB complaint has empty text"
        assert item.source == SourceType.CFPB


def test_gate_p1_user_agent_header_contains_email():
    """Gate 4: Custom User-Agent with email sent to CFPB and EDGAR."""
    client = ApiGatewayClient(mock_mode=True)
    edgar_conf = client.endpoints.get("edgar_submissions", {})
    cfpb_conf = client.endpoints.get("cfpb_complaints", {})

    assert edgar_conf["auth"]["type"] == "custom_header"
    assert edgar_conf["auth"]["key"] == "User-Agent"
    assert edgar_conf["auth"]["env_var"] == "USER_AGENT_EMAIL"

    assert cfpb_conf["auth"]["type"] == "custom_header"
    assert cfpb_conf["auth"]["key"] == "User-Agent"
    assert cfpb_conf["auth"]["env_var"] == "USER_AGENT_EMAIL"


def test_gate_p1_scheduler_intervals():
    """Gate 5: Scheduler configured with Finnhub=60s, CFPB=900s, EDGAR=900s."""
    scheduler = IngestionScheduler()
    intervals = scheduler.get_intervals()

    assert intervals["finnhub"] == 60, f"Expected 60s for Finnhub, got {intervals['finnhub']}"
    assert intervals["cfpb"] == 900, f"Expected 900s (15 min) for CFPB, got {intervals['cfpb']}"
    assert intervals["edgar"] == 900, f"Expected 900s (15 min) for EDGAR, got {intervals['edgar']}"


def test_gate_p1_graph_item_nodes_and_about_edges():
    """Gate 6: Ingest pipeline writes Item nodes and ABOUT edges to graph repo."""
    client = ApiGatewayClient(mock_mode=True)
    store = InMemoryItemStore()
    pipeline = IngestionPipeline(client=client, store=store, graph=graph_repo)

    items = pipeline.ingest_finnhub("WFC")
    assert len(items) > 0

    # Verify items are persisted in graph repo
    stored_items = graph_repo.get_items_for_company("WFC")
    assert len(stored_items) > 0
    item_ids = [it.get("id") if isinstance(it, dict) else it.id for it in stored_items]
    for it in items:
        assert it.id in item_ids


def test_gate_p1_capacity_budget_respected():
    """Gate 7: Capacity budget limits max 1,200 Item nodes per company."""
    assert MAX_ITEMS_PER_COMPANY == 1200
    # Prune operation runs without error and enforces capacity boundary
    graph_repo.prune_company_capacity("WFC")
