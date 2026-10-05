"""Weekly Digest view — on-demand summary report with charts."""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

import streamlit as st

from compliance_agent.dashboard.charts import (
    actions_taken_bar,
    changes_by_source_bar,
    proposals_by_severity_bar,
)
from compliance_agent.dashboard.theme import SOURCE_LABELS
from compliance_agent.storage.approvals import ApprovalActionRepository
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.proposals import ProposalRepository


def render_digest(conn: sqlite3.Connection) -> None:
    """Render the Weekly Digest tab: on-demand report with table + charts."""
    st.subheader("Weekly Digest")

    if st.button("Generate digest", key="digest_generate", type="primary"):
        _render_digest_content(conn)
    else:
        st.info("Click 'Generate digest' to build a fresh report.")


def _render_digest_content(conn: sqlite3.Connection) -> None:
    """Compute and render digest statistics for the past 7 days."""
    change_repo = ChangeRepository(conn)
    proposal_repo = ProposalRepository(conn)
    action_repo = ApprovalActionRepository(conn)

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    # ── Collect data ──────────────────────────────────────────────────────────
    all_changes = change_repo.list_recent(limit=2000)
    recent_changes = [c for c in all_changes if c.detected_at >= cutoff]

    changes_by_source: Counter[str] = Counter(
        SOURCE_LABELS.get(c.source, c.source) for c in recent_changes
    )

    all_pending = proposal_repo.list_by_state("pending")
    all_approved = proposal_repo.list_by_state("approved")
    all_rejected = proposal_repo.list_by_state("rejected")

    recent_proposals = [
        p
        for p in (all_pending + all_approved + all_rejected)
        if p.generated_at >= cutoff
    ]
    proposals_by_severity: Counter[str] = Counter(p.severity for p in recent_proposals)

    # Approval actions in last 7 days
    all_actions = []
    for p in all_approved + all_rejected:
        all_actions.extend(action_repo.get_by_proposal(p.proposal_id))
    recent_actions = [a for a in all_actions if a.acted_at >= cutoff]
    actions_by_type: Counter[str] = Counter(a.action for a in recent_actions)

    open_proposals = [p for p in all_pending if p.generated_at >= cutoff]

    # ── Summary table ────────────────────────────────────────────────────────
    st.markdown("#### Summary (last 7 days)")
    import pandas as pd

    summary_rows = [
        {"Metric": "Changes detected", "Value": len(recent_changes)},
        {"Metric": "Proposals generated", "Value": len(recent_proposals)},
        {"Metric": "Actions taken", "Value": len(recent_actions)},
        {"Metric": "Open items", "Value": len(open_proposals)},
    ]
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Charts ───────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        if changes_by_source:
            st.plotly_chart(
                changes_by_source_bar(dict(changes_by_source)),
                use_container_width=True,
            )
        else:
            st.caption("No changes detected this week.")

    with col2:
        if proposals_by_severity:
            st.plotly_chart(
                proposals_by_severity_bar(dict(proposals_by_severity)),
                use_container_width=True,
            )
        else:
            st.caption("No proposals generated this week.")

    if actions_by_type:
        st.plotly_chart(
            actions_taken_bar(dict(actions_by_type)),
            use_container_width=True,
        )
    else:
        st.caption("No approval actions taken this week.")
