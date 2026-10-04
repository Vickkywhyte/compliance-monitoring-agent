"""Repository for process mapping records (05_DATA_SPEC §3.4)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from compliance_agent.exceptions import StorageError
from compliance_agent.storage.models import ProcessMapping


class ProcessMappingRepository:
    """CRUD repository for ProcessMapping records. No raw SQL outside this class."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, mapping: ProcessMapping) -> bool:
        """Persist a ProcessMapping. Returns True if inserted, False if already exists."""
        existing = self.get_by_id(mapping.mapping_id)
        if existing is not None:
            return False
        try:
            self._conn.execute(
                """
                INSERT INTO process_mappings (
                    mapping_id, change_id, process_id, process_section_id,
                    impact_type, confidence, rationale, citation_quote,
                    prompt_version, model, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mapping.mapping_id,
                    mapping.change_id,
                    mapping.process_id,
                    mapping.process_section_id,
                    mapping.impact_type,
                    mapping.confidence,
                    mapping.rationale,
                    mapping.citation_quote,
                    mapping.prompt_version,
                    mapping.model,
                    mapping.generated_at.isoformat(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to insert mapping {mapping.mapping_id}: {exc}"
            ) from exc

    def get_by_id(self, mapping_id: str) -> ProcessMapping | None:
        """Return a ProcessMapping by its primary key, or None."""
        row = self._conn.execute(
            "SELECT * FROM process_mappings WHERE mapping_id = ?", (mapping_id,)
        ).fetchone()
        return _row_to_model(row) if row else None

    def get_by_change_id(self, change_id: str) -> list[ProcessMapping]:
        """Return all ProcessMappings for a change."""
        rows = self._conn.execute(
            "SELECT * FROM process_mappings WHERE change_id = ? ORDER BY confidence DESC",
            (change_id,),
        ).fetchall()
        return [_row_to_model(r) for r in rows]

    def list_recent(self, limit: int = 100) -> list[ProcessMapping]:
        """Return up to limit ProcessMappings ordered newest-first."""
        rows = self._conn.execute(
            "SELECT * FROM process_mappings ORDER BY generated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_model(r) for r in rows]


def _row_to_model(row: sqlite3.Row) -> ProcessMapping:
    return ProcessMapping(
        mapping_id=row["mapping_id"],
        change_id=row["change_id"],
        process_id=row["process_id"],
        process_section_id=row["process_section_id"],
        impact_type=row["impact_type"],
        confidence=float(row["confidence"]),
        rationale=row["rationale"] or "",
        citation_quote=row["citation_quote"] or "",
        prompt_version=row["prompt_version"],
        model=row["model"],
        generated_at=datetime.fromisoformat(row["generated_at"]).replace(
            tzinfo=timezone.utc
        ),
    )
