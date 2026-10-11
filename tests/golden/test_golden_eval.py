"""Test running golden evaluation script across labeling workflow states."""

from tests.golden.eval import run_full_evaluation


def test_golden_eval_execution():
    """Verify golden evaluation script executes cleanly across labeling lifecycle."""
    results = run_full_evaluation()

    if results.get("status") == "AWAITING_USER_LABELS":
        assert results["total_candidates"] == 60
        assert results["labeled_count"] < 40
    else:
        assert results.get("status") == "EVALUATED"
        assert "dev" in results
        assert "test" in results
        dev = results["dev"]
        test = results["test"]
        assert "accuracy" in dev["report"]
        assert "accuracy" in test["report"]
        assert len(dev["confusion_matrix"]) == len(dev["classes"])
        assert len(test["confusion_matrix"]) == len(test["classes"])
