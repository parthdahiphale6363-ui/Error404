"""Phase 8 Time-Machine Replay Unit and Gate Tests.

Verifies:
1. 15-day reporting lag strictly enforced for CFPB items.
2. EDGAR / Finnhub have immediate visibility (0 lag).
3. Deterministic replay computation at historical points in time.
4. Lead time and false alarms verified on 3 past cases + 2 calm controls.
"""

import pytest
from datetime import datetime, timezone, timedelta

from backend.replay.engine import ReplayEngine
from backend.schemas import Item, SourceType


def test_cfpb_fifteen_day_lag_enforced():
    engine = ReplayEngine()
    received_date = datetime(2023, 5, 1, 12, 0, tzinfo=timezone.utc)
    cfpb_item = Item(
        id="cfpb_lag_test_01",
        company="WFC",
        source=SourceType.CFPB,
        source_url="https://cfpb.gov/test",
        title="Unauthorized fees",
        text="Complaint narrative about fees.",
        published_at=received_date,
        content_hash="content_hash_01",
    )

    # At day +10 (before 15 days lag), item MUST NOT be visible
    as_of_day_10 = received_date + timedelta(days=10)
    visible_day_10 = engine.filter_visible_items([cfpb_item], as_of_day_10)
    assert len(visible_day_10) == 0, "CFPB complaint was visible before statutory 15-day review lag!"

    # At day +15, item becomes visible
    as_of_day_15 = received_date + timedelta(days=15)
    visible_day_15 = engine.filter_visible_items([cfpb_item], as_of_day_15)
    assert len(visible_day_15) == 1


def test_edgar_and_finnhub_have_immediate_visibility():
    engine = ReplayEngine()
    pub_date = datetime(2023, 5, 1, 12, 0, tzinfo=timezone.utc)
    edgar_item = Item(
        id="edgar_immediate_01",
        company="WFC",
        source=SourceType.EDGAR,
        source_url="https://sec.gov/test",
        title="Form 8-K Disclosure",
        text="Material regulatory disclosure.",
        published_at=pub_date,
        content_hash="content_hash_02",
    )
    finnhub_item = Item(
        id="finnhub_immediate_01",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://finnhub.io/test",
        title="Breaking News",
        text="Regulatory inquiry reported.",
        published_at=pub_date,
        content_hash="content_hash_03",
    )

    # Immediately visible on pub_date
    visible = engine.filter_visible_items([edgar_item, finnhub_item], pub_date)
    assert len(visible) == 2


def test_three_historical_cases_lead_times_and_zero_false_alarms():
    engine = ReplayEngine()
    cases = ["wfc_2022_cfpb", "efx_2017_breach", "navi_2024_servicing"]

    for case_id in cases:
        case = engine.get_benchmark_case(case_id)
        assert case.case_id == case_id
        assert case.lead_time_days >= 14, f"Case {case_id} lead time {case.lead_time_days}d < 14d!"
        assert case.false_alarms == 0, f"Case {case_id} had false alarms!"
        assert len(case.timeline) >= 4

        # Check early signal transition
        early_signals = [pt.early_signal for pt in case.timeline]
        assert True in early_signals, f"Case {case_id} must have early signal detected!"


def test_two_calm_controls_zero_early_signals_and_zero_false_alarms():
    engine = ReplayEngine()
    controls = ["pypl_calm_control", "coin_calm_control"]

    for control_id in controls:
        case = engine.get_benchmark_case(control_id)
        assert case.lead_time_days == 0
        assert case.false_alarms == 0
        # Calm controls must have all indices well below threshold (e.g. < 35) and 0 early signals
        for pt in case.timeline:
            assert pt.index < 35.0, f"Control {control_id} index {pt.index} exceeded calm threshold!"
            assert pt.early_signal is False, f"Control {control_id} fired false alarm early signal!"


def test_replay_determinism():
    engine = ReplayEngine()
    case1 = engine.get_benchmark_case("wfc_2022_cfpb")
    case2 = engine.get_benchmark_case("wfc_2022_cfpb")

    assert case1.timeline[0].index == case2.timeline[0].index
    assert case1.timeline[-1].index == case2.timeline[-1].index
