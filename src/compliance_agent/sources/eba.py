"""EBA source adapter — parses HTML with BeautifulSoup/html.parser (C-11).

Stable ID: canonical URL extracted from <link rel="canonical"> element.
Falls back to the source URL when no canonical link is present.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

from compliance_agent.exceptions import SourceParseError
from compliance_agent.sources.base import RawDocument, Source
from compliance_agent.storage.models import SourceType
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)

# Date formats found on EBA publication pages
_DATE_FORMATS = ("%d %B %Y", "%B %d, %Y", "%Y-%m-%d", "%d/%m/%Y")


def _parse_date(text: str | None) -> date | None:
    """Try known EBA date string formats, return None if none match."""
    if not text:
        return None
    text = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_eba_html(content: bytes, fallback_url: str = "") -> dict[str, Any]:
    """Parse an EBA publication HTML page into a single document dict.

    Uses html.parser (stdlib, no C extension required — safe for untrusted HTML).
    Raises SourceParseError for content that cannot be meaningfully parsed.
    """
    try:
        soup = BeautifulSoup(content, "html.parser")
    except Exception as exc:
        raise SourceParseError(f"EBA HTML parsing failed: {exc}") from exc

    # Stable ID: canonical URL
    canonical_el = soup.find("link", rel="canonical")
    if canonical_el and canonical_el.get("href"):
        stable_id = str(canonical_el["href"]).strip()
    else:
        stable_id = fallback_url

    if not stable_id:
        raise SourceParseError("EBA HTML: cannot determine stable_id (no canonical link and no fallback URL)")

    # Title: publication-title class, then h1, then page <title>
    title = ""
    for selector in [".publication-title", "h1", "title"]:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            break

    # Content: publication description or article body text
    content_text = ""
    for selector in [".publication-description", "article", "main", "body"]:
        el = soup.select_one(selector)
        if el:
            content_text = el.get_text(separator=" ", strip=True)
            break

    if not content_text:
        content_text = soup.get_text(separator=" ", strip=True)

    # Effective/publication date
    date_el = soup.select_one(".publication-date")
    effective_date = _parse_date(date_el.get_text(strip=True) if date_el else None)

    return {
        "stable_id": stable_id,
        "title": title,
        "content": content_text,
        "effective_date": effective_date,
    }


class EBASource(Source):
    """Fetches and parses EBA publication HTML pages."""

    @property
    def source_type(self) -> SourceType:
        return "eba"

    def fetch(self) -> list[RawDocument]:
        """Fetch EBA HTML page and return a single RawDocument."""
        result = self._fetcher.fetch(self._config.url, self.source_type, "html")
        doc = _parse_eba_html(result.content, fallback_url=self._config.url)

        raw_doc = RawDocument(
            source_type=self.source_type,
            stable_id=doc["stable_id"],
            title=doc["title"],
            content=doc["content"],
            raw_bytes=result.content,
            source_url=result.url,
            fetched_at=result.fetched_at,
            effective_date=doc["effective_date"],
        )

        _log.info(
            "eba_fetched",
            source=self._config.name,
            stable_id=doc["stable_id"],
        )
        return [raw_doc]
