"""Router — applies routing rules to set assignee_role on a Proposal."""
from __future__ import annotations

from pathlib import Path

import structlog

from compliance_agent.storage.models import Proposal

from .rules import RuleEngine

log = structlog.get_logger(__name__)


class Router:
    """Assign an `assignee_role` to a proposal using the RuleEngine."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        self._engine = RuleEngine(config_path)

    def route(self, proposal: Proposal) -> Proposal:
        """Return a copy of the proposal with `assignee_role` set by routing rules."""
        role, matched_rule = self._engine.evaluate(proposal)
        log.info(
            "proposal_routed",
            proposal_id=proposal.proposal_id,
            severity=proposal.severity,
            category=proposal.category,
            assigned_to=role,
            matched_rule=matched_rule,
        )
        return proposal.model_copy(update={"assignee_role": role})
