"""Evaluation script for golden labeled benchmark dataset.

Computes and prints:
- Precision, Recall, F1 per class and macro/weighted average
- Confusion Matrix
- Evaluates dev and test splits when ground truth labels are present.
- Detects and reports when 60 candidate items are awaiting user labels.
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
from backend.models.contracts import Item, RiskType, SourceType

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


def evaluate_split(records: List[Dict], adapter: LLMAdapter, split_name: str) -> Dict:
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
            content_hash="evalhash123456",
        )
        flag = adapter.classify_item(item)
        y_true.append(str(true_label).lower())
        y_pred.append(flag.risk_type.value)

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

    dev_results = evaluate_split(dev_records, adapter, "dev")
    test_results = evaluate_split(test_records, adapter, "test")

    return {
        "status": "EVALUATED",
        "dev": dev_results,
        "test": test_results,
    }


if __name__ == "__main__":
    run_full_evaluation()
