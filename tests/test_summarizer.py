"""Tests for Summarizer (Phase 4 — Lesson 3: assert observable behavior only).

All tests use FakeLLMBackend and in-memory SQLite. Every assertion checks
a return value or a persisted record — no mock.assert_called.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from compliance_agent.config.models import GatewayConfig, LLMConfig
from compliance_agent.exceptions import LLMError
from compliance_agent.intelligence.summarizer import Summarizer
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.models import Change, RegulatoryDocument
from compliance_agent.storage.summaries import SummaryRepository
from compliance_agent.utils.ids import new_ulid
from tests.mocks.llm import FakeLLMBackend

# ── Helpers ───────────────────────────────────────────────────────────────────

_CONTENT = (
    "Article 1: Credit institutions must maintain AML controls. "
    "Article 2: Compliance deadline is 2025-01-01. "
    "Article 3: Penalties apply for non-compliance."
)

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


def _make_doc(content: str = _CONTENT) -> RegulatoryDocument:
    return RegulatoryDocument(
        doc_id=new_ulid(),
        source="eurlex",
        stable_id="32024R0001",
        title="Test Regulation",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        source_url="https://eur-lex.europa.eu/test",
        fetched_at=datetime.now(timezone.utc),
    )


def _make_change(doc: RegulatoryDocument) -> Change:
    return Change(
        change_id="test_change_0001",
        doc_id=doc.doc_id,
        source=doc.source,
        stable_id=doc.stable_id,
        change_type="new",
        current_version=1,
        detected_at=datetime.now(timezone.utc),
    )


def _make_gateway(fake: FakeLLMBackend) -> LLMGateway:
    return LLMGateway(
        primary=fake,
        fallback=None,
        llm_config=_LLM_CFG,
        gateway_config=_GW_CFG,
    )


def _valid_response(doc: RegulatoryDocument, span_start: int = 0) -> str:
    span_end = min(span_start + 40, len(doc.content))
    return json.dumps({
        "text": "AML controls required for credit institutions with a 2025-01-01 deadline.",
        "citations": [{"span_start": span_start, "span_end": span_end}],
        "confidence": 0.85,
    })


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_summarizer_returns_summary_with_correct_change_id():
    doc = _make_doc()
    change = _make_change(doc)
    fake = FakeLLMBackend(responses=[_valid_response(doc)])
    gw = _make_gateway(fake)
    summarizer = Summarizer(gateway=gw)

    result = summarizer.summarize(change, doc)

    assert result.change_id == change.change_id
    assert result.text == "AML controls required for credit institutions with a 2025-01-01 deadline."
    assert result.low_confidence is False
    assert result.confidence == pytest.approx(0.85)


def test_summarizer_citations_use_document_content_not_llm_output():
    """quoted_text must come from doc.content[span_start:span_end], not from LLM."""
    doc = _make_doc()
    change = _make_change(doc)
    span_start, span_end = 0, 20
    fake_resp = json.dumps({
        "text": "A summary.",
        "citations": [{"span_start": span_start, "span_end": span_end}],
        "confidence": 0.9,
    })
    fake = FakeLLMBackend(responses=[fake_resp])
    gw = _make_gateway(fake)
    summarizer = Summarizer(gateway=gw)

    result = summarizer.summarize(change, doc)

    assert len(result.citations) == 1
    assert result.citations[0].quoted_text == doc.content[span_start:span_end]
    assert result.citations[0].source_url == doc.source_url


def test_summarizer_marks_low_confidence_on_invalid_json():
    doc = _make_doc()
    change = _make_change(doc)
    fake = FakeLLMBackend(responses=["NOT VALID JSON", "STILL NOT JSON"])
    gw = _make_gateway(fake)
    summarizer = Summarizer(gateway=gw)

    result = summarizer.summarize(change, doc)

    assert result.low_confidence is True
    assert result.citations == []


def test_summarizer_result_persists_to_storage():
    doc = _make_doc()
    change = _make_change(doc)
    fake = FakeLLMBackend(responses=[_valid_response(doc)])
    gw = _make_gateway(fake)
    summarizer = Summarizer(gateway=gw)

    summary = summarizer.summarize(change, doc)

    conn = get_connection(":memory:")
    migrate(conn)
    # Insert prerequisite records to satisfy FK constraints
    doc_repo = DocumentRepository(conn)
    change_repo = ChangeRepository(conn)
    doc_repo.upsert(doc)
    change_repo.insert(change)

    repo = SummaryRepository(conn)
    repo.insert(summary)

    retrieved = repo.get_by_id(summary.summary_id)
    assert retrieved is not None
    assert retrieved.summary_id == summary.summary_id
    assert retrieved.text == summary.text
    assert retrieved.prompt_version == "summarize_v1"


def test_summarizer_prompt_contains_fenced_document():
    """The prompt sent to the LLM must contain the document inside fence tags."""
    doc = _make_doc()
    change = _make_change(doc)
    fake = FakeLLMBackend(responses=[_valid_response(doc)])
    gw = _make_gateway(fake)
    summarizer = Summarizer(gateway=gw)

    summarizer.summarize(change, doc)

    assert len(fake.calls) >= 1
    prompt = fake.calls[0]
    assert "<UNTRUSTED_SOURCE_CONTENT>" in prompt
    assert "</UNTRUSTED_SOURCE_CONTENT>" in prompt
    assert doc.content in prompt
