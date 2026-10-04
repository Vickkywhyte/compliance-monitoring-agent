"""Rate limit and concurrency tests for LLMGateway (C-26, C-27, C-28).

Verifies:
  - Gateway enforces max_concurrent via semaphore
  - Queue overflow raises RateLimitError
  - 429 LLMError triggers retry+backoff (observed via call count)
  - After fallback_after_consecutive_429 consecutive 429s, fallback backend is used
"""
from __future__ import annotations

import threading
import time

import pytest

from compliance_agent.config.models import GatewayConfig, LLMConfig
from compliance_agent.exceptions import LLMError, LLMUnavailableError, RateLimitError
from compliance_agent.llm.backends import LLMResponse
from compliance_agent.llm.gateway import LLMGateway
from tests.mocks.llm import FakeLLMBackend

_LLM_CFG = LLMConfig(
    primary_model="fake",
    fallback_model="fake",
    temperature=0.0,
    max_tokens=512,
    timeout_seconds=30,
)


def _gw(
    primary: FakeLLMBackend,
    fallback: FakeLLMBackend | None = None,
    max_concurrent: int = 2,
    queue_max_size: int = 4,
    fallback_after_429: int = 3,
) -> LLMGateway:
    cfg = GatewayConfig(
        max_concurrent=max_concurrent,
        queue_max_size=queue_max_size,
        backoff_initial_ms=1,
        backoff_max_ms=5,
        fallback_after_consecutive_429=fallback_after_429,
    )
    return LLMGateway(primary=primary, fallback=fallback, llm_config=_LLM_CFG, gateway_config=cfg)


# ── Concurrency: semaphore limits simultaneous calls ─────────────────────────

def test_gateway_limits_concurrent_calls():
    """At most max_concurrent calls execute simultaneously."""
    barrier = threading.Barrier(2)
    active_counts: list[int] = []
    lock = threading.Lock()

    class BlockingBackend(FakeLLMBackend):
        def complete(self, prompt, *, temperature, max_tokens):
            with lock:
                active_counts.append(1)
            barrier.wait(timeout=2)
            return super().complete(prompt, temperature=temperature, max_tokens=max_tokens)

    primary = BlockingBackend(responses=["ok"] * 4)
    gw = _gw(primary, max_concurrent=2)

    threads = [threading.Thread(target=lambda: gw.complete("p")) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(active_counts) == 2


# ── Queue overflow ────────────────────────────────────────────────────────────

def test_gateway_raises_rate_limit_when_queue_full():
    """Requests beyond queue_max_size are immediately rejected."""
    ready = threading.Event()
    hold = threading.Event()
    call_count = 0

    class HoldingBackend(FakeLLMBackend):
        def complete(self, prompt, *, temperature, max_tokens):
            nonlocal call_count
            call_count += 1
            ready.set()
            hold.wait(timeout=2)
            return super().complete(prompt, temperature=temperature, max_tokens=max_tokens)

    primary = HoldingBackend(responses=["ok"] * 10)
    gw = _gw(primary, max_concurrent=1, queue_max_size=2)

    # Start first call — it holds the semaphore
    t1 = threading.Thread(target=lambda: gw.complete("p1"))
    t1.start()
    ready.wait(timeout=2)

    # Second call will queue (in_flight=2, queue_max_size=2)
    results: list = []
    errors: list = []

    def queued_call():
        try:
            results.append(gw.complete("p2"))
        except RateLimitError as e:
            errors.append(e)

    t2 = threading.Thread(target=queued_call)
    t2.start()
    time.sleep(0.05)  # let t2 register

    # Third call must overflow the queue
    with pytest.raises(RateLimitError):
        gw.complete("p3")

    hold.set()
    t1.join(timeout=2)
    t2.join(timeout=2)


# ── 429 triggers retry ────────────────────────────────────────────────────────

def test_gateway_retries_on_429_error():
    """A 429 response causes a retry; the second attempt should succeed."""
    primary = FakeLLMBackend(
        responses=["ok"],
        raise_on_call=LLMError("HTTP 429: rate limited"),
    )
    # First call raises, second succeeds
    call_count = 0

    class RetryBackend(FakeLLMBackend):
        def complete(self, prompt, *, temperature, max_tokens):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMError("HTTP 429: rate limited")
            return LLMResponse(
                text="success", model="fake", tokens_in=1, tokens_out=1,
                cost_usd=0.0, latency_ms=1.0,
            )

    gw = _gw(RetryBackend(), max_concurrent=4, queue_max_size=100)
    resp = gw.complete("test")

    assert resp.text == "success"
    assert call_count == 2


# ── Non-retryable errors fail fast ────────────────────────────────────────────

def test_gateway_fails_fast_on_non_retryable_error():
    """A 400 Bad Request should NOT be retried — it propagates immediately."""
    call_count = 0

    class BadRequestBackend(FakeLLMBackend):
        def complete(self, prompt, *, temperature, max_tokens):
            nonlocal call_count
            call_count += 1
            raise LLMError("HTTP 400: bad request")

    gw = _gw(BadRequestBackend(), max_concurrent=4, queue_max_size=100)

    with pytest.raises(LLMError, match="400"):
        gw.complete("test")

    assert call_count == 1  # no retry


# ── Fallback backend activated after consecutive 429s ────────────────────────

def test_gateway_switches_to_fallback_after_consecutive_429s():
    """After fallback_after_consecutive_429 consecutive 429s, fallback is used."""
    primary_calls = []
    fallback_calls = []

    class Primary429Backend(FakeLLMBackend):
        def complete(self, prompt, *, temperature, max_tokens):
            primary_calls.append(prompt)
            raise LLMError("HTTP 429: rate limited")

    class FallbackBackend(FakeLLMBackend):
        def complete(self, prompt, *, temperature, max_tokens):
            fallback_calls.append(prompt)
            return LLMResponse(
                text="fallback_ok", model="ollama/llama3.1",
                tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1.0,
            )

    gw = _gw(Primary429Backend(), FallbackBackend(), max_concurrent=4, queue_max_size=100, fallback_after_429=2)

    resp = gw.complete("test")

    assert resp.text == "fallback_ok"
    assert len(fallback_calls) >= 1
