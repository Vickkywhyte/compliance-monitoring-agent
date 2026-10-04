"""SQLite connection factory and idempotent migration runner (05_DATA_SPEC §8).

get_connection() — returns a configured sqlite3.Connection
migrate()        — applies the full DDL idempotently (CREATE IF NOT EXISTS)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from compliance_agent.exceptions import StorageError

# Full DDL from 05_DATA_SPEC §8, extended with append-only triggers (C-24)
_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS regulatory_documents (
    doc_id          TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    stable_id       TEXT NOT NULL,
    version         INTEGER NOT NULL,
    title           TEXT,
    content         TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    effective_date  TEXT,
    metadata        TEXT,
    UNIQUE(source, stable_id, version)
);

CREATE TABLE IF NOT EXISTS changes (
    change_id        TEXT PRIMARY KEY,
    doc_id           TEXT NOT NULL,
    source           TEXT NOT NULL,
    stable_id        TEXT NOT NULL,
    change_type      TEXT NOT NULL,
    diff             TEXT,
    previous_version INTEGER,
    current_version  INTEGER NOT NULL,
    detected_at      TEXT NOT NULL,
    effective_date   TEXT,
    metadata         TEXT,
    FOREIGN KEY (doc_id) REFERENCES regulatory_documents(doc_id)
);

CREATE TABLE IF NOT EXISTS summaries (
    summary_id      TEXT PRIMARY KEY,
    change_id       TEXT NOT NULL,
    text            TEXT NOT NULL,
    citations       TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    model           TEXT NOT NULL,
    confidence      REAL NOT NULL,
    low_confidence  INTEGER NOT NULL,
    generated_at    TEXT NOT NULL,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    cost_usd        REAL,
    FOREIGN KEY (change_id) REFERENCES changes(change_id)
);

CREATE TABLE IF NOT EXISTS process_mappings (
    mapping_id          TEXT PRIMARY KEY,
    change_id           TEXT NOT NULL,
    process_id          TEXT NOT NULL,
    process_section_id  TEXT NOT NULL,
    impact_type         TEXT NOT NULL,
    confidence          REAL NOT NULL,
    rationale           TEXT,
    citation_quote      TEXT,
    prompt_version      TEXT NOT NULL,
    model               TEXT NOT NULL,
    generated_at        TEXT NOT NULL,
    FOREIGN KEY (change_id) REFERENCES changes(change_id)
);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id         TEXT PRIMARY KEY,
    change_id           TEXT NOT NULL,
    mapping_ids         TEXT NOT NULL,
    assignee_role       TEXT NOT NULL,
    category            TEXT NOT NULL,
    severity            TEXT NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    deadline            TEXT,
    deadline_rationale  TEXT,
    evidence            TEXT NOT NULL,
    prompt_version      TEXT NOT NULL,
    model               TEXT NOT NULL,
    generated_at        TEXT NOT NULL,
    state               TEXT NOT NULL DEFAULT 'pending',
    version             INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (change_id) REFERENCES changes(change_id)
);

CREATE INDEX IF NOT EXISTS idx_proposals_state_role
    ON proposals(state, assignee_role);

CREATE TABLE IF NOT EXISTS approval_actions (
    action_id   TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    actor_role  TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    edits       TEXT,
    reason      TEXT,
    acted_at    TEXT NOT NULL,
    FOREIGN KEY (proposal_id) REFERENCES proposals(proposal_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id        TEXT PRIMARY KEY,
    occurred_at     TEXT NOT NULL,
    actor           TEXT NOT NULL,
    action          TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    correlation_id  TEXT NOT NULL,
    payload         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_entity
    ON audit_events(entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_audit_correlation
    ON audit_events(correlation_id);

-- Append-only enforcement: triggers reject UPDATE and DELETE (C-24)
CREATE TRIGGER IF NOT EXISTS prevent_update_audit_events
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only: UPDATE is not permitted');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_audit_events
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only: DELETE is not permitted');
END;
"""


def get_connection(db_path: str | Path = "data/compliance.db") -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys enabled.

    The caller owns the connection and must close it when done.
    """
    path = Path(db_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except sqlite3.Error as exc:
        raise StorageError(f"Cannot open database at {db_path}: {exc}") from exc


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the full schema DDL idempotently (all statements use IF NOT EXISTS).

    Requires an open connection as the first argument — obtain one via get_connection().
    """
    try:
        conn.executescript(_DDL)
        conn.commit()
    except sqlite3.Error as exc:
        raise StorageError(f"Migration failed: {exc}") from exc


if __name__ == "__main__":
    import tempfile

    print("=== storage/db self-test ===")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = get_connection(db_path)
        migrate(conn)

        # Verify expected tables exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        expected = {
            "regulatory_documents",
            "changes",
            "summaries",
            "process_mappings",
            "proposals",
            "approval_actions",
            "audit_events",
        }
        missing = expected - tables
        assert not missing, f"Missing tables: {missing}"
        print(f"  tables: {sorted(tables)}")

        # Verify triggers exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
        )
        triggers = {row[0] for row in cursor.fetchall()}
        assert "prevent_update_audit_events" in triggers
        assert "prevent_delete_audit_events" in triggers
        print(f"  triggers: {sorted(triggers)}")

        # Idempotency: running migrate again must not raise
        migrate(conn)
        print("  idempotent migrate: OK")

        conn.close()

    print("PASS")
