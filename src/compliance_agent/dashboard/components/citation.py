"""Citation component — renders a source citation with collapsible quoted text."""
from __future__ import annotations

import streamlit as st

from compliance_agent.storage.models import Citation


def citation_display_text(citation: Citation) -> str:
    """Return a compact text representation of *citation* (pure, no side-effects)."""
    return f"{citation.source_url} [{citation.span_start}:{citation.span_end}]"


def render_citation(citation: Citation) -> None:
    """Render *citation* as a URL label with a collapsible quoted-text expander."""
    label = citation_display_text(citation)
    with st.expander(label):
        st.caption(citation.quoted_text)
