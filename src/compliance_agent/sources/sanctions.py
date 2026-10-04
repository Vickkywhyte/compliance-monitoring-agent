"""EU Sanctions List source adapter — parses XML with defusedxml (C-10).

Stable ID: euReferenceNumber attribute on each <sanctionEntity> element
(e.g. "EU.2137.1"). Falls back to logicalId when euReferenceNumber is absent.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import defusedxml.ElementTree as ET
from defusedxml import DefusedXmlException

from compliance_agent.exceptions import SourceParseError
from compliance_agent.sources.base import RawDocument, Source
from compliance_agent.storage.models import SourceType
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)


def _parse_date(text: str | None) -> date | None:
    """Parse ISO-8601 date string, returning None on failure."""
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_sanctions_xml(content: bytes) -> list[dict[str, Any]]:
    """Parse EU Sanctions XML bytes into a list of entity dicts.

    Raises SourceParseError for malformed or unsafe XML.
    """
    try:
        root = ET.fromstring(content)
    except (DefusedXmlException, ET.ParseError, ValueError) as exc:
        raise SourceParseError(f"Sanctions XML parsing failed: {exc}") from exc

    entities: list[dict[str, Any]] = []

    for entity in root.findall(".//sanctionEntity"):
        eu_ref = entity.get("euReferenceNumber", "").strip()
        logical_id = entity.get("logicalId", "").strip()
        stable_id = eu_ref or logical_id
        if not stable_id:
            _log.warning("sanctions_missing_id", attribs=dict(entity.attrib))
            continue

        # Extract name from first nameAlias
        name_el = entity.find(".//wholeName")
        name = (name_el.text or "").strip() if name_el is not None else stable_id

        # Remark becomes the content body
        remark_el = entity.find(".//remark")
        content_text = (remark_el.text or "").strip() if remark_el is not None else ""
        if not content_text:
            content_text = f"Sanctioned entity: {name}"

        # Entry into force date from regulation element
        reg_el = entity.find(".//regulation")
        entry_date = None
        if reg_el is not None:
            entry_date = _parse_date(reg_el.get("entryIntoForceDate"))

        entities.append(
            {
                "stable_id": stable_id,
                "title": f"Sanctions entry: {name}",
                "content": content_text,
                "effective_date": entry_date,
            }
        )

    return entities


class SanctionsSource(Source):
    """Fetches and parses the EU consolidated sanctions list."""

    @property
    def source_type(self) -> SourceType:
        return "sanctions"

    def fetch(self) -> list[RawDocument]:
        """Fetch EU sanctions XML and return parsed RawDocument list."""
        result = self._fetcher.fetch(self._config.url, self.source_type, "xml")
        parsed = _parse_sanctions_xml(result.content)

        raw_docs: list[RawDocument] = []
        for entity in parsed:
            raw_docs.append(
                RawDocument(
                    source_type=self.source_type,
                    stable_id=entity["stable_id"],
                    title=entity["title"],
                    content=entity["content"],
                    raw_bytes=result.content,
                    source_url=result.url,
                    fetched_at=result.fetched_at,
                    effective_date=entity["effective_date"],
                )
            )

        _log.info(
            "sanctions_fetched",
            source=self._config.name,
            entities=len(raw_docs),
        )
        return raw_docs
