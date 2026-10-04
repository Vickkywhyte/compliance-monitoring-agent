"""Append-only audit event repository (C-23, C-24, C-25, 05_DATA_SPEC §3.7).

Exposes ONLY append() and query(). No update() or delete() methods exist.
SQLite-level triggers (in db.py DDL) provide defense-in-depth.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from compliance_agent.exceptions import AuditError, StorageError
from compliance_agent.storage.models import AuditEntityType, AuditEvent


class AuditRepository:
    """Repository for the audit_events table.

    This class intentionally exposes no mutation methods (no update, no delete).
    Any attempt to call such methods will raise AttributeError because they
    do not exist. The underlying SQLite triggers (C-24) enforce the same
    constraint at the database layer.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, event: AuditEvent) -> None:
        """Insert a new audit event. Raises AuditError on conflict or failure."""
        try:
            self._conn.execute(
                """
                INSERT INTO audit_events
                    (event_id, occurred_at, actor, action, entity_type,
                     entity_id, correlation_id, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.occurred_at.isoformat(),
                    event.actor,
                    event.action,
                    event.entity_type,
                    event.entity_id,
                    event.correlation_id,
                    json.dumps(event.payload),
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise AuditError(f"Duplicate audit event {event.event_id}: {exc}") from exc
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to append audit event: {exc}") from exc

    def query(
        self,
        *,
        entity_type: AuditEntityType | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query audit events with optional filters. Returns up to `limit` rows."""
        clauses: list[str] = []
        params: list[Any] = []

        if entity_type is not None:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        try:
            cursor = self._conn.execute(
                f"""
                SELECT event_id, occurred_at, actor, action, entity_type,
                       entity_id, correlation_id, payload
                FROM audit_events
                {where}
                ORDER BY occurred_at ASC
                LIMIT ?
                """,
                params,
            )
        except sqlite3.Error as exc:
            raise StorageError(f"Audit query failed: {exc}") from exc

        results: list[AuditEvent] = []
        for row in cursor.fetchall():
            results.append(
                AuditEvent(
                    event_id=row["event_id"],
                    occurred_at=datetime.fromisoformat(row["occurred_at"]),
                    actor=row["actor"],
                    action=row["action"],
                    entity_type=row["entity_type"],
                    entity_id=row["entity_id"],
                    correlation_id=row["correlation_id"],
                    payload=json.loads(row["payload"]),
                )
            )
        return results


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from compliance_agent.storage.db import get_connection, migrate
    from compliance_agent.utils.ids import new_ulid, now_utc

    print("=== storage/audit self-test ===")

    with tempfile.TemporaryDirectory() as tmp:
        conn = get_connection(Path(tmp) / "audit_test.db")
        migrate(conn)
        repo = AuditRepository(conn)

        event = AuditEvent(
            event_id=new_ulid(),
            occurred_at=now_utc(),
            actor="system",
            action="selftest",
            entity_type="system",
            entity_id="selftest-entity",
            correlation_id=new_ulid(),
            payload={"test": True},
        )
        repo.append(event)
        print("  append: OK")

        results = repo.query(entity_type="system", entity_id="selftest-entity")
        assert len(results) == 1, f"expected 1 event, got {len(results)}"
        assert results[0].event_id == event.event_id
        print("  query: OK")

        # Verify no update/delete methods exist on the repository
        assert not hasattr(repo, "update"), "repo must not expose update()"
        assert not hasattr(repo, "delete"), "repo must not expose delete()"
        print("  no update/delete methods: OK")

        conn.close()

    print("PASS")
