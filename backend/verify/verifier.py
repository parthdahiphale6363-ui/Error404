"""Blind Verifier Adapter for Dual-LLM Consensus Architecture.

Ensures absolute information isolation:
- The blind verifier receives ONLY raw item data (company, source, title, text, date).
- The verifier NEVER receives Mistral's output, severity score, topics, or reasoning.
- Uses Gemini as primary verifier and Groq as fallback.
"""

import json
import logging
from typing import Any, Dict, Optional

from backend.apigateway.client import ApiGatewayClient, gateway_client
from backend.schemas import Item, RiskType, VerificationResult

logger = logging.getLogger("verify.verifier")

VERIFIER_PROMPT_TEMPLATE = """You are an independent blind risk verifier conducting a second-opinion corporate risk assessment.
Evaluate the following source document for corporate entity {company}.

Strict Severity Rubric:
5: Major regulatory enforcement order, fine, criminal indictment, fatal breach or global platform failure.
4: Formal civil lawsuit, DOJ/SEC subpoena, multistate AG investigation, nationwide class action.
3: Credible consumer dispute of improper billing, systemic account hold, mixed file, or statutory defect.
2: Isolated single customer inquiry or minor administrative probe.
1: Speculative or unconfirmed rumor.
0: Routine corporate news, dividend notices, standard filings, or benign press releases.

Input Document:
Company: {company}
Date: {date}
Source: {source}
URL: {source_url}
Title: {title}
Text: {text}

Return ONLY a valid JSON object matching this schema:
{{
  "risk_type": "<legal|compliance|operational|noise>",
  "severity": <integer 0-5>,
  "confidence": <float 0.0-1.0>,
  "reason": "<one concise factual sentence grounding the rating strictly on the input text>"
}}
"""


class BlindVerifier:
    """Independent second-opinion verifier isolated from primary detector."""

    def __init__(self, client: Optional[ApiGatewayClient] = None, provider: str = "gemini"):
        self.client = client or gateway_client
        self.provider = provider

    def _verify_mock(self, item: Item) -> VerificationResult:
        """Deterministic high-fidelity second opinion for tests and mock mode."""
        text_lower = f"{item.title} {item.text}".lower()

        # Check noise
        if any(w in text_lower for w in ["dividend", "quarterly", "routine annual report", "grant", "clean energy"]):
            return VerificationResult(
                provider=self.provider,
                risk_type=RiskType.NOISE,
                severity=0,
                confidence=0.98,
                reason="Verifier confirms non-risk routine corporate notification.",
            )

        # Check Legal
        if any(w in text_lower for w in ["subpoena", "lawsuit", "class action", "investigative demand", "settlement", "wells notice"]):
            severity = 5 if any(w in text_lower for w in ["unregistered securities", "final judgment", "settlement"]) else 4
            return VerificationResult(
                provider=self.provider,
                risk_type=RiskType.LEGAL,
                severity=severity,
                confidence=0.92,
                reason="Independent review verifies formal legal or subpoena risk.",
            )

        # Check Compliance
        if any(w in text_lower for w in ["fine", "penalty", "cfpb orders", "forbearances", "overdraft fees", "unauthorized debit", "force-placed", "aml"]):
            severity = 5 if any(w in text_lower for w in ["3.7 billion", "$3.7b", "billions", "banned"]) else 4 if "audit" in text_lower or "aml" in text_lower else 3
            return VerificationResult(
                provider=self.provider,
                risk_type=RiskType.COMPLIANCE,
                severity=severity,
                confidence=0.90,
                reason="Independent review verifies regulatory compliance enforcement or customer fee dispute.",
            )

        # Check Operational
        if any(w in text_lower for w in ["outage", "latency", "locked my account", "mixed my credit file", "180-day hold", "glitch", "sim-swap", "drained"]):
            severity = 4 if any(w in text_lower for w in ["global latency", "outage freezes", "sim-swap"]) else 3
            return VerificationResult(
                provider=self.provider,
                risk_type=RiskType.OPERATIONAL,
                severity=severity,
                confidence=0.88,
                reason="Independent review verifies systemic infrastructure or operational account disruption.",
            )

        return VerificationResult(
            provider=self.provider,
            risk_type=RiskType.NOISE,
            severity=1,
            confidence=0.75,
            reason="Independent review finds minor signal without confirmed operational or regulatory incident.",
        )

    def verify(self, item: Item) -> Optional[VerificationResult]:
        """Perform blind verification on raw item. Note: Never accepts primary DetectionResult."""
        if self.client.mock_mode:
            return self._verify_mock(item)

        prompt = VERIFIER_PROMPT_TEMPLATE.format(
            company=item.company,
            date=item.published_at.isoformat(),
            source=getattr(item.source, "value", str(item.source)),
            source_url=item.source_url,
            title=item.title,
            text=item.text[:2000],
        )

        try:
            if self.provider == "groq":
                resp = self.client.request(
                    endpoint_name="groq_chat",
                    json_body={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"},
                    },
                )
                raw_text = resp["choices"][0]["message"]["content"]
            else:
                resp = self.client.request(
                    endpoint_name="gemini_generate_content",
                    path_params={"model": "gemini-2.5-flash"},
                    json_body={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.0,
                            "responseMimeType": "application/json",
                        },
                    },
                )
                raw_text = resp["candidates"][0]["content"]["parts"][0]["text"]

            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())

            return VerificationResult(
                provider=self.provider,
                risk_type=RiskType(data["risk_type"].lower()),
                severity=int(data["severity"]),
                confidence=float(data["confidence"]),
                reason=data["reason"],
            )
        except Exception as e:
            logger.warning("Blind verification failed for item %s via %s: %s", item.id, self.provider, e)
            return None


blind_verifier = BlindVerifier()
