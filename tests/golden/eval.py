"""Evaluation script for golden labeled benchmark dataset.

Computes and prints:
- Precision, Recall, F1 per class and macro/weighted average on Dev (20) and Test (20) splits separately
- Confusion Matrix for Dev and Test splits separately
- Topic tags spot-check on 20 items reported separately
- Detects and reports when candidate items are awaiting user labels.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Tuple

from sklearn.metrics import classification_report, confusion_matrix

from backend.apigateway.adapters.llm import LLMAdapter
from backend.apigateway.client import ApiGatewayClient
from backend.detect.engine import DetectionEngine
from backend.schemas import Item, RiskType, SourceType, DetectionResult

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


def evaluate_split(records: List[Dict], engine: DetectionEngine, split_name: str) -> Dict:
    y_true = []
    y_pred = []
    classes = [r.value for r in RiskType]

    print(f"\n=======================================================")
    print(f" EVALUATION REPORT: {split_name.upper()} SPLIT ({len(records)} ITEMS)")
    print(f"=======================================================")

    for rec in records:
        true_label = rec.get("user_labeled_risk_type") or rec.get("true_risk_type")
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
        detection = engine.detect(item)
        y_true.append(str(true_label).lower())
        y_pred.append(detection.risk_type.value)

    report = classification_report(
        y_true,
        y_pred,
        labels=classes,
        output_dict=True,
        zero_division=0,
    )
    report_text = classification_report(
        y_true,
        y_pred,
        labels=classes,
        zero_division=0,
    )
    print(report_text)

    cm = confusion_matrix(y_true, y_pred, labels=classes)
    print(f"Confusion Matrix ({split_name}):")
    print(f"Classes: {classes}")
    for idx, row in enumerate(cm):
        print(f"  {classes[idx]:<12}: {row.tolist()}")

    return {
        "split": split_name,
        "count": len(records),
        "report": report,
        "confusion_matrix": cm.tolist(),
        "classes": classes,
    }


def spot_check_topics(records: List[Dict], engine: DetectionEngine, count: int = 20) -> Dict[str, Any]:
    """Spot-check topic tags on designated items with true topics ground truth."""
    items_to_check = [r for r in records if r.get("true_topics")][:count]

    print(f"\n=======================================================")
    print(f" TOPIC TAGS SPOT-CHECK REPORT ({len(items_to_check)} ITEMS)")
    print(f"=======================================================")

    matches = 0
    details = []

    for rec in items_to_check:
        true_topics = rec.get("true_topics", [])
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
        detection = engine.detect(item)
        pred_topics = detection.topics

        # Overlap check
        overlap = set(true_topics).intersection(set(pred_topics))
        is_match = len(overlap) > 0 or (len(true_topics) == 0 and len(pred_topics) == 0)
        if is_match:
            matches += 1

        details.append({
            "id": rec["id"],
            "company": rec["company"],
            "true_topics": true_topics,
            "pred_topics": pred_topics,
            "match": is_match,
        })
        print(f"[{'PASS' if is_match else 'FAIL'}] {rec['id']} ({rec['company']}): True={true_topics} | Pred={pred_topics}")

    accuracy = (matches / len(items_to_check)) if items_to_check else 1.0
    print(f"\nTopic Spot-Check Match Rate: {matches}/{len(items_to_check)} ({accuracy:.1%})")

    return {
        "total_checked": len(items_to_check),
        "matches": matches,
        "accuracy": accuracy,
        "details": details,
    }


def run_full_evaluation() -> Dict[str, Any]:
    records = load_labeled_data()
    labeled_records = [
        r for r in records
        if r.get("user_labeled_risk_type") or r.get("true_risk_type")
    ]

    # Check if awaiting user labeling
    if len(labeled_records) < 10:
        print("\n=======================================================")
        print(" GOLDEN EVALUATION BENCHMARK: AWAITING USER LABELS")
        print("=======================================================")
        print(f"Dataset contains {len(records)} candidate items across 5 companies.")
        print(f"Currently {len(labeled_records)} items have ground truth labels.")
        print("Status: Paused awaiting user to label 40 items in data/labeled/labeled_items.jsonl.")
        return {
            "status": "AWAITING_USER_LABELS",
            "total_candidates": len(records),
            "labeled_count": len(labeled_records),
        }

    # If dev/test split is marked, use it; otherwise split evenly
    dev_records = [r for r in labeled_records if r.get("split") == "dev"]
    test_records = [r for r in labeled_records if r.get("split") == "test"]

    if not dev_records and not test_records:
        midpoint = len(labeled_records) // 2
        dev_records = labeled_records[:midpoint]
        test_records = labeled_records[midpoint:]

    client = ApiGatewayClient(mock_mode=True)
    adapter = LLMAdapter(client=client)
    # DetectionEngine using offline repository to avoid touching live database during eval
    engine = DetectionEngine(llm=adapter, graph=None)

    dev_results = evaluate_split(dev_records, engine, "dev")
    test_results = evaluate_split(test_records, engine, "test")
    topic_results = spot_check_topics(labeled_records, engine, count=20)

    return {
        "status": "EVALUATED",
        "dev": dev_results,
        "test": test_results,
        "topic_spotcheck": topic_results,
    }


if __name__ == "__main__":
    run_full_evaluation()
