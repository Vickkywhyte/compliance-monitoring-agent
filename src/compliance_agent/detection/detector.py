"""Change detector: compares stored document versions and emits Change records.

detect(docs, doc_repo, change_repo, source) → DetectReport

Detection runs AFTER DocumentRepository.upsert(), using the DB as the source of
truth for version history:

  latest.version == 1, no Change for it   → emit Change(type="new")
  latest.version  > 1, no Change for it   → emit Change(type="amended", diff=...)
  Change for latest version already exists → skip (idempotent; counted "unchanged")

Withdrawn detection: stable_ids present in the DB for the source but absent from
the current batch of incoming docs are emitted as Change(type="withdrawn").
"""
from __future__ import annotations

from dataclasses import dataclass

from compliance_agent.detection.diff import compute_diff
from compliance_agent.detection.stable_id import extract_stable_id
from compliance_agent.exceptions import StableIDError
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.models import Change, RegulatoryDocument
from compliance_agent.utils.ids import compute_change_id, now_utc
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)


@dataclass
class DetectReport:
    """Per-source summary of one detection run."""

    source: str
    total_docs: int
    new: int = 0
    amended: int = 0
    withdrawn: int = 0
    unchanged: int = 0
    errors: int = 0
    skipped_idempotent: int = 0  # alias for unchanged; kept for logging clarity


def detect(
    docs: list[RegulatoryDocument],
    doc_repo: DocumentRepository,
    change_repo: ChangeRepository,
    source: str,
) -> DetectReport:
    """Run change detection for one source's current document batch.

    Args:
        docs:        Latest documents for this source (already upserted into
                     DocumentRepository before calling this function).
        doc_repo:    Repository containing full version history.
        change_repo: Repository that receives the emitted Change records.
        source:      SourceType string (e.g. "eurlex", "sanctions", "eba").

    Returns:
        DetectReport with per-type counts.
    """
    report = DetectReport(source=source, total_docs=len(docs))
    fetched_stable_ids: set[str] = set()

    for doc in docs:
        try:
            stable_id = extract_stable_id(doc)
        except StableIDError as exc:
            _log.warning("stable_id_failed", doc_id=doc.doc_id, error=str(exc))
            report.errors += 1
            continue

        fetched_stable_ids.add(stable_id)

        all_versions = doc_repo.get_by_stable_id(doc.source, stable_id)
        if not all_versions:
            _log.warning(
                "doc_not_in_db",
                source=source,
                stable_id=stable_id,
                hint="call doc_repo.upsert() before detect()",
            )
            report.errors += 1
            continue

        latest = max(all_versions, key=lambda d: d.version)
        change = _build_change(all_versions, latest)

        inserted = change_repo.insert(change)
        if inserted:
            if change.change_type == "new":
                report.new += 1
            else:
                report.amended += 1
            _log.info(
                "change_detected",
                source=source,
                stable_id=stable_id,
                change_type=change.change_type,
                version=change.current_version,
                change_id=change.change_id,
            )
        else:
            report.unchanged += 1
            _log.debug(
                "change_skipped",
                source=source,
                stable_id=stable_id,
                change_id=change.change_id,
            )

    # ── Withdrawn detection ──────────────────────────────────────────────────
    known_stable_ids = set(doc_repo.list_stable_ids(source))
    withdrawn_ids = known_stable_ids - fetched_stable_ids

    if withdrawn_ids:
        _log.info("withdrawn_candidates", source=source, count=len(withdrawn_ids))
    else:
        _log.debug("no_withdrawals", source=source, known=len(known_stable_ids))

    for stable_id in withdrawn_ids:
        prior = doc_repo.get_by_stable_id(source, stable_id)
        if not prior:
            continue
        latest = max(prior, key=lambda d: d.version)
        withdrawal_version = latest.version + 1
        change_id = compute_change_id(source, stable_id, withdrawal_version)
        change = Change(
            change_id=change_id,
            doc_id=latest.doc_id,
            source=source,
            stable_id=stable_id,
            change_type="withdrawn",
            diff=None,
            previous_version=latest.version,
            current_version=withdrawal_version,
            detected_at=now_utc(),
            effective_date=latest.effective_date,
            metadata={},
        )
        inserted = change_repo.insert(change)
        if inserted:
            report.withdrawn += 1
            _log.info(
                "change_withdrawn",
                source=source,
                stable_id=stable_id,
                change_id=change.change_id,
            )
        else:
            report.unchanged += 1

    return report


# ── Private helpers ──────────────────────────────────────────────────────────


def _build_change(
    all_versions: list[RegulatoryDocument],
    latest: RegulatoryDocument,
) -> Change:
    """Construct the appropriate Change record for the latest document version."""
    source = latest.source
    stable_id = latest.stable_id
    change_id = compute_change_id(source, stable_id, latest.version)

    if latest.version == 1:
        return Change(
            change_id=change_id,
            doc_id=latest.doc_id,
            source=source,
            stable_id=stable_id,
            change_type="new",
            diff=None,
            previous_version=None,
            current_version=1,
            detected_at=now_utc(),
            effective_date=latest.effective_date,
            metadata={},
        )

    # Amendment: find previous version
    sorted_vs = sorted(all_versions, key=lambda d: d.version)
    previous = next(v for v in sorted_vs if v.version == latest.version - 1)
    diff_text = compute_diff(previous.content, latest.content)
    return Change(
        change_id=change_id,
        doc_id=latest.doc_id,
        source=source,
        stable_id=stable_id,
        change_type="amended",
        diff=diff_text,
        previous_version=previous.version,
        current_version=latest.version,
        detected_at=now_utc(),
        effective_date=latest.effective_date,
        metadata={},
    )


if __name__ == "__main__":
    import hashlib
    import tempfile
    from datetime import datetime, timezone
    from pathlib import Path

    from compliance_agent.storage.db import get_connection, migrate
    from compliance_agent.utils.ids import new_ulid

    print("=== detection/detector self-test ===")

    def _doc(source: str, stable_id: str, content: str) -> RegulatoryDocument:
        return RegulatoryDocument(
            doc_id=new_ulid(),
            source=source,
            stable_id=stable_id,
            title=f"Test {stable_id}",
            content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            source_url="http://example.com",
            fetched_at=datetime.now(timezone.utc),
        )

    conn = get_connection(":memory:")
    migrate(conn)
    dr = DocumentRepository(conn)
    cr = ChangeRepository(conn)

    doc = _doc("eurlex", "32024R0099", "Initial text.")
    dr.upsert(doc)
    r = detect([doc], dr, cr, source="eurlex")
    assert r.new == 1, f"expected 1 new, got {r.new}"
    print(f"  new doc detected: {r.new} new")

    r2 = detect([doc], dr, cr, source="eurlex")
    assert r2.unchanged == 1 and r2.new == 0
    print("  idempotent re-run: OK")

    amended = _doc("eurlex", "32024R0099", "Updated text with amendments.")
    dr.upsert(amended)
    r3 = detect([amended], dr, cr, source="eurlex")
    assert r3.amended == 1, f"expected 1 amended, got {r3.amended}"
    print(f"  amendment detected: {r3.amended} amended")

    conn.close()
    print("PASS")
