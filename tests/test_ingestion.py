"""Integration tests for the ingestion pipeline (observable behavior only)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from compliance_agent.ingestion.orchestrator import run_ingest
from compliance_agent.storage.db import get_connection
from compliance_agent.storage.documents import DocumentRepository


FIXTURE_DIR = Path("tests/fixtures/raw")


@pytest.mark.skipif(
    not FIXTURE_DIR.exists(),
    reason="tests/fixtures/raw/ not present",
)
def test_ingest_all_sources_succeed_in_fixture_mode() -> None:
    """All three sources run without error in fixture mode."""
    with tempfile.TemporaryDirectory() as tmp:
        report = run_ingest(fixture_mode=True, db_path=str(Path(tmp) / "test.db"))

    for sr in report.sources:
        assert sr.error is None, f"Source {sr.source!r} had error: {sr.error}"


@pytest.mark.skipif(
    not FIXTURE_DIR.exists(),
    reason="tests/fixtures/raw/ not present",
)
def test_ingest_produces_documents() -> None:
    """Fixture mode ingestion stores at least 3 documents total."""
    with tempfile.TemporaryDirectory() as tmp:
        report = run_ingest(fixture_mode=True, db_path=str(Path(tmp) / "test.db"))

    assert report.total_fetched >= 3, f"Expected >=3 documents, got {report.total_fetched}"
    assert report.total_new >= 3, f"Expected >=3 new documents, got {report.total_new}"


@pytest.mark.skipif(
    not FIXTURE_DIR.exists(),
    reason="tests/fixtures/raw/ not present",
)
def test_ingest_idempotent() -> None:
    """Running ingestion twice on the same DB leaves all docs unchanged on second run."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        report1 = run_ingest(fixture_mode=True, db_path=db_path)
        report2 = run_ingest(fixture_mode=True, db_path=db_path)

    assert report2.total_new == 0, f"Second run created new docs: {report2.total_new}"
    assert report2.total_unchanged == report1.total_new, (
        f"Second run unchanged ({report2.total_unchanged}) != "
        f"first run new ({report1.total_new})"
    )


@pytest.mark.skipif(
    not FIXTURE_DIR.exists(),
    reason="tests/fixtures/raw/ not present",
)
def test_document_read_back() -> None:
    """Documents stored during ingestion are retrievable by stable_id."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        run_ingest(fixture_mode=True, db_path=db_path)

        conn = get_connection(db_path)
        repo = DocumentRepository(conn)

        # EUR-Lex document
        docs = repo.get_by_stable_id("eurlex", "32024R0001")
        assert len(docs) == 1
        assert docs[0].source == "eurlex"
        assert docs[0].content_hash, "content_hash must be set"
        assert docs[0].version == 1

        # Sanctions entity
        docs = repo.get_by_stable_id("sanctions", "EU.2137.1")
        assert len(docs) == 1
        assert docs[0].source == "sanctions"

        conn.close()


@pytest.mark.skipif(
    not FIXTURE_DIR.exists(),
    reason="tests/fixtures/raw/ not present",
)
def test_ingest_report_structure() -> None:
    """IngestReport has a SourceReport for each enabled source."""
    with tempfile.TemporaryDirectory() as tmp:
        report = run_ingest(fixture_mode=True, db_path=str(Path(tmp) / "test.db"))

    source_names = {sr.source for sr in report.sources}
    # All three sources are enabled in sources.yaml
    assert len(report.sources) == 3
    assert report.started_at <= report.completed_at
