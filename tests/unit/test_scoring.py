"""Unit tests for Pure Python Corporate Risk Index scoring engine."""

from datetime import datetime, timedelta, timezone
import math
import pytest

from backend.models.contracts import Flag, RiskType
from backend.scoring.index import (
    calculate_decay,
    calculate_z_score,
    calculate_complaint_spike_bonus,
    calculate_risk_index,
    score_company,
)


def test_decay_formula_invariants():
    """Verify exponential decay half-life at 7 days."""
    assert calculate_decay(0.0) == pytest.approx(1.0, rel=1e-5)
    assert calculate_decay(7.0) == pytest.approx(0.5, rel=1e-5)
    assert calculate_decay(14.0) == pytest.approx(0.25, rel=1e-5)
    assert calculate_decay(21.0) == pytest.approx(0.125, rel=1e-5)
    assert calculate_decay(-1.0) == 0.0


def test_z_score_and_spike_bonus():
    """Verify complaint spike bonus = clamp(z - 1, 0, 5)."""
    # Flat baseline -> 0.0
    flat_baseline = [10.0, 10.0, 10.0, 10.0]
    z_flat = calculate_z_score(15.0, flat_baseline)
    assert z_flat == 0.0
    assert calculate_complaint_spike_bonus(z_flat) == 0.0

    # Normal baseline: mean = 10, std = 2
    baseline = [8.0, 10.0, 12.0]
    # z = (10 - 10) / 2 = 0 -> bonus = clamp(0 - 1, 0, 5) = 0
    z_normal = calculate_z_score(10.0, baseline)
    assert z_normal == pytest.approx(0.0, abs=1e-3)
    assert calculate_complaint_spike_bonus(z_normal) == 0.0

    # z = 3 -> bonus = 2
    assert calculate_complaint_spike_bonus(3.0) == 2.0
    # z = 7 -> bonus = clamp(6, 0, 5) = 5.0
    assert calculate_complaint_spike_bonus(7.0) == 5.0
    # z = 0.5 -> bonus = clamp(-0.5, 0, 5) = 0.0
    assert calculate_complaint_spike_bonus(0.5) == 0.0


def test_index_bounds_and_monotonicity():
    """Verify Index = 100 * (1 - exp(-S/10)) stays strictly within [0, 100]."""
    assert calculate_risk_index(0.0) == 0.0
    assert calculate_risk_index(-5.0) == 0.0

    # At S = 10, 100 * (1 - e^-1) ≈ 63.212
    assert calculate_risk_index(10.0) == pytest.approx(63.2121, rel=1e-3)

    # High S approaches 100 but never exceeds 100
    assert calculate_risk_index(100.0) == pytest.approx(99.9955, rel=1e-3)
    assert calculate_risk_index(1000.0) <= 100.0


def test_noise_contributes_zero():
    """Verify noise category contributes zero to risk score."""
    now = datetime.now(timezone.utc)
    flags = [
        Flag(
            item_id="noise_01",
            company="WFC",
            source_url="https://example.com/pr",
            date=now,
            risk_type=RiskType.NOISE,
            severity=5,  # High severity labelled noise must contribute 0
            confidence=0.99,
            reason="Benign PR release.",
        )
    ]
    score = score_company("WFC", as_of=now, flags=flags)
    assert score.raw_s == 0.0
    assert score.index_score == 0.0


def test_scoring_stacking_and_decay():
    """Verify stacking of legal and compliance items with decay."""
    now = datetime.now(timezone.utc)
    # Event 1: Legal severity 5, age 0 days -> 5 * 1.0 * 1.0 = 5.0
    flag1 = Flag(
        item_id="item_legal",
        company="WFC",
        source_url="https://example.com/legal",
        date=now,
        risk_type=RiskType.LEGAL,
        severity=5,
        confidence=0.95,
        reason="Major enforcement fine.",
    )
    # Event 2: Compliance severity 4, age 7 days -> 4 * 0.9 * 0.5 = 1.8
    flag2 = Flag(
        item_id="item_compliance",
        company="WFC",
        source_url="https://example.com/comp",
        date=now - timedelta(days=7),
        risk_type=RiskType.COMPLIANCE,
        severity=4,
        confidence=0.90,
        reason="Formal investigation probe.",
    )
    flags = [flag1, flag2]

    score = score_company("WFC", as_of=now, flags=flags)
    expected_s = 5.0 + 1.8  # 6.8
    assert score.raw_s == pytest.approx(expected_s, rel=1e-3)
    expected_index = 100.0 * (1.0 - math.exp(-6.8 / 10.0))
    assert score.index_score == pytest.approx(expected_index, rel=1e-3)

    # Check top contributing items
    assert len(score.top_contributing_items) == 2
    assert score.top_contributing_items[0].item_id == "item_legal"
    assert score.top_contributing_items[0].decayed_score == pytest.approx(5.0, rel=1e-3)
    assert score.top_contributing_items[1].item_id == "item_compliance"
    assert score.top_contributing_items[1].decayed_score == pytest.approx(1.8, rel=1e-3)


def test_scoring_determinism():
    """Verify pure Python scoring gives identical output for identical inputs."""
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    flag = Flag(
        item_id="item_op",
        company="PYPL",
        source_url="https://example.com/outage",
        date=now - timedelta(days=2),
        risk_type=RiskType.OPERATIONAL,
        severity=4,
        confidence=0.92,
        reason="Core checkout outage.",
    )
    baseline = [12.0, 15.0, 18.0, 14.0, 16.0]

    score1 = score_company("PYPL", as_of=now, flags=[flag], recent_7d_complaints=25.0, baseline_90d_complaints=baseline)
    score2 = score_company("PYPL", as_of=now, flags=[flag], recent_7d_complaints=25.0, baseline_90d_complaints=baseline)

    assert score1.index_score == score2.index_score
    assert score1.raw_s == score2.raw_s
    assert score1.z_score == score2.z_score
    assert score1.complaint_spike_bonus == score2.complaint_spike_bonus
    assert len(score1.top_contributing_items) == len(score2.top_contributing_items)
