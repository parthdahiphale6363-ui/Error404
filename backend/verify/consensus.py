"""Dual-LLM Consensus Engine.

Implements consensus rules according to brain.md Section 4:
1. Item is 'flagged' if Mistral primary severity >= 3.
2. Flagged items are verified blind by second-opinion verifier.
3. Agree: verifier also severity >= 3 AND same risk_type:
   status = 'agreed', final_severity = min(both), review_factor = 1.0.
4. Disagree or verifier unavailable:
   status = 'needs_review', final_severity = Mistral's, review_factor = 0.5.
5. Analyst confirm:
   status = 'confirmed', review_factor = 1.0.
6. Analyst dismiss:
   status = 'dismissed', review_factor = 0.0.
7. Mistral severity < 3:
   status = 'unflagged', final_severity = primary.severity, review_factor = 1.0.
"""

from typing import Optional

from backend.schemas import (
    AnalystVerdict,
    ConsensusFlag,
    ConsensusStatus,
    DetectionResult,
    Item,
    VerificationResult,
)


def evaluate_consensus(
    item: Item,
    primary: DetectionResult,
    verifier_result: Optional[VerificationResult] = None,
) -> ConsensusFlag:
    """Evaluate Dual-LLM consensus rules over primary detection and blind verifier."""
    # Rule 7: Primary severity < 3 bypasses verification
    if primary.severity < 3:
        return ConsensusFlag(
            item_id=item.id,
            company=item.company,
            source_url=item.source_url,
            date=item.published_at,
            risk_type=primary.risk_type,
            primary_severity=primary.severity,
            final_severity=primary.severity,
            confidence=primary.confidence,
            status=ConsensusStatus.UNFLAGGED,
            review_factor=1.0,
            topics=primary.topics,
            regulators=primary.regulators,
            reason=primary.reason,
            verifier_provider=None,
            verifier_severity=None,
            verifier_risk_type=None,
            analyst_verdict=None,
            is_simulated=getattr(item, "is_simulated", False),
        )

    # Rule 4: Verifier unavailable
    if verifier_result is None:
        return ConsensusFlag(
            item_id=item.id,
            company=item.company,
            source_url=item.source_url,
            date=item.published_at,
            risk_type=primary.risk_type,
            primary_severity=primary.severity,
            final_severity=primary.severity,
            confidence=primary.confidence,
            status=ConsensusStatus.NEEDS_REVIEW,
            review_factor=0.5,
            topics=primary.topics,
            regulators=primary.regulators,
            reason=f"{primary.reason} (Awaiting review: second-opinion verifier was unavailable).",
            verifier_provider=None,
            verifier_severity=None,
            verifier_risk_type=None,
            analyst_verdict=None,
            is_simulated=getattr(item, "is_simulated", False),
        )

    # Rule 3: Agree (both severity >= 3 and same risk_type)
    both_high = primary.severity >= 3 and verifier_result.severity >= 3
    same_type = primary.risk_type == verifier_result.risk_type

    if both_high and same_type:
        final_sev = min(primary.severity, verifier_result.severity)
        return ConsensusFlag(
            item_id=item.id,
            company=item.company,
            source_url=item.source_url,
            date=item.published_at,
            risk_type=primary.risk_type,
            primary_severity=primary.severity,
            final_severity=final_sev,
            confidence=round((primary.confidence + verifier_result.confidence) / 2.0, 3),
            status=ConsensusStatus.AGREED,
            review_factor=1.0,
            topics=primary.topics,
            regulators=primary.regulators,
            reason=f"{primary.reason} Consensus confirmed by {verifier_result.provider}.",
            verifier_provider=verifier_result.provider,
            verifier_severity=verifier_result.severity,
            verifier_risk_type=verifier_result.risk_type,
            analyst_verdict=None,
            is_simulated=getattr(item, "is_simulated", False),
        )

    # Rule 4: Disagree on risk_type or severity
    disagree_reason = (
        f"Verifier classified as {verifier_result.risk_type.value} (severity {verifier_result.severity})"
        if not same_type else
        f"Verifier assessed severity as {verifier_result.severity} (< 3 threshold)"
    )
    return ConsensusFlag(
        item_id=item.id,
        company=item.company,
        source_url=item.source_url,
        date=item.published_at,
        risk_type=primary.risk_type,
        primary_severity=primary.severity,
        final_severity=primary.severity,
        confidence=primary.confidence,
        status=ConsensusStatus.NEEDS_REVIEW,
        review_factor=0.5,
        topics=primary.topics,
        regulators=primary.regulators,
        reason=f"{primary.reason} (Needs review: {disagree_reason}).",
        verifier_provider=verifier_result.provider,
        verifier_severity=verifier_result.severity,
        verifier_risk_type=verifier_result.risk_type,
        analyst_verdict=None,
        is_simulated=getattr(item, "is_simulated", False),
    )


def apply_analyst_verdict(flag: ConsensusFlag, verdict: AnalystVerdict) -> ConsensusFlag:
    """Apply analyst confirm or dismiss verdict to consensus flag."""
    updated = flag.model_copy(deep=True)
    updated.analyst_verdict = verdict

    if verdict == AnalystVerdict.CONFIRM:
        updated.status = ConsensusStatus.CONFIRMED
        updated.review_factor = 1.0
    elif verdict == AnalystVerdict.DISMISS:
        updated.status = ConsensusStatus.DISMISSED
        updated.review_factor = 0.0

    return updated
