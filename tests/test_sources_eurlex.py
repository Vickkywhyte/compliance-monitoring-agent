"""Tests for the EUR-Lex source adapter (observable behavior only)."""
from __future__ import annotations

from pathlib import Path

import pytest

from compliance_agent.sources.eurlex import _parse_eurlex_xml
from compliance_agent.exceptions import SourceParseError


FIXTURE_PATH = Path("tests/fixtures/raw/eurlex_sample.xml")


def test_eurlex_parses_fixture() -> None:
    """Fixture XML produces exactly one document."""
    content = FIXTURE_PATH.read_bytes()
    docs = _parse_eurlex_xml(content)
    assert len(docs) == 1


def test_eurlex_stable_id_is_celex() -> None:
    """Stable ID extracted from CELEX element matches expected pattern."""
    content = FIXTURE_PATH.read_bytes()
    docs = _parse_eurlex_xml(content)
    assert docs[0]["stable_id"] == "32024R0001"


def test_eurlex_title_extracted() -> None:
    """Document title is non-empty."""
    content = FIXTURE_PATH.read_bytes()
    docs = _parse_eurlex_xml(content)
    assert docs[0]["title"].strip() != ""


def test_eurlex_content_extracted() -> None:
    """Document content is non-empty."""
    content = FIXTURE_PATH.read_bytes()
    docs = _parse_eurlex_xml(content)
    assert docs[0]["content"].strip() != ""


def test_eurlex_effective_date_parsed() -> None:
    """Effective date is parsed from EFFECTIVE_DATE element."""
    content = FIXTURE_PATH.read_bytes()
    docs = _parse_eurlex_xml(content)
    eff = docs[0]["effective_date"]
    assert eff is not None
    assert str(eff) == "2024-02-01"


def test_eurlex_invalid_celex_skipped() -> None:
    """Notices with invalid CELEX numbers are skipped, not raised."""
    xml = b"""<?xml version="1.0"?>
    <RESULTS>
      <NOTICE><CELEX>INVALID</CELEX><TITLE>x</TITLE><CONTENTS>y</CONTENTS></NOTICE>
    </RESULTS>"""
    docs = _parse_eurlex_xml(xml)
    assert docs == []


def test_eurlex_missing_celex_skipped() -> None:
    """Notices with no CELEX element are skipped silently."""
    xml = b"""<?xml version="1.0"?>
    <RESULTS>
      <NOTICE><TITLE>No CELEX</TITLE><CONTENTS>stuff</CONTENTS></NOTICE>
    </RESULTS>"""
    docs = _parse_eurlex_xml(xml)
    assert docs == []


def test_eurlex_malformed_xml_raises() -> None:
    """Malformed XML raises SourceParseError."""
    with pytest.raises(SourceParseError):
        _parse_eurlex_xml(b"<not valid xml at all <<<")
