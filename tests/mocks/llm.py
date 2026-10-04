"""Fake LLM backend for unit tests (Lesson 3: assert observable behavior).

FakeLLMBackend replaces real network calls with pre-configured responses.
Tests assert on Summary/ProcessMapping records stored in the DB, not on
whether mock methods were called.
"""
from __future__ import annotations

from compliance_agent.llm.backends import LLMBackend, LLMResponse


class FakeLLMBackend(LLMBackend):
    """Returns pre-configured text responses in order; records all prompts."""

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        raise_on_call: Exception | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._raise = raise_on_call
        self.calls: list[str] = []
        self._index = 0

    @property
    def backend_name(self) -> str:
        return "fake"

    def complete(self, prompt: str, *, temperature: float, max_tokens: int) -> LLMResponse:
        self.calls.append(prompt)
        if self._raise is not None:
            raise self._raise
        if self._index < len(self._responses):
            text = self._responses[self._index]
            self._index += 1
        else:
            text = '{"text": "Default summary.", "citations": [], "confidence": 0.5}'
        return LLMResponse(
            text=text,
            model="fake",
            tokens_in=10,
            tokens_out=10,
            cost_usd=0.0,
            latency_ms=1.0,
        )

    def reset(self) -> None:
        """Reset call history and response index for test reuse."""
        self.calls.clear()
        self._index = 0
