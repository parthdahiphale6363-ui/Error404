"""Unit tests covering Dual-LLM Consensus Rules and Blind Verifier Isolation."""

import inspect
from datetime import datetime, timezone
import pytest

from backend.schemas import (
    AnalystVerdict,
    ConsensusFlag,
    ConsensusStatus,
    DetectionResult,
    Item,
    RiskType,
    SourceType,
    VerificationResult,
)
from backend.verify.consensus import evaluate_consensus, apply_analyst_verdict
from backend.verify.verifier import BlindVerifier


def _sample_item(item_id: str = "item_test_01") -> Item:
    return Item(
        id=item_id,
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://example.com/cfpb-fine",
        title="CFPB Orders Wells Fargo to Pay Record Civil Money Penalty",
        text="The Consumer Financial Protection Bureau ordered Wells Fargo to pay fines for consumer loan abuses.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_consensus_01",
    )


def test_verifier_never_receives_primary_output():
    """Verify that BlindVerifier contract accepts ONLY the raw Item and NEVER receives primary DetectionResult."""
    sig = inspect.signature(BlindVerifier.verify)
    param_names = list(sig.parameters.keys())

    # First param is self, second param must be item
    assert "item" in param_names
    # Primary output, detection result, or mistral flag must NOT be parameters
    forbidden_terms = ["primary", "detection", "mistral", "flag", "primary_result", "first_opinion"]
    for term in forbidden_terms:
        assert term not in param_names, f"Blind verifier interface exposes primary output parameter: '{term}'"

    # Also verify runtime call passes only item
    captured_args = {}

    class MockVerifierClient:
        mock_mode = False
        def request(self, *args, **kwargs):
            captured_args.update(kwargs)
            return {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": '{"risk_type": "compliance", "severity": 4, "confidence": 0.9, "reason": "Severe regulatory fine identified."}'
                        }]
                    }
                }]
            }

    verifier = BlindVerifier(client=MockVerifierClient())
    item = _sample_item()
    result = verifier.verify(item)

    assert isinstance(result, VerificationResult)
    # The prompt sent over wire must contain item title and text, but ZERO primary scores or reasoning
    req_body_str = str(captured_args)
    assert item.title in req_body_str
    assert "primary_severity" not in req_body_str
    assert "DetectionResult" not in req_body_str


def test_consensus_rule_agree():
    """Agree: verifier also severity >= 3 and same risk_type -> status 'agreed', final_severity = min, review_factor = 1.0."""
    item = _sample_item()
    primary = DetectionResult(
        company="WFC",
        source_url=item.source_url,
        date=item.published_at,
        risk_type=RiskType.COMPLIANCE,
        severity=5,
        confidence=0.95,
        topics=["enforcement action"],
        regulators=["CFPB"],
        reason="Primary detected severe CFPB enforcement penalty.",
    )
    verifier_result = VerificationResult(
        provider="gemini",
        risk_type=RiskType.COMPLIANCE,
        severity=4,
        confidence=0.90,
        reason="Second opinion confirms compliance violation and enforcement action.",
    )

    flag = evaluate_consensus(item, primary, verifier_result)
    assert flag.status == ConsensusStatus.AGREED
    assert flag.final_severity == 4  # min(5, 4)
    assert flag.primary_severity == 5
    assert flag.review_factor == 1.0
    assert flag.verifier_provider == "gemini"
    assert flag.verifier_severity == 4


def test_consensus_rule_disagree_risk_type():
    """Disagree on risk type -> status 'needs_review', final_severity = Mistral's, review_factor = 0.5."""
    item = _sample_item()
    primary = DetectionResult(
        company="WFC",
        source_url=item.source_url,
        date=item.published_at,
        risk_type=RiskType.LEGAL,
        severity=4,
        confidence=0.90,
        topics=["litigation or class action"],
        regulators=["SEC"],
        reason="Primary classified as legal litigation risk.",
    )
    verifier_result = VerificationResult(
        provider="groq",
        risk_type=RiskType.OPERATIONAL,
        severity=4,
        confidence=0.88,
        reason="Verifier classified as operational system risk.",
    )

    flag = evaluate_consensus(item, primary, verifier_result)
    assert flag.status == ConsensusStatus.NEEDS_REVIEW
    assert flag.final_severity == 4  # Mistral's
    assert flag.review_factor == 0.5
    assert flag.verifier_risk_type == RiskType.OPERATIONAL


