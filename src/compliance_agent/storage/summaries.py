"""Repository for LLM-generated summaries (05_DATA_SPEC §3.3)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from compliance_agent.exceptions import StorageError
from compliance_agent.storage.models import Citation, Summary


class SummaryRepository:
    """CRUD repository for Summary records. No raw SQL outside this class."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, summary: Summary) -> bool:
        """Persist a Summary. Returns True if inserted, False if already exists."""
        existing = self.get_by_id(summary.summary_id)
        if existing is not None:
            return False
        try:
            self._conn.execute(
                """
                INSERT INTO summaries (
                    summary_id, change_id, text, citations, prompt_version,
                    model, confidence, low_confidence, generated_at,
                    tokens_in, tokens_out, cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.summary_id,
                    summary.change_id,
                    summary.text,
                    json.dumps([c.model_dump() for c in summary.citations]),
                    summary.prompt_version,
                    summary.model,
                    summary.confidence,
                    int(summary.low_confidence),
                    summary.generated_at.isoformat(),
                    summary.tokens_in,
                    summary.tokens_out,
                    summary.cost_usd,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to insert summary {summary.summary_id}: {exc}") from exc

    def get_by_id(self, summary_id: str) -> Summary | None:
        """Return a Summary by its primary key, or None."""
        row = self._conn.execute(
            "SELECT * FROM summaries WHERE summary_id = ?", (summary_id,)
        ).fetchone()
        return _row_to_model(row) if row else None

    def get_by_change_id(self, change_id: str) -> Summary | None:
        """Return the most recent Summary for a change, or None."""
        row = self._conn.execute(
            "SELECT * FROM summaries WHERE change_id = ? ORDER BY generated_at DESC LIMIT 1",
            (change_id,),
        ).fetchone()
        return _row_to_model(row) if row else None

    def list_recent(self, limit: int = 100) -> list[Summary]:
        """Return up to limit Summaries ordered newest-first."""
        rows = self._conn.execute(
            "SELECT * FROM summaries ORDER BY generated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_model(r) for r in rows]


def _row_to_model(row: sqlite3.Row) -> Summary:
    raw_cits = json.loads(row["citations"]) if row["citations"] else []
    citations = [Citation.model_validate(c) for c in raw_cits]
    return Summary(
        summary_id=row["summary_id"],
        change_id=row["change_id"],
        text=row["text"],
        citations=citations,
        prompt_version=row["prompt_version"],
        model=row["model"],
        confidence=float(row["confidence"]),
        low_confidence=bool(row["low_confidence"]),
        generated_at=datetime.fromisoformat(row["generated_at"]).replace(
            tzinfo=timezone.utc
        ),
        tokens_in=row["tokens_in"] or 0,
        tokens_out=row["tokens_out"] or 0,
        cost_usd=float(row["cost_usd"] or 0.0),
    )
