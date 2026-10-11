"""Export Neo4j Knowledge Graph to JSON archive.

Strictly exports all nodes and relationships for offline backup and restore testing.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from backend.db.graph_repo import graph_repo

logger = logging.getLogger(__name__)
DEFAULT_EXPORT_PATH = Path("data/export_graph.json")


def export_graph_to_json(target_path: Path = DEFAULT_EXPORT_PATH) -> Dict[str, Any]:
    """Export current graph nodes and relationships to JSON file."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    driver = graph_repo.get_driver()

    if not driver:
        # In-memory export
        export_data = {
            "companies": list(graph_repo._in_memory_companies.values()),
            "items": list(graph_repo._in_memory_items.values()),
            "topics": list(graph_repo._in_memory_topics.values()),
            "regulators": list(graph_repo._in_memory_regulators.values()),
            "relationships": graph_repo._in_memory_relationships,
            "export_ts": str(time_now := json.dumps(str(target_path))),
        }
        target_path.write_text(json.dumps(export_data, indent=2, default=str), encoding="utf-8")
        logger.info("Exported in-memory graph to %s", target_path)
        return export_data

    # Neo4j Driver mode
    query_nodes = "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props, elementId(n) AS id"
    query_edges = (
        "MATCH (a)-[r]->(b) "
        "RETURN type(r) AS type, properties(r) AS props, "
        "       coalesce(a.id, a.ticker, a.name) AS src, "
        "       coalesce(b.id, b.ticker, b.name) AS tgt"
    )

    with driver.session() as session:
        nodes = [dict(r) for r in session.run(query_nodes)]
        edges = [dict(r) for r in session.run(query_edges)]

    export_data = {
        "nodes": nodes,
        "edges": edges,
    }
    target_path.write_text(json.dumps(export_data, indent=2, default=str), encoding="utf-8")
    logger.info("Exported AuraDB graph to %s", target_path)
    return export_data


if __name__ == "__main__":
    export_graph_to_json()
    print("Graph export complete.")
