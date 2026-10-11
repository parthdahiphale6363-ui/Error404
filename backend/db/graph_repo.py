"""Neo4j Knowledge Graph Repository for Corporate Risk Radar.

STRICT ARCHITECTURAL RULE:
Only this module runs Cypher queries. All queries must be parameterized,
never string-built. Neo4j properties cannot be maps; nested structures
are serialized as JSON strings.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from neo4j import GraphDatabase, Driver
from backend.schemas import Item, ScorePoint, AlertRecord, ConsensusFlag

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
        self._last_conn_failure: float = 0.0
        self._in_memory_items: Dict[str, Dict[str, Any]] = {}
        self._in_memory_companies: Dict[str, Dict[str, Any]] = {}
        self._in_memory_topics: Dict[str, Dict[str, Any]] = {}
        self._in_memory_regulators: Dict[str, Dict[str, Any]] = {}
        self._in_memory_relationships: List[Dict[str, Any]] = []
        self._in_memory_alerts: List[Dict[str, Any]] = []
        self._seed_in_memory_entities()


    def _seed_in_memory_entities(self):
        """Seed default 5 target companies, benchmark taxonomy, and labeled items into in-memory store."""
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

        initial_regulators = ["CFPB", "SEC", "OCC", "DOJ", "FTC", "State AG"]
        for reg in initial_regulators:
            self._in_memory_regulators[reg] = {"name": reg}

        # Seed candidate & labeled items from data/labeled/labeled_items.jsonl
        labeled_path = Path(__file__).resolve().parent.parent.parent / "data" / "labeled" / "labeled_items.jsonl"
        if labeled_path.exists():
            try:
                with open(labeled_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        item_id = rec.get("id")
                        if not item_id:
                            continue
                        company = rec.get("company", "WFC")
                        rt_str = rec.get("user_labeled_risk_type") or "compliance"
                        sev = int(rec.get("user_labeled_severity") or 3)
                        topics = rec.get("true_topics") or []
                        regulators = rec.get("true_regulators") or []

                        item_dict = {
                            "id": item_id,
                            "company": company,
                            "source": rec.get("source", "finnhub"),
                            "source_url": rec.get("source_url", "https://example.com"),
                            "date": rec.get("date", "2026-03-10T12:00:00Z"),
                            "title": rec.get("title", ""),
                            "text": rec.get("text", ""),
                            "is_simulated": False,
                            "severity": sev,
                            "final_severity": sev,
                            "risk_type": rt_str,
                            "confidence": 0.92,
                            "reason": rec.get("title", ""),
                            "flagged": sev >= 3,
                            "topics": topics,
                            "regulators": regulators,
                            "topics_json": json.dumps(topics),
                            "regulators_json": json.dumps(regulators),
                        }
                        self._in_memory_items[item_id] = item_dict

                        # Link Item -> Company
                        self._in_memory_relationships.append({
                            "source": item_id,
                            "target": company,
                            "type": "ABOUT",
                        })

                        # Link Item -> Topics
                        for t in topics:
                            self._in_memory_topics[t] = {"name": t}
                            self._in_memory_relationships.append({
                                "source": item_id,
                                "target": t,
                                "type": "HAS_TOPIC",
                            })

                        # Link Item -> Regulators
                        for r in regulators:
                            self._in_memory_regulators[r] = {"name": r}
                            self._in_memory_relationships.append({
                                "source": item_id,
                                "target": r,
                                "type": "INVOLVES",
                            })
            except Exception as e:
                logger.warning(f"Failed to seed labeled items into in-memory store: {e}")

    @staticmethod
    def _probe_tcp(uri: str) -> bool:
        """Fast non-blocking TCP socket check to prevent threadpool hangs on blocked networks."""
        try:
            import socket
            clean = uri.split("://")[-1]
            host = clean.split(":")[0].split("/")[0]
            port = 7687
            if ":" in clean:
                parts = clean.split(":")
                if len(parts) > 1 and parts[1].split("/")[0].isdigit():
                    port = int(parts[1].split("/")[0])
            with socket.create_connection((host, port), timeout=0.8):
                return True
        except Exception:
            return False

    def _mark_driver_failure(self, err: Optional[Exception] = None):
        """Invalidate dead driver and enter cooldown."""
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None
        self._last_conn_failure = time.time()
        if err:
            logger.warning("Neo4j driver operation failed (%s). Operating in in-memory fallback.", err)

    def get_driver(self) -> Optional[Driver]:
        """Lazy-initialize and return the Neo4j driver if credentials exist."""
        if os.getenv("MOCK_MODE", "0").lower() in ("1", "true") or os.getenv("DISABLE_NEO4J", "0").lower() in ("1", "true"):
            return None
        if self._driver is not None:
            return self._driver
        now = time.time()
        # Cooldown failure retries to prevent blocking HTTP requests on unreachable hosts
        if now - self._last_conn_failure < 120.0:
            return None
        if self.uri and self.user and self.password:
            try:
                # Fast TCP probe before heavy driver init to prevent threadpool hangs on blocked networks
                if not self._probe_tcp(self.uri):
                    self._last_conn_failure = now
                    logger.info("Neo4j TCP port 7687 unreachable on current network. Operating with in-memory graph repository.")
                    return None

                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password),
                    connection_timeout=2.0,
                )
                self._driver.verify_connectivity()
                return self._driver
            except Exception as e:
                self._mark_driver_failure(e)
            return None
        return None

    def close(self):
        """Close Neo4j driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def check_health(self) -> Dict[str, Any]:
        """Check Neo4j connectivity, node/relationship counts, and capacity warning."""
        node_cnt = (
            len(self._in_memory_companies)
            + len(self._in_memory_items)
            + len(self._in_memory_topics)
            + len(self._in_memory_regulators)
        )
        rel_cnt = len(self._in_memory_relationships)

        driver = self.get_driver()
        if not driver:
            return {
                "connected": False,
                "node_count": node_cnt,
                "relationship_count": rel_cnt,
                "max_nodes": MAX_NODES,
                "max_relationships": MAX_RELATIONSHIPS,
                "node_capacity_pct": round(node_cnt / MAX_NODES * 100, 2),
                "rel_capacity_pct": round(rel_cnt / MAX_RELATIONSHIPS * 100, 2),
                "capacity_warning": False,
                "status": "in_memory_fallback",
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
            self._mark_driver_failure(e)
            return {
                "connected": False,
                "node_count": node_cnt,
                "relationship_count": rel_cnt,
                "max_nodes": MAX_NODES,
                "max_relationships": MAX_RELATIONSHIPS,
                "node_capacity_pct": round(node_cnt / MAX_NODES * 100, 2),
                "rel_capacity_pct": round(rel_cnt / MAX_RELATIONSHIPS * 100, 2),
                "capacity_warning": False,
                "status": "in_memory_fallback",
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

        try:
            with driver.session() as session:
                for q in queries:
                    session.run(q)
                    results.append(q)
            return results
        except Exception as e:
            self._mark_driver_failure(e)
            return ["Fallback: constraints registered in memory"]

    def upsert_company(self, ticker: str, name: str):
        """Upsert Company node with ticker and name."""
        self._in_memory_companies[ticker] = {"ticker": ticker, "name": name}
        driver = self.get_driver()
        if not driver:
            return
        query = (
            "MERGE (c:Company {ticker: $ticker}) "
            "ON CREATE SET c.name = $name "
            "ON MATCH SET c.name = $name"
        )
        try:
            with driver.session() as session:
                session.run(query, ticker=ticker, name=name)
        except Exception as e:
            self._mark_driver_failure(e)

    def upsert_item(self, item: Item, topics: Optional[List[str]] = None, regulators: Optional[List[str]] = None):
        """Upsert Item node with relationships to Company, Topics, and Regulators."""
        # Always update in-memory store
        try:
            self._in_memory_items[item.id] = item.model_dump() if hasattr(item, "model_dump") else dict(item)
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
        except Exception as e:
            logger.warning("In-memory item upsert error: %s", e)

        driver = self.get_driver()
        if not driver:
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
        try:
            with driver.session() as session:
                session.run(query, **params)
        except Exception as e:
            self._mark_driver_failure(e)

    def upsert_detection(self, item: Item, detection: Any):
        """Persist detection properties (severity, risk_type, flagged, confidence) and topic/regulator edges."""
        topics = getattr(detection, "topics", [])
        regulators = getattr(detection, "regulators", [])
        self.upsert_item(item, topics=topics, regulators=regulators)

        severity = getattr(detection, "severity", 0)
        risk_type = getattr(detection.risk_type, "value", str(detection.risk_type))
        confidence = getattr(detection, "confidence", 1.0)
        reason = getattr(detection, "reason", "")
        flagged = severity >= 3

        if item.id in self._in_memory_items:
            self._in_memory_items[item.id].update({
                "severity": severity,
                "risk_type": risk_type,
                "confidence": confidence,
                "reason": reason,
                "flagged": flagged,
                "topics": topics,
                "regulators": regulators,
            })

        driver = self.get_driver()
        if not driver:
            return

        query = (
            "MATCH (i:Item {id: $id}) "
            "SET i.severity = $severity, "
            "    i.risk_type = $risk_type, "
            "    i.confidence = $confidence, "
            "    i.reason = $reason, "
            "    i.flagged = $flagged, "
            "    i.topics_json = $topics_json, "
            "    i.regulators_json = $regulators_json"
        )
        try:
            with driver.session() as session:
                session.run(
                    query,
                    id=item.id,
                    severity=severity,
                    risk_type=risk_type,
                    confidence=confidence,
                    reason=reason,
                    flagged=flagged,
                    topics_json=json.dumps(topics),
                    regulators_json=json.dumps(regulators),
                )
        except Exception as e:
            self._mark_driver_failure(e)

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single item by ID."""
        driver = self.get_driver()
        if not driver:
            return self._in_memory_items.get(item_id)

        query = "MATCH (i:Item {id: $id}) RETURN i"
        try:
            with driver.session() as session:
                res = session.run(query, id=item_id)
                record = res.single()
                return dict(record["i"]) if record else None
        except Exception as e:
            self._mark_driver_failure(e)
            return self._in_memory_items.get(item_id)

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
        try:
            with driver.session() as session:
                res = session.run(query, ticker=ticker, limit=limit)
                return [dict(record["i"]) for record in res]
        except Exception as e:
            self._mark_driver_failure(e)
            return [
                v for v in self._in_memory_items.values()
                if v.get("company") == ticker
            ][:limit]

    def upsert_consensus(self, flag: ConsensusFlag):
        """Persist consensus flag attributes to Item node."""
        status_val = getattr(flag.status, "value", str(flag.status))
        risk_type_val = getattr(flag.risk_type, "value", str(flag.risk_type))
        verdict_val = getattr(flag.analyst_verdict, "value", str(flag.analyst_verdict)) if flag.analyst_verdict else None
        verifier_rt_val = getattr(flag.verifier_risk_type, "value", str(flag.verifier_risk_type)) if flag.verifier_risk_type else None

        # Always update in-memory state for seamless fallback
        if flag.item_id in self._in_memory_items:
            self._in_memory_items[flag.item_id].update({
                "status": status_val,
                "primary_severity": flag.primary_severity,
                "final_severity": flag.final_severity,
                "severity": flag.final_severity,
                "risk_type": risk_type_val,
                "review_factor": flag.review_factor,
                "verifier_provider": flag.verifier_provider,
                "verifier_severity": flag.verifier_severity,
                "verifier_risk_type": verifier_rt_val,
                "analyst_verdict": verdict_val,
                "confidence": flag.confidence,
                "reason": flag.reason,
            })
        else:
            self._in_memory_items[flag.item_id] = {
                "id": flag.item_id,
                "company": flag.company,
                "status": status_val,
                "primary_severity": flag.primary_severity,
                "final_severity": flag.final_severity,
                "severity": flag.final_severity,
                "risk_type": risk_type_val,
                "review_factor": flag.review_factor,
                "verifier_provider": flag.verifier_provider,
                "verifier_severity": flag.verifier_severity,
                "verifier_risk_type": verifier_rt_val,
                "analyst_verdict": verdict_val,
                "confidence": flag.confidence,
                "reason": flag.reason,
                "topics": flag.topics,
                "regulators": flag.regulators,
                "is_simulated": flag.is_simulated,
            }

        driver = self.get_driver()
        if not driver:
            return

        query = (
            "MATCH (i:Item {id: $id}) "
            "SET i.status = $status, "
            "    i.primary_severity = $primary_severity, "
            "    i.final_severity = $final_severity, "
            "    i.severity = $final_severity, "
            "    i.risk_type = $risk_type, "
            "    i.review_factor = $review_factor, "
            "    i.verifier_provider = $verifier_provider, "
            "    i.verifier_severity = $verifier_severity, "
            "    i.verifier_risk_type = $verifier_risk_type, "
            "    i.analyst_verdict = $analyst_verdict, "
            "    i.confidence = $confidence, "
            "    i.reason = $reason"
        )
        try:
            with driver.session() as session:
                session.run(
                    query,
                    id=flag.item_id,
                    status=status_val,
                    primary_severity=flag.primary_severity,
                    final_severity=flag.final_severity,
                    risk_type=risk_type_val,
                    review_factor=flag.review_factor,
                    verifier_provider=flag.verifier_provider,
                    verifier_severity=flag.verifier_severity,
                    verifier_risk_type=verifier_rt_val,
                    analyst_verdict=verdict_val,
                    confidence=flag.confidence,
                    reason=flag.reason,
                )
        except Exception as e:
            self._mark_driver_failure(e)

    def get_review_queue(self) -> List[Dict[str, Any]]:
        """Retrieve items with status 'needs_review'."""
        in_mem_queue = [
            v for v in self._in_memory_items.values()
            if v.get("status") == "needs_review"
        ]

        driver = self.get_driver()
        if not driver:
            return in_mem_queue

        query = (
            "MATCH (i:Item) "
            "WHERE i.status = 'needs_review' "
            "RETURN i ORDER BY i.date DESC"
        )
        try:
            with driver.session() as session:
                res = session.run(query)
                return [dict(record["i"]) for record in res]
        except Exception as e:
            self._mark_driver_failure(e)
            return in_mem_queue

    def update_verdict(self, item_id: str, verdict: Any) -> Optional[Dict[str, Any]]:
        """Update analyst verdict for an item in review queue."""
        verdict_str = getattr(verdict, "value", str(verdict)).lower()
        new_status = "confirmed" if verdict_str == "confirm" else "dismissed"
        new_rf = 1.0 if verdict_str == "confirm" else 0.0

        # Always update in-memory
        if item_id in self._in_memory_items:
            item = self._in_memory_items[item_id]
            item.update({
                "status": new_status,
                "analyst_verdict": verdict_str,
                "review_factor": new_rf,
            })

        driver = self.get_driver()
        if not driver:
            return self._in_memory_items.get(item_id)

        query = (
            "MATCH (i:Item {id: $id}) "
            "SET i.status = $status, "
            "    i.analyst_verdict = $verdict, "
            "    i.review_factor = $review_factor "
            "RETURN i"
        )
        try:
            with driver.session() as session:
                res = session.run(query, id=item_id, status=new_status, verdict=verdict_str, review_factor=new_rf)
                rec = res.single()
                return dict(rec["i"]) if rec else self._in_memory_items.get(item_id)
        except Exception as e:
            self._mark_driver_failure(e)
            return self._in_memory_items.get(item_id)

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
        ts_val = getattr(score_point, "ts", None)
        if ts_val is None:
            as_of_val = getattr(score_point, "as_of", None)
            ts_val = as_of_val.isoformat() if hasattr(as_of_val, "isoformat") else str(as_of_val)
        index_val = getattr(score_point, "index_score", getattr(score_point, "index", 0.0))
        top_json = getattr(score_point, "top_items_json", "[]")

        try:
            with driver.session() as session:
                session.run(
                    query,
                    ticker=ticker,
                    ts=ts_val,
                    index=index_val,
                    top_items_json=top_json,
                )
        except Exception as e:
            self._mark_driver_failure(e)

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
        try:
            with driver.session() as session:
                session.run(query, ticker=ticker, max_items=MAX_ITEMS_PER_COMPANY)
        except Exception as e:
            self._mark_driver_failure(e)

    def reset_simulated_items(self) -> int:
        """Remove all simulated items (`is_simulated=true`) and associated relationships."""
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
        in_memory_removed = initial - len(self._in_memory_items)

        driver = self.get_driver()
        if not driver:
            return in_memory_removed

        query = (
            "MATCH (i:Item {is_simulated: true}) "
            "DETACH DELETE i"
        )
        try:
            with driver.session() as session:
                session.run(query)
            return in_memory_removed
        except Exception as e:
            self._mark_driver_failure(e)
            return in_memory_removed

    def get_evidence_for_company(self, ticker: str, limit: int = 15) -> Dict[str, Any]:
        """Retrieve graph evidence for a company: items, recurrence, contagion, paths, nodes, edges."""
        driver = self.get_driver()
        ticker = ticker.upper()

        if not driver:
            # In-memory graph traversal
            comp_items = [
                v for v in self._in_memory_items.values()
                if v.get("company") == ticker
            ][:limit]

            # If no items in memory yet, return empty structured dict
            if not comp_items:
                nodes = [{"id": f"comp_{ticker}", "label": "Company", "properties": {"ticker": ticker}}]
                return {
                    "items": [],
                    "recurrence": [],
                    "contagion": [],
                    "paths": [],
                    "nodes": nodes,
                    "edges": [],
                }

            items_by_id = {item["id"]: item for item in comp_items}
            item_topics: Dict[str, List[str]] = {}
            item_regulators: Dict[str, List[str]] = {}

            # Discover topics & regulators from relationships or item properties
            for rel in self._in_memory_relationships:
                src = rel.get("source")
                tgt = rel.get("target")
                rtype = rel.get("type")
                if rtype == "HAS_TOPIC" and src:
                    item_topics.setdefault(src, []).append(tgt)
                elif rtype == "INVOLVES" and src:
                    item_regulators.setdefault(src, []).append(tgt)

            # Check if topics were stored as JSON strings
            for item_id, it in self._in_memory_items.items():
                if "topics_json" in it and item_id not in item_topics:
                    try:
                        item_topics[item_id] = json.loads(it["topics_json"])
                    except Exception:
                        pass
                if "regulators_json" in it and item_id not in item_regulators:
                    try:
                        item_regulators[item_id] = json.loads(it["regulators_json"])
                    except Exception:
                        pass

            recurrence = []
            contagion = []
            paths = []

            for i1 in comp_items:
                i1_id = i1["id"]
                t_list = item_topics.get(i1_id, [])
                for topic in t_list:
                    # Find other items with same topic
                    for other_id, other_topics in item_topics.items():
                        if other_id == i1_id or topic not in other_topics:
                            continue
                        other_item = self._in_memory_items.get(other_id)
                        if not other_item:
                            continue
                        if other_item.get("company") == ticker:
                            recurrence.append({"item_id": i1_id, "topic": topic, "related_item_id": other_id})
                            path_str = f"(Item:{i1_id})-[:HAS_TOPIC]->(Topic:{topic})<-[:HAS_TOPIC]-(Item:{other_id})"
                            if path_str not in paths:
                                paths.append(path_str)
                        else:
                            other_comp = other_item.get("company", "OTHER")
                            contagion.append({"item_id": i1_id, "topic": topic, "related_item_id": other_id, "other_company": other_comp})
                            path_str = f"(Item:{i1_id})-[:HAS_TOPIC]->(Topic:{topic})<-[:HAS_TOPIC]-(Item:{other_id})-[:ABOUT]->(Company:{other_comp})"
                            if path_str not in paths:
                                paths.append(path_str)

            # If no multi-item paths, generate item -> topic / regulator paths
            if not paths:
                for i1 in comp_items:
                    i1_id = i1["id"]
                    for t in item_topics.get(i1_id, []):
                        paths.append(f"(Item:{i1_id})-[:HAS_TOPIC]->(Topic:{t})")
                    for r in item_regulators.get(i1_id, []):
                        paths.append(f"(Item:{i1_id})-[:INVOLVES]->(Regulator:{r})")

            # Build visualization nodes and edges
            nodes = [{"id": f"comp_{ticker}", "label": "Company", "properties": {"ticker": ticker}}]
            edges = []
            seen_nodes = {f"comp_{ticker}"}

            for it in comp_items:
                i_id = it["id"]
                if i_id not in seen_nodes:
                    seen_nodes.add(i_id)
                    nodes.append({
                        "id": i_id,
                        "label": "Item",
                        "properties": {
                            "title": it.get("title", ""),
                            "severity": it.get("severity", it.get("final_severity", 3)),
                            "risk_type": it.get("risk_type", "compliance"),
                        },
                    })
                edges.append({"source": i_id, "target": f"comp_{ticker}", "type": "ABOUT", "properties": {}})

                for t in item_topics.get(i_id, []):
                    t_id = f"topic_{t.replace(' ', '_')}"
                    if t_id not in seen_nodes:
                        seen_nodes.add(t_id)
                        nodes.append({"id": t_id, "label": "Topic", "properties": {"name": t}})
                    edges.append({"source": i_id, "target": t_id, "type": "HAS_TOPIC", "properties": {}})

                for r in item_regulators.get(i_id, []):
                    r_id = f"reg_{r.replace(' ', '_')}"
                    if r_id not in seen_nodes:
                        seen_nodes.add(r_id)
                        nodes.append({"id": r_id, "label": "Regulator", "properties": {"name": r}})
                    edges.append({"source": i_id, "target": r_id, "type": "INVOLVES", "properties": {}})

            # Include multi-hop recurrence into topology nodes & edges
            for rec in recurrence[:8]:
                rel_id = rec["related_item_id"]
                topic = rec["topic"]
                t_id = f"topic_{topic.replace(' ', '_')}"
                if rel_id not in seen_nodes:
                    seen_nodes.add(rel_id)
                    r_item = self._in_memory_items.get(rel_id, {})
                    nodes.append({
                        "id": rel_id,
                        "label": "Item",
                        "properties": {
                            "title": r_item.get("title", ""),
                            "severity": r_item.get("severity", r_item.get("final_severity", 3)),
                            "risk_type": r_item.get("risk_type", "compliance"),
                            "is_recurrence": True,
                        },
                    })
                    edges.append({"source": rel_id, "target": f"comp_{ticker}", "type": "ABOUT", "properties": {"is_recurrence": True}})
                if t_id in seen_nodes:
                    edges.append({"source": rel_id, "target": t_id, "type": "HAS_TOPIC", "properties": {"is_recurrence": True}})

            # Include cross-company contagion paths into topology nodes & edges
            for con in contagion[:6]:
                c_other_comp = con["other_company"]
                c_rel_id = con["related_item_id"]
                c_topic = con["topic"]
                c_item = self._in_memory_items.get(c_rel_id, {})
                t_id = f"topic_{c_topic.replace(' ', '_')}"

                peer_comp_id = f"comp_{c_other_comp}"
                if peer_comp_id not in seen_nodes:
                    seen_nodes.add(peer_comp_id)
                    nodes.append({
                        "id": peer_comp_id,
                        "label": "Company",
                        "properties": {
                            "ticker": c_other_comp,
                            "name": self._in_memory_companies.get(c_other_comp, {}).get("name", c_other_comp),
                            "is_peer": True,
                        },
                    })

                if c_rel_id not in seen_nodes:
                    seen_nodes.add(c_rel_id)
                    nodes.append({
                        "id": c_rel_id,
                        "label": "Item",
                        "properties": {
                            "title": c_item.get("title", ""),
                            "severity": c_item.get("severity", c_item.get("final_severity", 3)),
                            "risk_type": c_item.get("risk_type", "compliance"),
                            "company": c_other_comp,
                            "is_contagion": True,
                        },
                    })
                edges.append({"source": c_rel_id, "target": peer_comp_id, "type": "ABOUT", "properties": {"is_contagion": True}})
                if t_id in seen_nodes:
                    edges.append({"source": c_rel_id, "target": t_id, "type": "HAS_TOPIC", "properties": {"is_contagion": True}})

            return {
                "items": comp_items,
                "recurrence": recurrence,
                "contagion": contagion,
                "paths": paths,
                "nodes": nodes,
                "edges": edges,
            }

        # Neo4j Driver Mode: Execute Cypher queries
        query_items = (
            "MATCH (i:Item)-[:ABOUT]->(c:Company {ticker: $ticker}) "
            "OPTIONAL MATCH (i)-[:HAS_TOPIC]->(t:Topic) "
            "OPTIONAL MATCH (i)-[:INVOLVES]->(r:Regulator) "
            "RETURN i, collect(DISTINCT t.name) AS topics, collect(DISTINCT r.name) AS regulators "
            "ORDER BY i.date DESC LIMIT $limit"
        )
        query_recurrence = (
            "MATCH (i1:Item)-[:ABOUT]->(c:Company {ticker: $ticker}), "
            "      (i1)-[:HAS_TOPIC]->(t:Topic)<-[:HAS_TOPIC]-(i2:Item)-[:ABOUT]->(c) "
            "WHERE i1.id <> i2.id "
            "RETURN i1.id AS id1, t.name AS topic, i2.id AS id2 "
            "LIMIT 25"
        )
        query_contagion = (
            "MATCH (i1:Item)-[:ABOUT]->(c:Company {ticker: $ticker}), "
            "      (i1)-[:HAS_TOPIC]->(t:Topic)<-[:HAS_TOPIC]-(i2:Item)-[:ABOUT]->(c2:Company) "
            "WHERE c.ticker <> c2.ticker "
            "RETURN i1.id AS id1, t.name AS topic, i2.id AS id2, c2.ticker AS other_ticker "
            "LIMIT 25"
        )

        try:
            with driver.session() as session:
                res_items = session.run(query_items, ticker=ticker, limit=limit)
                comp_items = []
                nodes = [{"id": f"comp_{ticker}", "label": "Company", "properties": {"ticker": ticker}}]
                edges = []
                seen_nodes = {f"comp_{ticker}"}
                paths = []

                for rec in res_items:
                    item_dict = dict(rec["i"])
                    topics = rec["topics"]
                    regulators = rec["regulators"]
                    item_dict["topics"] = topics
                    item_dict["regulators"] = regulators
                    comp_items.append(item_dict)

                    i_id = item_dict.get("id")
                    if i_id and i_id not in seen_nodes:
                        seen_nodes.add(i_id)
                        nodes.append({
                            "id": i_id,
                            "label": "Item",
                            "properties": {
                                "title": item_dict.get("title", ""),
                                "severity": item_dict.get("severity", item_dict.get("final_severity", 3)),
                                "risk_type": item_dict.get("risk_type", "compliance"),
                            },
                        })
                        edges.append({"source": i_id, "target": f"comp_{ticker}", "type": "ABOUT", "properties": {}})

                    for t in topics:
                        t_id = f"topic_{t.replace(' ', '_')}"
                        if t_id not in seen_nodes:
                            seen_nodes.add(t_id)
                            nodes.append({"id": t_id, "label": "Topic", "properties": {"name": t}})
                        edges.append({"source": i_id, "target": t_id, "type": "HAS_TOPIC", "properties": {}})

                    for r in regulators:
                        r_id = f"reg_{r.replace(' ', '_')}"
                        if r_id not in seen_nodes:
                            seen_nodes.add(r_id)
                            nodes.append({"id": r_id, "label": "Regulator", "properties": {"name": r}})
                        edges.append({"source": i_id, "target": r_id, "type": "INVOLVES", "properties": {}})

                res_rec = session.run(query_recurrence, ticker=ticker)
                recurrence = []
                for rec in res_rec:
                    recurrence.append({"item_id": rec["id1"], "topic": rec["topic"], "related_item_id": rec["id2"]})
                    path_str = f"(Item:{rec['id1']})-[:HAS_TOPIC]->(Topic:{rec['topic']})<-[:HAS_TOPIC]-(Item:{rec['id2']})"
                    if path_str not in paths:
                        paths.append(path_str)

                res_con = session.run(query_contagion, ticker=ticker)
                contagion = []
                for rec in res_con:
                    contagion.append({"item_id": rec["id1"], "topic": rec["topic"], "related_item_id": rec["id2"], "other_company": rec["other_ticker"]})
                    path_str = f"(Item:{rec['id1']})-[:HAS_TOPIC]->(Topic:{rec['topic']})<-[:HAS_TOPIC]-(Item:{rec['id2']})-[:ABOUT]->(Company:{rec['other_ticker']})"
                    if path_str not in paths:
                        paths.append(path_str)

                    # Add peer company & contagion items/edges to graph
                    peer_ticker = rec["other_ticker"]
                    peer_comp_id = f"comp_{peer_ticker}"
                    if peer_comp_id not in seen_nodes:
                        seen_nodes.add(peer_comp_id)
                        nodes.append({
                            "id": peer_comp_id,
                            "label": "Company",
                            "properties": {"ticker": peer_ticker, "is_peer": True},
                        })

                    con_item_id = rec["id2"]
                    if con_item_id not in seen_nodes:
                        seen_nodes.add(con_item_id)
                        nodes.append({
                            "id": con_item_id,
                            "label": "Item",
                            "properties": {"company": peer_ticker, "is_contagion": True},
                        })
                    edges.append({"source": con_item_id, "target": peer_comp_id, "type": "ABOUT", "properties": {"is_contagion": True}})
                    t_id = f"topic_{rec['topic'].replace(' ', '_')}"
                    if t_id in seen_nodes:
                        edges.append({"source": con_item_id, "target": t_id, "type": "HAS_TOPIC", "properties": {"is_contagion": True}})

                return {
                    "items": comp_items,
                    "recurrence": recurrence,
                    "contagion": contagion,
                    "paths": paths,
                    "nodes": nodes,
                    "edges": edges,
                }
        except Exception as e:
            self._mark_driver_failure(e)
            return self.get_evidence_for_company(ticker, limit)


# Default singleton instance
graph_repo = GraphRepo()

