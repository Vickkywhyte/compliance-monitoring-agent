"""Tests for the EU Sanctions source adapter (observable behavior only)."""
from __future__ import annotations

from pathlib import Path

import pytest

from compliance_agent.sources.sanctions import _parse_sanctions_xml
from compliance_agent.exceptions import SourceParseError


FIXTURE_PATH = Path("tests/fixtures/raw/sanctions_sample.xml")


def test_sanctions_parses_fixture() -> None:
    """Fixture XML produces exactly one entity."""
    content = FIXTURE_PATH.read_bytes()
    entities = _parse_sanctions_xml(content)
    assert len(entities) == 1


def test_sanctions_stable_id_is_eu_reference() -> None:
    """Stable ID is the euReferenceNumber attribute."""
    content = FIXTURE_PATH.read_bytes()
    entities = _parse_sanctions_xml(content)
    assert entities[0]["stable_id"] == "EU.2137.1"


def test_sanctions_title_contains_name() -> None:
    """Title includes the entity name."""
    content = FIXTURE_PATH.read_bytes()
    entities = _parse_sanctions_xml(content)
    assert "Test Sanctioned Entity" in entities[0]["title"]


def test_sanctions_content_non_empty() -> None:
    """Content field is non-empty."""
    content = FIXTURE_PATH.read_bytes()
    entities = _parse_sanctions_xml(content)
    assert entities[0]["content"].strip() != ""


def test_sanctions_entry_date_parsed() -> None:
    """Entry into force date is parsed from regulation element."""
    content = FIXTURE_PATH.read_bytes()
    entities = _parse_sanctions_xml(content)
    eff = entities[0]["effective_date"]
    assert eff is not None
    assert str(eff) == "2024-01-02"


def test_sanctions_entity_without_eu_ref_uses_logical_id() -> None:
    """When euReferenceNumber is absent, logicalId is used as stable_id."""
    xml = b"""<?xml version="1.0"?>
    <export date="2024-01-01" version="1.1">
      <sanctionEntity id="2" euReferenceNumber="" logicalId="EST-2" unitedNationId="">
        <nameAlias aliasType="N"><wholeName>No EU Ref</wholeName></nameAlias>
        <remark>No euReferenceNumber entity</remark>
      </sanctionEntity>
    </export>"""
    entities = _parse_sanctions_xml(xml)
    assert len(entities) == 1
    assert entities[0]["stable_id"] == "EST-2"


def test_sanctions_malformed_xml_raises() -> None:
    """Malformed XML raises SourceParseError."""
    with pytest.raises(SourceParseError):
        _parse_sanctions_xml(b"<broken>>>")
