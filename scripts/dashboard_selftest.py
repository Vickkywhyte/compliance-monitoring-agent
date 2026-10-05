"""Phase 6 self-test: imports every dashboard module and verifies pure functions (Lesson 2).

Streamlit views are NOT rendered here (they require a Streamlit server context).
This test verifies:
  1. Every view and component module can be imported without error.
  2. Pure functions produce correct output types.

Exits non-zero on any import or assertion failure.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make src importable when run directly
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

# ── Mock streamlit before any dashboard import ────────────────────────────────
# This prevents ImportError / Streamlit context errors when running outside
# a Streamlit server.
_st_mock = MagicMock()
_st_mock.session_state = {}
_st_mock.cache_resource = lambda f: f  # pass-through decorator
sys.modules["streamlit"] = _st_mock


def _import_all() -> None:
    """Import every dashboard module; raise on first failure."""
    modules = [
        "compliance_agent.dashboard",
        "compliance_agent.dashboard.theme",
        "compliance_agent.dashboard.state",
        "compliance_agent.dashboard.charts",
        "compliance_agent.dashboard.components",
        "compliance_agent.dashboard.components.header",
        "compliance_agent.dashboard.components.severity_badge",
        "compliance_agent.dashboard.components.citation",
        "compliance_agent.dashboard.components.evidence_list",
        "compliance_agent.dashboard.views",
        "compliance_agent.dashboard.views.feed",
        "compliance_agent.dashboard.views.queue",
        "compliance_agent.dashboard.views.change_detail",
        "compliance_agent.dashboard.views.audit_trail",
        "compliance_agent.dashboard.views.digest",
        "compliance_agent.dashboard.app",
    ]
    import importlib

    for mod in modules:
        importlib.import_module(mod)
        print(f"  import OK: {mod}")


def _test_pure_functions() -> None:
    """Exercise pure (non-Streamlit) functions for basic correctness."""
    from compliance_agent.dashboard.components.severity_badge import (
        severity_badge_html,
        severity_color,
    )
    from compliance_agent.dashboard.components.citation import citation_display_text
    from compliance_agent.dashboard.components.evidence_list import format_evidence_rows
    from compliance_agent.dashboard.charts import (
        actions_taken_bar,
        changes_by_source_bar,
        hallucination_bar,
        proposals_by_severity_bar,
    )
    from compliance_agent.storage.models import Citation, Evidence

    # severity_badge
    assert severity_color("critical") == "#d32f2f", "critical must be red"
    assert severity_color("low") == "#388e3c", "low must be green"
    html = severity_badge_html("high")
    assert "HIGH" in html, "badge must contain uppercased label"
    print("  pure: severity_badge OK")

    # citation
    cit = Citation(source_url="https://eur-lex.eu/doc/1", span_start=0, span_end=100, quoted_text="Article 1")
    text = citation_display_text(cit)
    assert "https://eur-lex.eu/doc/1" in text
    assert "[0:100]" in text
    print("  pure: citation OK")

    # evidence_list empty
    rows = format_evidence_rows([])
    assert rows == [], "empty evidence must return empty list"
    ev = Evidence(kind="citation", ref_id="x", excerpt="some text")
    rows2 = format_evidence_rows([ev])
    assert len(rows2) == 1
    assert rows2[0]["kind"] == "citation"
    print("  pure: evidence_list OK")

    # charts return Figure
    import plotly.graph_objects as go

    fig = proposals_by_severity_bar({"critical": 2, "high": 5})
    assert isinstance(fig, go.Figure), "proposals_by_severity_bar must return Figure"
    print("  pure: proposals_by_severity_bar OK")

    fig2 = hallucination_bar([{"label": "s1", "confidence": 0.3}, {"label": "s2", "confidence": 0.9}])
    assert isinstance(fig2, go.Figure), "hallucination_bar must return Figure"
    print("  pure: hallucination_bar OK")

    fig3 = changes_by_source_bar({"EUR-Lex": 10, "EBA": 3})
    assert isinstance(fig3, go.Figure)
    print("  pure: changes_by_source_bar OK")

    fig4 = actions_taken_bar({"approve": 5, "reject": 2})
    assert isinstance(fig4, go.Figure)
    print("  pure: actions_taken_bar OK")


def run_selftest() -> None:
    """Run all selftest checks; print PASS/FAIL summary."""
    print("=== Phase 6 dashboard selftest ===")
    _import_all()
    print()
    _test_pure_functions()
    print("\nPASS: all dashboard selftest checks passed")


if __name__ == "__main__":
    try:
        run_selftest()
    except Exception as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
