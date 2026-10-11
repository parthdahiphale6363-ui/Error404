"""Evaluation script comparing Mistral-only vs Dual-LLM Consensus Detector.

Prints:
- Mistral-only vs Consensus precision/recall/F1
- Consensus lift
- Agreement rate
- Review queue size
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import json
from typing import Any, Dict, List

from sklearn.metrics import classification_report

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.apigateway.adapters.llm import LLMAdapter
from backend.apigateway.client import ApiGatewayClient
from backend.detect.engine import DetectionEngine
from backend.schemas import ConsensusStatus, Item, RiskType, SourceType
from backend.verify.consensus import evaluate_consensus
from backend.verify.verifier import BlindVerifier

BENCHMARK_PATH = REPO_ROOT / "data" / "labeled" / "labeled_items.jsonl"


def load_labeled_data(path: Path = BENCHMARK_PATH) -> List[Dict]:
    items = []
    if not path.exists():
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def run_consensus_evaluation() -> Dict[str, Any]:
    records = load_labeled_data()
    labeled = [r for r in records if r.get("user_labeled_risk_type")]

    client = ApiGatewayClient(mock_mode=True)
    llm = LLMAdapter(client=client)
    det_engine = DetectionEngine(llm=llm, graph=None)
    verifier = BlindVerifier(client=client)

    y_true = []
    y_mistral = []
    y_consensus = []

    flagged_count = 0
    agreed_count = 0
    review_queue_count = 0

    print("\n=======================================================")
    print(" DUAL-LLM CONSENSUS EVALUATION (40 BENCHMARK ITEMS)")
    print("=======================================================")

    for rec in labeled:
        true_label = rec["user_labeled_risk_type"].lower()
        item = Item(
            id=rec["id"],
            company=rec["company"],
            source=SourceType(rec.get("source", "finnhub")),
            source_url=rec.get("source_url", "https://example.com/eval"),
            title=rec["title"],
            text=rec["text"],
            published_at=datetime.now(timezone.utc),
            content_hash=f"hash_{rec['id']}",
        )

        # 1. Primary detection (Mistral)
        primary = det_engine.detect(item)
        y_true.append(true_label)
        y_mistral.append(primary.risk_type.value)

        # 2. Dual-LLM Consensus verification
        if primary.severity >= 3:
            flagged_count += 1
            ver_res = verifier.verify(item)
            cflag = evaluate_consensus(item, primary, ver_res)
            if cflag.status == ConsensusStatus.AGREED:
                agreed_count += 1
            elif cflag.status == ConsensusStatus.NEEDS_REVIEW:
                review_queue_count += 1
            y_consensus.append(cflag.risk_type.value)
        else:
            cflag = evaluate_consensus(item, primary, verifier_result=None)
            y_consensus.append(cflag.risk_type.value)

    classes = [r.value for r in RiskType]
    rep_mistral = classification_report(y_true, y_mistral, labels=classes, output_dict=True, zero_division=0)
    rep_consensus = classification_report(y_true, y_consensus, labels=classes, output_dict=True, zero_division=0)

    agreement_rate = (agreed_count / flagged_count) if flagged_count > 0 else 1.0

    print(f"\n--- MISTRAL-ONLY ACCURACY ---: {rep_mistral['accuracy']:.1%}")
    print(f"--- CONSENSUS ACCURACY ---   : {rep_consensus['accuracy']:.1%}")
    print(f"Total Items Evaluated        : {len(labeled)}")
    print(f"Primary Flagged (sev >= 3)   : {flagged_count}")
    print(f"Consensus Agreed             : {agreed_count}")
    print(f"Agreement Rate               : {agreement_rate:.1%}")
    print(f"Needs Review Queue Size      : {review_queue_count}")

    print("\nMistral-Only Report:")
    print(classification_report(y_true, y_mistral, labels=classes, zero_division=0))

    print("\nConsensus Report:")
    print(classification_report(y_true, y_consensus, labels=classes, zero_division=0))

    return {
        "mistral_accuracy": rep_mistral["accuracy"],
        "consensus_accuracy": rep_consensus["accuracy"],
        "flagged_count": flagged_count,
        "agreed_count": agreed_count,
        "agreement_rate": agreement_rate,
        "review_queue_size": review_queue_count,
    }


if __name__ == "__main__":
    run_consensus_evaluation()
