"""Phase 3 detection script: run change detection over stored documents.

Usage:
    python scripts/03_detect.py

For each source, loads the latest version of every stored document, runs
change detection, inserts Change records, and prints a DetectReport. Safe to
run repeatedly — already-detected versions are skipped (idempotent).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from compliance_agent.detection.detector import detect
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)
_SOURCES = ["eurlex", "sanctions", "eba"]


def main() -> int:
    conn = get_connection()
    migrate(conn)

    doc_repo = DocumentRepository(conn)
    change_repo = ChangeRepository(conn)

    totals = dict(new=0, amended=0, withdrawn=0, unchanged=0, errors=0)

    for source in _SOURCES:
        docs = doc_repo.list_latest_by_source(source)
        report = detect(docs, doc_repo, change_repo, source=source)
        print(
            f"[{source}] docs={report.total_docs} "
            f"new={report.new} amended={report.amended} "
            f"withdrawn={report.withdrawn} unchanged={report.unchanged} "
            f"errors={report.errors}"
        )
        totals["new"] += report.new
        totals["amended"] += report.amended
        totals["withdrawn"] += report.withdrawn
        totals["unchanged"] += report.unchanged
        totals["errors"] += report.errors

    print(
        f"\nTotal: new={totals['new']} amended={totals['amended']} "
        f"withdrawn={totals['withdrawn']} unchanged={totals['unchanged']} "
        f"errors={totals['errors']}"
    )

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
