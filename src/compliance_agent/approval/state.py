"""Proposal state machine (ADR-009, 05_DATA_SPEC §3.5).

Valid transitions:
  pending  -> approved   (via approve or edit_approve)
  pending  -> rejected   (via reject)
  approved -> (terminal)
  rejected -> (terminal)
"""
from __future__ import annotations

from compliance_agent.exceptions import ApprovalError
from compliance_agent.storage.models import ProposalState

# Mapping from state to the set of reachable states
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"approved", "rejected"}),
    "approved": frozenset(),
    "rejected": frozenset(),
}


def validate_transition(current: ProposalState, target: ProposalState) -> None:
    """Raise ApprovalError if the transition current -> target is not permitted."""
    allowed = VALID_TRANSITIONS.get(current, frozenset())
    if not allowed:
        raise ApprovalError(
            f"Proposal is in terminal state '{current}' and cannot be transitioned"
        )
    if target not in allowed:
        raise ApprovalError(
            f"Invalid transition '{current}' -> '{target}'; allowed targets: {sorted(allowed)}"
        )


def is_terminal(state: ProposalState) -> bool:
    """Return True if state has no valid outgoing transitions."""
    return not VALID_TRANSITIONS.get(state, frozenset())
