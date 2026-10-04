"""Abstract base class for LLM backends and the LLMResponse data model."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Structured response returned by every LLM backend."""

    model_config = {"extra": "forbid"}

    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float


class LLMBackend(ABC):
    """Abstract base for all LLM backends (ADR-004)."""

    @abstractmethod
    def complete(self, prompt: str, *, temperature: float, max_tokens: int) -> LLMResponse:
        """Send a completion request; return a structured response."""
        ...

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Stable name used in logging and stored in Summary/ProcessMapping.model."""
        ...
