"""Metric ABC — base class for all evaluation metrics (06_EVAL_SPEC.md §3-§6)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal


class Metric(ABC):
    """Abstract base for all evaluation metrics.

    Subclasses implement per-entry `compute()`. Aggregation defaults to mean;
    override `compute_batch()` for metrics that require the full dataset context
    (e.g., detection precision, which needs a global false-positive count).
    """

    @abstractmethod
    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        """Return a single metric score for one golden entry vs. its actual output."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique snake_case metric name matching the eval report schema."""

    @property
    def direction(self) -> Literal["higher_better", "lower_better"]:
        """Whether higher or lower values indicate better performance."""
        return "higher_better"

    def compute_batch(
        self,
        golden_entries: list[dict],
        actual_outputs: list[dict],
    ) -> float:
        """Aggregate per-entry scores; default is the mean.

        Override for metrics that cannot be decomposed per-entry (e.g., precision
        when false-positive count is a global quantity).
        """
        if not golden_entries:
            return 0.0
        scores = [
            self.compute(g, a)
            for g, a in zip(golden_entries, actual_outputs)
        ]
        return sum(scores) / len(scores)
