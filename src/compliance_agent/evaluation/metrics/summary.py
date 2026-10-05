"""Summary metrics — faithfulness, hallucination rate, rubric score (06_EVAL_SPEC.md §4.1-§4.2, §4.6)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from compliance_agent.evaluation.metrics.base import Metric

if TYPE_CHECKING:
    from compliance_agent.evaluation.judge import EvalJudge


class SummaryFaithfulness(Metric):
    """Fraction of summary claims entailed by the source document (§4.1).

    actual_output keys:
        {"entailments": list[str]}  — per-claim verdicts: "yes"|"partial"|"no"

    If judge is provided and entailments are absent, the judge is called.
    For offline testing, inject pre-computed entailments in actual_output.
    """

    def __init__(self, judge: "EvalJudge | None" = None) -> None:
        self._judge = judge

    @property
    def name(self) -> str:
        return "summary_faithfulness"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        entailments = actual_output.get("entailments", [])
        if not entailments:
            return 0.0
        entailed = sum(1 for v in entailments if v == "yes")
        return entailed / len(entailments)


class SummaryHallucinationRate(Metric):
    """Fraction of claims NOT entailed, with partials counting 0.5 (§4.2).

    actual_output keys:
        {"entailments": list[str]}  — per-claim verdicts
    """

    @property
    def name(self) -> str:
        return "summary_hallucination_rate"

    @property
    def direction(self) -> Literal["higher_better", "lower_better"]:
        return "lower_better"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        entailments = actual_output.get("entailments", [])
        if not entailments:
            return 0.0
        n_no = sum(1 for v in entailments if v == "no")
        n_partial = sum(1 for v in entailments if v == "partial")
        return (n_no + 0.5 * n_partial) / len(entailments)


class SummaryRubricScore(Metric):
    """Mean rubric adherence score normalized to [0, 1] (§4.6).

    actual_output keys:
        {"rubric_score": float}  — raw judge score 1-5, or already normalized
    """

    @property
    def name(self) -> str:
        return "summary_rubric_score"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        raw = float(actual_output.get("rubric_score", 0.0))
        if raw > 1.0:
            return raw / 5.0
        return raw
