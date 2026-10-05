"""ApprovalActionRepository — parameterized SQL only (C-15, 05_DATA_SPEC §3.6)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from compliance_agent.exceptions import StorageError
from compliance_agent.storage.models import ApprovalAction


class ApprovalActionRepository:
    """CRUD (insert + query) for the approval_actions table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, action: ApprovalAction) -> bool:
        """Insert an approval action. Returns True on insert, False if duplicate."""
        try:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO approval_actions
                    (action_id, proposal_id, actor_role, actor_id, action, edits, reason, acted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.action_id,
                    action.proposal_id,
                    action.actor_role,
                    action.actor_id,
                    action.action,
                    json.dumps(action.edits) if action.edits is not None else None,
                    action.reason,
                    action.acted_at.isoformat(),
                ),
            )
            self._conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to insert approval action {action.action_id}: {exc}"
            ) from exc

    def get_by_proposal(self, proposal_id: str) -> list[ApprovalAction]:
        """Return all approval actions for a given proposal, oldest first."""
        try:
            cursor = self._conn.execute(
                "SELECT * FROM approval_actions WHERE proposal_id = ? ORDER BY acted_at ASC",
                (proposal_id,),
            )
            return [_row_to_action(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to get approval actions for proposal {proposal_id}: {exc}"
            ) from exc


def _row_to_action(row: sqlite3.Row) -> ApprovalAction:
    return ApprovalAction(
        action_id=row["action_id"],
        proposal_id=row["proposal_id"],
        actor_role=row["actor_role"],
        actor_id=row["actor_id"],
        action=row["action"],
        edits=json.loads(row["edits"]) if row["edits"] else None,
        reason=row["reason"],
        acted_at=datetime.fromisoformat(row["acted_at"]),
    )
