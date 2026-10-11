"""Contract test for SEC EDGAR submissions adapter vs saved fixture."""

from backend.apigateway.adapters.edgar import EdgarAdapter, TICKER_CIK_MAP
from backend.apigateway.client import ApiGatewayClient
from backend.models.contracts import SourceType


def test_edgar_adapter_contract():
    client = ApiGatewayClient(mock_mode=True)
    adapter = EdgarAdapter(client=client)

    items = adapter.fetch_filings("WFC", target_forms=["8-K", "10-K"])

    assert len(items) == 2
    filing_8k = items[0]

    assert filing_8k.company == "WFC"
    assert filing_8k.source == SourceType.EDGAR
    assert "8-K" in filing_8k.title
    assert "Item 8.01 Other Events" in filing_8k.text
    assert "sec.gov/Archives/edgar/data/72971" in filing_8k.source_url
    assert filing_8k.id == "edgar_000007297126000010"
