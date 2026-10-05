"""Proposal metrics — acceptance, edit, rejection rates (06_EVAL_SPEC.md §5.1-§5.3)."""
from __future__ import annotations

from compliance_agent.evaluation.metrics.base import Metric


class ProposalAcceptanceRate(Metric):
    """Fraction of proposals approved without edit (§5.1).

    actual_output keys: {"action": str}  — "approve" | "edit_approve" | "reject"
    """

    @property
    def name(self) -> str:
        return "proposal_acceptance_rate"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return 1.0 if actual_output.get("action") == "approve" else 0.0


class ProposalEditRate(Metric):
    """Fraction of proposals approved with edits (§5.2).

    actual_output keys: {"action": str}
    """

    @property
    def name(self) -> str:
        return "proposal_edit_rate"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return 1.0 if actual_output.get("action") == "edit_approve" else 0.0


class ProposalRejectionRate(Metric):
    """Fraction of proposals rejected (§5.3).

    actual_output keys: {"action": str}
    """

    @property
    def name(self) -> str:
        return "proposal_rejection_rate"

    @property
    def direction(self):  # type: ignore[override]
        return "lower_better"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return 1.0 if actual_output.get("action") == "reject" else 0.0
