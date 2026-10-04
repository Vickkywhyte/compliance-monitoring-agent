"""Tests for the EBA source adapter (observable behavior only)."""
from __future__ import annotations

from pathlib import Path

import pytest

from compliance_agent.sources.eba import _parse_eba_html
from compliance_agent.exceptions import SourceParseError


FIXTURE_PATH = Path("tests/fixtures/raw/eba_sample.html")


def test_eba_parses_fixture() -> None:
    """Fixture HTML produces a document dict."""
    content = FIXTURE_PATH.read_bytes()
    doc = _parse_eba_html(content, fallback_url="https://example.com/")
    assert doc is not None


def test_eba_stable_id_is_canonical_url() -> None:
    """Stable ID is the canonical URL from <link rel='canonical'>."""
    content = FIXTURE_PATH.read_bytes()
    doc = _parse_eba_html(content, fallback_url="https://example.com/")
    assert doc["stable_id"] == "https://www.eba.europa.eu/regulation-and-policy/guidelines/gl-2024-01"


def test_eba_title_extracted() -> None:
    """Title is extracted from the h1 or page title."""
    content = FIXTURE_PATH.read_bytes()
    doc = _parse_eba_html(content, fallback_url="https://example.com/")
    assert "EBA Guidelines" in doc["title"]


def test_eba_content_non_empty() -> None:
    """Content field contains readable text."""
    content = FIXTURE_PATH.read_bytes()
    doc = _parse_eba_html(content, fallback_url="https://example.com/")
    assert len(doc["content"]) > 20


def test_eba_effective_date_parsed() -> None:
    """Effective date is parsed from .publication-date element."""
    content = FIXTURE_PATH.read_bytes()
    doc = _parse_eba_html(content, fallback_url="https://example.com/")
    assert doc["effective_date"] is not None
    assert str(doc["effective_date"]) == "2024-01-01"


def test_eba_fallback_to_source_url() -> None:
    """When no canonical link is present, fallback_url becomes the stable_id."""
    html = b"<html><head><title>No Canonical</title></head><body>content</body></html>"
    fallback = "https://example.com/test-page"
    doc = _parse_eba_html(html, fallback_url=fallback)
    assert doc["stable_id"] == fallback


def test_eba_no_canonical_no_fallback_raises() -> None:
    """When no canonical link and no fallback_url, SourceParseError is raised."""
    html = b"<html><body>no canonical</body></html>"
    with pytest.raises(SourceParseError):
        _parse_eba_html(html, fallback_url="")
