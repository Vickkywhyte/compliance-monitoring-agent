"""Severity badge component — colour-coded label for proposal severity levels."""
from __future__ import annotations

import streamlit as st

from compliance_agent.dashboard.theme import SEVERITY_BG_COLORS, SEVERITY_COLORS


def severity_color(severity: str) -> str:
    """Return the foreground hex colour for *severity* (pure, no side-effects)."""
    return SEVERITY_COLORS.get(severity.lower(), SEVERITY_COLORS["unknown"])


def severity_bg_color(severity: str) -> str:
    """Return the background hex colour for *severity* (pure, no side-effects)."""
    return SEVERITY_BG_COLORS.get(severity.lower(), SEVERITY_BG_COLORS["unknown"])


def severity_badge_html(severity: str) -> str:
    """Return an inline-HTML badge string for *severity* (pure, no side-effects)."""
    fg = severity_color(severity)
    bg = severity_bg_color(severity)
    label = severity.upper()
    return (
        f'<span style="'
        f"background:{bg};color:{fg};padding:2px 8px;"
        f"border-radius:4px;font-size:0.78em;font-weight:700;"
        f'border:1px solid {fg};">'
        f"{label}</span>"
    )


def render_severity_badge(severity: str) -> None:
    """Render a colour-coded severity badge via st.markdown."""
    st.markdown(severity_badge_html(severity), unsafe_allow_html=True)
