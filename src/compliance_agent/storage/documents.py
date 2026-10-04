"""DocumentRepository: append-only upsert for RegulatoryDocument (C-15, C-23).

Upsert logic:
  - (source, stable_id) not found  → insert with version=1,  returns "new"
  - found, same content_hash       → skip,                   returns "unchanged"
  - found, different content_hash  → insert with version+1,  returns "updated"

All SQL uses parameterized queries (C-15). No UPDATE or DELETE statements.
The regulatory_documents table is created by storage/db.py's migrate() call.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Literal

from compliance_agent.storage.models import RegulatoryDocument
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)

UpsertResult = Literal["new", "unchanged", "updated"]


class DocumentRepository:
    """Read/write access to the regulatory_documents table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, doc: RegulatoryDocument) -> UpsertResult:
        """Insert or skip document based on content hash comparison.

        Returns "new", "unchanged", or "updated".
        Never issues UPDATE or DELETE — each version is a new row.
        """
        existing = self._get_latest(doc.source, doc.stable_id)

        if existing is None:
            self._insert(doc.model_copy(update={"version": 1}))
            _log.debug("doc_new", source=doc.source, stable_id=doc.stable_id)
            return "new"

        if existing["content_hash"] == doc.content_hash:
            _log.debug("doc_unchanged", source=doc.source, stable_id=doc.stable_id)
            return "unchanged"

        next_version = existing["version"] + 1
        self._insert(doc.model_copy(update={"version": next_version}))
        _log.debug(
            "doc_updated",
            source=doc.source,
            stable_id=doc.stable_id,
            version=next_version,
        )
        return "updated"

    def get_by_stable_id(
        self, source: str, stable_id: str
    ) -> list[RegulatoryDocument]:
        """Return all versions for (source, stable_id), oldest first."""
        rows = self._conn.execute(
            """
            SELECT doc_id, source, stable_id, version, title, content,
                   content_hash, source_url, fetched_at, effective_date, metadata
              FROM regulatory_documents
             WHERE source = ? AND stable_id = ?
             ORDER BY version ASC
            """,
            (source, stable_id),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_stable_ids(self, source: str) -> list[str]:
        """Return all distinct stable_ids stored for the given source."""
        rows = self._conn.execute(
            "SELECT DISTINCT stable_id FROM regulatory_documents WHERE source = ?",
            (source,),
        ).fetchall()
        return [row[0] for row in rows]

    def list_latest_by_source(self, source: str) -> list[RegulatoryDocument]:
        """Return the latest version of each document for the given source."""
        rows = self._conn.execute(
            """
            SELECT d.doc_id, d.source, d.stable_id, d.version, d.title,
                   d.content, d.content_hash, d.source_url, d.fetched_at,
                   d.effective_date, d.metadata
              FROM regulatory_documents d
             INNER JOIN (
                 SELECT stable_id, MAX(version) AS max_version
                   FROM regulatory_documents
                  WHERE source = ?
                  GROUP BY stable_id
             ) latest
                ON d.stable_id = latest.stable_id
               AND d.version   = latest.max_version
             WHERE d.source = ?
             ORDER BY d.stable_id
            """,
            (source, source),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_by_id(self, doc_id: str) -> RegulatoryDocument | None:
        """Return a single document by its ULID doc_id."""
        row = self._conn.execute(
            """
            SELECT doc_id, source, stable_id, version, title, content,
                   content_hash, source_url, fetched_at, effective_date, metadata
              FROM regulatory_documents
             WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        return self._row_to_model(row) if row else None

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_latest(self, source: str, stable_id: str) -> dict | None:
        """Return the row with the highest version for (source, stable_id)."""
        row = self._conn.execute(
            """
            SELECT content_hash, version
              FROM regulatory_documents
             WHERE source = ? AND stable_id = ?
             ORDER BY version DESC
             LIMIT 1
            """,
            (source, stable_id),
        ).fetchone()
        if row is None:
            return None
        return {"content_hash": row[0], "version": row[1]}

    def _insert(self, doc: RegulatoryDocument) -> None:
        """Insert one document row. Raises sqlite3.IntegrityError on duplicate."""
        self._conn.execute(
            """
            INSERT INTO regulatory_documents
                (doc_id, source, stable_id, version, title, content,
                 content_hash, source_url, fetched_at, effective_date, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.doc_id,
                doc.source,
                doc.stable_id,
                doc.version,
                doc.title,
                doc.content,
                doc.content_hash,
                doc.source_url,
                doc.fetched_at.isoformat(),
                doc.effective_date.isoformat() if doc.effective_date else None,
                json.dumps(doc.metadata),
            ),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> RegulatoryDocument:
        """Convert a DB row tuple to a RegulatoryDocument."""
        from datetime import date, datetime

        (
            doc_id, source, stable_id, version, title, content,
            content_hash, source_url, fetched_at_str, eff_date_str, metadata_str,
        ) = row

        fetched_at = datetime.fromisoformat(fetched_at_str)
        effective_date = date.fromisoformat(eff_date_str) if eff_date_str else None
        metadata = json.loads(metadata_str or "{}")

        return RegulatoryDocument(
            doc_id=doc_id,
            source=source,
            stable_id=stable_id,
            version=version,
            title=title,
            content=content,
            content_hash=content_hash,
            source_url=source_url,
            fetched_at=fetched_at,
            effective_date=effective_date,
            metadata=metadata,
        )
