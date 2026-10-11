"""Unit tests for Pydantic data contracts."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from backend.models.contracts import (
    Explanation,
    Flag,
    Item,
    ItemContribution,
    RiskType,
    ScorePoint,
    SourceType,
)


def test_item_valid():
    item = Item(
        id="item_001",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://example.com/news/1",
        title="Regulator investigates mortgage fees",
        text="Investigation opened into illegal overdraft and fee practices.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert item.company == "WFC"
    assert item.source == SourceType.FINNHUB
    assert not item.is_simulated


def test_flag_severity_bounds():
    now = datetime.now(timezone.utc)
    # Valid severity 0 to 5
    for sev in range(6):
        flag = Flag(
            item_id="item_001",
            company="WFC",
            source_url="https://example.com",
            date=now,
            risk_type=RiskType.LEGAL,
            severity=sev,
            confidence=0.85,
            reason="Valid rubric rating.",
        )
        assert flag.severity == sev

    # Out of bounds severity 6
    with pytest.raises(ValidationError):
        Flag(
            item_id="item_001",
            company="WFC",
            source_url="https://example.com",
            date=now,
            risk_type=RiskType.LEGAL,
            severity=6,
            confidence=0.85,
            reason="Invalid severity rating.",
        )

    # Out of bounds severity -1
    with pytest.raises(ValidationError):
        Flag(
            item_id="item_001",
            company="WFC",
            source_url="https://example.com",
            date=now,
            risk_type=RiskType.LEGAL,
            severity=-1,
            confidence=0.85,
            reason="Invalid negative severity.",
        )


def test_flag_confidence_bounds():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Flag(
            item_id="item_001",
            company="WFC",
            source_url="https://example.com",
            date=now,
            risk_type=RiskType.COMPLIANCE,
            severity=4,
            confidence=1.5,
            reason="Confidence cannot exceed 1.0",
        )


def test_score_point_bounds():
    now = datetime.now(timezone.utc)
    sp = ScorePoint(
        company="EFX",
        as_of=now,
        index_score=45.2,
        raw_s=6.1,
        z_score=1.5,
        complaint_spike_bonus=0.5,
        top_contributing_items=[],
    )
    assert 0.0 <= sp.index_score <= 100.0
    assert sp.complaint_spike_bonus == 0.5

    # Out of bounds index score
    with pytest.raises(ValidationError):
        ScorePoint(
            company="EFX",
            as_of=now,
            index_score=105.0,
            raw_s=15.0,
            z_score=0.0,
            complaint_spike_bonus=0.0,
        )


def test_explanation_requires_cited_source_ids():
    now = datetime.now(timezone.utc)
    # Valid explanation
    exp = Explanation(
        company="COIN",
        as_of=now,
        summary="Risk increased due to class action filing regarding transaction disclosure.",
        cited_source_ids=["cfpb_8901234"],
    )
    assert len(exp.cited_source_ids) == 1

    # Empty cited source ids must fail anti-hallucination guard
    with pytest.raises(ValidationError):
        Explanation(
            company="COIN",
            as_of=now,
            summary="Risk increased without any cited evidence in database.",
            cited_source_ids=[],
        )
