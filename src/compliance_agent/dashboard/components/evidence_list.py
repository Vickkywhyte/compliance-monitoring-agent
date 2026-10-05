"""Evidence list component — renders a list of Evidence items."""
from __future__ import annotations

import streamlit as st

from compliance_agent.storage.models import Evidence


def format_evidence_rows(evidence: list[Evidence]) -> list[dict[str, str]]:
    """Convert *evidence* to a list of display dicts (pure, no side-effects)."""
    return [
        {
            "kind": item.kind,
            "ref_id": item.ref_id,
            "excerpt": item.excerpt[:200],
        }
        for item in evidence
    ]


def render_evidence_list(evidence: list[Evidence]) -> None:
    """Render *evidence* items as an expander table; handles empty list gracefully."""
    if not evidence:
        st.caption("No evidence items.")
        return

    rows = format_evidence_rows(evidence)
    for row in rows:
        with st.expander(f"{row['kind'].upper()} — {row['ref_id'][:20]}…"):
            st.text(row["excerpt"])
