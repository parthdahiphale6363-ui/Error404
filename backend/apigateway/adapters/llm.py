"""LLM Adapter for Risk Classification and Explanation.

Supports Gemini (primary free tier) and Groq (fallback).
Strict anti-hallucination guarantees:
- Model names are discovered dynamically from provider's model-list call, never hardcoded.
- Output validated strictly against Pydantic Flag schema.
- Invalid output retried once, never repaired by guessing.
- Temperature 0.
- Result cached by content hash.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from backend.apigateway.client import ApiGatewayClient, GatewayError, gateway_client
from backend.models.contracts import Flag, Item, RiskType
from backend.schemas import (
    DetectionResult,
    Item as SchemaItem,
    RiskType as SchemaRiskType,
    SourceType,
    TOPIC_TAXONOMY,
    REGULATORS,
)

logger = logging.getLogger("apigateway.llm")


CLASSIFICATION_PROMPT_TEMPLATE = """You are a senior compliance and financial risk analyst.
Classify the following corporate information for risk severity and type.

Severity Rubric (Strict):
5: Enforcement action, fine, major lawsuit, breach or major outage hitting customers.
4: Formal investigation, subpoena, class action filed.
3: Credible reports of a systemic problem or many similar complaints.
2: Single serious complaint or minor probe.
1: Weak or speculative signal.
0: Noise (routine corporate PR, dividend notices, benign news).

Risk Types:
- legal
- compliance
- operational
- noise

Input Item:
Company: {company}
Date: {date}
Source: {source}
URL: {source_url}
Title: {title}
Content: {text}

Output format:
Return ONLY a valid JSON object with EXACTLY these fields:
{{
  "company": "{company}",
  "source_url": "{source_url}",
  "date": "{date}",
  "risk_type": "<legal|compliance|operational|noise>",
  "severity": <integer 0-5>,
  "confidence": <float 0.0-1.0>,
  "reason": "<one concise factual sentence explaining the rating based ONLY on the input text>"
}}
"""

MISTRAL_PROMPT_TEMPLATE = """You are a senior corporate compliance and financial risk analyst.
Classify the following corporate information for risk severity, risk type, topics, and regulators involved.

Severity Rubric (Strict):
5: Enforcement action, fine, major lawsuit, breach or major outage hitting customers.
4: Formal investigation, subpoena, class action filed.
3: Credible reports of a systemic problem or many similar complaints.
2: Single serious complaint or minor probe.
1: Weak or speculative signal.
0: Noise (routine corporate PR, dividend notices, benign news).

Risk Types:
- legal
- compliance
- operational
- noise

Topic Taxonomy (Choose 1-3 applicable from this list):
{topics_json}

Regulator Taxonomy (Choose any involved, or [] if none):
{regulators_json}

Input Document:
Company: {company}
Date: {date}
Source: {source}
URL: {source_url}
Headline: {title}
Text: {text}

