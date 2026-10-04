"""Regulatory source adapters (Phase 2 — ingestion layer)."""
from compliance_agent.sources.base import RawDocument, Source
from compliance_agent.sources.registry import build_sources

__all__ = ["RawDocument", "Source", "build_sources"]
