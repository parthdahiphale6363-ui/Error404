"""CFPB Consumer Complaint Database Adapter.

Ingests consumer complaints filtered strictly for items with consumer narratives.
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
from dateutil import parser as dt_parser

from backend.apigateway.client import ApiGatewayClient, gateway_client
from backend.schemas import Item, SourceType


class CFPBAdapter:
    """Adapter for CFPB consumer complaints API."""

    def __init__(self, client: Optional[ApiGatewayClient] = None):
        self.client = client or gateway_client

    def fetch_complaints(
        self,
        company_name: str,
        ticker: str,
        date_min: Optional[str] = None,
        date_max: Optional[str] = None,
        has_narrative: bool = True,
        size: int = 50,
        force_refresh: bool = False,
    ) -> List[Item]:
        """Fetch consumer complaints for a company and normalize into Item models."""
        params: Dict[str, Any] = {
            "company": company_name,
            "has_narrative": "true" if has_narrative else "false",
            "size": size,
            "sort": "created_date_desc",
        }
        if date_min:
            params["date_received_min"] = date_min
        if date_max:
            params["date_received_max"] = date_max

        raw_resp: Dict[str, Any] = self.client.request(
            endpoint_name="cfpb_complaints",
            params=params,
            force_refresh=force_refresh,
        )

        hits = raw_resp.get("hits", {}).get("hits", [])
        items: List[Item] = []

        for hit in hits:
            source = hit.get("_source", {})
            hit_company = source.get("company", "").upper()
            if company_name and (company_name.upper() not in hit_company and ticker.upper() not in hit_company):
                continue

            complaint_id = str(source.get("complaint_id") or hit.get("_id", ""))
            narrative = source.get("consumer_complaint_narrative", "").strip()
            product = source.get("product", "Consumer Financial Product")
            issue = source.get("issue", "General Issue")
            date_received_str = source.get("date_received")

            if has_narrative and not narrative:
                continue

            content_raw = f"{ticker}:{complaint_id}:{narrative}"
            content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()
            item_id = f"cfpb_{complaint_id}" if complaint_id else f"cfpb_{content_hash[:16]}"

            if date_received_str:
                try:
                    published_at = dt_parser.parse(date_received_str)
                    if published_at.tzinfo is None:
                        published_at = published_at.replace(tzinfo=timezone.utc)
                except Exception:
                    published_at = datetime.now(timezone.utc)
            else:
                published_at = datetime.now(timezone.utc)

            url = f"https://www.consumerfinance.gov/data-research/consumer-complaints/search/detail/{complaint_id}"
            title = f"CFPB Complaint: {product} — {issue}"

            item = Item(
                id=item_id,
                company=ticker.upper(),
                source=SourceType.CFPB,
                source_url=url,
                title=title,
                text=narrative or f"{product}: {issue}",
                published_at=published_at,
                is_simulated=False,
                content_hash=content_hash,
            )
            items.append(item)

        return items
