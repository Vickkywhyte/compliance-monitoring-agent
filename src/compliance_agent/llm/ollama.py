"""Ollama local LLM backend — fallback when OpenRouter is rate-limited (ADR-004)."""
from __future__ import annotations

import time

import httpx
import structlog

from compliance_agent.config.loader import get_settings, load_agent_config
from compliance_agent.exceptions import LLMUnavailableError

from .backends import LLMBackend, LLMResponse

log = structlog.get_logger(__name__)


class OllamaBackend(LLMBackend):
    """Calls a local Ollama instance via its /api/generate endpoint."""

    def __init__(self, model: str | None = None) -> None:
        cfg = load_agent_config()
        self._model = model or cfg.llm.fallback_model
        self._base_url = get_settings().ollama_base_url.rstrip("/")

    @property
    def backend_name(self) -> str:
        return f"ollama/{self._model}"

    def complete(self, prompt: str, *, temperature: float, max_tokens: int) -> LLMResponse:
        url = f"{self._base_url}/api/generate"
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        t0 = time.monotonic()
        try:
            resp = httpx.post(url, json=payload, timeout=60)
            latency_ms = (time.monotonic() - t0) * 1000
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(
                f"Ollama not reachable at {self._base_url}. "
                "Start Ollama with `ollama serve` or set OLLAMA_BASE_URL."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUnavailableError(
                f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMUnavailableError(f"Ollama request error: {exc}") from exc

        data = resp.json()
        return LLMResponse(
            text=data.get("response", ""),
            model=self._model,
            tokens_in=data.get("prompt_eval_count", 0),
            tokens_out=data.get("eval_count", 0),
            cost_usd=0.0,
            latency_ms=latency_ms,
        )
