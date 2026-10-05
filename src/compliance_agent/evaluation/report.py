"""Render an EvalReport as a human-readable text table (06_EVAL_SPEC.md §5.3)."""
from __future__ import annotations

import math

from compliance_agent.evaluation.runner import EvalReport


def render_report(report: EvalReport) -> str:
    """Return a formatted text table of the eval report."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"  Evaluation Report — {report.timestamp}")
    lines.append(f"  Golden set : {report.golden_path}")
    lines.append(f"  Entries    : {report.n_entries}")
    lines.append("=" * 72)
    lines.append(
        f"  {'Metric':<35} {'Mean':>8}  {'CI 95%':>18}  {'Direction':<14}"
    )
    lines.append("-" * 72)

    for name in sorted(report.metric_means):
        mean = report.metric_means[name]
        lo = report.metric_ci_lower.get(name, float("nan"))
        hi = report.metric_ci_upper.get(name, float("nan"))
        direction = report.metric_directions.get(name, "higher_better")

        mean_str = f"{mean:.4f}" if not math.isnan(mean) else "    n/a"
        ci_str = (
            f"[{lo:.4f}, {hi:.4f}]"
            if not (math.isnan(lo) or math.isnan(hi))
            else "         n/a      "
        )
        lines.append(f"  {name:<35} {mean_str:>8}  {ci_str:>18}  {direction:<14}")

    lines.append("=" * 72)
    return "\n".join(lines)


def print_report(report: EvalReport) -> None:
    """Print the rendered report to stdout."""
    print(render_report(report))
