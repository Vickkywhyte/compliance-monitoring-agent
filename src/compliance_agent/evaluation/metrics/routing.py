"""Routing metrics — accuracy, deadline, severity (06_EVAL_SPEC.md §5.4-§5.6)."""
from __future__ import annotations

from datetime import date

from compliance_agent.evaluation.metrics.base import Metric

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class RoutingAccuracy(Metric):
    """Fraction of proposals routed to the correct assignee_role (§5.4).

    golden_entry keys: {"expected_proposals": [{"assignee_role": str}]}
    actual_output keys: {"proposals": [{"assignee_role": str}]}
    """

    @property
    def name(self) -> str:
        return "routing_accuracy"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        expected_list = golden_entry.get("expected_proposals", [])
        actual_list = actual_output.get("proposals", [])
        if not expected_list or not actual_list:
            return 0.0
        expected_role = expected_list[0].get("assignee_role", "")
        actual_role = actual_list[0].get("assignee_role", "")
        return 1.0 if expected_role == actual_role else 0.0


class DeadlineAccuracy(Metric):
    """Fraction of proposals whose deadline is within ±1 day of golden (§5.5).

    golden_entry keys: {"expected_deadline": str | None}  — ISO date
    actual_output keys: {"proposals": [{"deadline": str | None}]}
    """

    @property
    def name(self) -> str:
        return "deadline_accuracy"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        golden_dl = golden_entry.get("expected_deadline")
        if not golden_dl:
            return 1.0  # no golden deadline → cannot be wrong
        actual_list = actual_output.get("proposals", [])
        if not actual_list:
            return 0.0
        actual_dl = actual_list[0].get("deadline")
        if not actual_dl:
            return 0.0
        try:
            gd = date.fromisoformat(golden_dl)
            ad = date.fromisoformat(str(actual_dl))
            return 1.0 if abs((ad - gd).days) <= 1 else 0.0
        except (ValueError, TypeError):
            return 0.0

    def compute_batch(
        self,
        golden_entries: list[dict],
        actual_outputs: list[dict],
    ) -> float:
        entries_with_golden = [
            (g, a)
            for g, a in zip(golden_entries, actual_outputs)
            if g.get("expected_deadline")
        ]
        if not entries_with_golden:
            return 1.0
        scores = [self.compute(g, a) for g, a in entries_with_golden]
        return sum(scores) / len(scores)


class SeverityAccuracy(Metric):
    """Fraction of proposals with correct severity (§5.6).

    golden_entry keys: {"expected_severity": str}
    actual_output keys: {"proposals": [{"severity": str}]}
    """

    @property
    def name(self) -> str:
        return "severity_accuracy"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        expected = golden_entry.get("expected_severity", "")
        actual_list = actual_output.get("proposals", [])
        if not actual_list:
            return 0.0
        actual_sev = actual_list[0].get("severity", "")
        return 1.0 if expected == actual_sev else 0.0
