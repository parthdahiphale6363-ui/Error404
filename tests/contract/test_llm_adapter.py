"""Contract test for LLM adapter vs saved fixtures and schema guarantees."""

from datetime import datetime, timezone
from backend.apigateway.adapters.llm import LLMAdapter
from backend.apigateway.client import ApiGatewayClient
from backend.models.contracts import Item, RiskType, SourceType


def test_llm_dynamic_model_listing():
    client = ApiGatewayClient(mock_mode=True)
    adapter = LLMAdapter(client=client)

    gemini_models = adapter.list_gemini_models()
    assert "gemini-2.5-flash" in gemini_models
    assert "gemini-2.5-pro" in gemini_models

    groq_models = adapter.list_groq_models()
    assert "llama-3.3-70b-versatile" in groq_models
    assert "llama-3.1-8b-instant" in groq_models


def test_llm_classification_contract():
    client = ApiGatewayClient(mock_mode=True)
    adapter = LLMAdapter(client=client)

    # Item with enforcement fine text
    fine_item = Item(
        id="item_wfc_01",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://example.com/wfc-fine",
        title="Regulator levies $3.7B fine on Wells Fargo",
        text="The CFPB ordered Wells Fargo to pay billions for illegal fees and consumer redress.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="abc1234567890",
    )

    flag = adapter.classify_item(fine_item)

    assert flag.company == "WFC"
    assert flag.severity == 5
    assert flag.risk_type in (RiskType.LEGAL, RiskType.COMPLIANCE)
    assert 0.0 <= flag.confidence <= 1.0
    assert flag.reason
    assert not flag.is_simulated
