"""Resend Email Adapter for Corporate Risk Radar.

Conforms strictly to API Gateway and Anti-Hallucination rules:
- Default EMAIL_MODE='dry_run': never calls Resend API, writes to data/outbox/.
- EMAIL_MODE='live': enforces allowlist, throttles to <= 2 req/sec, uses RESEND_API_KEY.
"""

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OUTBOX_DIR = Path("data/outbox")
DEFAULT_FROM = "onboarding@resend.dev"
LAST_SEND_TIME = 0.0


class ResendAdapter:
    """Adapter for sending alerts via Resend or writing dry-run previews."""

    def __init__(self, outbox_dir: Optional[Path] = None):
        self.outbox_dir = outbox_dir or OUTBOX_DIR
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def is_dry_run(self) -> bool:
        mode = os.getenv("EMAIL_MODE", "dry_run").strip().lower()
        return mode != "live"

    def get_allowlist(self) -> List[str]:
        raw = os.getenv("ALERT_TO_ALLOWLIST", "analyst@example.com")
        return [email.strip().lower() for email in raw.split(",") if email.strip()]

    def send_alert(
        self,
        to: List[str],
        subject: str,
        body_html: str,
        body_text: str,
        from_email: Optional[str] = None,
        key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch email through Resend live API or dry-run outbox."""
        global LAST_SEND_TIME

        from_email = from_email or os.getenv("ALERT_FROM", DEFAULT_FROM)
        clean_key = re.sub(r"[^a-zA-Z0-9_\-]", "_", key or f"alert_{int(time.time())}")

        if self.is_dry_run():
            outbox_file = self.outbox_dir / f"{clean_key}.html"
            content = (
                f"<!-- Subject: {subject} -->\n"
                f"<!-- To: {', '.join(to)} -->\n"
                f"<!-- From: {from_email} -->\n"
                f"<!-- Date: {datetime.now(timezone.utc).isoformat()} -->\n"
                f"{body_html}"
            )
            outbox_file.write_text(content, encoding="utf-8")
            logger.info("Alert written to dry-run outbox: %s", outbox_file)
            return {
                "id": f"dry_run_{clean_key}",
                "status": "dry_run_saved",
                "outbox_path": str(outbox_file),
                "to": to,
                "subject": subject,
            }

        # Live Mode Validation
        allowlist = self.get_allowlist()
        for recipient in to:
            if recipient.lower() not in allowlist:
                raise ValueError(
                    f"Recipient '{recipient}' is not permitted by ALERT_TO_ALLOWLIST: {allowlist}"
                )

        # Rate Limiting (<= 2 requests per second)
        now = time.time()
        elapsed = now - LAST_SEND_TIME
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)

        api_key = os.getenv("RESEND_API_KEY")
        if not api_key:
            raise ValueError("RESEND_API_KEY is not configured in environment.")

        import requests
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": to,
                "subject": subject,
                "html": body_html,
                "text": body_text,
            },
            timeout=10.0,
        )
        LAST_SEND_TIME = time.time()
        response.raise_for_status()
        return response.json()


resend_adapter = ResendAdapter()
