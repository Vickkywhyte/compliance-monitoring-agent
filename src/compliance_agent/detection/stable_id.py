"""Stable ID extraction and validation per source type (05_DATA_SPEC §7).

extract_stable_id(doc) → validated stable_id string.
Raises StableIDError if the ID is missing or malformed.
Does NOT fall back to a content hash — that would break amendment detection.
"""
from __future__ import annotations

import re

from compliance_agent.exceptions import StableIDError
from compliance_agent.storage.models import RegulatoryDocument

# CELEX: sector 3 (legislation) + 4-digit year + 1-2 uppercase doc-type letters + serial
_CELEX_RE = re.compile(r"^3\d{4}[A-Z]{1,2}\d+$")


def extract_stable_id(doc: RegulatoryDocument) -> str:
    """Return the validated stable ID for a RegulatoryDocument.

    EUR-Lex:    CELEX number (e.g. "32016R0679"); validated, returned uppercase.
    Sanctions:  EU reference or logical ID (e.g. "EU.2137.1"); returned as-is.
    EBA:        Canonical document URI; validated non-empty, returned as-is.

    Raises StableIDError on empty or malformed IDs.
    """
    sid = doc.stable_id.strip()
    if not sid:
        raise StableIDError(
            f"Empty stable_id on {doc.source} document {doc.doc_id}"
        )

    if doc.source == "eurlex":
        upper = sid.upper()
        if not _CELEX_RE.match(upper):
            raise StableIDError(
                f"Invalid CELEX number '{sid}' for eurlex document {doc.doc_id}; "
                f"expected pattern 3YYYYTTNNNN (e.g. 32016R0679)"
            )
        return upper

    if doc.source in ("sanctions", "eba"):
        return sid

    raise StableIDError(
        f"Unknown source type '{doc.source}' on document {doc.doc_id}"
    )


if __name__ == "__main__":
    from datetime import datetime, timezone

    print("=== detection/stable_id self-test ===")

    def _make(source: str, stable_id: str) -> RegulatoryDocument:
        return RegulatoryDocument(
            doc_id="01JTEST00000000000000000000",
            source=source,
            stable_id=stable_id,
            title="Test",
            content="Test",
            content_hash="abc",
            source_url="http://example.com",
            fetched_at=datetime.now(timezone.utc),
        )

    doc = _make("eurlex", "32016R0679")
    sid = extract_stable_id(doc)
    assert sid == "32016R0679", sid
    print(f"  eurlex CELEX: {sid}")

    doc_lower = _make("eurlex", "32016r0679")
    assert extract_stable_id(doc_lower) == "32016R0679"
    print("  eurlex lowercase → uppercase: OK")

    doc_sanc = _make("sanctions", "EU.2137.1")
    assert extract_stable_id(doc_sanc) == "EU.2137.1"
    print("  sanctions: OK")

    doc_eba = _make("eba", "https://www.eba.europa.eu/publications/gl-2024-01")
    assert extract_stable_id(doc_eba).startswith("https://")
    print("  eba URI: OK")

    try:
        extract_stable_id(_make("eurlex", "NOT-A-CELEX"))
        raise AssertionError("should have raised")
    except StableIDError as exc:
        print(f"  invalid CELEX → StableIDError: OK ({exc!s:.40s}...)")

    try:
        extract_stable_id(_make("eurlex", ""))
        raise AssertionError("should have raised")
    except StableIDError:
        print("  empty stable_id → StableIDError: OK")

    print("PASS")
