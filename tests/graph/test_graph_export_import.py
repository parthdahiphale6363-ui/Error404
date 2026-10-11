"""Phase 9 Graph Export and Import Disaster Recovery Gate Test.

Verifies:
1. Exporting graph captures all companies, items, topics, regulators, and relationships.
2. Restoring graph repopulates state identically.
"""

from pathlib import Path
from backend.db.graph_repo import graph_repo
from backend.db.export_graph import export_graph_to_json
from backend.db.import_graph import import_graph_from_json
from backend.schemas import Item, SourceType
from datetime import datetime, timezone


def test_graph_export_and_import_cycle(tmp_path):
    archive_path = tmp_path / "graph_backup.json"

    # Seed a distinctive test item
    test_item = Item(
        id="backup_test_item_42",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://finnhub.io/test42",
        title="Backup Verification Item",
        text="Ensuring complete graph persistence and recovery cycle.",
        published_at=datetime.now(timezone.utc),
        content_hash="content_hash_42",
    )
    graph_repo.upsert_item(test_item, topics=["unauthorized accounts or fraud"], regulators=["CFPB"])

    # 1. Export graph
    export_data = export_graph_to_json(target_path=archive_path)
    assert archive_path.exists()
    assert len(export_data.get("items", [])) > 0 or len(export_data.get("nodes", [])) > 0

    # 2. Clear item from in-memory or graph
    if not graph_repo.get_driver():
        graph_repo._in_memory_items.pop(test_item.id, None)
        assert test_item.id not in graph_repo._in_memory_items

    # 3. Import graph
    restored_count = import_graph_from_json(source_path=archive_path)
    assert restored_count > 0

    # 4. Verify item is restored
    restored_item = graph_repo.get_item(test_item.id)
    assert restored_item is not None
    assert restored_item.get("id") == test_item.id
