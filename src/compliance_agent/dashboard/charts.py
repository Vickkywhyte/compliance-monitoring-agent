"""Pure chart functions — each accepts data and returns a plotly Figure.

No side-effects, no Streamlit calls. Used by digest.py and other views.
"""
from __future__ import annotations

import plotly.graph_objects as go

from compliance_agent.dashboard.theme import CHART_COLORS, SEVERITY_COLORS


def proposals_by_severity_bar(counts: dict[str, int]) -> go.Figure:
    """Return a bar chart of proposal counts keyed by severity level."""
    order = ["critical", "high", "medium", "low"]
    labels = [s for s in order if s in counts]
    values = [counts[s] for s in labels]
    colors = [SEVERITY_COLORS.get(s, "#757575") for s in labels]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=values,
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Proposals by Severity",
        xaxis_title="Severity",
        yaxis_title="Count",
        showlegend=False,
        margin={"t": 50, "b": 40, "l": 40, "r": 20},
    )
    return fig


def actions_taken_bar(counts: dict[str, int]) -> go.Figure:
    """Return a bar chart of approval actions (approved / edited / rejected)."""
    labels = list(counts.keys())
    values = list(counts.values())

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=CHART_COLORS[: len(labels)],
            text=values,
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Actions Taken",
        xaxis_title="Action",
        yaxis_title="Count",
        showlegend=False,
        margin={"t": 50, "b": 40, "l": 40, "r": 20},
    )
    return fig


def changes_by_source_bar(counts: dict[str, int]) -> go.Figure:
    """Return a bar chart of change counts keyed by regulatory source."""
    labels = list(counts.keys())
    values = list(counts.values())

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=CHART_COLORS[: len(labels)],
            text=values,
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Changes Detected by Source",
        xaxis_title="Source",
        yaxis_title="Count",
        showlegend=False,
        margin={"t": 50, "b": 40, "l": 40, "r": 20},
    )
    return fig


def hallucination_bar(scores: list[dict[str, object]]) -> go.Figure:
    """Return a bar chart of LLM confidence scores to surface low-confidence summaries.

    Each entry in *scores* is expected to have keys 'label' (str) and 'confidence' (float).
    Bars below 0.5 are highlighted in orange to flag potential hallucination risk.
    """
    labels = [str(s.get("label", "")) for s in scores]
    values = [float(s.get("confidence", 0.0)) for s in scores]
    colors = [
        SEVERITY_COLORS["high"] if v < 0.5 else CHART_COLORS[0]
        for v in values
    ]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=[f"{v:.2f}" for v in values],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Summary Confidence (hallucination risk)",
        xaxis_title="Summary",
        yaxis_title="Confidence",
        yaxis_range=[0, 1.1],
        showlegend=False,
        margin={"t": 50, "b": 40, "l": 40, "r": 20},
    )
    fig.add_hline(y=0.5, line_dash="dash", line_color="orange", annotation_text="threshold")
    return fig
