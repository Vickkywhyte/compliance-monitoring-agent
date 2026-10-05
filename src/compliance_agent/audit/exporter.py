"""AuditExporter — export proposal audit chains to JSON and PDF (ADR-008)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from compliance_agent.exceptions import StorageError
from compliance_agent.storage.audit import AuditRepository
from compliance_agent.storage.approvals import ApprovalActionRepository
from compliance_agent.storage.proposals import ProposalRepository

log = structlog.get_logger(__name__)


class AuditExporter:
    """Export proposal audit chains to structured formats."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._audit_repo = AuditRepository(conn)
        self._proposal_repo = ProposalRepository(conn)
        self._action_repo = ApprovalActionRepository(conn)

    def export_proposal_chain(self, proposal_id: str) -> dict[str, Any]:
        """Return the full audit history for a proposal as a dict.

        Includes: proposal snapshot, approval actions, and audit events.
        """
        proposal = self._proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            raise StorageError(f"Proposal not found: {proposal_id}")

        actions = self._action_repo.get_by_proposal(proposal_id)
        audit_events = self._audit_repo.query(
            entity_id=proposal_id, limit=200
        ) + self._audit_repo.query(entity_type="approval_action", limit=200)

        # Deduplicate events
        seen: set[str] = set()
        unique_events = []
        for ev in audit_events:
            if ev.event_id not in seen:
                seen.add(ev.event_id)
                unique_events.append(ev)
        unique_events.sort(key=lambda e: e.occurred_at)

        return {
            "proposal_id": proposal_id,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "proposal": proposal.model_dump(mode="json"),
            "approval_actions": [a.model_dump(mode="json") for a in actions],
            "audit_events": [
                {
                    "event_id": e.event_id,
                    "occurred_at": e.occurred_at.isoformat(),
                    "actor": e.actor,
                    "action": e.action,
                    "entity_type": e.entity_type,
                    "entity_id": e.entity_id,
                    "correlation_id": e.correlation_id,
                    "payload": e.payload,
                }
                for e in unique_events
            ],
        }

    def export_to_json(
        self,
        path: Path | str,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """Export matching audit events to a JSON file. Returns event count."""
        path = Path(path)
        filters = filters or {}

        events = self._audit_repo.query(
            entity_type=filters.get("entity_type"),
            entity_id=filters.get("entity_id"),
            correlation_id=filters.get("correlation_id"),
            limit=filters.get("limit", 1000),
        )

        records = [
            {
                "event_id": e.event_id,
                "occurred_at": e.occurred_at.isoformat(),
                "actor": e.actor,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "correlation_id": e.correlation_id,
                "payload": e.payload,
            }
            for e in events
        ]

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records, indent=2, default=str))
        log.info("audit_exported_json", path=str(path), count=len(records))
        return len(records)

    def export_to_pdf(
        self,
        path: Path | str,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """Export matching audit events to a PDF file. Returns event count."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.lib import colors

        path = Path(path)
        filters = filters or {}

        events = self._audit_repo.query(
            entity_type=filters.get("entity_type"),
            entity_id=filters.get("entity_id"),
            correlation_id=filters.get("correlation_id"),
            limit=filters.get("limit", 1000),
        )

        styles = getSampleStyleSheet()
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(str(path), pagesize=A4)
        story = []

        story.append(Paragraph("Compliance Agent — Audit Export", styles["Title"]))
        story.append(Spacer(1, 0.5 * cm))

        if events:
            data = [["Event ID", "Occurred At", "Actor", "Action", "Entity"]]
            for e in events:
                data.append(
                    [
                        e.event_id[:16],
                        e.occurred_at.strftime("%Y-%m-%d %H:%M"),
                        e.actor[:20],
                        e.action[:30],
                        f"{e.entity_type}/{e.entity_id[:16]}",
                    ]
                )
            tbl = Table(data, repeatRows=1)
            tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                    ]
                )
            )
            story.append(tbl)
        else:
            story.append(Paragraph("No audit events matched the given filters.", styles["Normal"]))

        doc.build(story)
        log.info("audit_exported_pdf", path=str(path), count=len(events))
        return len(events)
