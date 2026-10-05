"""Mapping metrics — precision, recall, Brier score (06_EVAL_SPEC.md §4.3-§4.5)."""
from __future__ import annotations

from typing import Literal

from compliance_agent.evaluation.metrics.base import Metric


def _matched_count(golden_mappings: list[dict], actual_mappings: list[dict]) -> int:
    """Count how many actual mappings match golden entries (both process_id AND impact_type)."""
    golden_set = {(m["process_id"], m["impact_type"]) for m in golden_mappings}
    return sum(
        1 for m in actual_mappings
        if (m.get("process_id"), m.get("impact_type")) in golden_set
    )


class MappingPrecision(Metric):
    """Fraction of emitted mappings that match a golden mapping (§4.3).

    actual_output keys: {"mappings": list[{"process_id", "impact_type", "confidence"}]}
    golden_entry keys: {"expected_mappings": list[{"process_id", "impact_type"}]}
    """

    @property
    def name(self) -> str:
        return "mapping_precision"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        actual = actual_output.get("mappings", [])
        if not actual:
            return 0.0
        matched = _matched_count(golden_entry.get("expected_mappings", []), actual)
        return matched / len(actual)


class MappingRecall(Metric):
    """Fraction of golden mappings that were emitted (§4.4).

    actual_output keys: {"mappings": list[{"process_id", "impact_type"}]}
    golden_entry keys: {"expected_mappings": list[{"process_id", "impact_type"}]}
    """

    @property
    def name(self) -> str:
        return "mapping_recall"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        expected = golden_entry.get("expected_mappings", [])
        if not expected:
            return 1.0  # nothing expected → nothing to miss
        actual = actual_output.get("mappings", [])
        matched = _matched_count(expected, actual)
        return matched / len(expected)


class ConfidenceBrier(Metric):
    """Mean squared error between confidence and correctness (§4.5).

    Lower is better. Target ≤ 0.15.

    actual_output keys: {"mappings": list[{"process_id", "impact_type", "confidence"}]}
    golden_entry keys: {"expected_mappings": list[{"process_id", "impact_type"}]}
    """

    @property
    def name(self) -> str:
        return "confidence_brier"

    @property
    def direction(self) -> Literal["higher_better", "lower_better"]:
        return "lower_better"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        actual = actual_output.get("mappings", [])
        if not actual:
            return 0.0
        golden_set = {
            (m["process_id"], m["impact_type"])
            for m in golden_entry.get("expected_mappings", [])
        }
        errors = []
        for m in actual:
            correctness = 1.0 if (m.get("process_id"), m.get("impact_type")) in golden_set else 0.0
            conf = float(m.get("confidence", 0.5))
            errors.append((conf - correctness) ** 2)
        return sum(errors) / len(errors) if errors else 0.0
