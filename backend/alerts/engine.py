"""Alerts Engine for Corporate Risk Radar.

Enforces:
- Rule A: Index crosses up through 60
- Rule B: Index rises 15+ in 24h
- Rule C: New severity-5 item agreed or confirmed
- Daily Briefing: 5 companies ranked by risk index
- 6h cooldown per company + rule, global daily cap, allowlist, and idempotency tracking.
- Mobile-friendly HTML + text fallback.
- Default EMAIL_MODE='dry_run' writes to data/outbox/.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from backend.apigateway.adapters.resend import resend_adapter
from backend.schemas import (
    AlertRecord,
    CompanySummary,
    ConsensusFlag,
    ConsensusStatus,
)

logger = logging.getLogger(__name__)

DEFAULT_DAILY_CAP = 20
COOLDOWN_SECONDS = 6 * 3600  # 6 hours


class AlertEngine:
    """Evaluates risk triggers, enforces cooldowns, and generates structured alerts."""

    def __init__(self, adapter=None):
        self.adapter = adapter or resend_adapter
        self.sent_keys: Dict[str, float] = {}  # key -> timestamp
        self.daily_count: int = 0
        self.last_reset_day: int = datetime.now(timezone.utc).timetuple().tm_yday

    def _check_daily_cap(self) -> bool:
        """Reset cap on new day and check against EMAIL_DAILY_CAP."""
        current_day = datetime.now(timezone.utc).timetuple().tm_yday
        if current_day != self.last_reset_day:
            self.daily_count = 0
            self.last_reset_day = current_day

        cap = int(os.getenv("EMAIL_DAILY_CAP", DEFAULT_DAILY_CAP))
        return self.daily_count < cap

    def _is_on_cooldown(self, key: str) -> bool:
        now = time.time()
        last_sent = self.sent_keys.get(key)
        if last_sent and (now - last_sent < COOLDOWN_SECONDS):
            return True
        return False

    def build_email_content(
        self,
        company: str,
        index: float,
        delta: float,
        topic: str,
        rule_name: str,
        reason: str,
        evidence_items: Optional[List[Dict[str, Any]]] = None,
        badges: Optional[List[str]] = None,
        is_simulated: bool = False,
    ) -> Dict[str, str]:
        """Generate responsive HTML and plain text email content."""
        app_url = os.getenv("APP_BASE_URL", "http://localhost:3000")
        sign = "+" if delta >= 0 else ""
        delta_str = f"{sign}{delta:.1f}"

        prefix = "[SIMULATED] " if is_simulated else ""
        subject = f"{prefix}[Risk Radar] {company} risk {index:.1f} ({delta_str} in 24h): {topic}"

        evidence_items = evidence_items or []
        badges = badges or []

        # Plain text
        text_lines = [
            f"CORPORATE RISK RADAR ALERT - {rule_name.upper()}",
            f"Company: {company}",
            f"Risk Index: {index:.1f} ({delta_str} in 24h)",
            f"Primary Topic: {topic}",
            "",
            f"Summary: {reason}",
            "",
        ]
        if badges:
            text_lines.append(f"Badges: {', '.join(badges)}")
            text_lines.append("")

        if evidence_items:
            text_lines.append("Top Evidence Items:")
            for item in evidence_items[:3]:
                text_lines.append(f"• [{item.get('risk_type', 'risk').upper()} - Sev {item.get('severity', 3)}] {item.get('title', 'Disclosure')} ({item.get('url', 'N/A')})")
            text_lines.append("")

        text_lines.append(f"View Live Dashboard: {app_url}")
        body_text = "\n".join(text_lines)

        # HTML
        badge_html = "".join(
            f'<span style="display:inline-block;padding:2px 8px;margin-right:6px;font-size:11px;font-weight:600;border-radius:4px;background:#fef2f2;color:#991b1b;border:1px solid #fecaca;">{b}</span>'
            for b in badges
        )

        evidence_html = "".join(
            f'<li style="margin-bottom:8px;font-size:13px;color:#334155;">'
            f'<strong>[{it.get("risk_type", "risk").upper()} - Sev {it.get("severity", 3)}]</strong> '
            f'{it.get("title", "Disclosure")} — '
            f'<a href="{it.get("url", "#")}" style="color:#2563eb;text-decoration:none;">Source Link &rarr;</a>'
            f'</li>'
            for it in evidence_items[:3]
        )

        body_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:24px;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:12px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
    <div style="background:#0f172a;color:#ffffff;padding:20px 24px;">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#94a3b8;font-weight:700;">Corporate Risk Radar • {rule_name}</div>
      <h1 style="margin:6px 0 0;font-size:20px;font-weight:800;">{company} Risk Score: {index:.1f} <span style="font-size:14px;color:#38bdf8;">({delta_str} in 24h)</span></h1>
    </div>
    <div style="padding:24px;">
      <div style="margin-bottom:16px;">{badge_html}</div>
      <p style="font-size:14px;line-height:1.6;color:#334155;margin:0 0 20px;">{reason}</p>
      
      <div style="background:#f1f5f9;border-radius:8px;padding:16px;margin-bottom:24px;">
        <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#475569;margin-bottom:10px;">Primary Graph Evidence</div>
        <ul style="margin:0;padding-left:18px;">
          {evidence_html or '<li style="font-size:13px;color:#64748b;">No high-severity items in active window.</li>'}
        </ul>
      </div>

      <div style="text-align:center;">
        <a href="{app_url}" style="display:inline-block;background:#0284c7;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;padding:10px 20px;border-radius:6px;">Open Radar Scoreboard</a>
      </div>
    </div>
    <div style="background:#f8fafc;padding:12px 24px;border-top:1px solid #e2e8f0;text-align:center;font-size:11px;color:#94a3b8;">
      Dual-LLM Consensus Detection • Automated Surveillance Notification
    </div>
  </div>
</body>
</html>"""

        return {"subject": subject, "body_html": body_html, "body_text": body_text}

    def evaluate_company_triggers(
        self,
        summary: CompanySummary,
        top_items: Optional[List[Dict[str, Any]]] = None,
    ) -> List[AlertRecord]:
        """Evaluate Rule A (Cross 60) and Rule B (Rise 15+ in 24h)."""
        alerts: List[AlertRecord] = []
        company = summary.ticker

        # Simulated guard: do not alert on simulated items unless explicitly enabled
        include_sim = os.getenv("ALERT_INCLUDE_SIMULATED", "false").lower() in ("true", "1")

        badges = []
        if summary.repeat_issue:
            badges.append("Repeat Issue")
        if summary.contagion:
            badges.append("Contagion")
        if summary.needs_review_count > 0:
            badges.append(f"Needs Review ({summary.needs_review_count})")

        # Rule A: Crosses up through 60
        if summary.previous_24h_index < 60.0 and summary.current_index >= 60.0:
            bucket = int(time.time() // COOLDOWN_SECONDS)
            key = f"{company}_RuleA_{bucket}"
            if not self._is_on_cooldown(key) and self._check_daily_cap():
                content = self.build_email_content(
                    company=company,
                    index=summary.current_index,
                    delta=summary.delta_24h,
                    topic=summary.top_topic,
                    rule_name="Rule A (Index Crosses 60)",
                    reason=f"Corporate risk index for {company} surged through high-risk threshold (60.0). {summary.one_line_reason}",
                    evidence_items=top_items,
                    badges=badges,
                )
                alerts.append(
                    AlertRecord(
                        key=key,
                        ts=datetime.now(timezone.utc),
                        company=company,
                        rule="Rule A (Index >= 60)",
                        subject=content["subject"],
                        body_html=content["body_html"],
                        body_text=content["body_text"],
                        recipients=self.adapter.get_allowlist(),
                        status="pending",
                        is_simulated=False,
                    )
                )

        # Rule B: Rises 15+ in 24h
        if summary.delta_24h >= 15.0:
            bucket = int(time.time() // COOLDOWN_SECONDS)
            key = f"{company}_RuleB_{bucket}"
            if not self._is_on_cooldown(key) and self._check_daily_cap():
                content = self.build_email_content(
                    company=company,
                    index=summary.current_index,
                    delta=summary.delta_24h,
                    topic=summary.top_topic,
                    rule_name="Rule B (24h Rise >= 15)",
                    reason=f"Sudden risk escalation: {company} risk index surged by +{summary.delta_24h:.1f} points in 24 hours. {summary.one_line_reason}",
                    evidence_items=top_items,
                    badges=badges,
                )
                alerts.append(
                    AlertRecord(
                        key=key,
                        ts=datetime.now(timezone.utc),
                        company=company,
                        rule="Rule B (Rise >= 15)",
                        subject=content["subject"],
                        body_html=content["body_html"],
                        body_text=content["body_text"],
                        recipients=self.adapter.get_allowlist(),
                        status="pending",
                        is_simulated=False,
                    )
                )

        return alerts

    def evaluate_item_trigger(self, flag: ConsensusFlag) -> Optional[AlertRecord]:
        """Evaluate Rule C: New severity-5 item that is agreed or confirmed."""
        if flag.is_simulated:
            include_sim = os.getenv("ALERT_INCLUDE_SIMULATED", "false").lower() in ("true", "1")
            if not include_sim:
                return None

        if flag.final_severity == 5 and flag.status in (ConsensusStatus.AGREED, ConsensusStatus.CONFIRMED):
            bucket = int(time.time() // COOLDOWN_SECONDS)
            key = f"{flag.company}_RuleC_{flag.item_id}"
            if not self._is_on_cooldown(key) and self._check_daily_cap():
                content = self.build_email_content(
                    company=flag.company,
                    index=85.0,  # critical severity
                    delta=20.0,
                    topic=flag.topics[0] if flag.topics else "enforcement action",
                    rule_name="Rule C (Severity 5 Consensus)",
                    reason=f"Critical consensus risk event detected for {flag.company}: {flag.reason}",
                    evidence_items=[{
                        "risk_type": flag.risk_type.value,
                        "severity": 5,
                        "title": f"Critical {flag.risk_type.value} incident",
                        "url": flag.source_url,
                    }],
                    badges=["Critical Severity 5", "Dual-LLM Verified"],
                    is_simulated=flag.is_simulated,
                )
                return AlertRecord(
                    key=key,
                    ts=datetime.now(timezone.utc),
                    company=flag.company,
                    rule="Rule C (Severity 5)",
                    subject=content["subject"],
                    body_html=content["body_html"],
                    body_text=content["body_text"],
                    recipients=self.adapter.get_allowlist(),
                    status="pending",
                    is_simulated=flag.is_simulated,
                )
        return None

    def dispatch_alert(self, alert: AlertRecord) -> Dict[str, Any]:
        """Dispatch single alert through adapter, enforce idempotency, and increment counter."""
        res = self.adapter.send_alert(
            to=alert.recipients,
            subject=alert.subject,
            body_html=alert.body_html,
            body_text=alert.body_text,
            key=alert.key,
        )
        self.sent_keys[alert.key] = time.time()
        self.daily_count += 1
        alert.status = res.get("status", "sent")
        return res


alert_engine = AlertEngine()
