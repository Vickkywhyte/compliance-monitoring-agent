"""Live Feed view — paginated table of recent regulatory changes."""
from __future__ import annotations

import sqlite3
from datetime import datetime

import streamlit as st

from compliance_agent.dashboard.components.severity_badge import severity_badge_html
from compliance_agent.dashboard.theme import SOURCE_LABELS
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.models import Change, Severity
from compliance_agent.storage.proposals import ProposalRepository

_PAGE_SIZE = 50

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


def _highest_severity(severities: list[str]) -> str:
    """Return the most severe label from *severities* (pure, no side-effects)."""
    if not severities:
        return "—"
    return min(severities, key=lambda s: _SEVERITY_ORDER.get(s, 99))


def render_feed(conn: sqlite3.Connection) -> None:
    """Render the Live Feed tab: filterable, paginated change table."""
    st.subheader("Live Feed")

    change_repo = ChangeRepository(conn)
    proposal_repo = ProposalRepository(conn)

    all_changes = change_repo.list_recent(limit=1000)

    # ── Filters ───────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        source_filter = st.selectbox(
            "Source",
            options=["All"] + list(SOURCE_LABELS.values()),
            key="feed_source_filter",
        )
    with col2:
        type_filter = st.selectbox(
            "Change Type",
            options=["All", "new", "amended", "withdrawn"],
            key="feed_type_filter",
        )
    with col3:
        date_from = st.date_input("From", value=None, key="feed_date_from")
    with col4:
        date_to = st.date_input("To", value=None, key="feed_date_to")

    # Build reverse-lookup: display label → source key
    _label_to_key = {v: k for k, v in SOURCE_LABELS.items()}

    filtered: list[Change] = []
    for c in all_changes:
        if source_filter != "All" and c.source != _label_to_key.get(source_filter, source_filter):
            continue
        if type_filter != "All" and c.change_type != type_filter:
            continue
        if date_from is not None and c.detected_at.date() < date_from:
            continue
        if date_to is not None and c.detected_at.date() > date_to:
            continue
        filtered.append(c)

    # ── Pagination ────────────────────────────────────────────────────────────
    total = len(filtered)
    page = st.session_state.get("feed_page", 0)
    max_page = max(0, (total - 1) // _PAGE_SIZE)
    page = min(page, max_page)
    st.session_state["feed_page"] = page

    page_items = filtered[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]

    st.caption(f"{total} changes (page {page + 1} of {max_page + 1})")

    if not page_items:
        st.info("No changes match the current filters.")
        return

    # ── Table ────────────────────────────────────────────────────────────────
    # Build rows with highest-severity proposal info
    rows = []
    for c in page_items:
        proposals = proposal_repo.list_by_change(c.change_id)
        top_sev = _highest_severity([p.severity for p in proposals])
        action_states = list({p.state for p in proposals})
        state_label = ", ".join(action_states) if action_states else "—"
        rows.append(
            {
                "change_id": c.change_id[:16] + "…",
                "_full_id": c.change_id,
                "source": SOURCE_LABELS.get(c.source, c.source),
                "type": c.change_type,
                "detected_at": c.detected_at.strftime("%Y-%m-%d %H:%M"),
                "top_severity": top_sev,
                "action_state": state_label,
            }
        )

    # Render as an interactive table using st.dataframe with selection
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "Change ID": r["change_id"],
                "Source": r["source"],
                "Type": r["type"],
                "Detected At": r["detected_at"],
                "Severity": r["top_severity"],
                "State": r["action_state"],
            }
            for r in rows
        ]
    )

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Row click: select change for detail view
    selected_label = st.selectbox(
        "Select a change to drill into",
        options=["— select —"] + [r["change_id"] for r in rows],
        key="feed_row_selector",
    )
    if selected_label != "— select —":
        # Map abbreviated ID back to full
        full_id = next(
            (r["_full_id"] for r in rows if r["change_id"] == selected_label), None
        )
        if full_id:
            st.session_state["selected_change_id"] = full_id
            st.session_state["return_to"] = "feed"
            st.rerun()

    # ── Pagination controls ───────────────────────────────────────────────────
    pcol1, pcol2, pcol3 = st.columns([1, 2, 1])
    with pcol1:
        if page > 0 and st.button("← Previous", key="feed_prev"):
            st.session_state["feed_page"] = page - 1
            st.rerun()
    with pcol3:
        if page < max_page and st.button("Next →", key="feed_next"):
            st.session_state["feed_page"] = page + 1
            st.rerun()
