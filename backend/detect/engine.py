"""Detection Engine orchestrating Keyword Filtering, Mistral Classification, and Graph Persistence."""

from typing import List, Optional
from backend.apigateway.adapters.llm import LLMAdapter
from backend.db.graph_repo import GraphRepo, graph_repo
from backend.detect.filter import KeywordFilter
from backend.schemas import DetectionResult, Item, RiskType


class DetectionEngine:
    """Orchestrates Phase 2 Detection workflow."""

    def __init__(
        self,
        llm: Optional[LLMAdapter] = None,
        graph: Optional[GraphRepo] = None,
        kfilter: Optional[KeywordFilter] = None,
    ):
        self.llm = llm or LLMAdapter()
        self.graph = graph or graph_repo
        self.kfilter = kfilter or KeywordFilter()

    def detect(self, item: Item) -> DetectionResult:
        """Evaluate item through keyword pre-filter and Mistral classifier, persisting to graph."""
        should_analyze, matched_keywords = self.kfilter.evaluate(item)

        if not should_analyze:
            # Fast-path for verified non-risk noise
            result = DetectionResult(
                company=item.company,
                source_url=item.source_url,
                date=item.published_at,
                risk_type=RiskType.NOISE,
                severity=0,
                confidence=0.99,
                topics=["other"],
                regulators=[],
                reason="Pre-filtered: benign corporate communication without risk indicators.",
            )
        else:
            # Full Mistral strict classification
            result = self.llm.classify_with_mistral(item)

        # Persist detection result and edges to Graph
        if self.graph:
            self.graph.upsert_detection(item, result)

        return result

    def detect_batch(self, items: List[Item]) -> List[DetectionResult]:
        """Detect risk across a list of items."""
        return [self.detect(item) for item in items]


detection_engine = DetectionEngine()
