"""Proposal approval package — state machine, service, and optimistic locking."""
from __future__ import annotations

from .service import ApprovalService
from .state import validate_transition

__all__ = ["ApprovalService", "validate_transition"]
