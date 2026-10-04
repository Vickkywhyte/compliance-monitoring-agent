"""Parser security tests: XXE, billion laughs, oversized content, path traversal (C-10, C-11, C-12, C-38).

These tests verify that the parsers and fetcher reject malicious or
oversized inputs before any processing occurs.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from compliance_agent.exceptions import IngestError, SourceParseError
from compliance_agent.ingestion.fetch import MAX_SIZE_BYTES, Fetcher, _validate_safe_name
from compliance_agent.sources.eurlex import _parse_eurlex_xml
from compliance_agent.sources.sanctions import _parse_sanctions_xml


# ── C-10: defusedxml blocks XXE and entity attacks ──────────────────────────


def test_xxe_in_eurlex_xml_is_rejected() -> None:
    """XXE attempt in EUR-Lex XML is rejected by defusedxml (C-10)."""
    xxe_xml = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b"<RESULTS><NOTICE><CELEX>&xxe;</CELEX></NOTICE></RESULTS>"
    )
    with pytest.raises(SourceParseError):
        _parse_eurlex_xml(xxe_xml)


def test_xxe_in_sanctions_xml_is_rejected() -> None:
    """XXE attempt in Sanctions XML is rejected by defusedxml (C-10)."""
    xxe_xml = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b"<export><sanctionEntity id='1' euReferenceNumber='EU.1' logicalId='L1'>&xxe;</sanctionEntity></export>"
    )
    with pytest.raises(SourceParseError):
        _parse_sanctions_xml(xxe_xml)


def test_billion_laughs_in_eurlex_xml_is_rejected() -> None:
    """Billion laughs entity expansion in EUR-Lex XML is rejected (C-10)."""
    billion_laughs = (
        b'<?xml version="1.0"?>'
        b"<!DOCTYPE lolz ["
        b'  <!ENTITY lol "lol">'
        b'  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        b'  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        b"]>"
        b"<RESULTS><NOTICE><CELEX>&lol3;</CELEX></NOTICE></RESULTS>"
    )
    with pytest.raises(SourceParseError):
        _parse_eurlex_xml(billion_laughs)


def test_billion_laughs_in_sanctions_xml_is_rejected() -> None:
    """Billion laughs entity expansion in Sanctions XML is rejected (C-10)."""
    billion_laughs = (
        b'<?xml version="1.0"?>'
        b"<!DOCTYPE lolz ["
        b'  <!ENTITY lol "lol">'
        b'  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        b"]>"
        b"<export>&lol2;</export>"
    )
    with pytest.raises(SourceParseError):
        _parse_sanctions_xml(billion_laughs)


# ── C-11: BeautifulSoup handles malformed HTML without crashing ─────────────


def test_malformed_html_does_not_crash() -> None:
    """Severely malformed HTML is handled gracefully by BeautifulSoup (C-11)."""
    from compliance_agent.sources.eba import _parse_eba_html

    malformed = b"<html><head><title>Test</title><body><p>unclosed"
    doc = _parse_eba_html(malformed, fallback_url="https://example.com/test")
    # Must not raise; fallback_url used as stable_id
    assert doc["stable_id"] == "https://example.com/test"


def test_html_with_script_injection_does_not_execute() -> None:
    """Script tags in HTML content are not executed (parsed as text only) (C-11)."""
    from compliance_agent.sources.eba import _parse_eba_html

    html = (
        b"<html><head><link rel='canonical' href='https://example.com/doc'/></head>"
        b"<body><script>alert('xss')</script><p>safe content</p></body></html>"
    )
    doc = _parse_eba_html(html, fallback_url="https://example.com/doc")
    # Script content may appear as text but the parse must not raise or execute code
    assert doc is not None
    assert doc["stable_id"] == "https://example.com/doc"


# ── C-12: Fetcher rejects responses over 50 MB ──────────────────────────────


def test_oversized_response_raises_ingest_error(tmp_path: Path) -> None:
    """Responses larger than 50 MB are rejected before processing (C-12)."""
    large_content = b"x" * (MAX_SIZE_BYTES + 1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = large_content
    mock_response.headers = {"content-type": "application/xml"}

    fetcher = Fetcher(cache_dir=tmp_path)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        with pytest.raises(IngestError, match="too large"):
            fetcher.fetch("https://example.com/huge.xml", "eurlex", "xml")


def test_response_at_size_limit_is_accepted(tmp_path: Path) -> None:
    """Responses exactly at the 50 MB limit are accepted."""
    exact_content = b"x" * MAX_SIZE_BYTES

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = exact_content
    mock_response.headers = {"content-type": "application/xml"}

    fetcher = Fetcher(cache_dir=tmp_path)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = fetcher.fetch("https://example.com/ok.xml", "eurlex", "xml")
        assert result.status_code == 200


# ── C-38, C-39: Path traversal in source names is rejected ──────────────────


def test_path_traversal_in_source_name_is_rejected() -> None:
    """Source names with ../ or path separators raise IngestError (C-38, C-39)."""
    for dangerous_name in ["../etc/passwd", "../../root", "foo/bar", "test\x00null"]:
        with pytest.raises(IngestError, match="Unsafe source name"):
            _validate_safe_name(dangerous_name)


def test_safe_source_names_are_accepted() -> None:
    """Valid source names (alphanumeric + hyphen + underscore) are accepted."""
    for safe_name in ["eurlex", "eu_sanctions", "eba-rss", "source123"]:
        _validate_safe_name(safe_name)  # Must not raise


def test_fixture_path_traversal_via_fetcher(tmp_path: Path) -> None:
    """Fetcher rejects source_type containing path traversal characters."""
    fetcher = Fetcher(fixture_dir=Path("tests/fixtures/raw"))
    with pytest.raises(IngestError, match="Unsafe source name"):
        fetcher.fetch("https://example.com/x.xml", "../../../etc/passwd", "xml")
