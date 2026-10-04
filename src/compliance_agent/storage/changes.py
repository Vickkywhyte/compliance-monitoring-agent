"""ChangeRepository: get-or-create storage for Change records (C-15, C-16).

insert(change) → True if newly inserted, False if change_id already existed.
All SQL uses parameterized queries only (C-15).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from compliance_agent.exceptions import StorageError
from compliance_agent.storage.models import Change
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)


class ChangeRepository:
    """Read/write access to the changes table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, change: Change) -> bool:
        """Insert a Change, silently skipping if change_id already exists.

        Returns True when newly inserted, False when the change_id was already
        present (idempotent: re-running detection on the same data is safe).
        """
        if self.get_by_id(change.change_id) is not None:
            _log.debug("change_insert_skipped", change_id=change.change_id)
            return False

        try:
            self._conn.execute(
                """
                INSERT INTO changes
                    (change_id, doc_id, source, stable_id, change_type, diff,
                     previous_version, current_version, detected_at,
                     effective_date, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change.change_id,
                    change.doc_id,
                    change.source,
                    change.stable_id,
                    change.change_type,
                    change.diff,
                    change.previous_version,
                    change.current_version,
                    change.detected_at.isoformat(),
                    change.effective_date.isoformat() if change.effective_date else None,
                    json.dumps(change.metadata),
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to insert change {change.change_id}: {exc}"
            ) from exc

        return True

    def get_by_id(self, change_id: str) -> Change | None:
        """Return the Change with this change_id, or None if not found."""
        row = self._conn.execute(
            """
            SELECT change_id, doc_id, source, stable_id, change_type, diff,
                   previous_version, current_version, detected_at,
                   effective_date, metadata
              FROM changes
             WHERE change_id = ?
            """,
            (change_id,),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def get_by_stable_id(self, source: str, stable_id: str) -> list[Change]:
        """Return all Changes for (source, stable_id), ordered by current_version."""
        rows = self._conn.execute(
            """
            SELECT change_id, doc_id, source, stable_id, change_type, diff,
                   previous_version, current_version, detected_at,
                   effective_date, metadata
              FROM changes
             WHERE source = ? AND stable_id = ?
             ORDER BY current_version ASC
            """,
            (source, stable_id),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_recent(self, limit: int = 100) -> list[Change]:
        """Return the most recently detected changes, newest first."""
        rows = self._conn.execute(
            """
            SELECT change_id, doc_id, source, stable_id, change_type, diff,
                   previous_version, current_version, detected_at,
                   effective_date, metadata
              FROM changes
             ORDER BY detected_at DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    # ── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> Change:
        """Convert a DB row tuple to a Change model."""
        (
            change_id, doc_id, source, stable_id, change_type, diff,
            previous_version, current_version, detected_at_str,
            eff_date_str, metadata_str,
        ) = row

        return Change(
            change_id=change_id,
            doc_id=doc_id,
            source=source,
            stable_id=stable_id,
            change_type=change_type,
            diff=diff,
            previous_version=previous_version,
            current_version=current_version,
            detected_at=datetime.fromisoformat(detected_at_str),
            effective_date=date.fromisoformat(eff_date_str) if eff_date_str else None,
            metadata=json.loads(metadata_str or "{}"),
        )


if __name__ == "__main__":
    from datetime import timezone

    from compliance_agent.storage.db import get_connection, migrate
    from compliance_agent.storage.models import Change
    from compliance_agent.utils.ids import compute_change_id, new_ulid, now_utc

    print("=== storage/changes self-test ===")

    conn = get_connection(":memory:")
    migrate(conn)
    repo = ChangeRepository(conn)

    doc_id = new_ulid()

    # Need a regulatory_documents row for the FK
    conn.execute(
        "INSERT INTO regulatory_documents "
        "(doc_id, source, stable_id, version, title, content, content_hash, "
        "source_url, fetched_at) "
        "VALUES (?, 'eurlex', '32024R0001', 1, 'T', 'C', 'H', 'http://x.com', ?)",
        (doc_id, now_utc().isoformat()),
    )
    conn.commit()

    change = Change(
        change_id=compute_change_id("eurlex", "32024R0001", 1),
        doc_id=doc_id,
        source="eurlex",
        stable_id="32024R0001",
        change_type="new",
        diff=None,
        previous_version=None,
        current_version=1,
        detected_at=now_utc(),
    )

    inserted = repo.insert(change)
    assert inserted is True
    print("  insert → True: OK")

    inserted_again = repo.insert(change)
    assert inserted_again is False
    print("  re-insert → False (idempotent): OK")

    fetched = repo.get_by_id(change.change_id)
    assert fetched is not None
    assert fetched.change_type == "new"
    print("  get_by_id read-back: OK")

    by_stable = repo.get_by_stable_id("eurlex", "32024R0001")
    assert len(by_stable) == 1
    print("  get_by_stable_id: OK")

    recent = repo.list_recent(10)
    assert len(recent) == 1
    print("  list_recent: OK")

    conn.close()
    print("PASS")
