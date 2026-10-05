#!/usr/bin/env python
"""Phase 7 — Evaluation harness self-test (06_EVAL_SPEC.md §5).

Runs a 5-entry mini golden set through the evaluation runner in fixture mode
(no live pipeline, no LLM calls) and asserts:
- All expected metrics appear in the report.
- Every metric value is in [0, 1] or >= 0 (for unbounded metrics).
- The report serializes without error.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path


UNBOUNDED_METRICS = {
    "e2e_latency_p50_ms",
    "e2e_latency_p95_ms",
    "cost_per_1k_changes_usd",
}

EXPECTED_METRICS = {
    "detection_recall",
    "detection_precision",
    "mapping_precision",
    "mapping_recall",
    "confidence_brier",
    "proposal_acceptance_rate",
    "proposal_edit_rate",
    "proposal_rejection_rate",
    "routing_accuracy",
    "deadline_accuracy",
    "severity_accuracy",
    "e2e_latency_p50_ms",
    "e2e_latency_p95_ms",
    "cost_per_1k_changes_usd",
    "llm_fallback_rate",
    "audit_completeness",
    "approval_bypass_rate",
    "summary_faithfulness",
    "summary_hallucination_rate",
    "summary_rubric_score",
}


def _make_golden_jsonl(path: Path) -> None:
    """Write a 5-entry mini golden set (all low severity → proposals may be empty)."""
    entries = [
        {
            "id": f"selftest-{i:03d}",
            "source": "EUR-Lex",
            "source_url": "https://eur-lex.europa.eu/selftest",
            "raw_content_path": str(path.parent / "raw.txt"),
            "change_type": "new_requirement",
            "expected_mappings": [{"process_id": "aml", "impact_type": "new_obligation"}],
            "expected_proposals": [],
            "expected_severity": "low",
            "annotated_at": "2026-10-01",
        }
        for i in range(1, 6)
    ]
    (path.parent / "raw.txt").write_text("Selftest raw content.", encoding="utf-8")
    path.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
    )


def _make_pipeline_results() -> list[dict]:
    """Five synthetic pipeline output dicts (one per golden entry)."""
    return [
        {
            "detected": True,
            "fp_count": 0,
            "mappings": [{"process_id": "aml", "impact_type": "new_obligation", "confidence": 0.9}],
            "action": "approve",
            "proposals": [{"assignee_role": "compliance_officer", "severity": "low", "deadline": "2026-11-05"}],
            "latency_ms": 3000.0,
            "cost_usd": 0.05,
            "fallback_calls": 0,
            "llm_calls": 4,
            "audit_complete": True,
            "bypassed": False,
            "entailments": ["yes", "yes"],
            "rubric_score": 4,
        }
        for _ in range(5)
    ]


def main() -> int:
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        golden_path = Path(tmpdir) / "golden.jsonl"
        _make_golden_jsonl(golden_path)
        pipeline_results = _make_pipeline_results()

        from compliance_agent.evaluation.runner import run_eval

        try:
            report = run_eval(
                golden_path=golden_path,
                config_path=None,
                pipeline_results=pipeline_results,
                fixture_llm=True,
                skip_file_checks=False,
            )
        except Exception as exc:
            print(f"FAIL: run_eval raised: {exc}", file=sys.stderr)
            return 1

        # Check all expected metrics are present
        for name in EXPECTED_METRICS:
            if name not in report.metric_means:
                errors.append(f"missing metric: {name!r}")

        # Check all metric values are in valid range
        for name, val in report.metric_means.items():
            if math.isnan(val):
                continue
            if name in UNBOUNDED_METRICS:
                if val < 0:
                    errors.append(f"{name}: value {val} < 0 (expected >= 0)")
            else:
                if not (0.0 <= val <= 1.0):
                    errors.append(f"{name}: value {val} outside [0, 1]")

        # Check JSON serialization
        try:
            report.model_dump_json()
        except Exception as exc:
            errors.append(f"JSON serialization failed: {exc}")

    if errors:
        print(f"\neval-selftest FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    n = len(report.metric_means)
    print(f"eval-selftest OK — {report.n_entries} entries, {n} metrics computed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
