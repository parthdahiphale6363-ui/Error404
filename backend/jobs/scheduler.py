"""Ingestion Scheduler.

Coordinates periodic ingestion runs:
- Finnhub: every 60s
- CFPB: every 900s (15 min)
- SEC EDGAR: every 900s (15 min)
"""

from datetime import datetime, timezone
import logging
import threading
import time
from typing import Dict, Optional

from backend.ingest.pipeline import IngestionPipeline, COMPANY_METADATA

logger = logging.getLogger("jobs.scheduler")


class IngestionScheduler:
    """Configures and runs periodic ingestion tasks."""

    DEFAULT_INTERVALS = {
        "finnhub": 60,     # 60 seconds
        "cfpb": 900,       # 15 minutes (900s)
        "edgar": 900,      # 15 minutes (900s)
    }

    def __init__(
        self,
        pipeline: Optional[IngestionPipeline] = None,
        intervals: Optional[Dict[str, int]] = None,
    ):
        self.pipeline = pipeline or IngestionPipeline()
        self.intervals = dict(intervals or self.DEFAULT_INTERVALS)
        self.last_run: Dict[str, float] = {
            "finnhub": 0.0,
            "cfpb": 0.0,
            "edgar": 0.0,
        }
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def get_intervals(self) -> Dict[str, int]:
        """Return configured intervals in seconds."""
        return dict(self.intervals)

    def run_provider_ingest(self, provider: str) -> int:
        """Run single ingestion pass for a provider across all companies."""
        total_new = 0
        for company in COMPANY_METADATA.keys():
            if provider == "finnhub":
                new_items = self.pipeline.ingest_finnhub(company)
            elif provider == "cfpb":
                new_items = self.pipeline.ingest_cfpb(company, has_narrative=True)
            elif provider == "edgar":
                new_items = self.pipeline.ingest_edgar(company)
            else:
                new_items = []
            total_new += len(new_items)

        self.last_run[provider] = time.time()
        logger.info("Ingestion completed for %s: %d new items", provider, total_new)
        return total_new

    def tick(self) -> Dict[str, int]:
        """Evaluate due tasks and execute them."""
        now = time.time()
        results: Dict[str, int] = {}

        for provider, interval in self.intervals.items():
            elapsed = now - self.last_run.get(provider, 0.0)
            if elapsed >= interval:
                count = self.run_provider_ingest(provider)
                results[provider] = count

        return results

    def start_background(self, poll_interval_sec: float = 1.0):
        """Start scheduler in a background thread."""
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                try:
                    self.tick()
                except Exception as e:
                    logger.error("Error in scheduler cycle: %s", e)
                time.sleep(poll_interval_sec)

        self._thread = threading.Thread(target=_loop, daemon=True, name="IngestionScheduler")
        self._thread.start()

    def stop_background(self):
        """Stop background scheduler thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = IngestionScheduler()
    print("Running initial ingestion tick...")
    res = scheduler.tick()
    print(f"Ingestion results: {res}")
