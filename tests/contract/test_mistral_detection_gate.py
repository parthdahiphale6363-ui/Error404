"""Contract tests for Mistral detection gate and strict JSON schema."""

from datetime import datetime, timezone
from backend.apigateway.client import ApiGatewayClient
from backend.apigateway.adapters.llm import LLMAdapter
from backend.schemas import DetectionResult, Item, RiskType, SourceType, TOPIC_TAXONOMY, REGULATORS


def test_mistral_strict_json_schema_contract():
    """Verify Mistral classification returns strict DetectionResult schema matching brain.md Section 12."""
    client = ApiGatewayClient(mock_mode=True)
    adapter = LLMAdapter(client=client)

    item = Item(
        id="test_mistral_01",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://news.example.com/wfc-cfpb-fine",
        title="CFPB orders Wells Fargo to pay $3.7B over illegal auto loan fees",
        text="The Consumer Financial Protection Bureau ordered Wells Fargo to pay a record penalty for illegal charges.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_mistral_01",
    )

    result = adapter.classify_with_mistral(item)
    assert isinstance(result, DetectionResult)
    assert result.company == "WFC"
    assert result.source_url == item.source_url
    assert result.severity in range(0, 6)
    assert result.severity >= 4  # Major regulatory enforcement
    assert result.risk_type in (RiskType.COMPLIANCE, RiskType.LEGAL)
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.reason) >= 5
    assert isinstance(result.topics, list)
    assert isinstance(result.regulators, list)
    assert any(t in TOPIC_TAXONOMY for t in result.topics)
    assert any(r in REGULATORS for r in result.regulators)


def test_mistral_noise_classification():
    """Verify routine corporate dividend/press release classifies as noise with severity 0."""
    client = ApiGatewayClient(mock_mode=True)
    adapter = LLMAdapter(client=client)

    noise_item = Item(
        id="test_mistral_noise",
        company="PYPL",
        source=SourceType.FINNHUB,
        source_url="https://news.example.com/pypl-earnings",
        title="PayPal reports quarterly dividend and investor relations conference schedule",
        text="PayPal executives will present at an upcoming financial technology investor conference.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_mistral_noise",
    )

    result = adapter.classify_with_mistral(noise_item)
    assert isinstance(result, DetectionResult)
    assert result.risk_type == RiskType.NOISE
    assert result.severity == 0
    assert result.confidence >= 0.8