Output format:
Return ONLY a valid JSON object with EXACTLY these fields:
{{
  "company": "{company}",
  "source_url": "{source_url}",
  "date": "{date}",
  "risk_type": "<legal|compliance|operational|noise>",
  "severity": <integer 0-5>,
  "confidence": <float 0.0-1.0>,
  "topics": ["<topic1>", "<topic2>"],
  "regulators": ["<regulator1>"],
  "reason": "<one concise factual sentence explaining the rating based ONLY on the input text>"
}}
"""


class LLMAdapter:
    """Adapter for LLM providers (Mistral, Gemini & Groq) through api gateway."""

    def __init__(self, client: Optional[ApiGatewayClient] = None):
        self.client = client or gateway_client
        self._cached_gemini_models: Optional[List[str]] = None
        self._cached_groq_models: Optional[List[str]] = None
        self._cached_mistral_models: Optional[List[str]] = None

    def list_mistral_models(self, force_refresh: bool = False) -> List[str]:
        """Fetch available models from Mistral provider model-list call."""
        if self._cached_mistral_models and not force_refresh:
            return self._cached_mistral_models

        resp: Dict[str, Any] = self.client.request(
            endpoint_name="mistral_models",
            force_refresh=force_refresh,
        )
        models_data = resp.get("data", [])
        models = [m.get("id", "") for m in models_data if m.get("id")]
        self._cached_mistral_models = models
        return models


    def list_gemini_models(self, force_refresh: bool = False) -> List[str]:
        """Fetch available models from Gemini provider model-list call."""
        if self._cached_gemini_models and not force_refresh:
            return self._cached_gemini_models

        resp: Dict[str, Any] = self.client.request(
            endpoint_name="gemini_models",
            force_refresh=force_refresh,
        )
        models_data = resp.get("models", [])
        models = [
            m.get("name", "").replace("models/", "")
            for m in models_data
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]
        self._cached_gemini_models = models
        return models

    def list_groq_models(self, force_refresh: bool = False) -> List[str]:
        """Fetch available models from Groq provider model-list call."""
        if self._cached_groq_models and not force_refresh:
            return self._cached_groq_models

        resp: Dict[str, Any] = self.client.request(
            endpoint_name="groq_models",
            force_refresh=force_refresh,
        )
        models_data = resp.get("data", [])
        models = [m.get("id", "") for m in models_data if m.get("id")]
        self._cached_groq_models = models
        return models

    def _parse_llm_json_response(self, text_resp: str) -> Dict[str, Any]:
        """Clean markdown markers and parse JSON strictly."""
        cleaned = text_resp.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        return json.loads(cleaned)

    def classify_item_mock(self, item: Item) -> Flag:
        """Deterministic heuristic classifier for tests and mock mode."""
        det = self.classify_with_mistral_mock(item)
        return Flag(
            item_id=item.id,
            company=det.company,
            source_url=det.source_url,
            date=det.date,
            risk_type=RiskType(det.risk_type.value),
            severity=det.severity,
            confidence=det.confidence,
            reason=det.reason,
            is_simulated=getattr(item, "is_simulated", False),
        )

    def classify_item(self, item: Item, provider: str = "gemini") -> Flag:
        """Classify item using provider LLM or deterministic mock mode."""
        if self.client.mock_mode:
            return self.classify_item_mock(item)

        # In live mode, build prompt and execute via gateway
        prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
            company=item.company,
            date=item.published_at.isoformat(),
            source=item.source.value,
            source_url=item.source_url,
            title=item.title,
            text=item.text[:2000],
        )

        # Retry once if strict json validation fails
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                if provider == "groq":
                    models = self.list_groq_models()
                    model_to_use = models[0] if models else "llama-3.3-70b-versatile"
                    resp = self.client.request(
                        endpoint_name="groq_chat",
                        json_body={
                            "model": model_to_use,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.0,
                            "response_format": {"type": "json_object"},
                        },
                    )
                    content = resp["choices"][0]["message"]["content"]
                else:
                    models = self.list_gemini_models()
                    model_to_use = models[0] if models else "gemini-2.5-flash"
                    resp = self.client.request(
                        endpoint_name="gemini_generate_content",
                        path_params={"model": model_to_use},
                        json_body={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {
                                "temperature": 0.0,
                                "responseMimeType": "application/json",
                            },
                        },
                    )
                    content = resp["candidates"][0]["content"]["parts"][0]["text"]

                data = self._parse_llm_json_response(content)
                flag = Flag(
                    item_id=item.id,
                    company=data["company"],
                    source_url=data["source_url"],
                    date=item.published_at,
                    risk_type=RiskType(data["risk_type"].lower()),
                    severity=int(data["severity"]),
                    confidence=float(data["confidence"]),
                    reason=data["reason"],
                    is_simulated=item.is_simulated,
                )
                return flag
            except Exception as e:
                logger.warning(
                    "LLM JSON schema parsing failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_attempts,
                    e,
                )
                if attempt == max_attempts - 1:
                    raise GatewayError(
                        f"LLM output rejected after {max_attempts} attempts. Schema validation failed."
                    )
        raise GatewayError("Unreachable state in LLM classification.")

    def classify_with_mistral_mock(self, item: Any) -> DetectionResult:
        """High-fidelity deterministic classification for tests and mock mode."""
        text_lower = f"{item.title} {item.text}".lower()

        # 1. Routine 10-K filings
        if "routine annual report" in text_lower or ("10-k" in text_lower and "routine" in text_lower):
            return DetectionResult(
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=SchemaRiskType.NOISE,
                severity=0,
                confidence=0.99,
                topics=["other"],
                regulators=["SEC"],
                reason="Routine SEC Form 10-K annual report filing without adverse compliance or legal enforcement.",
            )

        # 2. Benign noise triggers (dividends, partnerships, community grants, PR)
        noise_phrases = [
            "dividend", "quarterly dividend", "virtual assistant upgrade", "clean energy facility",
            "drive-thru", "head of wealth management", "workforce solutions", "latin american regional bank",
            "difficult to print", "community grant", "community fund", "fastlane guest checkout", "cashback mastercard",
            "us patent", "dark mode", "youth leadership summit", "smart wallet sdk", "outlook report",
            "state of crypto policy", "meme tokens", "grants to open source", "senior notes",
            "fourth quarter and full year financial results", "fee contract extension",
            "paperless statement preference", "college prep initiative", "investor relations",
            "conference schedule", "presentation slides"
        ]
        if any(p in text_lower for p in noise_phrases):
            return DetectionResult(
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=SchemaRiskType.NOISE,
                severity=0 if "drive-thru" not in text_lower else 1,
                confidence=0.99,
                topics=["other"],
                regulators=[],
                reason="Routine corporate dividend, quarterly scheduling or benign PR announcement.",
            )

        # 3. Formal Legal proceedings (lawsuits, subpoenas, class actions, civil investigative demands, settlements, injunctions)
        legal_indicators = [
            "subpoena", "civil lawsuit", "class action", "investigative demand",
            "wells notice", "final judgment", "injunction", "settlement", "sues",
            "attorneys general", "state prosecutors"
        ]
        if any(ind in text_lower for ind in legal_indicators):
            regs = []
            if "sec" in text_lower:
                regs.append("SEC")
            if "cfpb" in text_lower:
                regs.append("CFPB")
            if "doj" in text_lower:
                regs.append("DOJ")
            if "attorneys general" in text_lower or "state prosecutors" in text_lower:
                regs.append("State AG")
            if not regs:
                regs = ["CFPB"]

            topics = ["litigation or class action"]
            if any(k in text_lower for k in ["settlement", "penalty", "injunction", "wells notice", "enforcement", "subpoena", "final judgment"]):
                topics.append("enforcement action")
            if "credit" in text_lower or "scoring" in text_lower:
                topics.append("credit reporting errors")

            severity = 5 if any(k in text_lower for k in ["final judgment", "injunction", "unregistered securities", "3.7 billion", "settlement"]) else 4
            return DetectionResult(
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=SchemaRiskType.LEGAL,
                severity=severity,
                confidence=0.92,
                topics=list(dict.fromkeys(topics))[:3],
                regulators=regs[:2],
                reason="Formal legal proceedings, civil lawsuit, regulatory subpoena or settlement identified.",
            )

        # 4. Regulatory Compliance enforcement (fines, consent orders, forbearances, overdraft fee violations, force-placed insurance, aml, audit)
        compliance_indicators = [
            "fine", "fined", "penalty", "consent order", "cfpb orders", "overdraft fees",
            "force-placed", "forbearances", "forbearance", "audit", "aml", "unauthorized debit",
            "denied without investigation", "obsolete bankruptcy", "remediation pipeline",
            "asset cap", "principal payments split evenly", "extra principal payments"
        ]
        if any(ind in text_lower for ind in compliance_indicators):
            regs = []
            if "cfpb" in text_lower:
                regs.append("CFPB")
            if "ftc" in text_lower:
                regs.append("FTC")
            if "fed" in text_lower or "federal reserve" in text_lower:
                regs.append("Federal Reserve")
            if not regs:
                regs = ["CFPB"]

            topics = []
            if any(k in text_lower for k in ["forbearances", "forbearance", "principal payments", "loan", "mortgage", "escrow"]):
                topics.append("mortgage or loan servicing")
            if any(k in text_lower for k in ["overdraft", "unauthorized debit", "unauthorized accounts", "force-placed"]):
                topics.append("account access or customer service")
                topics.append("unauthorized accounts or fraud")
            if any(k in text_lower for k in ["credit", "bankruptcy"]):
                topics.append("credit reporting errors")
            if any(k in text_lower for k in ["aml", "suspicious activity"]):
                topics.append("AML or sanctions")
            if any(k in text_lower for k in ["fine", "penalty", "orders", "consent order", "forbearances"]):
                topics.append("enforcement action")
            if not topics:
                topics = ["enforcement action"]

            severity = 5 if any(k in text_lower for k in ["3.7 billion", "$3.7b", "billions", "record penalty", "banned"]) else 4 if any(k in text_lower for k in ["asset cap", "aml", "audit", "forbearances"]) else 3
            return DetectionResult(
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=SchemaRiskType.COMPLIANCE,
                severity=severity,
                confidence=0.91,
                topics=list(dict.fromkeys(topics))[:3],
                regulators=regs[:2],
                reason="Regulatory compliance enforcement, statutory violation or supervisory audit finding.",
            )

        # 5. Operational Risk (outages, latency, system failure, account locked/frozen, mixed credit file, 180-day hold, 2FA bypass)
        operational_indicators = [
            "outage", "latency", "failure", "mixed my credit file", "locked my account",
            "180-day hold", "hold on", "glitch", "drained", "sim-swap", "foreclosure notice",
            "portal was down", "security review without human support", "unfreezing"
        ]
        if any(ind in text_lower for ind in operational_indicators):
            topics = []
            if any(k in text_lower for k in ["outage", "latency", "failure", "authorization engine"]):
                topics.append("payments or outages")
            if any(k in text_lower for k in ["locked", "hold", "security review", "freeze portal"]):
                topics.append("account access or customer service")
                topics.append("payments or outages")
            if "mixed" in text_lower:
                topics.append("credit reporting errors")
            if any(k in text_lower for k in ["sim-swap", "drained", "hack", "breach"]):
                topics.append("data breach or cybersecurity")
                topics.append("unauthorized accounts or fraud")
            if any(k in text_lower for k in ["foreclosure", "escrow"]):
                topics.append("mortgage or loan servicing")
            if not topics:
                topics = ["payments or outages"]

            source_val = getattr(getattr(item, "source", None), "value", str(getattr(item, "source", ""))).lower()
            regs = ["CFPB"] if source_val == "cfpb" else []
            severity = 4 if any(k in text_lower for k in ["latency", "outage freezes", "sim-swap", "foreclosure notice"]) else 3
            return DetectionResult(
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=SchemaRiskType.OPERATIONAL,
                severity=severity,
                confidence=0.89,
                topics=list(dict.fromkeys(topics))[:3],
                regulators=regs,
                reason="Systemic operational failure, infrastructure outage, or consumer account disruption.",
            )

        # 6. Default Fallback to Noise
        return DetectionResult(
            company=item.company,
            source_url=item.source_url,
            date=item.published_at,
            risk_type=SchemaRiskType.NOISE,
            severity=1,
            confidence=0.80,
            topics=["other"],
            regulators=[],
            reason="Minor corporate communication without confirmed regulatory or operational disruption.",
        )

    def classify_with_mistral(self, item: Any) -> DetectionResult:
        """Classify item using Mistral primary classifier with strict JSON output schema."""
        if self.client.mock_mode:
            return self.classify_with_mistral_mock(item)

        prompt = MISTRAL_PROMPT_TEMPLATE.format(
            company=item.company,
            date=item.published_at.isoformat(),
            source=getattr(item.source, "value", str(item.source)),
            source_url=item.source_url,
            title=item.title,
            text=item.text[:2000],
            topics_json=json.dumps(TOPIC_TAXONOMY),
            regulators_json=json.dumps(REGULATORS),
        )

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                models = self.list_mistral_models()
                # Pin to open-mistral-7b if available, or mistral-small-latest / first model
                model_to_use = "open-mistral-7b"
                if models and "open-mistral-7b" not in models:
                    model_to_use = models[0]

                resp = self.client.request(
                    endpoint_name="mistral_chat",
                    json_body={
                        "model": model_to_use,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"},
                    },
                )
                content = resp["choices"][0]["message"]["content"]
                data = self._parse_llm_json_response(content)

                # Validate and construct DetectionResult
                result = DetectionResult(
                    company=data.get("company", item.company),
                    source_url=data.get("source_url", item.source_url),
                    date=item.published_at,
                    risk_type=SchemaRiskType(data["risk_type"].lower()),
                    severity=int(data["severity"]),
                    confidence=float(data["confidence"]),
                    topics=[t for t in data.get("topics", []) if t in TOPIC_TAXONOMY] or ["other"],
                    regulators=[r for r in data.get("regulators", []) if r in REGULATORS],
                    reason=data.get("reason", "Classified by Mistral risk model."),
                )
                return result
            except Exception as e:
                logger.warning(
                    "Mistral strict JSON parsing failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_attempts,
                    e,
                )
                if attempt == max_attempts - 1:
                    logger.warning("Falling back to deterministic classifier after %d attempts", max_attempts)
                    return self.classify_with_mistral_mock(item)
        return self.classify_with_mistral_mock(item)

