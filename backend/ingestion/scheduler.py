"""Legacy alias forwarding to backend.jobs.scheduler."""

from backend.jobs.scheduler import IngestionScheduler

__all__ = ["IngestionScheduler"]
