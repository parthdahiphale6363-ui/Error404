"""Ingestion Pipeline and Deduplication Store.

Coordinates multi-source data ingestion from Finnhub, CFPB, and SEC EDGAR.
Enforces strict deduplication via content hash and item ID.
Persists Item nodes and ABOUT relationships to Neo4j graph repository.
Enforces the 1,200 item capacity budget per company.
"""

from datetime import datetime, timedelta, timezone
import logging
from threading import Lock
from typing import Dict, List, Optional, Set

from backend.apigateway.client import ApiGatewayClient, gateway_client
from backend.apigateway.adapters.finnhub import FinnhubAdapter
from backend.apigateway.adapters.cfpb import CFPBAdapter
from backend.apigateway.adapters.edgar import EdgarAdapter
from backend.db.graph_repo import GraphRepo, graph_repo
from backend.schemas import Item, SourceType

logger = logging.getLogger("ingest.pipeline")

COMPANY_METADATA: Dict[str, Dict[str, str]] = {
    "WFC": {
        "name": "WELLS FARGO & COMPANY",
        "cik": "0000072971",
        "industry": "Commercial Banking",
    },
    "EFX": {
        "name": "EQUIFAX, INC.",
        "cik": "0000033185",
        "industry": "Credit Reporting",
    },
    "PYPL": {
        "name": "Paypal Holdings, Inc",
        "cik": "0001633917",
        "industry": "Digital Payments",
    },
    "COIN": {
        "name": "Coinbase, Inc.",
        "cik": "0001679788",
        "industry": "Crypto Asset Exchange",
    },
    "NAVI": {
        "name": "Navient Solutions, LLC.",
        "cik": "0001593538",
        "industry": "Student Loan Servicing",
    },
}


class InMemoryItemStore:
    """Thread-safe item repository with content-hash and ID deduplication."""

    def __init__(self):
        self._lock = Lock()
        self._items: Dict[str, Item] = {}
        self._content_hashes: Set[str] = set()

    def add(self, item: Item) -> bool:
        """Add item if not already present. Returns True if added, False if duplicate."""
        with self._lock:
            if item.id in self._items or item.content_hash in self._content_hashes:
                return False
            self._items[item.id] = item
            self._content_hashes.add(item.content_hash)
            return True

    def get(self, item_id: str) -> Optional[Item]:
        with self._lock:
            return self._items.get(item_id)

    def get_by_company(self, company: str) -> List[Item]:
        with self._lock:
            target = company.upper()
            items = [item for item in self._items.values() if item.company.upper() == target]
            items.sort(key=lambda x: x.published_at, reverse=True)
            return items

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def all(self) -> List[Item]:
        with self._lock:
            items = list(self._items.values())
            items.sort(key=lambda x: x.published_at, reverse=True)
            return items

    def clear(self):
        with self._lock:
            self._items.clear()
            self._content_hashes.clear()


item_store = InMemoryItemStore()


class IngestionPipeline:
    """Coordinates multi-source data ingestion with deduplication and graph persistence."""

    def __init__(
        self,
        client: Optional[ApiGatewayClient] = None,
        store: Optional[InMemoryItemStore] = None,
        graph: Optional[GraphRepo] = None,
    ):
        self.client = client or gateway_client
        self.store = store or item_store
        self.graph = graph or graph_repo
        self.finnhub = FinnhubAdapter(client=self.client)
        self.cfpb = CFPBAdapter(client=self.client)
        self.edgar = EdgarAdapter(client=self.client)

    def _persist_and_prune(self, items: List[Item], company: str) -> List[Item]:
        """Add to memory store, persist to graph repo, and prune capacity if needed."""
        new_items: List[Item] = []
        for item in items:
            if self.store.add(item):
                new_items.append(item)
                if self.graph:
                    self.graph.upsert_item(item)

        if new_items and self.graph:
            self.graph.prune_company_capacity(company)

        return new_items

    def ingest_finnhub(
        self,
        company: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Item]:
        """Ingest company news from Finnhub."""
        now = datetime.now(timezone.utc)
        if not to_date:
            to_date = now.strftime("%Y-%m-%d")
        if not from_date:
            from_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        try:
            items = self.finnhub.fetch_company_news(symbol=company, from_date=from_date, to_date=to_date)
            return self._persist_and_prune(items, company.upper())
        except Exception as e:
            logger.warning("Finnhub ingestion error for %s: %s", company, e)
            return []

    def ingest_cfpb(
        self,
        company: str,
        has_narrative: bool = True,
        size: int = 50,
    ) -> List[Item]:
        """Ingest CFPB complaints for company (strictly requiring consumer narrative)."""
        meta = COMPANY_METADATA.get(company.upper(), {})
        company_name = meta.get("name", company)

        now = datetime.now(timezone.utc)
        date_max = now.strftime("%Y-%m-%d")
        date_min = (now - timedelta(days=90)).strftime("%Y-%m-%d")

        try:
            items = self.cfpb.fetch_complaints(
                company_name=company_name,
                ticker=company.upper(),
                date_min=date_min,
                date_max=date_max,
                has_narrative=has_narrative,
                size=size,
            )
            return self._persist_and_prune(items, company.upper())
        except Exception as e:
            logger.warning("CFPB ingestion error for %s: %s", company, e)
            return []

    def ingest_edgar(
        self,
        company: str,
        max_items: int = 10,
    ) -> List[Item]:
        """Ingest SEC EDGAR regulatory filings."""
        try:
            items = self.edgar.fetch_filings(ticker=company.upper(), max_items=max_items)
            return self._persist_and_prune(items, company.upper())
        except Exception as e:
            logger.warning("SEC EDGAR ingestion error for %s: %s", company, e)
            return []

    def ingest_company(self, company: str, limit_per_source: int = 10) -> List[Item]:
        """Ingest all available data for a specific company."""
        all_new: List[Item] = []
        all_new.extend(self.ingest_finnhub(company))
        all_new.extend(self.ingest_cfpb(company, has_narrative=True, size=limit_per_source))
        all_new.extend(self.ingest_edgar(company, max_items=limit_per_source))
        return all_new

    def ingest_all_companies(
        self,
        companies: Optional[List[str]] = None,
        limit_per_source: int = 10,
    ) -> List[Item]:
        """Ingest data across all tracked companies."""
        target_companies = companies or list(COMPANY_METADATA.keys())
        all_new: List[Item] = []
        for company in target_companies:
            all_new.extend(self.ingest_company(company, limit_per_source=limit_per_source))
        return all_new
