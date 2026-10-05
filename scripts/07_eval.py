#!/usr/bin/env python
"""Phase 7 — Evaluation harness CLI (06_EVAL_SPEC.md §5).

Usage:
    python scripts/07_eval.py --golden data/eval/golden.jsonl
    python scripts/07_eval.py --golden data/eval/golden.jsonl --fixture-llm
    python scripts/07_eval.py --golden data/eval/golden.jsonl --config config/agent.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the compliance-agent evaluation harness against a golden set."
    )
    p.add_argument(
        "--golden",
        required=True,
        help="Path to the golden set JSONL file.",
    )
    p.add_argument(
        "--config",
        default=None,
        help="Path to agent config YAML (optional; uses default when omitted).",
    )
    p.add_argument(
        "--fixture-llm",
        action="store_true",
        default=False,
        help="Skip live LLM calls; use pre-computed entailment/rubric values from golden set.",
    )
    p.add_argument(
        "--skip-file-checks",
        action="store_true",
        default=False,
        help="Skip raw_content_path existence checks (useful for CI without raw fixtures).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    from compliance_agent.evaluation.report import print_report
    from compliance_agent.evaluation.runner import run_eval

    golden_path = Path(args.golden)
    if not golden_path.exists():
        print(f"ERROR: golden set not found: {golden_path}", file=sys.stderr)
        return 1

    try:
        report = run_eval(
            golden_path=golden_path,
            config_path=args.config,
            fixture_llm=args.fixture_llm,
            skip_file_checks=args.skip_file_checks,
        )
    except Exception as exc:
        print(f"ERROR: evaluation failed: {exc}", file=sys.stderr)
        return 1

    print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
