"""ApprovalService — atomic approve/edit_approve/reject with optimistic locking.

Every action executes in a single SQLite transaction (C-20):
  1. UPDATE proposals (optimistic lock: WHERE version=? AND state='pending')
  2. INSERT approval_actions
  3. INSERT audit_events
  4. COMMIT

If the optimistic lock fails (rowcount == 0), ConcurrentModificationError is raised
and the transaction is rolled back. This prevents double-approval (T-05).

The connection is set to isolation_level=None so that Python does not issue
implicit BEGIN statements that would conflict with our explicit BEGIN IMMEDIATE.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

import structlog

from compliance_agent.exceptions import ApprovalError, ConcurrentModificationError, StorageError
from compliance_agent.storage.models import (
    ApprovalAction,
    ApprovalActionType,
    AuditEntityType,
    Proposal,
    ProposalState,
    Role,
)
from compliance_agent.utils.ids import new_ulid, now_utc

from .state import validate_transition

log = structlog.get_logger(__name__)


class ApprovalService:
    """Execute approval actions atomically with optimistic concurrency control."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        # Manual transaction control required for atomic multi-statement writes
        self._conn.isolation_level = None

    def approve(
        self,
        proposal_id: str,
        actor_role: Role,
        actor_id: str,
    ) -> ApprovalAction:
        """Approve a pending proposal. Raises ApprovalError if not pending."""
        return self._execute_approval(
            proposal_id=proposal_id,
            actor_role=actor_role,
            actor_id=actor_id,
            action_type="approve",
            new_state="approved",
        )

    def edit_approve(
        self,
        proposal_id: str,
        actor_role: Role,
        actor_id: str,
        edits: dict[str, Any],
    ) -> ApprovalAction:
        """Approve with edits. Raises ApprovalError if not pending."""
        return self._execute_approval(
            proposal_id=proposal_id,
            actor_role=actor_role,
            actor_id=actor_id,
            action_type="edit_approve",
            new_state="approved",
            edits=edits,
        )

    def reject(
        self,
        proposal_id: str,
        actor_role: Role,
        actor_id: str,
        reason: str,
    ) -> ApprovalAction:
        """Reject a pending proposal. Raises ApprovalError if not pending."""
        return self._execute_approval(
            proposal_id=proposal_id,
            actor_role=actor_role,
            actor_id=actor_id,
            action_type="reject",
            new_state="rejected",
            reason=reason,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _execute_approval(
        self,
        proposal_id: str,
        actor_role: Role,
        actor_id: str,
        action_type: ApprovalActionType,
        new_state: ProposalState,
        edits: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> ApprovalAction:
        proposal = self._fetch_proposal(proposal_id)
        if proposal is None:
            raise ApprovalError(f"Proposal not found: {proposal_id}")

        # State machine check (raises ApprovalError if invalid)
        validate_transition(proposal.state, new_state)

        expected_version = proposal.version
        now = now_utc()
        action_id = new_ulid()
        event_id = new_ulid()
        correlation_id = new_ulid()

        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise ConcurrentModificationError(
                f"Cannot acquire write lock for proposal {proposal_id}: {exc}"
            ) from exc

        try:
            cursor = self._conn.execute(
                """
                UPDATE proposals SET state = ?, version = version + 1
                WHERE proposal_id = ? AND version = ? AND state = 'pending'
                """,
                (new_state, proposal_id, expected_version),
            )
            if cursor.rowcount == 0:
                self._conn.execute("ROLLBACK")
                raise ConcurrentModificationError(
                    f"Proposal {proposal_id} was concurrently modified "
                    f"(expected version={expected_version})"
                )

            self._conn.execute(
                """
                INSERT INTO approval_actions
                    (action_id, proposal_id, actor_role, actor_id, action, edits, reason, acted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    proposal_id,
                    actor_role,
                    actor_id,
                    action_type,
                    json.dumps(edits) if edits is not None else None,
                    reason,
                    now.isoformat(),
                ),
            )

            self._conn.execute(
                """
                INSERT INTO audit_events
                    (event_id, occurred_at, actor, action, entity_type,
                     entity_id, correlation_id, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    now.isoformat(),
                    actor_id,
                    f"proposal_{action_type}d",
                    "approval_action",
                    action_id,
                    correlation_id,
                    json.dumps(
                        {
                            "proposal_id": proposal_id,
                            "actor_role": actor_role,
                            "previous_state": proposal.state,
                            "new_state": new_state,
                            "version_before": expected_version,
                            "version_after": expected_version + 1,
                        }
                    ),
                ),
            )

            self._conn.execute("COMMIT")

        except (ApprovalError, ConcurrentModificationError):
            raise
        except Exception as exc:
            try:
                self._conn.execute("ROLLBACK")
            except Exception:
                pass
            raise StorageError(f"Approval transaction failed: {exc}") from exc

        log.info(
            "proposal_approval_completed",
            proposal_id=proposal_id,
            action=action_type,
            actor_id=actor_id,
            new_state=new_state,
        )
        return ApprovalAction(
            action_id=action_id,
            proposal_id=proposal_id,
            actor_role=actor_role,
            actor_id=actor_id,
            action=action_type,
            edits=edits,
            reason=reason,
            acted_at=now,
        )

    def _fetch_proposal(self, proposal_id: str) -> Proposal | None:
        """Read the current proposal state outside the write transaction."""
        import json as _json
        from datetime import date
        from compliance_agent.storage.models import Evidence

        try:
            cursor = self._conn.execute(
                "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
            )
            row = cursor.fetchone()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to fetch proposal {proposal_id}: {exc}") from exc

        if row is None:
            return None

        return Proposal(
            proposal_id=row["proposal_id"],
            change_id=row["change_id"],
            mapping_ids=_json.loads(row["mapping_ids"]),
            assignee_role=row["assignee_role"],
            category=row["category"],
            severity=row["severity"],
            title=row["title"],
            description=row["description"],
            deadline=date.fromisoformat(row["deadline"]) if row["deadline"] else None,
            deadline_rationale=row["deadline_rationale"] or "",
            evidence=[Evidence(**e) for e in _json.loads(row["evidence"])],
            prompt_version=row["prompt_version"],
            model=row["model"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
            state=row["state"],
            version=row["version"],
        )
