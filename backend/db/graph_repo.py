"""Neo4j Knowledge Graph Repository for Corporate Risk Radar.

STRICT ARCHITECTURAL RULE:
Only this module runs Cypher queries. All queries must be parameterized,
never string-built. Neo4j properties cannot be maps; nested structures
are serialized as JSON strings.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from neo4j import GraphDatabase, Driver
from backend.schemas import Item, ScorePoint, AlertRecord

logger = logging.getLogger(__name__)

# AuraDB Free Capacity Limits
MAX_NODES = 50_000
MAX_RELATIONSHIPS = 175_000
CAPACITY_WARN_THRESHOLD = 0.70  # Warn at 70% capacity

MAX_ITEMS_PER_COMPANY = 1_200
MAX_ALERTS = 500


class GraphRepo:
    """Encapsulates all Neo4j Cypher queries and capacity management."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.uri = uri or os.getenv("NEO4J_URI")
        self.user = user or os.getenv("NEO4J_USER")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        self._driver: Optional[Driver] = None
        self._in_memory_items: Dict[str, Dict[str, Any]] = {}
        self._in_memory_companies: Dict[str, Dict[str, Any]] = {}
        self._in_memory_topics: Dict[str, Dict[str, Any]] = {}
        self._in_memory_regulators: Dict[str, Dict[str, Any]] = {}
        self._in_memory_relationships: List[Dict[str, Any]] = []
        self._in_memory_alerts: List[Dict[str, Any]] = []
        self._seed_in_memory_entities()

    def _seed_in_memory_entities(self):
        """Seed default 5 target companies and benchmark taxonomy into in-memory store."""
        initial_companies = [
            ("WFC", "Wells Fargo & Company"),
            ("EFX", "Equifax Inc."),
            ("PYPL", "PayPal Holdings, Inc."),
            ("COIN", "Coinbase Global, Inc."),
            ("NAVI", "Navient Corporation"),
        ]
        for ticker, name in initial_companies:
            self._in_memory_companies[ticker] = {"ticker": ticker, "name": name}

        initial_topics = [
            "unauthorized accounts or fraud",
            "credit reporting errors",
            "enforcement action",
            "payments or outages",
            "mortgage or loan servicing",
        ]
        for topic in initial_topics:
            self._in_memory_topics[topic] = {"name": topic}

        initial_regulators = ["CFPB", "SEC", "OCC", "DOJ", "FTC"]
        for reg in initial_regulators:
            self._in_memory_regulators[reg] = {"name": reg}

    def get_driver(self) -> Optional[Driver]:
        """Lazy-initialize and return the Neo4j driver if credentials exist."""
        if self._driver is not None:
            return self._driver
        if self.uri and self.user and self.password:
            try:
                self._driver = GraphDatabase.driver(
                    self.uri, auth=(self.user, self.password)
                )
                self._driver.verify_connectivity()
                return self._driver
            except Exception as e:
                logger.warning(f"Neo4j connection failed: {e}. Operating in fallback mode.")
                self._driver = None
            return None
        return None

    def close(self):
        """Close Neo4j driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def check_health(self) -> Dict[str, Any]:
        """Check Neo4j connectivity, node/relationship counts, and capacity warning."""
        driver = self.get_driver()
        if not driver:
            node_cnt = (
                len(self._in_memory_companies)
                + len(self._in_memory_items)
                + len(self._in_memory_topics)
                + len(self._in_memory_regulators)
            )
            rel_cnt = len(self._in_memory_relationships)
            return {
                "connected": False,
                "node_count": node_cnt,
                "relationship_count": rel_cnt,
                "max_nodes": MAX_NODES,
                "max_relationships": MAX_RELATIONSHIPS,
                "node_capacity_pct": round(node_cnt / MAX_NODES * 100, 2),
                "rel_capacity_pct": round(rel_cnt / MAX_RELATIONSHIPS * 100, 2),
                "capacity_warning": False,
                "status": "offline_fallback",
            }


        try:
            with driver.session() as session:
                node_res = session.run("MATCH (n) RETURN count(n) AS cnt")
                node_count = node_res.single()["cnt"]

                rel_res = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
                rel_count = rel_res.single()["cnt"]

                node_pct = node_count / MAX_NODES
                rel_pct = rel_count / MAX_RELATIONSHIPS
                warning = (node_pct >= CAPACITY_WARN_THRESHOLD) or (rel_pct >= CAPACITY_WARN_THRESHOLD)

                return {
                    "connected": True,
                    "node_count": node_count,
                    "relationship_count": rel_count,
                    "max_nodes": MAX_NODES,
                    "max_relationships": MAX_RELATIONSHIPS,
                    "node_capacity_pct": round(node_pct * 100, 2),
                    "rel_capacity_pct": round(rel_pct * 100, 2),
                    "capacity_warning": warning,
                    "status": "connected",
                }
        except Exception as e:
            logger.error(f"Error querying Neo4j health: {e}")
            return {
                "connected": False,
                "node_count": 0,
                "relationship_count": 0,
                "max_nodes": MAX_NODES,
                "max_relationships": MAX_RELATIONSHIPS,
                "node_capacity_pct": 0.0,
                "rel_capacity_pct": 0.0,
                "capacity_warning": False,
                "status": f"error: {str(e)}",
            }

    def init_constraints(self) -> List[str]:
        """Create uniqueness constraints for Graph Model.
        
        Constraints:
        - Item.id IS UNIQUE
        - Company.ticker IS UNIQUE
        - Topic.name IS UNIQUE
        - Regulator.name IS UNIQUE
        - Alert.key IS UNIQUE
        """
        driver = self.get_driver()
        queries = [
            "CREATE CONSTRAINT item_id_uniq IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT company_ticker_uniq IF NOT EXISTS FOR (c:Company) REQUIRE c.ticker IS UNIQUE",
            "CREATE CONSTRAINT topic_name_uniq IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT regulator_name_uniq IF NOT EXISTS FOR (r:Regulator) REQUIRE r.name IS UNIQUE",
            "CREATE CONSTRAINT alert_key_uniq IF NOT EXISTS FOR (a:Alert) REQUIRE a.key IS UNIQUE",
        ]
        results = []
        if not driver:
            return ["Fallback: constraints registered in memory"]

        with driver.session() as session:
            for q in queries:
                session.run(q)
                results.append(q)
        return results

    def upsert_company(self, ticker: str, name: str):
        """Upsert Company node with ticker and name."""
        driver = self.get_driver()
        if not driver:
            self._in_memory_companies[ticker] = {"ticker": ticker, "name": name}
            return
        query = (
            "MERGE (c:Company {ticker: $ticker}) "
            "ON CREATE SET c.name = $name "
            "ON MATCH SET c.name = $name"
        )
        with driver.session() as session:
            session.run(query, ticker=ticker, name=name)

    def upsert_item(self, item: Item, topics: Optional[List[str]] = None, regulators: Optional[List[str]] = None):
        """Upsert Item node with relationships to Company, Topics, and Regulators."""
        driver = self.get_driver()
        if not driver:
            self._in_memory_items[item.id] = item.model_dump()
            # Link Item -> Company (ABOUT)
            if item.company not in self._in_memory_companies:
                self._in_memory_companies[item.company] = {"ticker": item.company, "name": item.company}
            self._in_memory_relationships.append({
                "source": item.id,
                "target": item.company,
                "type": "ABOUT",
            })
            if topics:
                for t in topics:
                    self._in_memory_topics[t] = {"name": t}
                    self._in_memory_relationships.append({
                        "source": item.id,
                        "target": t,
                        "type": "HAS_TOPIC",
                    })
            if regulators:
                for r in regulators:
                    self._in_memory_regulators[r] = {"name": r}
                    self._in_memory_relationships.append({
                        "source": item.id,
                        "target": r,
                        "type": "INVOLVES",
                    })
            return


        # Prepare parameters; store embedding or lists as primitive arrays or JSON strings
        params = {
            "id": item.id,
            "source": item.source,
            "url": item.url,
            "date": item.date,
            "title": item.title,
            "text_hash": item.text_hash,
            "is_simulated": item.is_simulated,
            "company": item.company,
            "topics": topics or [],
            "regulators": regulators or [],
        }

        query = (
            "MERGE (i:Item {id: $id}) "
            "SET i.source = $source, "
            "    i.url = $url, "
            "    i.date = $date, "
            "    i.title = $title, "
            "    i.text_hash = $text_hash, "
            "    i.is_simulated = $is_simulated "
            "WITH i "
            "MERGE (c:Company {ticker: $company}) "
            "MERGE (i)-[:ABOUT]->(c) "
            "WITH i "
            "FOREACH (t_name IN $topics | "
            "    MERGE (t:Topic {name: t_name}) "
            "    MERGE (i)-[:HAS_TOPIC]->(t) "
            ") "
            "WITH i "
            "FOREACH (r_name IN $regulators | "
            "    MERGE (r:Regulator {name: r_name}) "
            "    MERGE (i)-[:INVOLVES]->(r) "
            ")"
        )
        with driver.session() as session:
            session.run(query, **params)

    def get_items_for_company(self, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve items about a company."""
        driver = self.get_driver()
        if not driver:
            return [
                v for v in self._in_memory_items.values()
                if v.get("company") == ticker
            ][:limit]

        query = (
            "MATCH (i:Item)-[:ABOUT]->(c:Company {ticker: $ticker}) "
            "RETURN i ORDER BY i.date DESC LIMIT $limit"
        )
        with driver.session() as session:
            res = session.run(query, ticker=ticker, limit=limit)
            return [dict(record["i"]) for record in res]

    def record_score_point(self, ticker: str, score_point: ScorePoint):
        """Append hourly ScorePoint node to Company."""
        driver = self.get_driver()
        if not driver:
            return

        query = (
            "MATCH (c:Company {ticker: $ticker}) "
            "CREATE (s:ScorePoint {ts: $ts, index: $index, top_items_json: $top_items_json}) "
            "CREATE (c)-[:HAS_SCORE]->(s)"
        )
        with driver.session() as session:
            session.run(
                query,
                ticker=ticker,
                ts=score_point.ts,
                index=score_point.index,
                top_items_json=score_point.top_items_json,
            )

    def prune_company_capacity(self, ticker: str):
        """Prune oldest unflagged, unlabeled items when count exceeds capacity budget."""
        driver = self.get_driver()
        if not driver:
            return

        # Prune Item nodes beyond MAX_ITEMS_PER_COMPANY (1,200)
        query = (
            "MATCH (i:Item)-[:ABOUT]->(c:Company {ticker: $ticker}) "
            "WHERE (i.flagged IS NULL OR i.flagged = false) AND i.analyst_verdict IS NULL "
            "WITH i ORDER BY i.date ASC "
            "WITH collect(i) AS items "
            "WHERE size(items) > $max_items "
            "WITH items[0..(size(items) - $max_items)] AS to_delete "
            "UNWIND to_delete AS d "
            "DETACH DELETE d"
        )
        with driver.session() as session:
            session.run(query, ticker=ticker, max_items=MAX_ITEMS_PER_COMPANY)

    def reset_simulated_items(self) -> int:
        """Remove all simulated items (`is_simulated=true`) and associated relationships."""
        driver = self.get_driver()
        if not driver:
            sim_ids = {
                k for k, v in self._in_memory_items.items()
                if v.get("is_simulated", False)
            }
            initial = len(self._in_memory_items)
            self._in_memory_items = {
                k: v for k, v in self._in_memory_items.items()
                if not v.get("is_simulated", False)
            }
            self._in_memory_relationships = [
                r for r in self._in_memory_relationships
                if r.get("source") not in sim_ids and r.get("target") not in sim_ids
            ]
            return initial - len(self._in_memory_items)


        query = (
            "MATCH (i:Item {is_simulated: true}) "
            "WITH i, count(i) AS cnt "
            "DETACH DELETE i "
            "RETURN cnt"
        )
        with driver.session() as session:
            res = session.run(query)
            record = res.single()
            return record["cnt"] if record else 0


# Default singleton instance
graph_repo = GraphRepo()
