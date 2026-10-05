"""Page header component — title, subtitle, and divider."""
from __future__ import annotations

import streamlit as st


def render_header(title: str, subtitle: str = "") -> None:
    """Render a page header with an optional subtitle and a visual divider."""
    st.title(title)
    if subtitle:
        st.caption(subtitle)
    st.divider()
