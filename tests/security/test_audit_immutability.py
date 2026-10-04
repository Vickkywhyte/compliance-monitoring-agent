"""Audit immutability tests (C-23, C-24, C-25).

Verifies that the AuditRepository exposes only append() and query(),
and that direct SQL UPDATE/DELETE on audit_events raises (via trigger).
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from compliance_agent.storage.audit import AuditRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.models import AuditEvent
from compliance_agent.utils.ids import new_ulid, now_utc


@pytest.fixture()
def db_conn():
    """Provide a fresh in-memory-ish SQLite connection with migrations applied."""
    with tempfile.TemporaryDirectory() as tmp:
        conn = get_connection(Path(tmp) / "audit_test.db")
        migrate(conn)
        yield conn
        conn.close()


@pytest.fixture()
def repo(db_conn) -> AuditRepository:
    return AuditRepository(db_conn)


def _make_event(**overrides) -> AuditEvent:
    defaults = dict(
        event_id=new_ulid(),
        occurred_at=now_utc(),
        actor="system",
        action="test_action",
        entity_type="system",
        entity_id="test-entity-001",
        correlation_id=new_ulid(),
        payload={"detail": "test"},
    )
    defaults.update(overrides)
    return AuditEvent(**defaults)


# ── Repository API contract (C-23) ───────────────────────────────────────────


def test_repo_has_append_method(repo):
    """AuditRepository exposes an append() method."""
    assert hasattr(repo, "append") and callable(repo.append)


def test_repo_has_query_method(repo):
    """AuditRepository exposes a query() method."""
    assert hasattr(repo, "query") and callable(repo.query)


def test_repo_has_no_update_method(repo):
    """AuditRepository must NOT expose an update() method (C-23)."""
    assert not hasattr(repo, "update"), "update() must not exist on AuditRepository"


def test_repo_has_no_delete_method(repo):
    """AuditRepository must NOT expose a delete() method (C-23)."""
    assert not hasattr(repo, "delete"), "delete() must not exist on AuditRepository"


# ── Append and read-back (Lesson 5) ─────────────────────────────────────────


def test_append_and_query_roundtrip(repo):
    """An appended event can be retrieved via query() (read-back test)."""
    event = _make_event(entity_id="roundtrip-001")
    repo.append(event)

    results = repo.query(entity_id="roundtrip-001")
    assert len(results) == 1
    assert results[0].event_id == event.event_id
    assert results[0].actor == "system"
    assert results[0].payload == {"detail": "test"}


def test_multiple_append_accumulates(repo):
    """Multiple appended events are all retrievable."""
    corr_id = new_ulid()
    for i in range(3):
        repo.append(_make_event(correlation_id=corr_id, entity_id=f"multi-{i}"))

    results = repo.query(correlation_id=corr_id)
    assert len(results) == 3


# ── SQLite trigger enforcement (C-24, C-25) ──────────────────────────────────


def test_direct_sql_update_raises(db_conn, repo):
    """Direct SQL UPDATE on audit_events raises a database error via trigger (C-24, C-25).

    SQLite RAISE(ABORT, ...) maps to sqlite3.IntegrityError in Python's sqlite3 module.
    """
    event = _make_event(entity_id="immutable-001")
    repo.append(event)

    # Accept either IntegrityError or OperationalError — both indicate the trigger fired.
    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="append-only"):
        db_conn.execute(
            "UPDATE audit_events SET actor = 'tampered' WHERE event_id = ?",
            (event.event_id,),
        )


def test_direct_sql_delete_raises(db_conn, repo):
    """Direct SQL DELETE on audit_events raises a database error via trigger (C-24, C-25).

    SQLite RAISE(ABORT, ...) maps to sqlite3.IntegrityError in Python's sqlite3 module.
    """
    event = _make_event(entity_id="immutable-002")
    repo.append(event)

    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="append-only"):
        db_conn.execute(
            "DELETE FROM audit_events WHERE event_id = ?",
            (event.event_id,),
        )
