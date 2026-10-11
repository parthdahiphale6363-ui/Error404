"""Keyword Pre-Filter Engine for Corporate Risk Radar.

Fast pre-filtering to identify potential legal, compliance, and operational risks
before executing LLM classification, saving tokens and improving throughput.
"""

import re
from typing import List, Set, Tuple
from backend.schemas import Item, SourceType

LEGAL_KEYWORDS: Set[str] = {
    "lawsuit",
    "lawsuits",
    "sue",
    "sued",
    "suing",
    "court",
    "subpoena",
    "subpoenas",
    "class action",
    "litigation",
    "attorney general",
    "prosecutor",
    "indictment",
    "injunction",
    "trial",
    "allegations",
    "settlement",
    "plaintiff",
    "unlawful",
    "verdict",
}

COMPLIANCE_KEYWORDS: Set[str] = {
    "cfpb",
    "sec",
    "doj",
    "ftc",
    "occ",
    "fdic",
    "finra",
    "fine",
    "fined",
    "penalty",
    "consent order",
    "enforcement",
    "sanction",
    "sanctions",
    "violation",
    "violations",
    "investigation",
    "investigating",
    "probe",
    "regulatory",
    "regulator",
    "audit",
    "banned",
    "deceptive",
    "unfair",
    "abusive",
    "unauthorized",
    "compliance",
    "misconduct",
    "fraud",
    "fraudulent",
}

OPERATIONAL_KEYWORDS: Set[str] = {
    "outage",
    "outages",
    "downtime",
    "breach",
    "hacked",
    "hack",
    "cyberattack",
    "vulnerability",
    "data leak",
    "glitch",
    "ransomware",
    "system failure",
    "failure",
    "latency",
    "timeout",
    "degradation",
    "disruption",
    "service interruption",
    "offline",
}

NOISE_TRIGGERS: Set[str] = {
    "dividend",
    "dividends",
    "quarterly dividend",
    "payout",
    "investor relations",
    "conference schedule",
    "presentation slides",
    "earnings call transcript",
}


class KeywordFilter:
    """Evaluates items for risk signal indicators prior to LLM classification."""

    def __init__(self):
        self._all_risk_keywords = LEGAL_KEYWORDS | COMPLIANCE_KEYWORDS | OPERATIONAL_KEYWORDS

    def evaluate(self, item: Item) -> Tuple[bool, List[str]]:
        """Evaluate whether an item contains risk indicators.
        
        Returns:
            Tuple of (should_analyze: bool, matched_keywords: List[str])
        """
        # Regulatory filings and consumer complaints always require analysis
        if item.source in (SourceType.CFPB, SourceType.EDGAR):
            return True, [item.source.value]

        # Scan title and text
        full_text = f"{item.title} {item.text}".lower()

        matched: List[str] = []
        for kw in self._all_risk_keywords:
            if " " in kw:
                if kw in full_text:
                    matched.append(kw)
            else:
                # Word boundary match for single words
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, full_text):
                    matched.append(kw)

        if matched:
            return True, matched

        # If it only contains noise triggers, explicitly bypass
        return False, []
