"""OpenRouter LLM backend — free-tier primary (ADR-004)."""
from __future__ import annotations

import time

import httpx
import structlog

from compliance_agent.config.loader import get_settings, load_agent_config
from compliance_agent.exceptions import LLMError

from .backends import LLMBackend, LLMResponse

log = structlog.get_logger(__name__)

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterBackend(LLMBackend):
    """Calls the OpenRouter OpenAI-compatible chat completions API."""

    def __init__(self, model: str | None = None, timeout_s: int | None = None) -> None:
        cfg = load_agent_config()
        self._model = model or cfg.llm.primary_model
        self._timeout = timeout_s or cfg.llm.timeout_seconds

    @property
    def backend_name(self) -> str:
        return f"openrouter/{self._model}"

    def complete(self, prompt: str, *, temperature: float, max_tokens: int) -> LLMResponse:
        api_key = get_settings().openrouter_api_key
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY is not set; cannot call OpenRouter")

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        t0 = time.monotonic()
        try:
            resp = httpx.post(_ENDPOINT, json=payload, headers=headers, timeout=self._timeout)
            latency_ms = (time.monotonic() - t0) * 1000
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"OpenRouter HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMError(f"OpenRouter request error: {exc}") from exc

        data = resp.json()
        choice = data["choices"][0]
        text = choice["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            text=text,
            model=self._model,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            cost_usd=0.0,
            latency_ms=latency_ms,
        )
