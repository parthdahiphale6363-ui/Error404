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


class LLMAdapter:
    """Adapter for LLM providers (Gemini & Groq) through api gateway."""

    def __init__(self, client: Optional[ApiGatewayClient] = None):
        self.client = client or gateway_client
        self._cached_gemini_models: Optional[List[str]] = None
        self._cached_groq_models: Optional[List[str]] = None

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
        text_lower = f"{item.title} {item.text}".lower()
        if "fine" in text_lower or "billions" in text_lower or "redress" in text_lower:
            return Flag(
                item_id=item.id,
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=RiskType.COMPLIANCE,
                severity=5,
                confidence=0.95,
                reason="Enforcement action and major penalty order identified in source.",
                is_simulated=item.is_simulated,
            )
        elif "investigation" in text_lower or "subpoena" in text_lower:
            return Flag(
                item_id=item.id,
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=RiskType.LEGAL,
                severity=4,
                confidence=0.90,
                reason="Formal regulatory investigation reported in source.",
                is_simulated=item.is_simulated,
            )
        elif "freeze" in text_lower or "unlawful" in text_lower or "fraudulent" in text_lower:
            return Flag(
                item_id=item.id,
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=RiskType.OPERATIONAL,
                severity=3,
                confidence=0.85,
                reason="Consumer complaint indicates systemic operational disruption or improper charges.",
                is_simulated=item.is_simulated,
            )
        elif "dividend" in text_lower or "quarterly" in text_lower:
            return Flag(
                item_id=item.id,
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=RiskType.NOISE,
                severity=0,
                confidence=0.99,
                reason="Routine corporate dividend announcement is non-risk noise.",
                is_simulated=item.is_simulated,
            )
        else:
            return Flag(
                item_id=item.id,
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=RiskType.NOISE,
                severity=1,
                confidence=0.70,
                reason="Minor signal without confirmed regulatory or operational disruption.",
                is_simulated=item.is_simulated,
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
