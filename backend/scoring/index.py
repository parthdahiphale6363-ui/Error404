"""Corporate Risk Index scoring engine in pure Python.

Strict anti-hallucination guarantee: Pure Python mathematical calculation.
No network, no database, no LLM dependencies.
Formula:
    Index = 100 * (1 - exp(-S/10))
    S = sum(severity * type_weight * 0.5^(age_days/7)) + complaint_spike_bonus
    complaint_spike_bonus = clamp(z - 1, 0, 5)
    Weights: legal=1.0, compliance=0.9, operational=0.7, noise=0.0
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
import numpy as np

from backend.models.contracts import Flag, ItemContribution, RiskType, ScorePoint

TYPE_WEIGHTS: Dict[RiskType, float] = {
    RiskType.LEGAL: 1.0,
    RiskType.COMPLIANCE: 0.9,
    RiskType.OPERATIONAL: 0.7,
    RiskType.NOISE: 0.0,
}


def calculate_decay(age_days: float, half_life_days: float = 7.0) -> float:
    """Calculate exponential decay factor: 0.5^(age_days / 7)."""
    if age_days < 0:
        return 0.0
    return float(0.5 ** (age_days / half_life_days))


def calculate_z_score(
    recent_7d_count: float,
    baseline_90d_counts: Sequence[float],
) -> float:
    """Calculate z-score of 7-day count against 90-day baseline distribution.

    If baseline has flat variance (std dev == 0) or fewer than 2 data points, z is 0.0.
    """
    if not baseline_90d_counts or len(baseline_90d_counts) < 2:
        return 0.0

    mean_val = float(np.mean(baseline_90d_counts))
    std_val = float(np.std(baseline_90d_counts, ddof=1))

    if std_val <= 1e-9:
        return 0.0

    return float((recent_7d_count - mean_val) / std_val)


def calculate_complaint_spike_bonus(z_score: float) -> float:
    """Compute complaint spike bonus: clamp(z - 1, 0, 5)."""
    raw_bonus = z_score - 1.0
    return float(max(0.0, min(raw_bonus, 5.0)))


def calculate_risk_index(raw_s: float) -> float:
    """Calculate rolling Corporate Risk Index from raw S: Index = 100 * (1 - exp(-S/10))."""
    if raw_s <= 0.0:
        return 0.0
    index_val = 100.0 * (1.0 - math.exp(-raw_s / 10.0))
    return float(max(0.0, min(round(index_val, 4), 100.0)))


def score_company(
    company: str,
    as_of: datetime,
    flags: Sequence[Flag],
    recent_7d_complaints: float = 0.0,
    baseline_90d_complaints: Optional[Sequence[float]] = None,
    top_n: int = 10,
) -> ScorePoint:
    """Compute rolling Corporate Risk Index score point for a company as of a given timestamp.

    Pure-Python:
    - Filters flags occurring at or prior to `as_of`.
    - Computes item-level decayed contributions.
    - Applies category weights (noise has 0 weight).
    - Computes complaint spike bonus based on z-score against 90-day baseline.
    - Determines top contributing items for UI visualization.
    """
    contributions: List[ItemContribution] = []
    item_sum = 0.0
    has_simulated = False

    for flag in flags:
        if flag.company.upper() != company.upper():
            continue
        if flag.is_simulated:
            has_simulated = True

        time_delta = as_of - flag.date
        age_seconds = time_delta.total_seconds()
        if age_seconds < 0:
            # Future event relative to as_of; ignore in causal scoring
            continue

        age_days = age_seconds / 86400.0
        weight = TYPE_WEIGHTS.get(flag.risk_type, 0.0)
        review_factor = float(getattr(flag, "review_factor", 1.0))

        sev = int(getattr(flag, "final_severity", getattr(flag, "severity", 0)))

        if weight == 0.0 or sev == 0 or flag.risk_type == RiskType.NOISE or review_factor == 0.0:
            decayed = 0.0
        else:
            decay = calculate_decay(age_days=age_days, half_life_days=7.0)
            decayed = float(sev * weight * review_factor * decay)

        contribution = ItemContribution(
            item_id=flag.item_id,
            risk_type=flag.risk_type,
            severity=sev,
            review_factor=round(review_factor, 2),
            age_days=round(age_days, 4),
            weight=weight,
            decayed_score=round(decayed, 4),
        )
        contributions.append(contribution)
        item_sum += decayed

    # Z-score and complaint spike bonus
    z_score = 0.0
    spike_bonus = 0.0
    if baseline_90d_complaints:
        z_score = calculate_z_score(recent_7d_complaints, baseline_90d_complaints)
        spike_bonus = calculate_complaint_spike_bonus(z_score)

    raw_s = float(item_sum + spike_bonus)
    index_score = calculate_risk_index(raw_s)

    # Sort contributions by decayed_score descending
    contributions.sort(key=lambda c: c.decayed_score, reverse=True)
    top_items = contributions[:top_n]

    return ScorePoint(
        company=company.upper(),
        as_of=as_of,
        index_score=index_score,
        raw_s=round(raw_s, 4),
        z_score=round(z_score, 4),
        complaint_spike_bonus=round(spike_bonus, 4),
        top_contributing_items=top_items,
        is_simulated=has_simulated,
    )


def score(
    items: Sequence[Any],
    as_of: datetime,
    company: Optional[str] = None,
    recent_7d_complaints: float = 0.0,
    baseline_90d_complaints: Optional[Sequence[float]] = None,
    top_n: int = 10,
) -> ScorePoint:
    """Pure-function risk index score calculation matching brain.md Section 12."""
    target_comp = company
    if not target_comp and items:
        target_comp = getattr(items[0], "company", "WFC")
    elif not target_comp:
        target_comp = "WFC"

    return score_company(
        company=target_comp,
        as_of=as_of,
        flags=items,
        recent_7d_complaints=recent_7d_complaints,
        baseline_90d_complaints=baseline_90d_complaints,
        top_n=top_n,
    )
