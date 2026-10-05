"""AuditRecorder — convenience wrapper around Phase 1 AuditRepository.

Provides named convenience functions for common audit events. All writes
go through AuditRepository.append(), which is append-only (C-23, C-24).
"""
from __future__ import annotations

import sqlite3
from typing import Any

import structlog

from compliance_agent.storage.audit import AuditRepository
from compliance_agent.storage.models import AuditEvent, AuditEntityType
from compliance_agent.utils.ids import new_ulid, now_utc

log = structlog.get_logger(__name__)


class AuditRecorder:
    """High-level audit recording using the Phase 1 AuditRepository."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._repo = AuditRepository(conn)

    def record(self, event: AuditEvent) -> None:
        """Append an audit event. Raises AuditError on failure."""
        self._repo.append(event)

    def record_proposal_created(
        self,
        proposal_id: str,
        change_id: str,
        actor: str = "system",
        correlation_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._record(
            actor=actor,
            action="proposal_created",
            entity_type="proposal",
            entity_id=proposal_id,
            correlation_id=correlation_id or new_ulid(),
            payload={"change_id": change_id, **(extra or {})},
        )

    def record_approval_action(
        self,
        action_id: str,
        proposal_id: str,
        actor: str,
        action: str,
        correlation_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._record(
            actor=actor,
            action=f"proposal_{action}d",
            entity_type="approval_action",
            entity_id=action_id,
            correlation_id=correlation_id or new_ulid(),
            payload={"proposal_id": proposal_id, **(extra or {})},
        )

    def record_change_detected(
        self,
        change_id: str,
        source: str,
        change_type: str,
        correlation_id: str | None = None,
    ) -> None:
        self._record(
            actor="system",
            action="change_detected",
            entity_type="change",
            entity_id=change_id,
            correlation_id=correlation_id or new_ulid(),
            payload={"source": source, "change_type": change_type},
        )

    def _record(
        self,
        actor: str,
        action: str,
        entity_type: AuditEntityType,
        entity_id: str,
        correlation_id: str,
        payload: dict[str, Any],
    ) -> None:
        event = AuditEvent(
            event_id=new_ulid(),
            occurred_at=now_utc(),
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            payload=payload,
        )
        self._repo.append(event)
        log.info("audit_event_recorded", action=action, entity_id=entity_id)
