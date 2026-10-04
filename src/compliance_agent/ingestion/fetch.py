"""HTTP fetcher with retry, size limit, and fixture-mode support (C-12, C-38).

Fetcher is the only place that makes outbound HTTP requests in the ingestion
layer. It caches raw content to data/raw/{source_type}/{timestamp}.{ext}.
Fixture mode loads from tests/fixtures/raw/{source_type}_sample.{ext} instead.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx

from compliance_agent.exceptions import IngestError
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)

# 50 MB hard limit on any single response (C-12)
MAX_SIZE_BYTES = 50 * 1024 * 1024

# Only alphanumeric, hyphen, and underscore are safe in cache directory names (C-38)
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class FetchResult:
    """Result of a single HTTP fetch operation."""

    url: str
    content: bytes
    status_code: int
    fetched_at: datetime
    content_type: str
    cached_path: Path | None


def _validate_safe_name(name: str) -> None:
    """Raise IngestError if name contains path-traversal characters (C-38, C-39)."""
    if not _SAFE_NAME_RE.match(name):
        raise IngestError(
            f"Unsafe source name for cache path: {name!r}. "
            "Only [a-zA-Z0-9_-] is permitted."
        )


def _exponential_backoff(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Return wait time in seconds for exponential backoff (capped at 30 s)."""
    return min(base * (2**attempt), cap)


class Fetcher:
    """HTTP fetcher with retry, size enforcement, and disk caching.

    Pass fixture_dir to load from disk instead of making HTTP requests.
    fixture_dir is expected to contain files named {source_type}_sample.{ext}.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        cache_dir: Path | str = Path("data/raw"),
        fixture_dir: Path | str | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache_dir = Path(cache_dir)
        self._fixture_dir = Path(fixture_dir) if fixture_dir else None

    def fetch(self, url: str, source_type: str, ext: str = "xml") -> FetchResult:
        """Fetch URL (or load fixture) and return a FetchResult.

        source_type is used for both cache directory and fixture filename lookup.
        """
        _validate_safe_name(source_type)

        if self._fixture_dir:
            return self._load_fixture(source_type, ext)
        return self._fetch_with_retry(url, source_type, ext)

    # ── Fixture loading ──────────────────────────────────────────────────────

    def _load_fixture(self, source_type: str, ext: str) -> FetchResult:
        fixture_path = self._fixture_dir / f"{source_type}_sample.{ext}"  # type: ignore[operator]
        if not fixture_path.exists():
            raise IngestError(
                f"Fixture file not found: {fixture_path}. "
                "Run tests from the repository root so the relative path resolves."
            )
        content = fixture_path.read_bytes()
        _log.debug("fixture_loaded", path=str(fixture_path), size=len(content))
        return FetchResult(
            url=str(fixture_path),
            content=content,
            status_code=200,
            fetched_at=datetime.now().astimezone(),
            content_type="text/html" if ext == "html" else "application/xml",
            cached_path=None,
        )

    # ── HTTP fetch with retry ────────────────────────────────────────────────

    def _fetch_with_retry(self, url: str, source_type: str, ext: str) -> FetchResult:
        _retryable = (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                result = self._do_single_fetch(url, source_type, ext)
                return result
            except _retryable as exc:
                last_exc = exc
                _log.warning(
                    "fetch_transient_error",
                    url=url,
                    attempt=attempt + 1,
                    error=str(exc),
                )
            except IngestError as exc:
                # 4xx and oversized responses are not retried
                if "4" in str(exc)[:5] or "too large" in str(exc):
                    raise
                last_exc = exc
                _log.warning(
                    "fetch_server_error",
                    url=url,
                    attempt=attempt + 1,
                    error=str(exc),
                )

            if attempt < self._max_retries - 1:
                delay = _exponential_backoff(attempt)
                _log.debug("fetch_backoff", seconds=delay, attempt=attempt + 1)
                time.sleep(delay)

        raise IngestError(
            f"All {self._max_retries} fetch attempts failed for {url}: {last_exc}"
        ) from last_exc

    def _do_single_fetch(self, url: str, source_type: str, ext: str) -> FetchResult:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url, follow_redirects=True)

        if 400 <= resp.status_code < 500:
            raise IngestError(f"HTTP {resp.status_code} client error for {url}")
        if resp.status_code >= 500:
            raise IngestError(f"HTTP {resp.status_code} server error for {url}")

        content = resp.content
        if len(content) > MAX_SIZE_BYTES:
            raise IngestError(
                f"Response too large: {len(content):,} bytes (limit {MAX_SIZE_BYTES:,})"
            )

        cached_path = self._cache_content(content, source_type, ext)
        return FetchResult(
            url=url,
            content=content,
            status_code=resp.status_code,
            fetched_at=datetime.now().astimezone(),
            content_type=resp.headers.get("content-type", ""),
            cached_path=cached_path,
        )

    def _cache_content(self, content: bytes, source_type: str, ext: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        target_dir = self._cache_dir / source_type
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{ts}.{ext}"
        path.write_bytes(content)
        _log.debug("fetch_cached", path=str(path), size=len(content))
        return path
