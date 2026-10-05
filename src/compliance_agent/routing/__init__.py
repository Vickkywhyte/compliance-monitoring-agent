"""Proposal routing package — rules-based assignment of proposals to roles."""
from __future__ import annotations

from .router import Router
from .rules import RuleEngine

__all__ = ["Router", "RuleEngine"]
