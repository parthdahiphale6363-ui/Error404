"""Legacy alias forwarding to backend.ingest.pipeline."""

from backend.ingest.pipeline import IngestionPipeline, InMemoryItemStore, COMPANY_METADATA, item_store

__all__ = ["IngestionPipeline", "InMemoryItemStore", "COMPANY_METADATA", "item_store"]
