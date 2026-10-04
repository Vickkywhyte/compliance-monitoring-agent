"""Tests for Phase 3 change detection (Lesson 3: assert observable behavior only).

All tests use in-memory SQLite — no mocks, no monkeypatching of function calls.
Every assertion checks a return value, a persisted record, or an observable count.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from compliance_agent.detection.detector import detect
from compliance_agent.detection.diff import compute_diff
from compliance_agent.detection.stable_id import extract_stable_id
from compliance_agent.exceptions import DiffError, StableIDError
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.models import RegulatoryDocument
from compliance_agent.utils.ids import compute_change_id, new_ulid


# ── Helpers ──────────────────────────────────────────────────────────────────


def _repos():
    """Return (doc_repo, change_repo) backed by an in-memory SQLite database."""
    conn = get_connection(":memory:")
    migrate(conn)
    return DocumentRepository(conn), ChangeRepository(conn)


def _make_doc(
    source: str,
    stable_id: str,
    content: str = "Default regulatory content.",
) -> RegulatoryDocument:
    return RegulatoryDocument(
        doc_id=new_ulid(),
        source=source,
        stable_id=stable_id,
        title=f"Doc {stable_id}",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        source_url=f"https://example.com/{stable_id}",
        fetched_at=datetime.now(timezone.utc),
    )


# ── Stable ID extraction ─────────────────────────────────────────────────────


def test_stable_id_extraction_eurlex():
    doc = _make_doc("eurlex", "32016R0679")
    assert extract_stable_id(doc) == "32016R0679"


def test_stable_id_extraction_eurlex_uppercased():
    """Lowercase input is normalised to uppercase."""
    doc = _make_doc("eurlex", "32016r0679")
    assert extract_stable_id(doc) == "32016R0679"


def test_stable_id_extraction_sanctions():
    doc = _make_doc("sanctions", "EU.2137.1")
    assert extract_stable_id(doc) == "EU.2137.1"


def test_stable_id_extraction_eba():
    uri = "https://www.eba.europa.eu/publications/guidelines/gl-2024-01"
    doc = _make_doc("eba", uri)
    assert extract_stable_id(doc) == uri


def test_stable_id_extraction_raises_on_missing():
    doc = _make_doc("eurlex", "")
    with pytest.raises(StableIDError):
        extract_stable_id(doc)


def test_stable_id_extraction_raises_on_invalid_celex():
    doc = _make_doc("eurlex", "INVALID-NOT-CELEX")
    with pytest.raises(StableIDError):
        extract_stable_id(doc)


# ── Diff ─────────────────────────────────────────────────────────────────────


def test_diff_on_identical_content_returns_empty():
    assert compute_diff("same text\nhere\n", "same text\nhere\n") == ""


def test_diff_produces_unified_format():
    old = "Article 1: original text\nArticle 2: unchanged\n"
    new = "Article 1: updated text\nArticle 2: unchanged\n"
    result = compute_diff(old, new)
    assert "---" in result
    assert "+++" in result
    assert "-Article 1: original text" in result
    assert "+Article 1: updated text" in result


def test_diff_raises_on_binary():
    with pytest.raises(DiffError):
        compute_diff("hello\x00world", "other content")


# ── Detection ────────────────────────────────────────────────────────────────


def test_detect_new_document():
    doc_repo, change_repo = _repos()
    doc = _make_doc("eurlex", "32024R0001", "New regulation text.")
    doc_repo.upsert(doc)

    report = detect([doc], doc_repo, change_repo, source="eurlex")

    assert report.new == 1
    assert report.amended == 0
    changes = change_repo.get_by_stable_id("eurlex", "32024R0001")
    assert len(changes) == 1
    assert changes[0].change_type == "new"
    assert changes[0].previous_version is None
    assert changes[0].current_version == 1


def test_detect_amended_document():
    doc_repo, change_repo = _repos()

    doc_v1 = _make_doc("eurlex", "32024R0002", "Original regulatory text.")
    doc_repo.upsert(doc_v1)
    detect([doc_v1], doc_repo, change_repo, source="eurlex")

    doc_v2 = _make_doc("eurlex", "32024R0002", "Updated text with material amendments.")
    doc_repo.upsert(doc_v2)  # stored as version 2

    report = detect([doc_v2], doc_repo, change_repo, source="eurlex")

    assert report.amended == 1
    changes = change_repo.get_by_stable_id("eurlex", "32024R0002")
    amended = [c for c in changes if c.change_type == "amended"]
    assert len(amended) == 1
    assert amended[0].previous_version == 1
    assert amended[0].current_version == 2
    assert amended[0].diff is not None
    assert "-Original regulatory text" in amended[0].diff
    assert "+Updated text" in amended[0].diff


def test_detect_unchanged_document():
    doc_repo, change_repo = _repos()
    doc = _make_doc("eurlex", "32024R0003", "Stable regulatory text.")
    doc_repo.upsert(doc)
    detect([doc], doc_repo, change_repo, source="eurlex")

    report = detect([doc], doc_repo, change_repo, source="eurlex")

    assert report.unchanged == 1
    assert report.new == 0
    assert report.amended == 0
    # Still only one Change record (from the first run)
    assert len(change_repo.get_by_stable_id("eurlex", "32024R0003")) == 1


def test_detection_is_idempotent():
    doc_repo, change_repo = _repos()
    doc = _make_doc("sanctions", "EU.999.1", "Sanctioned entity content.")
    doc_repo.upsert(doc)

    report1 = detect([doc], doc_repo, change_repo, source="sanctions")
    report2 = detect([doc], doc_repo, change_repo, source="sanctions")

    assert report1.new == 1
    assert report2.new == 0
    assert report2.unchanged == 1
    # Exactly one Change record exists after two runs
    assert len(change_repo.get_by_stable_id("sanctions", "EU.999.1")) == 1


def test_change_id_is_deterministic():
    cid1 = compute_change_id("eurlex", "32024R0001", 1)
    cid2 = compute_change_id("eurlex", "32024R0001", 1)
    assert cid1 == cid2
    assert len(cid1) == 16


def test_change_id_differs_by_version():
    cid_v1 = compute_change_id("eurlex", "32024R0001", 1)
    cid_v2 = compute_change_id("eurlex", "32024R0001", 2)
    assert cid_v1 != cid_v2
