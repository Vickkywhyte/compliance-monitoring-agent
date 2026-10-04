"""Rate-limiting utilities: token bucket and exponential backoff.

Used by the LLM gateway (Phase 4) to enforce concurrency and retry budgets.
"""
from __future__ import annotations

import math
import random
import threading
import time


class TokenBucket:
    """Thread-safe token bucket for rate limiting.

    Tokens replenish at `rate` per second up to `capacity`.
    """

    def __init__(self, rate: float, capacity: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Add tokens accrued since the last refill (call with lock held)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume `tokens` without blocking.

        Returns True if tokens were consumed, False if insufficient.
        """
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_for_token(self, tokens: float = 1.0) -> float:
        """Block until `tokens` are available, then consume them.

        Returns the number of seconds waited.
        """
        start = time.monotonic()
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return time.monotonic() - start
            # Sleep for the approximate time until enough tokens accrue
            with self._lock:
                deficit = tokens - self._tokens
            time.sleep(max(0.001, deficit / self._rate))


def exponential_backoff(
    attempt: int,
    initial_ms: int = 500,
    max_ms: int = 30_000,
    jitter: bool = True,
) -> float:
    """Compute exponential backoff delay in seconds.

    Args:
        attempt:    Zero-indexed attempt number (0 = first retry).
        initial_ms: Base delay in milliseconds.
        max_ms:     Maximum delay in milliseconds.
        jitter:     If True, add uniform random jitter up to ±25%.

    Returns:
        Delay in seconds.
    """
    delay_ms = min(initial_ms * (2**attempt), max_ms)
    if jitter:
        jitter_range = delay_ms * 0.25
        delay_ms += random.uniform(-jitter_range, jitter_range)
    return max(0.0, delay_ms / 1000.0)


if __name__ == "__main__":
    print("=== utils/ratelimit self-test ===")

    bucket = TokenBucket(rate=10.0, capacity=5.0)
    consumed = [bucket.consume() for _ in range(5)]
    assert all(consumed), "should consume 5 tokens from a full bucket"
    assert not bucket.consume(), "bucket should be empty now"
    print(f"  TokenBucket consume: OK (5 tokens consumed, 6th rejected)")

    # Wait for partial refill
    time.sleep(0.15)
    assert bucket.consume(), "bucket should have refilled slightly"
    print("  TokenBucket refill: OK")

    b0 = exponential_backoff(0, initial_ms=100, max_ms=10000, jitter=False)
    b1 = exponential_backoff(1, initial_ms=100, max_ms=10000, jitter=False)
    b2 = exponential_backoff(2, initial_ms=100, max_ms=10000, jitter=False)
    assert math.isclose(b0, 0.1), f"expected 0.1s, got {b0}"
    assert math.isclose(b1, 0.2), f"expected 0.2s, got {b1}"
    assert math.isclose(b2, 0.4), f"expected 0.4s, got {b2}"
    print(f"  exponential_backoff: {b0:.2f}s / {b1:.2f}s / {b2:.2f}s")

    bmax = exponential_backoff(20, initial_ms=100, max_ms=1000, jitter=False)
    assert math.isclose(bmax, 1.0), f"expected cap at 1.0s, got {bmax}"
    print(f"  backoff cap: {bmax:.2f}s")

    print("PASS")
