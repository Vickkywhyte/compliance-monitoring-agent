"""Audit Trail view — global, filterable audit event log with JSON export."""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import streamlit as st

from compliance_agent.audit.exporter import AuditExporter
from compliance_agent.storage.audit import AuditRepository
from compliance_agent.storage.models import AuditEntityType

_ENTITY_TYPES: list[str] = [
    "regulatory_document",
    "change",
    "summary",
    "process_mapping",
    "proposal",
    "approval_action",
    "ingestion_run",
    "system",
]


def render_audit_trail(conn: sqlite3.Connection) -> None:
    """Render the Audit Trail tab: filterable event log with export."""
    st.subheader("Audit Trail")

    audit_repo = AuditRepository(conn)

    # ── Filters ───────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        entity_type_filter = st.selectbox(
            "Entity type",
            options=["All"] + _ENTITY_TYPES,
            key="audit_entity_type",
        )
    with col2:
        actor_filter = st.text_input("Actor contains", key="audit_actor_filter")
    with col3:
        date_from = st.date_input("From", value=None, key="audit_date_from")
    with col4:
        date_to = st.date_input("To", value=None, key="audit_date_to")

    entity_type_param: AuditEntityType | None = (
        entity_type_filter if entity_type_filter != "All" else None  # type: ignore[assignment]
    )

    events = audit_repo.query(entity_type=entity_type_param, limit=1000)

    # Post-filter on actor and date (AuditRepository.query doesn't support these)
    if actor_filter:
        events = [e for e in events if actor_filter.lower() in e.actor.lower()]
    if date_from is not None:
        events = [e for e in events if e.occurred_at.date() >= date_from]
    if date_to is not None:
        events = [e for e in events if e.occurred_at.date() <= date_to]

    # Reverse-chronological
    events.sort(key=lambda e: e.occurred_at, reverse=True)

    st.caption(f"{len(events)} event(s)")

    # ── Export ────────────────────────────────────────────────────────────────
    if st.button("Export JSON", key="audit_export_json"):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as fh:
            export_path = Path(fh.name)
        exporter = AuditExporter(conn)
        exporter.export_to_json(export_path, filters={})
        st.download_button(
            label="Download audit.json",
            data=export_path.read_text(),
            file_name="audit_export.json",
            mime="application/json",
            key="audit_download",
        )

    # ── Table ─────────────────────────────────────────────────────────────────
    if not events:
        st.info("No audit events match the current filters.")
        return

    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "Time": e.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                "Actor": e.actor,
                "Action": e.action,
                "Entity Type": e.entity_type,
                "Entity ID": e.entity_id[:24] + "…",
            }
            for e in events
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)
