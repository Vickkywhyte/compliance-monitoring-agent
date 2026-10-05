"""Proposal generator: two-layer design per 09_AGENT_DESIGN.md §5.

Rules layer (no LLM, ADR-010):
  - severity  : from change.source, impact_types, effective_date proximity
  - deadline  : regex from doc.content, else effective_date, else config default
  - category  : inferred from dominant impact_type

LLM layer (propose_v1.txt):
  - title (≤ 120 chars)
  - description (≤ 500 chars)
  - rationale
  - category (may refine within controlled vocabulary; rules-layer guess used on parse failure)

The LLM NEVER sets severity, deadline, or assignee_role; those are owned
by the rules engine and the router respectively (ADR-010).
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import structlog

from compliance_agent.exceptions import LLMError, ValidationError
from compliance_agent.intelligence.fencing import fence
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.llm.prompts import PromptRegistry
from compliance_agent.storage.models import (
    Change,
    Evidence,
    ProcessMapping,
    Proposal,
    ProposalCategory,
    RegulatoryDocument,
    Severity,
    Summary,
)
from compliance_agent.utils.ids import new_ulid, now_utc

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Rules-layer: impact_type → default ProposalCategory
_IMPACT_TO_CATEGORY: dict[str, ProposalCategory] = {
    "add_control": "policy_update",
    "modify_control": "procedure_update",
    "add_screening": "screening_update",
    "modify_screening": "screening_update",
    "update_reporting": "reporting_update",
    "no_impact": "no_action",
}

_VALID_CATEGORIES: frozenset[str] = frozenset(_IMPACT_TO_CATEGORY.values()) | frozenset(
    {"training_required", "customer_action"}
)

# Deadline extraction patterns (searched in doc.content[:2000])
_DEADLINE_PATTERNS = [
    re.compile(
        r"(?:by|before|effective)\s+(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE
    ),
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
]
_MONTH_MAP: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


class Proposer:
    """Generate a Proposal from a Change, its ProcessMappings, and a Summary."""

    def __init__(
        self,
        gateway: LLMGateway,
        registry: PromptRegistry | None = None,
        prompt_version: int = 1,
        default_deadline_days: int = 30,
    ) -> None:
        self._gateway = gateway
        self._registry = registry or PromptRegistry(_PROMPTS_DIR)
        self._prompt_version = prompt_version
        self._default_deadline_days = default_deadline_days

    def propose(
        self,
        change: Change,
        mappings: list[ProcessMapping],
        summary: Summary,
        doc: RegulatoryDocument,
    ) -> Proposal:
        """Generate one Proposal. Raises ValidationError if mappings is empty."""
        if not mappings:
            raise ValidationError(
                "Cannot generate proposal: no process mappings provided"
            )

        # ── Rules layer ───────────────────────────────────────────────────────
        severity: Severity = self._compute_severity(change, mappings)
        deadline, deadline_rationale = self._extract_deadline(doc, change)
        category: ProposalCategory = self._infer_category(mappings)

        # ── LLM layer ─────────────────────────────────────────────────────────
        prompt = self._build_prompt(change, mappings, summary, doc)
        version_str = f"propose_v{self._prompt_version}"
        llm_data: dict[str, Any] = {}
        last_resp = None

        for attempt in range(2):
            try:
                resp = self._gateway.complete(prompt)
                last_resp = resp
                parsed = json.loads(resp.text)
                if not all(k in parsed for k in ("title", "description", "rationale")):
                    raise ValueError("Missing required LLM output fields")
                llm_data = parsed
                break
            except (json.JSONDecodeError, ValueError, LLMError) as exc:
                log.warning("proposer_llm_parse_error", attempt=attempt, error=str(exc))
                if attempt == 1:
                    llm_data = {
                        "title": (
                            f"Compliance action required: {change.change_type} "
                            f"to {change.stable_id}"
                        )[:120],
                        "description": summary.text[:500],
                        "rationale": "LLM parse failed; fallback description used.",
                        "category": category,
                    }

        # LLM may refine category but only within the controlled vocabulary
        llm_category = llm_data.get("category", "")
        if llm_category in _VALID_CATEGORIES:
            category = llm_category  # type: ignore[assignment]

        evidence = self._build_evidence(change, mappings, summary)
        model_name = last_resp.model if last_resp else "unknown"

        return Proposal(
            proposal_id=new_ulid(),
            change_id=change.change_id,
            mapping_ids=[m.mapping_id for m in mappings],
            assignee_role="officer",  # provisional; Router.route() will override
            category=category,
            severity=severity,
            title=str(llm_data.get("title", ""))[:120],
            description=str(llm_data.get("description", ""))[:500],
            deadline=deadline,
            deadline_rationale=deadline_rationale,
            evidence=evidence,
            prompt_version=version_str,
            model=model_name,
            generated_at=now_utc(),
            state="pending",
            version=1,
        )

    # ── Rules layer ───────────────────────────────────────────────────────────

    def _compute_severity(
        self, change: Change, mappings: list[ProcessMapping]
    ) -> Severity:
        """Determine severity from rules only — LLM output is never used here."""
        today = date.today()
        eff = change.effective_date
        is_sanctions = change.source == "sanctions"
        has_sanctions_mapping = any(m.process_id == "sanctions_screening" for m in mappings)

        # CRITICAL: sanctions source/mapping with immediate or past effective date
        if is_sanctions or has_sanctions_mapping:
            if eff is None or eff <= today:
                return "critical"

        if eff is not None:
            days_until = (eff - today).days
            if days_until <= 30:
                return "high"
            if days_until <= 90:
                return "medium"

        return "low"

    def _extract_deadline(
        self, doc: RegulatoryDocument, change: Change
    ) -> tuple[date | None, str]:
        """Extract deadline from doc.content via regex or fall back to defaults."""
        for pattern in _DEADLINE_PATTERNS:
            m = pattern.search(doc.content[:2000])
            if m:
                parsed = _parse_date_str(m.group(1))
                if parsed:
                    return parsed, f"Extracted from regulation text: '{m.group(0).strip()}'"

        if change.effective_date:
            return (
                change.effective_date,
                "Using regulation's effective date as deadline",
            )

        deadline = date.today() + timedelta(days=self._default_deadline_days)
        return (
            deadline,
            f"No explicit date in source; {self._default_deadline_days}-day default applied",
        )

    def _infer_category(self, mappings: list[ProcessMapping]) -> ProposalCategory:
        """Select category from the dominant impact_type across all mappings."""
        counts: dict[str, int] = {}
        for m in mappings:
            counts[m.impact_type] = counts.get(m.impact_type, 0) + 1
        dominant = max(counts, key=lambda k: counts[k])
        return _IMPACT_TO_CATEGORY.get(dominant, "procedure_update")

    # ── Evidence builder ──────────────────────────────────────────────────────

    def _build_evidence(
        self,
        change: Change,
        mappings: list[ProcessMapping],
        summary: Summary,
    ) -> list[Evidence]:
        items: list[Evidence] = []
        for citation in summary.citations[:2]:
            items.append(
                Evidence(
                    kind="citation",
                    ref_id=summary.summary_id,
                    excerpt=citation.quoted_text[:200],
                )
            )
        for m in mappings[:3]:
            items.append(
                Evidence(kind="mapping", ref_id=m.mapping_id, excerpt=m.rationale[:200])
            )
        if change.diff:
            items.append(
                Evidence(kind="diff", ref_id=change.change_id, excerpt=change.diff[:200])
            )
        # Guarantee at least one evidence item
        if not items:
            items.append(
                Evidence(
                    kind="regulation_text",
                    ref_id=change.change_id,
                    excerpt=summary.text[:200],
                )
            )
        return items

    # ── Prompt builder ────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        change: Change,
        mappings: list[ProcessMapping],
        summary: Summary,
        doc: RegulatoryDocument,
    ) -> str:
        template = self._registry.load("propose", version=self._prompt_version)
        mapping_text = "\n".join(
            f"- Process: {m.process_id} | Impact: {m.impact_type} | {m.rationale}"
            for m in mappings[:5]
        )
        return (
            template
            .replace("{{CHANGE_SUMMARY}}", fence(summary.text))
            .replace("{{PROCESS_MAPPING}}", fence(mapping_text))
            .replace("{{REGULATION_EXCERPT}}", fence(doc.content[:500]))
        )


def _parse_date_str(date_str: str) -> date | None:
    """Parse a date string in ISO or 'DD Month YYYY' formats."""
    date_str = date_str.strip()
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        pass
    parts = date_str.split()
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = _MONTH_MAP.get(parts[1].lower())
            year = int(parts[2])
            if month:
                return date(year, month, day)
        except (ValueError, KeyError):
            pass
    return None
