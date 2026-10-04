"""Phase 2 ingestion self-test (Lesson 2: every entry point has a self-test).

Runs the ingestion pipeline in fixture mode and asserts:
1. All three sources produced at least one document
2. Idempotency: running twice leaves all docs as "unchanged" on second run
3. DocumentRepository.get_by_stable_id() returns the stored docs

Exits 0 on pass, 1 on any failure.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Ensure src/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from compliance_agent.config.loader import load_sources_config
from compliance_agent.ingestion.fetch import Fetcher
from compliance_agent.ingestion.orchestrator import ingest_all, run_ingest
from compliance_agent.sources.registry import build_sources
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.utils.logging import configure_logging

import asyncio


def selftest() -> None:
    configure_logging()
    print("=== 02_ingest_selftest ===")

    fixture_dir = Path("tests/fixtures/raw")
    if not fixture_dir.exists():
        print(f"FAIL: fixture directory not found: {fixture_dir}", file=sys.stderr)
        sys.exit(1)

    # ── Test 1: all three sources produce documents ──────────────────────────
    print("\n[1] All sources produce documents in fixture mode...")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        report = run_ingest(fixture_mode=True, db_path=str(db_path))

        assert report.total_fetched >= 3, (
            f"Expected at least 3 documents, got {report.total_fetched}"
        )
        source_names = {sr.source for sr in report.sources}
        for source_report in report.sources:
            assert source_report.error is None, (
                f"Source {source_report.source!r} failed: {source_report.error}"
            )
            assert source_report.fetched >= 1, (
                f"Source {source_report.source!r} fetched 0 documents"
            )
        print(f"   PASS — fetched {report.total_fetched} docs from: {sorted(source_names)}")

    # ── Test 2: idempotency ──────────────────────────────────────────────────
    print("\n[2] Idempotency: second run returns all unchanged...")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"

        report1 = run_ingest(fixture_mode=True, db_path=str(db_path))
        report2 = run_ingest(fixture_mode=True, db_path=str(db_path))

        assert report2.total_new == 0, (
            f"Expected 0 new docs on second run, got {report2.total_new}"
        )
        assert report2.total_unchanged == report1.total_new + report1.total_unchanged, (
            f"Second run unchanged ({report2.total_unchanged}) != "
            f"first run stored ({report1.total_new})"
        )
        print(f"   PASS — run1 new={report1.total_new}, run2 unchanged={report2.total_unchanged}")

    # ── Test 3: DocumentRepository read-back ────────────────────────────────
    print("\n[3] Read-back: stored docs are retrievable by stable_id...")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        run_ingest(fixture_mode=True, db_path=str(db_path))

        conn = get_connection(str(db_path))
        repo = DocumentRepository(conn)

        eurlex_docs = repo.get_by_stable_id("eurlex", "32024R0001")
        assert len(eurlex_docs) == 1, (
            f"Expected 1 eurlex doc, got {len(eurlex_docs)}"
        )
        assert eurlex_docs[0].stable_id == "32024R0001"
        assert eurlex_docs[0].content_hash, "content_hash must not be empty"
        print(f"   PASS — eurlex doc: {eurlex_docs[0].stable_id!r} v{eurlex_docs[0].version}")

        sanctions_docs = repo.get_by_stable_id("sanctions", "EU.2137.1")
        assert len(sanctions_docs) == 1, (
            f"Expected 1 sanctions doc, got {len(sanctions_docs)}"
        )
        print(f"   PASS — sanctions doc: {sanctions_docs[0].stable_id!r} v{sanctions_docs[0].version}")

        conn.close()

    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    try:
        selftest()
        sys.exit(0)
    except (AssertionError, Exception) as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        sys.exit(1)
