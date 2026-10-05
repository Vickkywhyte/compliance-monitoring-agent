"""ProposalRepository — parameterized SQL only (C-15, 05_DATA_SPEC §3.5)."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from compliance_agent.exceptions import StorageError
from compliance_agent.storage.models import Evidence, Proposal, ProposalState, Role


class ProposalRepository:
    """CRUD operations for the proposals table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, proposal: Proposal) -> bool:
        """Insert if not present (get-or-create by proposal_id). Returns True on insert."""
        try:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO proposals
                    (proposal_id, change_id, mapping_ids, assignee_role, category,
                     severity, title, description, deadline, deadline_rationale,
                     evidence, prompt_version, model, generated_at, state, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.change_id,
                    json.dumps(proposal.mapping_ids),
                    proposal.assignee_role,
                    proposal.category,
                    proposal.severity,
                    proposal.title,
                    proposal.description,
                    proposal.deadline.isoformat() if proposal.deadline else None,
                    proposal.deadline_rationale,
                    json.dumps([e.model_dump() for e in proposal.evidence]),
                    proposal.prompt_version,
                    proposal.model,
                    proposal.generated_at.isoformat(),
                    proposal.state,
                    proposal.version,
                ),
            )
            self._conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to insert proposal {proposal.proposal_id}: {exc}") from exc

    def get_by_id(self, proposal_id: str) -> Proposal | None:
        """Fetch a single proposal by ID; returns None if not found."""
        try:
            cursor = self._conn.execute(
                "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
            )
            row = cursor.fetchone()
            return _row_to_proposal(row) if row else None
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to get proposal {proposal_id}: {exc}") from exc

    def list_by_state(
        self, state: ProposalState, role: Role | None = None
    ) -> list[Proposal]:
        """List proposals by state, optionally filtered by assignee_role."""
        try:
            if role is not None:
                cursor = self._conn.execute(
                    "SELECT * FROM proposals WHERE state = ? AND assignee_role = ? ORDER BY generated_at DESC",
                    (state, role),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM proposals WHERE state = ? ORDER BY generated_at DESC",
                    (state,),
                )
            return [_row_to_proposal(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to list proposals by state={state}: {exc}") from exc

    def list_by_change(self, change_id: str) -> list[Proposal]:
        """Return all proposals linked to a given change_id."""
        try:
            cursor = self._conn.execute(
                "SELECT * FROM proposals WHERE change_id = ? ORDER BY generated_at DESC",
                (change_id,),
            )
            return [_row_to_proposal(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to list proposals for change {change_id}: {exc}") from exc

    def update_state_with_lock(
        self,
        proposal_id: str,
        expected_version: int,
        new_state: ProposalState,
    ) -> bool:
        """Optimistic-lock state update; returns True on success, False on version mismatch."""
        try:
            cursor = self._conn.execute(
                """
                UPDATE proposals SET state = ?, version = version + 1
                WHERE proposal_id = ? AND version = ? AND state = 'pending'
                """,
                (new_state, proposal_id, expected_version),
            )
            self._conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to update proposal {proposal_id}: {exc}"
            ) from exc


def _row_to_proposal(row: sqlite3.Row) -> Proposal:
    """Convert a SQLite row to a Proposal model."""
    return Proposal(
        proposal_id=row["proposal_id"],
        change_id=row["change_id"],
        mapping_ids=json.loads(row["mapping_ids"]),
        assignee_role=row["assignee_role"],
        category=row["category"],
        severity=row["severity"],
        title=row["title"],
        description=row["description"],
        deadline=date.fromisoformat(row["deadline"]) if row["deadline"] else None,
        deadline_rationale=row["deadline_rationale"] or "",
        evidence=[Evidence(**e) for e in json.loads(row["evidence"])],
        prompt_version=row["prompt_version"],
        model=row["model"],
        generated_at=datetime.fromisoformat(row["generated_at"]),
        state=row["state"],
        version=row["version"],
    )
