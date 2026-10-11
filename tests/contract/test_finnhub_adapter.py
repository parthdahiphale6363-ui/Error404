"""Contract test for Finnhub adapter vs saved fixture."""

from backend.apigateway.adapters.finnhub import FinnhubAdapter
from backend.apigateway.client import ApiGatewayClient
from backend.models.contracts import SourceType


def test_finnhub_adapter_contract():
    client = ApiGatewayClient(mock_mode=True)
    adapter = FinnhubAdapter(client=client)

    items = adapter.fetch_company_news("WFC", "2026-03-01", "2026-03-15")

    assert len(items) == 2
    first_item = items[0]

    assert first_item.company == "WFC"
    assert first_item.source == SourceType.FINNHUB
    assert "CFPB Orders Wells Fargo" in first_item.title
    assert "billions" in first_item.text.lower()
    assert first_item.source_url.startswith("https://")
    assert first_item.content_hash
    assert not first_item.is_simulated
