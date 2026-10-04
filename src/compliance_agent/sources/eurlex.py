"""EUR-Lex source adapter — parses OJ-format XML with defusedxml (C-10).

Stable ID: CELEX number matching pattern 3\\d{4}[A-Z]{1,2}\\d+
(e.g. 32024R0001 = year 2024, Regulation type R, document 0001).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import defusedxml.ElementTree as ET
from defusedxml import DefusedXmlException

from compliance_agent.exceptions import IngestError, SourceParseError
from compliance_agent.sources.base import RawDocument, Source
from compliance_agent.storage.models import SourceType
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)

# CELEX number: sector 3 (legislation) + year + document-type letters + serial
_CELEX_RE = re.compile(r"3\d{4}[A-Z]{1,2}\d+")


def _parse_date(text: str | None) -> date | None:
    """Try ISO-8601 (YYYY-MM-DD) then compact (YYYYMMDD) formats."""
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_eurlex_xml(content: bytes) -> list[dict[str, Any]]:
    """Parse EUR-Lex XML bytes into a list of document dicts.

    Raises SourceParseError for malformed or unsafe XML.
    """
    try:
        root = ET.fromstring(content)
    except (DefusedXmlException, ET.ParseError, ValueError) as exc:
        raise SourceParseError(f"EUR-Lex XML parsing failed: {exc}") from exc

    docs: list[dict[str, Any]] = []
    # Support both <RESULTS><NOTICE>... and bare <NOTICE>... structures
    notices = root.findall(".//NOTICE") or ([root] if root.tag == "NOTICE" else [])

    for notice in notices:
        celex_el = notice.find("CELEX")
        if celex_el is None or not celex_el.text:
            _log.warning("eurlex_missing_celex", tag=notice.tag)
            continue

        raw_celex = celex_el.text.strip()
        if not _CELEX_RE.match(raw_celex):
            _log.warning("eurlex_invalid_celex", value=raw_celex)
            continue

        title_el = notice.find("TITLE")
        title = (title_el.text or "").strip() if title_el is not None else ""

        contents_el = notice.find("CONTENTS")
        content_text = (contents_el.text or "").strip() if contents_el is not None else ""

        eff_date_el = notice.find("EFFECTIVE_DATE")
        doc_date_el = notice.find("DATE_DOCUMENT")
        effective_date = _parse_date(
            eff_date_el.text if eff_date_el is not None else None
        ) or _parse_date(
            doc_date_el.text if doc_date_el is not None else None
        )

        docs.append(
            {
                "stable_id": raw_celex,
                "title": title,
                "content": content_text,
                "effective_date": effective_date,
            }
        )

    return docs


class EurLexSource(Source):
    """Fetches and parses EUR-Lex OJ XML documents."""

    @property
    def source_type(self) -> SourceType:
        return "eurlex"

    def fetch(self) -> list[RawDocument]:
        """Fetch EUR-Lex XML and return parsed RawDocument list."""
        result = self._fetcher.fetch(self._config.url, self.source_type, "xml")
        parsed = _parse_eurlex_xml(result.content)

        raw_docs: list[RawDocument] = []
        for doc in parsed:
            raw_docs.append(
                RawDocument(
                    source_type=self.source_type,
                    stable_id=doc["stable_id"],
                    title=doc["title"],
                    content=doc["content"],
                    raw_bytes=result.content,
                    source_url=result.url,
                    fetched_at=result.fetched_at,
                    effective_date=doc["effective_date"],
                )
            )

        _log.info(
            "eurlex_fetched",
            source=self._config.name,
            documents=len(raw_docs),
        )
        return raw_docs
