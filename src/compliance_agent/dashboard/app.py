"""Compliance Agent Dashboard — Streamlit entry point.

Run with:
    streamlit run src/compliance_agent/dashboard/app.py

Architecture:
- Reads directly from SQLite via repositories (no FastAPI in v1).
- All state mutations route through ApprovalService (C-18).
- Session state tracks selected_change_id for the Change Detail drill-down.
"""
from __future__ import annotations

import streamlit as st

from compliance_agent.dashboard.state import get_config_summary, get_db_connection, init_session_state
from compliance_agent.dashboard.views.audit_trail import render_audit_trail
from compliance_agent.dashboard.views.change_detail import render_change_detail
from compliance_agent.dashboard.views.digest import render_digest
from compliance_agent.dashboard.views.feed import render_feed
from compliance_agent.dashboard.views.queue import render_queue


def main() -> None:
    """Entry point: configure page, render sidebar, dispatch to active view."""
    st.set_page_config(
        page_title="Compliance Agent",
        page_icon="🏛",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()
    conn = get_db_connection()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("⚖ Compliance Agent")
        st.divider()

        st.markdown("**Session**")
        role = st.selectbox(
            "Your role",
            options=["analyst", "officer", "mlro"],
            index=["analyst", "officer", "mlro"].index(
                st.session_state.get("session_role", "officer")
            ),
            key="sidebar_role",
        )
        st.session_state["session_role"] = role

        actor_id = st.text_input(
            "Actor ID",
            value=st.session_state.get("actor_id", "dashboard_user"),
            key="sidebar_actor",
        )
        st.session_state["actor_id"] = actor_id

        st.divider()

        st.markdown("**Configuration**")
        cfg = get_config_summary()
        for k, v in cfg.items():
            st.caption(f"`{k}`: {v}")

        st.divider()

        # Session stats
        st.markdown("**Session Stats**")
        try:
            from compliance_agent.storage.proposals import ProposalRepository

            proposal_repo = ProposalRepository(conn)
            pending_count = len(proposal_repo.list_by_state("pending"))
            st.metric("Pending proposals", pending_count)
        except Exception:
            st.caption("Stats unavailable")

        st.divider()
        st.caption("v0.1.0 · Phase 6")

    # ── Change Detail drill-down (overrides tabs) ─────────────────────────────
    if st.session_state.get("selected_change_id"):
        render_change_detail(conn, st.session_state["selected_change_id"])
        return

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_feed, tab_queue, tab_audit, tab_digest = st.tabs(
        ["📰 Live Feed", "✅ Approval Queue", "📋 Audit Trail", "📊 Weekly Digest"]
    )

    with tab_feed:
        render_feed(conn)

    with tab_queue:
        render_queue(conn)

    with tab_audit:
        render_audit_trail(conn)

    with tab_digest:
        render_digest(conn)


if __name__ == "__main__":
    main()
