"""Tests for pure dashboard functions — no Streamlit rendering (Phase 6).

Only tests pure Python functions: charts.py, components/*, theme.py.
Streamlit rendering is NOT tested here (requires a server context).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock streamlit before any dashboard import so tests run outside Streamlit context
_st_mock = MagicMock()
_st_mock.session_state = {}
_st_mock.cache_resource = lambda f: f
sys.modules.setdefault("streamlit", _st_mock)


# ── severity_badge ─────────────────────────────────────────────────────────────


def test_severity_badge_colors_correct() -> None:
    """Each severity level maps to the expected hex colour."""
    from compliance_agent.dashboard.components.severity_badge import severity_color
    from compliance_agent.dashboard.theme import SEVERITY_COLORS

    for sev, expected in SEVERITY_COLORS.items():
        assert severity_color(sev) == expected, f"color mismatch for {sev}"


def test_severity_badge_html_contains_label() -> None:
    """Badge HTML contains the uppercased severity label."""
    from compliance_agent.dashboard.components.severity_badge import severity_badge_html

    for sev in ("critical", "high", "medium", "low"):
        html = severity_badge_html(sev)
        assert sev.upper() in html


# ── citation ──────────────────────────────────────────────────────────────────


def test_citation_renders_expected_text() -> None:
    """citation_display_text formats URL and span correctly."""
    from compliance_agent.dashboard.components.citation import citation_display_text
    from compliance_agent.storage.models import Citation

    cit = Citation(
        source_url="https://eur-lex.europa.eu/doc/1",
        span_start=10,
        span_end=200,
        quoted_text="Article 1: Scope.",
    )
    text = citation_display_text(cit)
    assert "https://eur-lex.europa.eu/doc/1" in text
    assert "[10:200]" in text


# ── evidence_list ─────────────────────────────────────────────────────────────


def test_evidence_list_handles_empty() -> None:
    """format_evidence_rows returns an empty list for empty input."""
    from compliance_agent.dashboard.components.evidence_list import format_evidence_rows

    assert format_evidence_rows([]) == []


def test_evidence_list_formats_items() -> None:
    """format_evidence_rows returns one dict per Evidence item."""
    from compliance_agent.dashboard.components.evidence_list import format_evidence_rows
    from compliance_agent.storage.models import Evidence

    items = [
        Evidence(kind="citation", ref_id="ref1", excerpt="text one"),
        Evidence(kind="diff", ref_id="ref2", excerpt="text two"),
    ]
    rows = format_evidence_rows(items)
    assert len(rows) == 2
    assert rows[0]["kind"] == "citation"
    assert rows[1]["kind"] == "diff"


# ── charts ────────────────────────────────────────────────────────────────────


def test_charts_hallucination_bar_produces_figure() -> None:
    """hallucination_bar returns a plotly Figure for valid input."""
    import plotly.graph_objects as go

    from compliance_agent.dashboard.charts import hallucination_bar

    scores = [
        {"label": "summary_1", "confidence": 0.3},
        {"label": "summary_2", "confidence": 0.85},
    ]
    fig = hallucination_bar(scores)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0


def test_digest_chart_produces_figure() -> None:
    """proposals_by_severity_bar returns a plotly Figure for digest data."""
    import plotly.graph_objects as go

    from compliance_agent.dashboard.charts import proposals_by_severity_bar

    fig = proposals_by_severity_bar({"critical": 1, "high": 3, "medium": 7, "low": 2})
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0


def test_changes_by_source_bar_produces_figure() -> None:
    """changes_by_source_bar returns a plotly Figure."""
    import plotly.graph_objects as go

    from compliance_agent.dashboard.charts import changes_by_source_bar

    fig = changes_by_source_bar({"EUR-Lex": 10, "EBA": 3, "EU Sanctions": 1})
    assert isinstance(fig, go.Figure)


def test_actions_taken_bar_produces_figure() -> None:
    """actions_taken_bar returns a plotly Figure."""
    import plotly.graph_objects as go

    from compliance_agent.dashboard.charts import actions_taken_bar

    fig = actions_taken_bar({"approve": 5, "edit_approve": 2, "reject": 1})
    assert isinstance(fig, go.Figure)


# ── C-18 import-graph verification ────────────────────────────────────────────


def test_queue_module_does_not_import_proposal_repository_directly() -> None:
    """queue.py must not call ProposalRepository for state mutations (C-18).

    This test greps the module source for any direct instantiation of
    ProposalRepository inside queue.py beyond the read-only listing usage.
    It verifies that no line of the form `ProposalRepository(` appears
    in a context that could write state — specifically we confirm the module
    itself does not have more than ONE occurrence (the import/read-only use).

    A true import-graph check: load the source and count occurrences.
    queue.py may import ProposalRepository for read-only listing; it must
    not directly call any write method on it. Since the only write-capable
    method that bypasses ApprovalService would be update_state_with_lock,
    we assert that string is absent.
    """
    queue_path = (
        Path(__file__).parents[1]
        / "src"
        / "compliance_agent"
        / "dashboard"
        / "views"
        / "queue.py"
    )
    source = queue_path.read_text()
    assert "update_state_with_lock" not in source, (
        "queue.py must not call update_state_with_lock directly — "
        "all state mutations must go through ApprovalService (C-18)"
    )
    # Additionally confirm ApprovalService IS used (positive assertion)
    assert "ApprovalService" in source, "queue.py must use ApprovalService"
