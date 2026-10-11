"""Export accuracy numbers and replay scorecard to JSON for presentation slides."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_EXPORT_PATH = REPO_ROOT / "data" / "export_scorecard.json"


def export_accuracy_and_replay_scorecard(
    eval_results: Optional[Dict[str, Any]] = None,
    replay_results: Optional[Dict[str, Any]] = None,
    target_path: Path = DEFAULT_EXPORT_PATH,
) -> Dict[str, Any]:
    """Generate and write a JSON scorecard of model accuracy and replay lead times."""

    scorecard: Dict[str, Any] = {
        "metadata": {
            "title": "Corporate Risk Radar — Accuracy & Time-Machine Replay Scorecard",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "target_companies": ["WFC", "EFX", "PYPL", "COIN", "NAVI"],
        },
        "accuracy_benchmark": eval_results or {
            "note": "Awaiting user ground-truth labels for 40 candidate items in data/labeled/labeled_items.jsonl",
            "status": "LABELS_PENDING",
            "stratified_candidates_generated": 60,
        },
        "replay_scorecard": replay_results or {
            "proposed_cases": [
                {
                    "case_id": "WFC_2022_CFPB_MISMANAGEMENT",
                    "company": "WFC",
                    "official_action": "CFPB Orders Wells Fargo to Pay $3.7B for Loan and Overdraft Mismanagement",
                    "official_event_date": "2022-12-20",
                    "official_source_url": "https://www.consumerfinance.gov/about-us/newsroom/cfpb-orders-wells-fargo-to-pay-37-billion-for-widespread-mismanagement-of-auto-loans-mortgages-and-deposit-accounts/",
                    "expected_lead_time_days": 96,
                    "target_signal_types": ["compliance", "operational"],
                },
                {
                    "case_id": "COIN_2023_SEC_UNREGISTERED_EXCHANGE",
                    "company": "COIN",
                    "official_action": "SEC Files Lawsuit Against Coinbase for Operating as Unregistered Exchange",
                    "official_event_date": "2023-06-06",
                    "official_source_url": "https://www.sec.gov/news/press-release/2023-102",
                    "expected_lead_time_days": 76,
                    "target_signal_types": ["legal", "compliance"],
                },
                {
                    "case_id": "NAVI_2024_CFPB_BAN",
                    "company": "NAVI",
                    "official_action": "CFPB Orders Navient to Pay $120M and Permanently Bans Federal Loan Servicing",
                    "official_event_date": "2024-09-12",
                    "official_source_url": "https://www.consumerfinance.gov/about-us/newsroom/cfpb-orders-navient-to-pay-120-million-for-years-of-student-loan-servicing-failures/",
                    "expected_lead_time_days": 90,
                    "target_signal_types": ["compliance", "legal"],
                },
            ],
            "calm_controls": [
                {
                    "control_id": "PYPL_Q2_2023_CALM",
                    "company": "PYPL",
                    "window": "2023-04-01 to 2023-06-30",
                    "description": "Routine payment processing operations with steady complaint baseline and no enforcement actions.",
                    "target_false_alarm": False,
                },
                {
                    "control_id": "EFX_Q1_2024_CALM",
                    "company": "EFX",
                    "window": "2024-01-01 to 2024-03-31",
                    "description": "Standard credit reporting operations following settled remediation programs with no major investigations.",
                    "target_false_alarm": False,
                },
            ],
        },
    }

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(scorecard, f, indent=2)

    return scorecard


if __name__ == "__main__":
    export_accuracy_and_replay_scorecard()
