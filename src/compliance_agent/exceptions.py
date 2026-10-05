"""Typed exceptions for the compliance agent.

All application-level errors derive from ComplianceAgentError so callers can
distinguish them from unexpected third-party exceptions.
"""
from __future__ import annotations


class ComplianceAgentError(Exception):
    """Base class for all compliance agent exceptions."""


class ConfigError(ComplianceAgentError):
    """Raised when configuration is missing, malformed, or invalid."""


class StorageError(ComplianceAgentError):
    """Raised when a database operation fails unexpectedly."""


class AuditError(StorageError):
    """Raised when an audit operation violates the append-only contract."""


class IngestError(ComplianceAgentError):
    """Raised when a regulatory source cannot be fetched or parsed."""


class ParseError(IngestError):
    """Raised when document parsing fails (XML, HTML, or encoding issues)."""


class SourceParseError(ParseError):
    """Raised when XML or HTML parsing of a specific source document fails."""


class RateLimitError(ComplianceAgentError):
    """Raised when the LLM gateway rejects a call due to quota exhaustion."""


class LLMError(ComplianceAgentError):
    """Raised when an LLM call fails after all retries."""


class ValidationError(ComplianceAgentError):
    """Raised when a Pydantic model or output vocabulary check fails."""


class StableIDError(ComplianceAgentError):
    """Raised when a stable ID cannot be extracted or fails format validation."""


class DiffError(ComplianceAgentError):
    """Raised when diff computation fails (binary content, oversized input)."""


class LLMUnavailableError(LLMError):
    """Raised when no LLM backend is reachable (Ollama offline, all retries exhausted)."""


class ApprovalError(ComplianceAgentError):
    """Raised when an approval action violates the state machine or business rules."""


class ConcurrentModificationError(ApprovalError):
    """Raised when an optimistic lock check fails (another writer modified the proposal)."""


class GoldenValidationError(ComplianceAgentError):
    """Raised when a golden-set entry fails the quality gate."""
