"""Import Neo4j Knowledge Graph from JSON archive.

Restores all nodes and relationships to test graph disaster recovery and migration.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict
from backend.db.graph_repo import graph_repo

logger = logging.getLogger(__name__)
DEFAULT_IMPORT_PATH = Path("data/export_graph.json")


def import_graph_from_json(source_path: Path = DEFAULT_IMPORT_PATH) -> int:
    """Import graph data from JSON archive."""
    if not source_path.exists():
        raise FileNotFoundError(f"Export archive not found at {source_path}")

    raw = json.loads(source_path.read_text(encoding="utf-8"))
    driver = graph_repo.get_driver()

    if not driver:
        # In-memory restore
        if "companies" in raw:
            for c in raw.get("companies", []):
                graph_repo._in_memory_companies[c["ticker"]] = c
            for it in raw.get("items", []):
                graph_repo._in_memory_items[it["id"]] = it
            for t in raw.get("topics", []):
                graph_repo._in_memory_topics[t["name"]] = t
            for r in raw.get("regulators", []):
                graph_repo._in_memory_regulators[r["name"]] = r
            graph_repo._in_memory_relationships = list(raw.get("relationships", []))
            return len(graph_repo._in_memory_items)
        return 0

    # Neo4j Driver Mode: Restore nodes and edges
    nodes = raw.get("nodes", [])
    edges = raw.get("edges", [])

    with driver.session() as session:
        # Clear existing non-company nodes
        session.run("MATCH (n) WHERE NOT n:Company DETACH DELETE n")

        for n in nodes:
            labels = ":".join(n.get("labels", ["Node"]))
            props = n.get("props", {})
            session.run(f"MERGE (n:{labels} {{id: $id}}) SET n += $props", id=props.get("id", "node"), props=props)

        for e in edges:
            rel_type = e.get("type", "RELATED")
            src = e.get("src")
            tgt = e.get("tgt")
            session.run(
                f"MATCH (a), (b) WHERE (a.id = $src OR a.ticker = $src OR a.name = $src) "
                f"                 AND (b.id = $tgt OR b.ticker = $tgt OR b.name = $tgt) "
                f"MERGE (a)-[r:{rel_type}]->(b)",
                src=src,
                tgt=tgt,
            )

    logger.info("Restored %d nodes and %d edges to AuraDB", len(nodes), len(edges))
    return len(nodes)


if __name__ == "__main__":
    count = import_graph_from_json()
    print(f"Graph restored successfully ({count} records).")
