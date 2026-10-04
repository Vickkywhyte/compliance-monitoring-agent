"""Source ABC and RawDocument intermediate representation.

Every regulatory source adapter inherits from Source and implements fetch().
The fetch() method returns RawDocument instances; the ingestion orchestrator
then normalizes these into RegulatoryDocument records.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from compliance_agent.config.models import SourceConfig
from compliance_agent.storage.models import SourceType


@dataclass
class RawDocument:
    """Parsed intermediate document before normalization to RegulatoryDocument."""

    source_type: SourceType
    stable_id: str
    title: str
    content: str
    raw_bytes: bytes
    source_url: str
    fetched_at: datetime
    effective_date: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Source(ABC):
    """Abstract base class for all regulatory source adapters."""

    def __init__(self, config: SourceConfig, fetcher: Any) -> None:
        self._config = config
        self._fetcher = fetcher

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Return the controlled-vocabulary source type string."""

    @abstractmethod
    def fetch(self) -> list[RawDocument]:
        """Fetch and parse documents from this source.

        Returns a list of RawDocument instances ready for normalization.
        Raises IngestError on HTTP failure; SourceParseError on malformed content.
        """
