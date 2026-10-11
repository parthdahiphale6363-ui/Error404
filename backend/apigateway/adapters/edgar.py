"""SEC EDGAR Submissions Adapter.

Ingests regulatory filings (8-K, 10-K, 10-Q) from SEC EDGAR API.
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
from dateutil import parser as dt_parser

from backend.apigateway.client import ApiGatewayClient, gateway_client
from backend.schemas import Item, SourceType

TICKER_CIK_MAP: Dict[str, str] = {
    "WFC": "0000072971",
    "EFX": "0000033185",
    "PYPL": "0001633917",
    "COIN": "0001679788",
    "NAVI": "0001593538",
}


class EdgarAdapter:
    """Adapter for SEC EDGAR corporate filings."""

    def __init__(self, client: Optional[ApiGatewayClient] = None):
        self.client = client or gateway_client

    def fetch_filings(
        self,
        ticker: str,
        target_forms: Optional[List[str]] = None,
        max_items: int = 10,
        force_refresh: bool = False,
    ) -> List[Item]:
        """Fetch recent submissions for a ticker from SEC EDGAR."""
        ticker_upper = ticker.upper()
        cik = TICKER_CIK_MAP.get(ticker_upper)
        if not cik:
            raise ValueError(f"No registered SEC CIK found for ticker '{ticker}'")

        if target_forms is None:
            target_forms = ["8-K", "10-Q", "10-K"]

        raw_resp: Dict[str, Any] = self.client.request(
            endpoint_name="edgar_submissions",
            path_params={"cik": cik},
            force_refresh=force_refresh,
        )

        recent = raw_resp.get("filings", {}).get("recent", {})
        accession_numbers = recent.get("accessionNumber", [])
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        acceptance_datetimes = recent.get("acceptanceDateTime", [])
        primary_docs = recent.get("primaryDocument", [])
        doc_descriptions = recent.get("primaryDocDescription", [])
        items_reported = recent.get("items", [])

        num_records = min(len(accession_numbers), len(forms))
        items: List[Item] = []

        cik_clean = cik.lstrip("0")

        for i in range(num_records):
            form = forms[i]
            if form not in target_forms:
                continue

            accession = accession_numbers[i]
            if self.client.mock_mode and cik != "0000072971":
                accession = accession.replace("0000072971", cik)
            accession_clean = accession.replace("-", "")
            filing_date = filing_dates[i] if i < len(filing_dates) else ""
            acc_time = acceptance_datetimes[i] if i < len(acceptance_datetimes) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            desc = doc_descriptions[i] if i < len(doc_descriptions) else ""
            item_tag = items_reported[i] if i < len(items_reported) else ""

            if acc_time:
                try:
                    published_at = dt_parser.parse(acc_time)
                    if published_at.tzinfo is None:
                        published_at = published_at.replace(tzinfo=timezone.utc)
                except Exception:
                    published_at = datetime.now(timezone.utc)
            elif filing_date:
                try:
                    published_at = dt_parser.parse(filing_date).replace(tzinfo=timezone.utc)
                except Exception:
                    published_at = datetime.now(timezone.utc)
            else:
                published_at = datetime.now(timezone.utc)

            content_raw = f"{accession}:{form}:{desc}:{item_tag}"
            content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()
            item_id = f"edgar_{accession_clean}"

            url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{accession_clean}/{primary_doc}"
                if primary_doc
                else f"https://www.sec.gov/edgar/browse/?CIK={cik}"
            )

            title = f"SEC Form {form} Submission ({ticker_upper})"
            if item_tag:
                title += f" - {item_tag}"

            body = (
                f"Filing Form: {form}\n"
                f"Description: {desc or 'Regulatory Corporate Disclosure'}\n"
                f"Filing Date: {filing_date}\n"
                f"Items: {item_tag}"
            )

            item = Item(
                id=item_id,
                company=ticker_upper,
                source=SourceType.EDGAR,
                source_url=url,
                title=title,
                text=body,
                published_at=published_at,
                is_simulated=False,
                content_hash=content_hash,
            )
            items.append(item)

            if len(items) >= max_items:
                break

        return items
