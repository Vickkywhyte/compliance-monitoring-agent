"""Rules-based routing engine — no LLM calls (ADR-010, 09_AGENT_DESIGN.md §6).

Loads configs/routing.yaml and evaluates rules by priority ascending.
First matching rule wins. Unmatched proposals fall through to the default rule.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from compliance_agent.exceptions import ConfigError
from compliance_agent.storage.models import Proposal, Role

log = structlog.get_logger(__name__)

_DEFAULT_ROUTING_PATH = Path(__file__).parents[3] / "configs" / "routing.yaml"


class RoutingRule:
    """A single routing rule with a priority, match conditions, and assignment."""

    def __init__(self, priority: int, when: dict[str, str], assign_to: Role) -> None:
        self.priority = priority
        self.when = when
        self.assign_to = assign_to

    def matches(self, proposal: Proposal) -> bool:
        """Return True if all conditions in `when` match the proposal."""
        for field, expected in self.when.items():
            actual = getattr(proposal, field, None)
            if actual != expected:
                return False
        return True


class RuleEngine:
    """Evaluates routing rules against a proposal; returns (role, rule_name)."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        path = Path(config_path) if config_path else _DEFAULT_ROUTING_PATH
        self._rules, self._default_role, self._flag_unmatched = _load_rules(path)

    def evaluate(self, proposal: Proposal) -> tuple[Role, str]:
        """Return (assignee_role, rule_description) for the best-matching rule.

        Rules are evaluated in ascending priority order; first match wins.
        Unmatched proposals fall to the default rule.
        """
        for rule in self._rules:
            if rule.matches(proposal):
                rule_name = f"priority={rule.priority} when={rule.when}"
                log.info(
                    "routing_rule_matched",
                    proposal_id=proposal.proposal_id,
                    priority=rule.priority,
                    assign_to=rule.assign_to,
                    rule=rule_name,
                )
                return rule.assign_to, rule_name

        log.info(
            "routing_rule_unmatched",
            proposal_id=proposal.proposal_id,
            default_role=self._default_role,
            flag_unmatched=self._flag_unmatched,
        )
        return self._default_role, "default"


def _load_rules(path: Path) -> tuple[list[RoutingRule], Role, bool]:
    """Load and parse routing.yaml; return sorted rules, default role, flag."""
    if not path.exists():
        raise ConfigError(f"Routing config not found: {path}")
    try:
        with path.open() as fh:
            data: dict[str, Any] = yaml.safe_load(fh)
    except Exception as exc:
        raise ConfigError(f"Cannot parse routing config {path}: {exc}") from exc

    raw_rules: list[dict[str, Any]] = data.get("rules", [])
    rules: list[RoutingRule] = []
    for r in raw_rules:
        rules.append(
            RoutingRule(
                priority=int(r["priority"]),
                when=dict(r.get("when", {})),
                assign_to=r["assign_to"],
            )
        )
    rules.sort(key=lambda r: r.priority)

    default = data.get("default", {})
    default_role: Role = default.get("assign_to", "officer")
    flag_unmatched: bool = bool(default.get("flag_unmatched", False))

    return rules, default_role, flag_unmatched
