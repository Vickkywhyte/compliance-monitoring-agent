"""Approval Queue view — pending proposals with approve/edit+approve/reject actions.

Security note (C-18): all state mutations go through ApprovalService.
ProposalRepository is used read-only for listing; it is NEVER used to write state.
Do not add direct ProposalRepository state-write calls to this module.
"""
from __future__ import annotations

import sqlite3

import streamlit as st

from compliance_agent.approval.service import ApprovalService
from compliance_agent.dashboard.components.evidence_list import render_evidence_list
from compliance_agent.dashboard.components.severity_badge import severity_badge_html
from compliance_agent.dashboard.theme import SOURCE_LABELS, STATE_COLORS
from compliance_agent.exceptions import ApprovalError
from compliance_agent.storage.models import Proposal, Role
from compliance_agent.storage.proposals import ProposalRepository

_ROLES: list[str] = ["analyst", "officer", "mlro"]


def render_queue(conn: sqlite3.Connection) -> None:
    """Render the Approval Queue tab: filterable pending proposals with action buttons."""
    st.subheader("Approval Queue")

    proposal_repo = ProposalRepository(conn)

    # ── Filters ───────────────────────────────────────────────────────────────
    session_role: str = st.session_state.get("session_role", "officer")
    role_filter: str = st.selectbox(
        "Filter by role",
        options=["All"] + _ROLES,
        index=_ROLES.index(session_role) + 1 if session_role in _ROLES else 0,
        key="queue_role_filter",
    )
    role_param: Role | None = role_filter if role_filter != "All" else None  # type: ignore[assignment]

    pending = proposal_repo.list_by_state("pending", role=role_param)

    if not pending:
        st.info("No pending proposals" + (f" for role '{role_filter}'" if role_filter != "All" else "") + ".")
        return

    st.caption(f"{len(pending)} pending proposal(s)")

    for proposal in pending:
        _render_proposal_row(conn, proposal)


def _render_proposal_row(conn: sqlite3.Connection, proposal: Proposal) -> None:
    """Render a single proposal row with inline detail expansion and action buttons."""
    badge = severity_badge_html(proposal.severity)
    state_color = STATE_COLORS.get(proposal.state, "#333")

    with st.expander(
        f"{proposal.proposal_id[:16]}… | {proposal.title[:60]} | deadline {proposal.deadline or '—'}",
        expanded=False,
    ):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**Severity:** {badge}", unsafe_allow_html=True)
            st.markdown(f"**Category:** `{proposal.category}`")
            st.markdown(f"**Assignee role:** `{proposal.assignee_role}`")
            st.markdown(f"**State:** <span style='color:{state_color}'>{proposal.state}</span>", unsafe_allow_html=True)
            st.markdown(f"**Description:** {proposal.description}")
            if proposal.deadline_rationale:
                st.caption(f"Deadline rationale: {proposal.deadline_rationale}")
        with col2:
            if proposal.state == "pending":
                _render_action_buttons(conn, proposal)

        with st.expander("Evidence", expanded=False):
            render_evidence_list(proposal.evidence)

        if st.button("View change detail", key=f"queue_detail_{proposal.proposal_id}"):
            st.session_state["selected_change_id"] = proposal.change_id
            st.session_state["selected_proposal_id"] = proposal.proposal_id
            st.session_state["return_to"] = "queue"
            st.rerun()


def _render_action_buttons(conn: sqlite3.Connection, proposal: Proposal) -> None:
    """Render Approve / Edit+Approve / Reject buttons for a pending proposal."""
    actor_id: str = st.session_state.get("actor_id", "dashboard_user")
    actor_role: Role = st.session_state.get("session_role", "officer")  # type: ignore[assignment]
    service = ApprovalService(conn)

    if st.button("✔ Approve", key=f"approve_{proposal.proposal_id}", type="primary"):
        try:
            service.approve(proposal.proposal_id, actor_role, actor_id)
            st.toast(f"Proposal {proposal.proposal_id[:12]}… approved.", icon="✅")
            st.rerun()
        except ApprovalError as exc:
            st.error(str(exc))

    if st.button("✏ Edit+Approve", key=f"edit_approve_{proposal.proposal_id}"):
        st.session_state[f"edit_mode_{proposal.proposal_id}"] = True
        st.rerun()

    if st.session_state.get(f"edit_mode_{proposal.proposal_id}"):
        new_title = st.text_input("Title", value=proposal.title, key=f"edit_title_{proposal.proposal_id}")
        new_desc = st.text_area("Description", value=proposal.description, key=f"edit_desc_{proposal.proposal_id}")
        if st.button("Confirm Edit+Approve", key=f"confirm_edit_{proposal.proposal_id}"):
            try:
                service.edit_approve(
                    proposal.proposal_id,
                    actor_role,
                    actor_id,
                    edits={"title": new_title, "description": new_desc},
                )
                st.toast("Proposal approved with edits.", icon="✅")
                st.session_state.pop(f"edit_mode_{proposal.proposal_id}", None)
                st.rerun()
            except ApprovalError as exc:
                st.error(str(exc))

    if st.button("✗ Reject", key=f"reject_{proposal.proposal_id}"):
        st.session_state[f"reject_mode_{proposal.proposal_id}"] = True
        st.rerun()

    if st.session_state.get(f"reject_mode_{proposal.proposal_id}"):
        reason = st.text_area("Rejection reason (required)", key=f"reject_reason_{proposal.proposal_id}")
        if st.button("Confirm Reject", key=f"confirm_reject_{proposal.proposal_id}"):
            if not reason.strip():
                st.warning("Reason is required before rejecting.")
            else:
                try:
                    service.reject(proposal.proposal_id, actor_role, actor_id, reason)
                    st.toast("Proposal rejected.", icon="❌")
                    st.session_state.pop(f"reject_mode_{proposal.proposal_id}", None)
                    st.rerun()
                except ApprovalError as exc:
                    st.error(str(exc))
