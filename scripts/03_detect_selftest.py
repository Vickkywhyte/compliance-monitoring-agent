"""Phase 3 self-test: verifies detection correctness and idempotency.

Three assertions (all use in-memory SQLite, no network calls):
  1. Three new documents → exactly 3 new Change records.
  2. Re-running detection on the same documents → 0 new Changes (idempotency).
  3. An amended document → 1 amended Change with a non-empty diff.

Exits non-zero on any assertion failure.
"""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from compliance_agent.detection.detector import detect
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.models import RegulatoryDocument
from compliance_agent.utils.ids import new_ulid


def _make_doc(source: str, stable_id: str, content: str) -> RegulatoryDocument:
    return RegulatoryDocument(
        doc_id=new_ulid(),
        source=source,
        stable_id=stable_id,
        title=f"Selftest: {stable_id}",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        source_url=f"https://example.com/{stable_id}",
        fetched_at=datetime.now(timezone.utc),
        version=1,
    )


def main() -> int:
    conn = get_connection(":memory:")
    migrate(conn)
    doc_repo = DocumentRepository(conn)
    change_repo = ChangeRepository(conn)

    # ── Assertion 1: 3 new documents → 3 new Change records ─────────────────
    docs = [
        _make_doc("eurlex",    "32024R0001", "AML regulation text version 1."),
        _make_doc("sanctions", "EU.2137.1",  "Sanctioned entity Alpha Corp."),
        _make_doc("eba",       "https://eba.europa.eu/pub/gl-2024-01", "EBA GL 2024/01."),
    ]
    for doc in docs:
        doc_repo.upsert(doc)

    r_eur  = detect(docs[0:1], doc_repo, change_repo, source="eurlex")
    r_san  = detect(docs[1:2], doc_repo, change_repo, source="sanctions")
    r_eba  = detect(docs[2:3], doc_repo, change_repo, source="eba")

    total_new = r_eur.new + r_san.new + r_eba.new
    assert total_new == 3, f"[FAIL] Assertion 1: expected 3 new, got {total_new}"
    print(f"[PASS] Assertion 1: {total_new} new Change records detected")

    # ── Assertion 2: re-run → 0 new, 3 unchanged (idempotency) ──────────────
    r2_eur = detect(docs[0:1], doc_repo, change_repo, source="eurlex")
    r2_san = detect(docs[1:2], doc_repo, change_repo, source="sanctions")
    r2_eba = detect(docs[2:3], doc_repo, change_repo, source="eba")

    total_new_rerun = r2_eur.new + r2_san.new + r2_eba.new
    assert total_new_rerun == 0, (
        f"[FAIL] Assertion 2: expected 0 new on re-run, got {total_new_rerun}"
    )
    total_unchanged = r2_eur.unchanged + r2_san.unchanged + r2_eba.unchanged
    assert total_unchanged == 3, (
        f"[FAIL] Assertion 2: expected 3 unchanged, got {total_unchanged}"
    )
    print(f"[PASS] Assertion 2: 0 new on re-run ({total_unchanged} unchanged)")

    # ── Assertion 3: amended document → 1 amended Change with non-empty diff ─
    amended_doc = _make_doc(
        "eurlex", "32024R0001",
        "AML regulation text version 2, with amendments to article 3(b).",
    )
    doc_repo.upsert(amended_doc)  # inserts v2 (hash differs from v1)

    r_amended = detect([amended_doc], doc_repo, change_repo, source="eurlex")
    assert r_amended.amended == 1, (
        f"[FAIL] Assertion 3: expected 1 amended, got {r_amended.amended}"
    )

    changes = change_repo.get_by_stable_id("eurlex", "32024R0001")
    amended_changes = [c for c in changes if c.change_type == "amended"]
    assert len(amended_changes) == 1, (
        f"[FAIL] Assertion 3: expected 1 amended Change in DB, got {len(amended_changes)}"
    )
    assert amended_changes[0].diff, "[FAIL] Assertion 3: diff must be non-empty"
    assert "-AML regulation text version 1" in amended_changes[0].diff, (
        "[FAIL] Assertion 3: diff must contain removed line"
    )
    assert "+AML regulation text version 2" in amended_changes[0].diff, (
        "[FAIL] Assertion 3: diff must contain added line"
    )
    print("[PASS] Assertion 3: 1 amended Change with correct unified diff")

    conn.close()
    print("\nAll selftest assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
