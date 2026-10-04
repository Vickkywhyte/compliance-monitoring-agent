"""Pydantic v2 models for all core entities (05_DATA_SPEC §2–§3).

I/O models use extra="ignore" so extra DB columns are tolerated.
Controlled vocabularies are defined as Literal type aliases.

NOTE: The spec's §2 defines `ApprovalAction = Literal[...]` and §3.6 defines
`class ApprovalAction(BaseModel)`. To avoid the Python name collision,
the Literal is defined here as `ApprovalActionType` and the Pydantic model
class is named `ApprovalActionRecord`; `ApprovalAction` refers to the model
class so the public import is `from storage.models import ApprovalAction`.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Controlled vocabularies (05_DATA_SPEC §2) ─────────────────────────────

SourceType = Literal["eurlex", "sanctions", "eba"]

ChangeType = Literal["new", "amended", "withdrawn"]

Severity = Literal["critical", "high", "medium", "low"]

ImpactType = Literal[
    "add_control",
    "modify_control",
    "add_screening",
    "modify_screening",
    "update_reporting",
    "no_impact",
]

ProposalCategory = Literal[
    "screening_update",
    "policy_update",
    "procedure_update",
    "reporting_update",
    "training_required",
    "customer_action",
    "no_action",
]

ProposalState = Literal["pending", "approved", "rejected"]

# Named with "Type" suffix to avoid collision with the ApprovalAction model class below
ApprovalActionType = Literal["approve", "edit_approve", "reject"]

Role = Literal["analyst", "officer", "mlro"]

AuditEntityType = Literal[
    "regulatory_document",
    "change",
    "summary",
    "process_mapping",
    "proposal",
    "approval_action",
    "ingestion_run",
    "system",
]

Priority = Literal["p0", "p1", "p2", "p3"]


# ── Core entities (05_DATA_SPEC §3) ──────────────────────────────────────────


class RegulatoryDocument(BaseModel):
    """Fetched and normalised regulatory document (§3.1)."""

    model_config = {"extra": "ignore"}

    doc_id: str
    source: SourceType
    stable_id: str
    title: str
    content: str
    content_hash: str
    source_url: str
    fetched_at: datetime
    effective_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = 1


class Change(BaseModel):
    """Detected regulatory change record (§3.2)."""

    model_config = {"extra": "ignore"}

    change_id: str
    doc_id: str
    source: SourceType
    stable_id: str
    change_type: ChangeType
    diff: str | None = None
    previous_version: int | None = None
    current_version: int
    detected_at: datetime
    effective_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    """Source citation within a regulatory document (§3.3)."""

    model_config = {"extra": "forbid"}

    source_url: str
    span_start: int
    span_end: int
    quoted_text: str


class Summary(BaseModel):
    """LLM-generated summary of a regulatory change (§3.3)."""

    model_config = {"extra": "ignore"}

    summary_id: str
    change_id: str
    text: str
    citations: list[Citation]
    prompt_version: str
    model: str
    confidence: float
    low_confidence: bool
    generated_at: datetime
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class ProcessMapping(BaseModel):
    """Mapping from a regulatory change to an internal business process (§3.4)."""

    model_config = {"extra": "ignore"}

    mapping_id: str
    change_id: str
    process_id: str
    process_section_id: str
    impact_type: ImpactType
    confidence: float
    rationale: str
    citation_quote: str
    prompt_version: str
    model: str
    generated_at: datetime


class Evidence(BaseModel):
    """Evidence item attached to a compliance proposal (§3.5)."""

    model_config = {"extra": "forbid"}

    kind: Literal["citation", "mapping", "diff", "regulation_text"]
    ref_id: str
    excerpt: str


class Proposal(BaseModel):
    """Structured action proposal generated from a regulatory change (§3.5)."""

    model_config = {"extra": "ignore"}

    proposal_id: str
    change_id: str
    mapping_ids: list[str]
    assignee_role: Role
    category: ProposalCategory
    severity: Severity
    title: str
    description: str
    deadline: date | None = None
    deadline_rationale: str = ""
    evidence: list[Evidence]
    prompt_version: str
    model: str
    generated_at: datetime
    state: ProposalState = "pending"
    version: int = 1


class ApprovalAction(BaseModel):
    """Human approval, edit-approval, or rejection of a proposal (§3.6).

    Class is named ApprovalAction; the action field uses ApprovalActionType
    to avoid a Python name collision with this class.
    """

    model_config = {"extra": "ignore"}

    action_id: str
    proposal_id: str
    actor_role: Role
    actor_id: str
    action: ApprovalActionType
    edits: dict[str, Any] | None = None
    reason: str | None = None
    acted_at: datetime


class AuditEvent(BaseModel):
    """Append-only audit event (§3.7). Never updated or deleted."""

    model_config = {"extra": "ignore"}

    event_id: str
    occurred_at: datetime
    actor: str
    action: str
    entity_type: AuditEntityType
    entity_id: str
    correlation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
