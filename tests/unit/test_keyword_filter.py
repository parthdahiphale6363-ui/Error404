"""Unit tests for keyword pre-filtering engine."""

from datetime import datetime, timezone
from backend.detect.filter import KeywordFilter
from backend.schemas import Item, RiskType, SourceType


def test_keyword_filter_identifies_legal_signals():
    kf = KeywordFilter()
    item = Item(
        id="item_legal_1",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://news.example.com/wfc-lawsuit",
        title="Class action lawsuit filed against Wells Fargo over mortgage fees",
        text="Plaintiffs allege unlawful fee overcharges in federal district court.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_legal_1",
    )
    should_run, matched_keywords = kf.evaluate(item)
    assert should_run is True
    assert any(k in ["lawsuit", "class action", "court", "unlawful"] for k in matched_keywords)


def test_keyword_filter_identifies_compliance_signals():
    kf = KeywordFilter()
    item = Item(
        id="item_comp_1",
        company="COIN",
        source=SourceType.FINNHUB,
        source_url="https://news.example.com/coin-probe",
        title="SEC issues formal subpoena to Coinbase regarding staking program",
        text="The regulatory agency commenced an enforcement probe regarding securities laws.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_comp_1",
    )
    should_run, matched_keywords = kf.evaluate(item)
    assert should_run is True
    assert any(k in ["sec", "subpoena", "enforcement", "probe"] for k in matched_keywords)


def test_keyword_filter_identifies_operational_signals():
    kf = KeywordFilter()
    item = Item(
        id="item_op_1",
        company="PYPL",
        source=SourceType.FINNHUB,
        source_url="https://news.example.com/pypl-outage",
        title="PayPal suffers major service disruption and customer transaction outage",
        text="Global users reported inability to process checkout payments and access balances.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_op_1",
    )
    should_run, matched_keywords = kf.evaluate(item)
    assert should_run is True
    assert any(k in ["outage", "disruption"] for k in matched_keywords)


def test_keyword_filter_flags_regulatory_sources_always():
    kf = KeywordFilter()
    # CFPB complaint with generic text must always be evaluated
    cfpb_item = Item(
        id="item_cfpb_1",
        company="EFX",
        source=SourceType.CFPB,
        source_url="https://cfpb.gov/complaints/1",
        title="Consumer credit reporting dispute",
        text="Incorrect balance listed on report.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_cfpb_1",
    )
    should_run, _ = kf.evaluate(cfpb_item)
    assert should_run is True


def test_keyword_filter_skips_benign_noise():
    kf = KeywordFilter()
    noise_item = Item(
        id="item_noise_1",
        company="WFC",
        source=SourceType.FINNHUB,
        source_url="https://news.example.com/wfc-dividend",
        title="Wells Fargo declares regular quarterly common stock dividend of $0.35",
        text="The board of directors approved the standard dividend payable to shareholders of record.",
        published_at=datetime.now(timezone.utc),
        is_simulated=False,
        content_hash="hash_noise_1",
    )
    should_run, matched_keywords = kf.evaluate(noise_item)
    assert should_run is False
    assert len(matched_keywords) == 0
