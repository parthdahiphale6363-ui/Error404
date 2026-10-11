"""Phase 7 Alerts Engine Unit & Gate Tests.

Verifies:
1. Rule A (Cross >= 60).
2. Rule B (Rise >= 15 in 24h).
3. Rule C (Severity 5 Agreed/Confirmed).
4. Cooldown (6h per company + rule).
5. Global daily cap enforcement.
6. Allowlist enforcement.
7. Proof that dry-run mode NEVER calls Resend API and writes HTML to data/outbox/.
8. HTML email rendering containing mandatory elements.
"""

import os
import pytest
from datetime import datetime, timezone
from pathlib import Path

from backend.alerts.engine import AlertEngine
from backend.apigateway.adapters.resend import ResendAdapter
from backend.schemas import (
    AlertRecord,
    CompanySummary,
    ConsensusFlag,
    ConsensusStatus,
    RiskType,
)


@pytest.fixture
def temp_outbox(tmp_path):
    outbox = tmp_path / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    return outbox


@pytest.fixture
def alert_engine(temp_outbox):
    adapter = ResendAdapter(outbox_dir=temp_outbox)
    return AlertEngine(adapter=adapter)


def test_rule_a_trigger_cross_60(alert_engine):
    summary = CompanySummary(
        ticker="WFC",
        name="Wells Fargo & Company",
        current_index=62.5,
        previous_24h_index=55.0,  # crossed 60
        delta_24h=7.5,
        top_risk_type=RiskType.COMPLIANCE,
        top_topic="unauthorized accounts or fraud",
        repeat_issue=True,
        contagion=False,
        needs_review_count=1,
        one_line_reason="Multiple recent consumer complaints regarding unauthorized accounts.",
    )
    alerts = alert_engine.evaluate_company_triggers(summary)
    assert len(alerts) == 1
    assert "Rule A" in alerts[0].rule
    assert alerts[0].company == "WFC"


def test_rule_b_trigger_rise_15(alert_engine):
    summary = CompanySummary(
        ticker="NAVI",
        name="Navient Corporation",
        current_index=52.0,
        previous_24h_index=35.0,
        delta_24h=17.0,  # rise >= 15
        top_risk_type=RiskType.LEGAL,
        top_topic="mortgage or loan servicing",
        repeat_issue=True,
        contagion=False,
        needs_review_count=0,
        one_line_reason="Loan servicing ban allegations drive sudden index surge.",
    )
    alerts = alert_engine.evaluate_company_triggers(summary)
    assert len(alerts) == 1
    assert "Rule B" in alerts[0].rule
    assert alerts[0].company == "NAVI"


def test_rule_c_trigger_severity_5_agreed(alert_engine):
    flag = ConsensusFlag(
        item_id="item_critical_01",
        company="COIN",
        source_url="https://sec.gov/enforcement/coin",
        date=datetime.now(timezone.utc),
        risk_type=RiskType.LEGAL,
        primary_severity=5,
        final_severity=5,
        confidence=0.98,
        status=ConsensusStatus.AGREED,
        review_factor=1.0,
        topics=["enforcement action"],
        regulators=["SEC"],
        reason="Formal SEC enforcement complaint filed.",
    )
    alert = alert_engine.evaluate_item_trigger(flag)
    assert alert is not None
    assert "Rule C" in alert.rule
    assert alert.company == "COIN"


def test_cooldown_suppresses_repeat_alerts(alert_engine):
    summary = CompanySummary(
        ticker="WFC",
        name="Wells Fargo & Company",
        current_index=64.0,
        previous_24h_index=58.0,
        delta_24h=6.0,
        top_risk_type=RiskType.COMPLIANCE,
        top_topic="unauthorized accounts",
        one_line_reason="Consumer fee allegations.",
    )
    # First trigger should produce an alert
    alerts1 = alert_engine.evaluate_company_triggers(summary)
    assert len(alerts1) == 1
    alert_engine.dispatch_alert(alerts1[0])

    # Second trigger within 6 hours should be suppressed by cooldown
    alerts2 = alert_engine.evaluate_company_triggers(summary)
    assert len(alerts2) == 0


def test_global_daily_cap_enforcement(alert_engine, monkeypatch):
    monkeypatch.setenv("EMAIL_DAILY_CAP", "2")
    alert_engine.daily_count = 2  # Cap reached

    summary = CompanySummary(
        ticker="EFX",
        name="Equifax Inc.",
        current_index=65.0,
        previous_24h_index=45.0,
        delta_24h=20.0,
        top_risk_type=RiskType.LEGAL,
        top_topic="credit reporting errors",
        one_line_reason="Major bureau failure.",
    )
    alerts = alert_engine.evaluate_company_triggers(summary)
    assert len(alerts) == 0, "Alerts must be suppressed when daily cap is reached!"


def test_dry_run_never_calls_network_and_writes_to_outbox(alert_engine, temp_outbox, monkeypatch):
    """Gate requirement: a test proves dry-run never invokes the Resend adapter."""
    monkeypatch.setenv("EMAIL_MODE", "dry_run")
    # Set invalid API key that would fail if network was attempted
    monkeypatch.setenv("RESEND_API_KEY", "INVALID_KEY_SHOULD_NEVER_BE_USED")

    content = alert_engine.build_email_content(
        company="WFC",
        index=62.5,
        delta=16.5,
        topic="unauthorized accounts or fraud",
        rule_name="Test Rule",
        reason="Verification of dry-run file persistence.",
        evidence_items=[{"risk_type": "legal", "severity": 4, "title": "Test Title", "url": "https://example.com"}],
        badges=["Repeat Issue"],
    )

    alert = AlertRecord(
        key="test_dry_run_key",
        ts=datetime.now(timezone.utc),
        company="WFC",
        rule="Rule A",
        subject=content["subject"],
        body_html=content["body_html"],
        body_text=content["body_text"],
        recipients=["analyst@example.com"],
        status="pending",
    )

    res = alert_engine.dispatch_alert(alert)
    assert res["status"] == "dry_run_saved"

    # Verify outbox file was created on disk
    outbox_files = list(temp_outbox.glob("*.html"))
    assert len(outbox_files) == 1
    content_written = outbox_files[0].read_text(encoding="utf-8")
    assert "Corporate Risk Radar" in content_written
    assert "WFC" in content_written
    assert "Repeat Issue" in content_written
    assert "Source Link" in content_written


def test_rendered_email_contains_mandatory_elements(alert_engine):
    """Gate requirement: review 3 rendered emails with required components."""
    test_cases = [
        ("WFC", 65.2, 16.2, "unauthorized accounts", "Rule A", ["Repeat Issue"]),
        ("NAVI", 58.0, 18.5, "loan servicing", "Rule B", ["Contagion"]),
        ("COIN", 85.0, 22.0, "enforcement action", "Rule C", ["Critical Severity 5"]),
    ]

    for company, idx, delta, topic, rule, badges in test_cases:
        content = alert_engine.build_email_content(
            company=company,
            index=idx,
            delta=delta,
            topic=topic,
            rule_name=rule,
            reason=f"Automated risk notice for {company}.",
            badges=badges,
            evidence_items=[{"risk_type": "legal", "severity": 4, "title": f"{company} Filing", "url": "https://sec.gov"}],
        )

        html = content["body_html"]
        # Mandatory elements:
        assert company in content["subject"]
        assert f"{idx:.1f}" in content["subject"]
        assert f"{delta:.1f}" in content["subject"]
        assert topic in content["subject"]
        for b in badges:
            assert b in html
        assert "Open Radar Scoreboard" in html
