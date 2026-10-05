"""Change Detail drill-down view — full context for a single regulatory change."""
from __future__ import annotations

import sqlite3

import streamlit as st

from compliance_agent.approval.service import ApprovalService
from compliance_agent.dashboard.components.citation import render_citation
from compliance_agent.dashboard.components.evidence_list import render_evidence_list
from compliance_agent.dashboard.components.severity_badge import severity_badge_html
from compliance_agent.dashboard.theme import SOURCE_LABELS, STATE_COLORS
from compliance_agent.exceptions import ApprovalError
from compliance_agent.storage.audit import AuditRepository
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.mappings import ProcessMappingRepository
from compliance_agent.storage.models import Proposal, Role
from compliance_agent.storage.proposals import ProposalRepository
from compliance_agent.storage.summaries import SummaryRepository


def render_change_detail(conn: sqlite3.Connection, change_id: str) -> None:
    """Render the full drill-down detail for *change_id*."""
    change_repo = ChangeRepository(conn)
    summary_repo = SummaryRepository(conn)
    mapping_repo = ProcessMappingRepository(conn)
    proposal_repo = ProposalRepository(conn)
    audit_repo = AuditRepository(conn)

    change = change_repo.get_by_id(change_id)
    if change is None:
        st.error(f"Change not found: {change_id}")
        return

    # ── Back button ──────────────────────────────────────────────────────────
    return_to = st.session_state.get("return_to", "feed")
    if st.button(f"← Back to {return_to.title()}", key="detail_back"):
        st.session_state["selected_change_id"] = None
        st.rerun()

    st.divider()

    # ── Header ───────────────────────────────────────────────────────────────
    st.subheader(f"Change Detail — {change_id[:24]}…")

    meta_col1, meta_col2, meta_col3, meta_col4 = st.columns(4)
    with meta_col1:
        st.metric("Source", SOURCE_LABELS.get(change.source, change.source))
    with meta_col2:
        st.metric("Type", change.change_type)
    with meta_col3:
        st.metric("Detected", change.detected_at.strftime("%Y-%m-%d"))
    with meta_col4:
        st.metric("Effective", str(change.effective_date or "—"))

    st.caption(f"Stable ID: `{change.stable_id}` | Doc ID: `{change.doc_id}`")

    st.divider()

    # ── Summary ──────────────────────────────────────────────────────────────
    st.markdown("### Summary")
    summary = summary_repo.get_by_change_id(change_id)
    summaries = [summary] if summary else []
    if summaries:
        s = summaries[0]
        st.write(s.text)
        if s.low_confidence:
            st.warning("Low-confidence summary — review carefully.")
        st.caption(
            f"Model: {s.model} | Confidence: {s.confidence:.2f} | "
            f"Prompt: {s.prompt_version}"
        )
        if s.citations:
            st.markdown("**Citations:**")
            for citation in s.citations:
                render_citation(citation)
    else:
        st.info("No summary generated yet.")

    st.divider()

    # ── Process Mappings ─────────────────────────────────────────────────────
    st.markdown("### Process Mappings")
    mappings = mapping_repo.get_by_change_id(change_id)
    if mappings:
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "Process": m.process_id,
                    "Section": m.process_section_id,
                    "Impact": m.impact_type,
                    "Confidence": f"{m.confidence:.2f}",
                    "Rationale": m.rationale[:120] + "…" if len(m.rationale) > 120 else m.rationale,
                }
                for m in mappings
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No process mappings yet.")

    st.divider()

    # ── Proposals ────────────────────────────────────────────────────────────
    st.markdown("### Proposals")
    proposals = proposal_repo.list_by_change(change_id)
    if proposals:
        for proposal in proposals:
            _render_proposal_card(conn, proposal)
    else:
        st.info("No proposals generated yet.")

    st.divider()

    # ── Audit Trail ──────────────────────────────────────────────────────────
    st.markdown("### Audit Trail")
    events = audit_repo.query(entity_id=change_id, limit=200)
    # Append proposal-level events
    for proposal in proposals:
        events += audit_repo.query(entity_id=proposal.proposal_id, limit=50)
    events.sort(key=lambda e: e.occurred_at, reverse=True)

    if events:
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "Time": e.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "Actor": e.actor,
                    "Action": e.action,
                    "Entity": e.entity_type,
                    "ID": e.entity_id[:20] + "…",
                }
                for e in events
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No audit events yet.")


def _render_proposal_card(conn: sqlite3.Connection, proposal: Proposal) -> None:
    """Render a single proposal card with state badge and action buttons."""
    badge = severity_badge_html(proposal.severity)
    state_color = STATE_COLORS.get(proposal.state, "#333")

    with st.expander(
        f"{proposal.proposal_id[:16]}… | {proposal.title[:60]}",
        expanded=False,
    ):
        st.markdown(f"**Severity:** {badge}", unsafe_allow_html=True)
        st.markdown(
            f"**State:** <span style='color:{state_color};font-weight:700'>{proposal.state.upper()}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Category:** `{proposal.category}` | **Assignee:** `{proposal.assignee_role}`")
        st.markdown(f"**Deadline:** {proposal.deadline or '—'} — {proposal.deadline_rationale}")
        st.markdown(f"**Description:** {proposal.description}")

        render_evidence_list(proposal.evidence)

        if proposal.state == "pending":
            _render_proposal_actions(conn, proposal)


def _render_proposal_actions(conn: sqlite3.Connection, proposal: Proposal) -> None:
    """Render approval action buttons for a pending proposal in the detail view."""
    actor_id: str = st.session_state.get("actor_id", "dashboard_user")
    actor_role: Role = st.session_state.get("session_role", "officer")  # type: ignore[assignment]
    service = ApprovalService(conn)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✔ Approve", key=f"detail_approve_{proposal.proposal_id}", type="primary"):
            try:
                service.approve(proposal.proposal_id, actor_role, actor_id)
                st.toast("Approved.", icon="✅")
                st.rerun()
            except ApprovalError as exc:
                st.error(str(exc))
    with col3:
        if st.button("✗ Reject", key=f"detail_reject_{proposal.proposal_id}"):
            st.session_state[f"detail_reject_{proposal.proposal_id}"] = True
            st.rerun()

    if st.session_state.get(f"detail_reject_{proposal.proposal_id}"):
        reason = st.text_area("Reason (required)", key=f"detail_reason_{proposal.proposal_id}")
        if st.button("Confirm", key=f"detail_confirm_reject_{proposal.proposal_id}"):
            if not reason.strip():
                st.warning("Reason is required.")
            else:
                try:
                    service.reject(proposal.proposal_id, actor_role, actor_id, reason)
                    st.toast("Rejected.", icon="❌")
                    st.session_state.pop(f"detail_reject_{proposal.proposal_id}", None)
                    st.rerun()
                except ApprovalError as exc:
                    st.error(str(exc))