def test_consensus_rule_disagree_severity():
    """Disagree on severity (verifier < 3) -> status 'needs_review', final_severity = Mistral's, review_factor = 0.5."""
    item = _sample_item()
    primary = DetectionResult(
        company="WFC",
        source_url=item.source_url,
        date=item.published_at,
        risk_type=RiskType.COMPLIANCE,
        severity=4,
        confidence=0.85,
        topics=["enforcement action"],
        regulators=["CFPB"],
        reason="Primary sees credible compliance violation.",
    )
    verifier_result = VerificationResult(
        provider="gemini",
        risk_type=RiskType.COMPLIANCE,
        severity=2,  # severity < 3
        confidence=0.70,
        reason="Verifier considers this a minor non-critical complaint.",
    )

    flag = evaluate_consensus(item, primary, verifier_result)
    assert flag.status == ConsensusStatus.NEEDS_REVIEW
    assert flag.final_severity == 4
    assert flag.review_factor == 0.5


def test_consensus_rule_verifier_unavailable():
    """Verifier unavailable -> status 'needs_review', final_severity = Mistral's, review_factor = 0.5."""
    item = _sample_item()
    primary = DetectionResult(
        company="WFC",
        source_url=item.source_url,
        date=item.published_at,
        risk_type=RiskType.LEGAL,
        severity=4,
        confidence=0.92,
        topics=["litigation or class action"],
        regulators=["DOJ"],
        reason="Primary classified subpoena risk.",
    )

    flag = evaluate_consensus(item, primary, verifier_result=None)
    assert flag.status == ConsensusStatus.NEEDS_REVIEW
    assert flag.final_severity == 4
    assert flag.review_factor == 0.5
    assert flag.verifier_provider is None


def test_consensus_rule_unflagged():
    """Primary severity < 3 is not verified: status 'unflagged', review_factor = 1.0."""
    item = _sample_item()
    primary = DetectionResult(
        company="WFC",
        source_url=item.source_url,
        date=item.published_at,
        risk_type=RiskType.NOISE,
        severity=1,
        confidence=0.80,
        topics=["other"],
        regulators=[],
        reason="Primary identified minor noise signal.",
    )

    flag = evaluate_consensus(item, primary, verifier_result=None)
    assert flag.status == ConsensusStatus.UNFLAGGED
    assert flag.review_factor == 1.0
    assert flag.final_severity == 1


def test_consensus_analyst_confirm_and_dismiss():
    """Analyst confirm: status 'confirmed', review_factor = 1.0. Analyst dismiss: status 'dismissed', review_factor = 0.0."""
    item = _sample_item()
    primary = DetectionResult(
        company="WFC",
        source_url=item.source_url,
        date=item.published_at,
        risk_type=RiskType.COMPLIANCE,
        severity=4,
        confidence=0.85,
        topics=["enforcement action"],
        regulators=["CFPB"],
        reason="Unresolved dispute.",
    )
    # Start in needs_review
    initial_flag = evaluate_consensus(item, primary, verifier_result=None)
    assert initial_flag.status == ConsensusStatus.NEEDS_REVIEW
    assert initial_flag.review_factor == 0.5

    # Confirm
    confirmed = apply_analyst_verdict(initial_flag, AnalystVerdict.CONFIRM)
    assert confirmed.status == ConsensusStatus.CONFIRMED
    assert confirmed.review_factor == 1.0
    assert confirmed.analyst_verdict == AnalystVerdict.CONFIRM

    # Dismiss
    dismissed = apply_analyst_verdict(initial_flag, AnalystVerdict.DISMISS)
    assert dismissed.status == ConsensusStatus.DISMISSED
    assert dismissed.review_factor == 0.0
    assert dismissed.analyst_verdict == AnalystVerdict.DISMISS
