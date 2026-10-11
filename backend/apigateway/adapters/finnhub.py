"""Finnhub API Adapter.

Converts raw Finnhub company news into standardized Item contracts.
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional

from backend.apigateway.client import ApiGatewayClient, gateway_client
from backend.schemas import Item, SourceType


class FinnhubAdapter:
    """Adapter for Finnhub company news endpoint."""

    def __init__(self, client: Optional[ApiGatewayClient] = None):
        self.client = client or gateway_client

    def fetch_company_news(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        force_refresh: bool = False,
    ) -> List[Item]:
        """Fetch news for a symbol and normalize into Item models."""
        raw_items: List[Dict[str, Any]] = self.client.request(
            endpoint_name="finnhub_company_news",
            params={
                "symbol": symbol.upper(),
                "from": from_date,
                "to": to_date,
            },
            force_refresh=force_refresh,
        )

        items: List[Item] = []
        for raw in raw_items:
            related = raw.get("related", "").upper()
            if related and related != symbol.upper():
                continue

            raw_id = str(raw.get("id", ""))
            headline = raw.get("headline", "").strip()
            summary = raw.get("summary", "").strip()
            url = raw.get("url", "")
            epoch = raw.get("datetime", 0)

            if not headline and not summary:
                continue

            content_raw = f"{symbol}:{headline}:{summary}"
            content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()
            item_id = f"finnhub_{symbol.upper()}_{raw_id}" if raw_id else f"finnhub_{content_hash[:16]}"
            published_at = datetime.fromtimestamp(epoch, tz=timezone.utc)

            item = Item(
                id=item_id,
                company=symbol.upper(),
                source=SourceType.FINNHUB,
                source_url=url or f"https://finnhub.io/news/{item_id}",
                title=headline,
                text=summary,
                published_at=published_at,
                is_simulated=False,
                content_hash=content_hash,
            )
            items.append(item)

        return items
