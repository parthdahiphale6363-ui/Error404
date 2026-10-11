"""Contract test for CFPB consumer complaints adapter vs saved fixture."""

from backend.apigateway.adapters.cfpb import CFPBAdapter
from backend.apigateway.client import ApiGatewayClient
from backend.models.contracts import SourceType


def test_cfpb_adapter_contract():
    client = ApiGatewayClient(mock_mode=True)
    adapter = CFPBAdapter(client=client)

    items = adapter.fetch_complaints(
        company_name="WELLS FARGO & COMPANY",
        ticker="WFC",
        has_narrative=True,
    )

    assert len(items) == 2
    wfc_complaint = items[0]

    assert wfc_complaint.company == "WFC"
    assert wfc_complaint.source == SourceType.CFPB
    assert "Checking or savings account" in wfc_complaint.title
    assert "froze my primary checking account" in wfc_complaint.text
    assert wfc_complaint.source_url.startswith("https://www.consumerfinance.gov/")
    assert wfc_complaint.id == "cfpb_8901234"
