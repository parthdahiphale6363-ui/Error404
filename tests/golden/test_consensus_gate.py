"""Gate test for Phase 3 Dual-LLM Consensus."""

from tests.golden.eval_consensus import run_consensus_evaluation


def test_consensus_gate_metrics():
    """Verify Phase 3 consensus evaluation satisfies gate criteria."""
    metrics = run_consensus_evaluation()

    assert metrics["mistral_accuracy"] >= 0.85
    assert metrics["consensus_accuracy"] >= 0.85
    assert metrics["agreement_rate"] >= 0.70
    assert metrics["review_queue_size"] <= 10
    assert metrics["flagged_count"] == 20
