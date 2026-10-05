"""Evaluation runner — orchestrates metrics over a golden set (06_EVAL_SPEC.md §5).

run_eval(golden_path, config_path, *, pipeline_results=None, fixture_llm=False)
    → EvalReport

Fixture mode: when pipeline_results is provided, pipeline stages are skipped and
metrics are computed directly from the pre-computed list of per-entry dicts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from compliance_agent.evaluation.golden import GoldenEntry, load_golden, validate_golden
from compliance_agent.evaluation.metrics.base import Metric
from compliance_agent.evaluation.metrics.coverage import DetectionPrecision, DetectionRecall
from compliance_agent.evaluation.metrics.mapping import (
    ConfidenceBrier,
    MappingPrecision,
    MappingRecall,
)
from compliance_agent.evaluation.metrics.operational import (
    ApprovalBypassRate,
    AuditCompleteness,
    CostPer1kChanges,
    E2ELatencyP50,
    E2ELatencyP95,
    LLMFallbackRate,
)
from compliance_agent.evaluation.metrics.proposal import (
    ProposalAcceptanceRate,
    ProposalEditRate,
    ProposalRejectionRate,
)
from compliance_agent.evaluation.metrics.routing import (
    DeadlineAccuracy,
    RoutingAccuracy,
    SeverityAccuracy,
)
from compliance_agent.evaluation.metrics.summary import (
    SummaryFaithfulness,
    SummaryHallucinationRate,
    SummaryRubricScore,
)
from compliance_agent.evaluation.stats import bootstrap_ci

log = structlog.get_logger(__name__)

_RESULTS_DIR = Path("results/evals")


class EvalEntryResult(BaseModel):
    """Per-entry metric scores."""

    entry_id: str
    scores: dict[str, float] = Field(default_factory=dict)


class EvalReport(BaseModel):
    """Aggregated evaluation report."""

    timestamp: str
    golden_path: str
    n_entries: int
    metric_means: dict[str, float] = Field(default_factory=dict)
    metric_ci_lower: dict[str, float] = Field(default_factory=dict)
    metric_ci_upper: dict[str, float] = Field(default_factory=dict)
    metric_directions: dict[str, str] = Field(default_factory=dict)
    entry_results: list[EvalEntryResult] = Field(default_factory=list)


def _build_metrics(fixture_llm: bool = False) -> list[Metric]:
    """Instantiate all metrics. With fixture_llm, summary metrics use no judge."""
    return [
        DetectionRecall(),
        DetectionPrecision(),
        MappingPrecision(),
        MappingRecall(),
        ConfidenceBrier(),
        ProposalAcceptanceRate(),
        ProposalEditRate(),
        ProposalRejectionRate(),
        RoutingAccuracy(),
        DeadlineAccuracy(),
        SeverityAccuracy(),
        E2ELatencyP50(),
        E2ELatencyP95(),
        CostPer1kChanges(),
        LLMFallbackRate(),
        AuditCompleteness(),
        ApprovalBypassRate(),
        SummaryFaithfulness(judge=None),
        SummaryHallucinationRate(),
        SummaryRubricScore(),
    ]


def run_eval(
    golden_path: str | Path,
    config_path: str | Path | None = None,
    *,
    pipeline_results: list[dict[str, Any]] | None = None,
    fixture_llm: bool = False,
    skip_file_checks: bool = False,
) -> EvalReport:
    """Run evaluation and return an EvalReport.

    Args:
        golden_path: Path to JSONL golden set.
        config_path: Path to agent config (unused in fixture mode).
        pipeline_results: Pre-computed per-entry outputs; bypasses pipeline when set.
        fixture_llm: If True, LLM-dependent metrics receive no judge (use pre-computed values).
        skip_file_checks: If True, raw_content_path existence checks are skipped (for tests).
    """
    entries = load_golden(golden_path)
    validate_golden(entries, check_files=not skip_file_checks)
    metrics = _build_metrics(fixture_llm=fixture_llm)

    if pipeline_results is None:
        pipeline_results = _run_pipeline(entries, config_path)

    if len(pipeline_results) != len(entries):
        raise ValueError(
            f"pipeline_results length {len(pipeline_results)} != "
            f"golden entries length {len(entries)}"
        )

    entry_results: list[EvalEntryResult] = []
    per_metric_values: dict[str, list[float]] = {m.name: [] for m in metrics}

    for entry, actual in zip(entries, pipeline_results):
        scores: dict[str, float] = {}
        golden_dict = entry.model_dump()
        for m in metrics:
            try:
                score = m.compute(golden_dict, actual)
                scores[m.name] = score
                per_metric_values[m.name].append(score)
            except Exception as exc:
                log.warning("metric_compute_error", metric=m.name, entry_id=entry.id, error=str(exc))
        entry_results.append(EvalEntryResult(entry_id=entry.id, scores=scores))

    # Dataset-level metrics that override per-entry mean
    for m in metrics:
        if per_metric_values[m.name]:
            golden_dicts = [e.model_dump() for e in entries]
            try:
                batch_val = m.compute_batch(golden_dicts, pipeline_results)
                per_metric_values[m.name] = [batch_val]
            except Exception:
                pass

    means: dict[str, float] = {}
    ci_lower: dict[str, float] = {}
    ci_upper: dict[str, float] = {}
    directions: dict[str, str] = {}

    for m in metrics:
        vals = per_metric_values[m.name]
        directions[m.name] = m.direction
        if not vals:
            means[m.name] = float("nan")
            ci_lower[m.name] = float("nan")
            ci_upper[m.name] = float("nan")
            continue
        means[m.name] = sum(vals) / len(vals)
        if len(vals) >= 2:
            lo, hi = bootstrap_ci(vals)
            ci_lower[m.name] = lo
            ci_upper[m.name] = hi
        else:
            ci_lower[m.name] = vals[0]
            ci_upper[m.name] = vals[0]

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = EvalReport(
        timestamp=ts,
        golden_path=str(golden_path),
        n_entries=len(entries),
        metric_means=means,
        metric_ci_lower=ci_lower,
        metric_ci_upper=ci_upper,
        metric_directions=directions,
        entry_results=entry_results,
    )

    _save_report(report, ts)
    return report


def _run_pipeline(
    entries: list[GoldenEntry],
    config_path: str | Path | None,
) -> list[dict[str, Any]]:
    """Run the live compliance pipeline for each golden entry.

    This is a stub that returns empty dicts — a real implementation would
    invoke the detection + processing + approval pipeline stages.
    """
    log.warning(
        "pipeline_stub",
        msg="Live pipeline execution not yet wired; returning empty outputs for each entry",
    )
    return [{} for _ in entries]


def _save_report(report: EvalReport, ts: str) -> None:
    """Persist report as JSON under results/evals/."""
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / f"{ts}.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    log.info("eval_report_saved", path=str(out))
