"""Coverage metrics — detection recall and precision (06_EVAL_SPEC.md §3)."""
from __future__ import annotations

from typing import Literal

from compliance_agent.evaluation.metrics.base import Metric


class DetectionRecall(Metric):
    """Fraction of golden changes that the detector identified (§3.1).

    Per-entry: 1.0 if detected, 0.0 if missed.
    Batch aggregate: mean == TP / (TP + FN).

    actual_output keys: {"detected": bool}
    golden_entry keys: {"stable_id": str, "change_type": str}
    """

    @property
    def name(self) -> str:
        return "detection_recall"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return 1.0 if actual_output.get("detected", False) else 0.0


class DetectionPrecision(Metric):
    """Fraction of emitted changes that belong to the golden set (§3.2).

    Per-entry compute returns 1.0 for TP, 0.0 for FN.
    compute_batch overrides to use global `fp_count` from actual_outputs[0].

    actual_output keys: {"detected": bool, "fp_count": int}
    """

    @property
    def name(self) -> str:
        return "detection_precision"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return 1.0 if actual_output.get("detected", False) else 0.0

    def compute_batch(
        self,
        golden_entries: list[dict],
        actual_outputs: list[dict],
    ) -> float:
        if not actual_outputs:
            return 0.0
        tp = sum(1 for a in actual_outputs if a.get("detected", False))
        fp = actual_outputs[0].get("fp_count", 0)
        denom = tp + fp
        return tp / denom if denom > 0 else 0.0
