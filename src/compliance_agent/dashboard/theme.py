"""Centralised colour palette and style constants for the dashboard.

All values here are pure Python constants — no side effects, no Streamlit calls.
"""
from __future__ import annotations

# Severity → hex colour mapping (used by severity_badge and charts)
SEVERITY_COLORS: dict[str, str] = {
    "critical": "#d32f2f",  # red-700
    "high": "#f57c00",      # orange-700
    "medium": "#fbc02d",    # yellow-700
    "low": "#388e3c",       # green-700
    "unknown": "#757575",   # grey-600
}

# Lighter background tints for badge rendering
SEVERITY_BG_COLORS: dict[str, str] = {
    "critical": "#ffebee",
    "high": "#fff3e0",
    "medium": "#fffde7",
    "low": "#e8f5e9",
    "unknown": "#f5f5f5",
}

# Proposal state colours
STATE_COLORS: dict[str, str] = {
    "pending": "#1565c0",   # blue-800
    "approved": "#2e7d32",  # green-800
    "rejected": "#c62828",  # red-800
}

# Chart colour sequence (plotly-compatible)
CHART_COLORS: list[str] = [
    "#1565c0",
    "#d32f2f",
    "#f57c00",
    "#fbc02d",
    "#388e3c",
    "#6a1b9a",
]

# General palette
PALETTE: dict[str, str] = {
    "primary": "#1565c0",
    "surface": "#ffffff",
    "background": "#f8f9fa",
    "border": "#dee2e6",
    "text": "#212529",
    "muted": "#6c757d",
}

# Source → display name
SOURCE_LABELS: dict[str, str] = {
    "eurlex": "EUR-Lex",
    "sanctions": "EU Sanctions",
    "eba": "EBA",
}
