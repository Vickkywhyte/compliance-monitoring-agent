"""LLM gateway: concurrency-limited, retried, with Ollama fallback (ADR-014).

Concurrency: threading.Semaphore(max_concurrent) limits simultaneous calls.
Queue: in_flight counter rejects requests once queue_max_size is reached.
Backoff: exponential with ±20% jitter, 500 ms → 30 s, only on 429/503.
Fallback: after fallback_after_consecutive_429 consecutive 429s, routes to
          Ollama for _FALLBACK_DURATION_S seconds then retries primary.
"""
from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timedelta, timezone

import structlog

from compliance_agent.config.models import GatewayConfig, LLMConfig
from compliance_agent.exceptions import LLMError, LLMUnavailableError, RateLimitError

from .backends import LLMBackend, LLMResponse

log = structlog.get_logger(__name__)

_FALLBACK_DURATION_S = 300  # 5 minutes
_MAX_ATTEMPTS = 10


class LLMGateway:
    """Thread-safe LLM gateway with rate limiting, retries, and backend fallback."""

    def __init__(
        self,
        primary: LLMBackend,
        fallback: LLMBackend | None,
        llm_config: LLMConfig,
        gateway_config: GatewayConfig,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._llm_cfg = llm_config
        self._gw_cfg = gateway_config
        self._semaphore = threading.Semaphore(gateway_config.max_concurrent)
        self._lock = threading.Lock()
        self._in_flight: int = 0
        self._consecutive_429: int = 0
        self._fallback_until: datetime | None = None

    @property
    def in_flight(self) -> int:
        """Current number of requests active + waiting (for monitoring)."""
        with self._lock:
            return self._in_flight

    def complete(self, prompt: str) -> LLMResponse:
        """Route a prompt through the gateway; apply rate limiting and retry."""
        with self._lock:
            if self._in_flight >= self._gw_cfg.queue_max_size:
                raise RateLimitError(
                    f"LLM gateway queue full (max={self._gw_cfg.queue_max_size})"
                )
            self._in_flight += 1

        try:
            self._semaphore.acquire()
            try:
                return self._dispatch(prompt)
            finally:
                self._semaphore.release()
        finally:
            with self._lock:
                self._in_flight -= 1

    # ── Internal ──────────────────────────────────────────────────────────────

    def _dispatch(self, prompt: str) -> LLMResponse:
        """Select backend and execute with retry+backoff on 429/503."""
        backoff_ms = self._gw_cfg.backoff_initial_ms

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            backend = self._select_backend()
            try:
                resp = backend.complete(
                    prompt,
                    temperature=self._llm_cfg.temperature,
                    max_tokens=self._llm_cfg.max_tokens,
                )
                with self._lock:
                    self._consecutive_429 = 0
                log.info(
                    "llm_call_success",
                    backend=backend.backend_name,
                    attempt=attempt,
                    tokens_in=resp.tokens_in,
                    tokens_out=resp.tokens_out,
                    latency_ms=round(resp.latency_ms, 1),
                )
                return resp
            except LLMError as exc:
                status = _extract_status_code(exc)
                if status in (429, 503):
                    self._record_429()
                    jitter = random.uniform(0.8, 1.2)
                    sleep_s = (backoff_ms * jitter) / 1000
                    log.warning(
                        "llm_rate_limited",
                        backend=backend.backend_name,
                        status=status,
                        attempt=attempt,
                        sleep_s=round(sleep_s, 3),
                        consecutive_429=self._consecutive_429,
                    )
                    time.sleep(sleep_s)
                    backoff_ms = min(backoff_ms * 2, self._gw_cfg.backoff_max_ms)
                else:
                    raise  # fail fast on non-retryable errors

        raise LLMUnavailableError(f"Gateway exhausted {_MAX_ATTEMPTS} retries")

    def _record_429(self) -> None:
        """Increment 429 counter and arm fallback if threshold reached."""
        with self._lock:
            self._consecutive_429 += 1
            if (
                self._consecutive_429 >= self._gw_cfg.fallback_after_consecutive_429
                and self._fallback is not None
                and self._fallback_until is None
            ):
                self._fallback_until = datetime.now(timezone.utc) + timedelta(
                    seconds=_FALLBACK_DURATION_S
                )
                log.warning(
                    "llm_switching_to_fallback",
                    until=self._fallback_until.isoformat(),
                    backend=self._fallback.backend_name,
                )

    def _select_backend(self) -> LLMBackend:
        """Return the fallback backend when in the fallback window, else primary."""
        with self._lock:
            if self._fallback is not None and self._fallback_until is not None:
                now = datetime.now(timezone.utc)
                if now < self._fallback_until:
                    return self._fallback
                # Window expired — return to primary
                self._fallback_until = None
                self._consecutive_429 = 0
                log.info("llm_returning_to_primary", backend=self._primary.backend_name)
        return self._primary


def _extract_status_code(exc: LLMError) -> int | None:
    """Parse the first recognisable HTTP status code from an LLMError message."""
    msg = str(exc)
    for code in (429, 503, 500, 400, 401, 403, 404):
        if str(code) in msg:
            return code
    return None
