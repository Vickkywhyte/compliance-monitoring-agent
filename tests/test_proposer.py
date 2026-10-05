"""Tests for Proposer (Phase 5 — Lesson 3: assert observable behavior only).

Rules layer is verified by asserting on the returned Proposal's fields —
NOT by checking whether internal methods were called. All tests use FakeLLMBackend.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from compliance_agent.config.models import GatewayConfig, LLMConfig
from compliance_agent.exceptions import ValidationError
from compliance_agent.intelligence.proposer import Proposer
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.storage.models import (
    Change,
    Citation,
    ProcessMapping,
    RegulatoryDocument,
    Summary,
)
from compliance_agent.utils.ids import new_ulid
from tests.mocks.llm import FakeLLMBackend

# ── Shared test fixtures ──────────────────────────────────────────────────────

_LLM_CFG = LLMConfig(
    primary_model="fake",
    fallback_model="fake",
    temperature=0.0,
    max_tokens=512,
    timeout_seconds=30,
)
_GW_CFG = GatewayConfig(
    max_concurrent=4,
    queue_max_size=100,
    backoff_initial_ms=500,
    backoff_max_ms=30000,
    fallback_after_consecutive_429=3,
)

_CONTENT = (
    "Regulation (EU) 2026/001: Credit institutions must update AML controls. "
    "All changes effective by 15 January 2027. Penalties apply for non-compliance."
)


def _make_doc(content: str = _CONTENT) -> RegulatoryDocument:
    return RegulatoryDocument(
        doc_id=new_ulid(),
        source="eurlex",
        stable_id="32026R0001",
        title="Test AML Regulation",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        source_url="https://eur-lex.europa.eu/test",
        fetched_at=datetime.now(timezone.utc),
        effective_date=date(2027, 1, 15),
    )


def _make_change(
    doc: RegulatoryDocument,
    source: str = "eurlex",
    effective_date: date | None = None,
) -> Change:
    return Change(
        change_id="test_change_p5_001",
        doc_id=doc.doc_id,
        source=source,
        stable_id=doc.stable_id,
        change_type="amended",
        current_version=2,
        detected_at=datetime.now(timezone.utc),
        effective_date=effective_date or doc.effective_date,
    )


def _make_mapping(
    change_id: str,
    process_id: str = "aml_monitoring",
    impact_type: str = "add_control",
) -> ProcessMapping:
    return ProcessMapping(
        mapping_id=new_ulid(),
        change_id=change_id,
        process_id=process_id,
        process_section_id="sec_01",
        impact_type=impact_type,
        confidence=0.85,
        rationale="Regulation requires updated AML monitoring controls",
        citation_quote="must update AML controls",
        prompt_version="map_v1",
        model="fake",
        generated_at=datetime.now(timezone.utc),
    )


def _make_summary(change_id: str, doc: RegulatoryDocument) -> Summary:
    return Summary(
        summary_id=new_ulid(),
        change_id=change_id,
        text="Regulation mandates updated AML controls for credit institutions by January 2027.",
        citations=[
            Citation(
                source_url=doc.source_url,
                span_start=0,
                span_end=50,
                quoted_text=doc.content[0:50],
            )
        ],
        prompt_version="summarize_v1",
        model="fake",
        confidence=0.9,
        low_confidence=False,
        generated_at=datetime.now(timezone.utc),
    )


def _valid_llm_response(category: str = "policy_update") -> str:
    return json.dumps({
        "title": "Update AML monitoring controls per Regulation (EU) 2026/001",
        "description": "Review AML monitoring thresholds and update policy documentation to comply with the new regulation by the specified deadline.",
        "rationale": "Regulation (EU) 2026/001 mandates updated AML controls for all credit institutions.",
        "category": category,
    })


def _make_gateway(fake: FakeLLMBackend) -> LLMGateway:
    return LLMGateway(
        primary=fake,
        fallback=None,
        llm_config=_LLM_CFG,
        gateway_config=_GW_CFG,
    )


def _make_proposer(fake: FakeLLMBackend, default_deadline_days: int = 30) -> Proposer:
    return Proposer(
        gateway=_make_gateway(fake),
        default_deadline_days=default_deadline_days,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_proposer_creates_proposal_with_citations():
    """Proposer returns a Proposal with evidence items derived from mappings and citations."""
    doc = _make_doc()
    change = _make_change(doc)
    mapping = _make_mapping(change.change_id)
    summary = _make_summary(change.change_id, doc)
    fake = FakeLLMBackend(responses=[_valid_llm_response()])

    proposer = _make_proposer(fake)
    proposal = proposer.propose(change, [mapping], summary, doc)

    assert proposal.change_id == change.change_id
    assert mapping.mapping_id in proposal.mapping_ids
    assert len(proposal.evidence) >= 1
    assert proposal.state == "pending"
    assert proposal.version == 1
    assert len(proposal.title) <= 120
    assert len(proposal.description) <= 500


def test_proposer_severity_follows_rules_not_llm():
    """Severity comes from rules; LLM response has no severity field and is ignored."""
    doc = _make_doc()
    today = date.today()
    # effective_date within 30 days → HIGH
    near_date = today + timedelta(days=20)
    change = _make_change(doc, effective_date=near_date)
    mapping = _make_mapping(change.change_id)
    summary = _make_summary(change.change_id, doc)
    fake = FakeLLMBackend(responses=[_valid_llm_response()])

    proposer = _make_proposer(fake)
    proposal = proposer.propose(change, [mapping], summary, doc)

    assert proposal.severity == "high"


def test_proposer_deadline_follows_rules_not_llm():
    """Deadline is derived from rules/regex; the LLM response never contains a deadline."""
    doc = _make_doc()
    change = _make_change(doc)
    mapping = _make_mapping(change.change_id)
    summary = _make_summary(change.change_id, doc)
    fake = FakeLLMBackend(responses=[_valid_llm_response()])

    proposer = _make_proposer(fake)
    proposal = proposer.propose(change, [mapping], summary, doc)

    # Deadline must be set (from regex "15 January 2027" in _CONTENT or effective_date)
    assert proposal.deadline is not None
    assert proposal.deadline_rationale != ""


def test_proposer_rejects_empty_mappings():
    """Proposer raises ValidationError when no mappings are provided."""
    doc = _make_doc()
    change = _make_change(doc)
    summary = _make_summary(change.change_id, doc)
    fake = FakeLLMBackend(responses=[_valid_llm_response()])

    proposer = _make_proposer(fake)
    with pytest.raises(ValidationError, match="no process mappings"):
        proposer.propose(change, [], summary, doc)


def test_proposer_extracts_deadline_from_source_text():
    """Deadline is extracted from 'effective by DD Month YYYY' pattern in doc.content."""
    content = (
        "Regulation ABC: All institutions must comply effective by 01 March 2027. "
        "Non-compliance penalties apply."
    )
    doc = _make_doc(content)
    change = _make_change(doc, effective_date=None)
    change = change.model_copy(update={"effective_date": None})
    mapping = _make_mapping(change.change_id)
    summary = _make_summary(change.change_id, doc)
    fake = FakeLLMBackend(responses=[_valid_llm_response()])

    proposer = _make_proposer(fake)
    proposal = proposer.propose(change, [mapping], summary, doc)

    assert proposal.deadline == date(2027, 3, 1)
    assert "01 March 2027" in proposal.deadline_rationale or "Extracted" in proposal.deadline_rationale


def test_proposer_defaults_deadline_when_absent():
    """When no date is found in content and no effective_date, the config default is used."""
    content = "Regulation with no date information."
    doc = RegulatoryDocument(
        doc_id=new_ulid(),
        source="eba",
        stable_id="EBA/GL/2026/01",
        title="No-Date Test",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        source_url="https://eba.europa.eu/test",
        fetched_at=datetime.now(timezone.utc),
        effective_date=None,
    )
    change = Change(
        change_id="test_nodate_001",
        doc_id=doc.doc_id,
        source="eba",
        stable_id=doc.stable_id,
        change_type="new",
        current_version=1,
        detected_at=datetime.now(timezone.utc),
        effective_date=None,
    )
    mapping = _make_mapping(change.change_id)
    summary = _make_summary(change.change_id, doc)
    fake = FakeLLMBackend(responses=[_valid_llm_response()])

    proposer = _make_proposer(fake, default_deadline_days=45)
    proposal = proposer.propose(change, [mapping], summary, doc)

    expected = date.today() + timedelta(days=45)
    assert proposal.deadline == expected
    assert "45" in proposal.deadline_rationale


def test_proposer_sanctions_source_with_past_date_is_critical():
    """A sanctions change with an effective_date in the past must yield CRITICAL severity."""
    doc = _make_doc()
    yesterday = date.today() - timedelta(days=1)
    change = _make_change(doc, source="sanctions", effective_date=yesterday)
    mapping = _make_mapping(change.change_id, process_id="sanctions_screening")
    summary = _make_summary(change.change_id, doc)
    fake = FakeLLMBackend(responses=[_valid_llm_response()])

    proposer = _make_proposer(fake)
    proposal = proposer.propose(change, [mapping], summary, doc)

    assert proposal.severity == "critical"
