"""Tests for Mapper (Phase 4 — Lesson 3: assert observable behavior only).

All tests use FakeLLMBackend and an ephemeral Chroma collection. Every
assertion checks a return value or a persisted ProcessMapping record.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import chromadb
import pytest

from compliance_agent.config.models import GatewayConfig, LLMConfig
from compliance_agent.intelligence.mapper import Mapper
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.mappings import ProcessMappingRepository
from compliance_agent.storage.models import Change, Citation, RegulatoryDocument, Summary
from compliance_agent.utils.ids import new_ulid
from tests.mocks.llm import FakeLLMBackend

# ── Helpers ───────────────────────────────────────────────────────────────────

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

_CHUNK_ID = "aml_test:0"
_CHUNK_TEXT = "AML risk assessment identifies exposure across products and customers."


def _make_collection() -> tuple:
    """Return (chroma_client, collection) pre-loaded with one known chunk.

    Uses a unique collection name per call so parallel tests don't collide.
    """
    import uuid

    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(f"test_kb_{uuid.uuid4().hex[:8]}")
    collection.upsert(
        ids=[_CHUNK_ID],
        documents=[_CHUNK_TEXT],
        metadatas=[{"source": "aml_test.md", "chunk_index": 0}],
    )
    return client, collection


def _make_summary(change_id: str) -> Summary:
    return Summary(
        summary_id=new_ulid(),
        change_id=change_id,
        text="New AML requirements for credit institutions increase risk assessment obligations.",
        citations=[],
        prompt_version="summarize_v1",
        model="fake",
        confidence=0.85,
        low_confidence=False,
        generated_at=datetime.now(timezone.utc),
    )


def _make_change() -> Change:
    return Change(
        change_id=new_ulid(),
        doc_id=new_ulid(),
        source="eurlex",
        stable_id="32024R0001",
        change_type="new",
        current_version=1,
        detected_at=datetime.now(timezone.utc),
    )


def _valid_mapping_response(section_id: str = _CHUNK_ID) -> str:
    return json.dumps({
        "mappings": [
            {
                "process_id": "aml",
                "process_section_id": section_id,
                "impact_type": "modify_control",
                "confidence": 0.78,
                "rationale": "New AML requirements modify risk assessment controls.",
                "citation_quote": "risk assessment obligations",
            }
        ]
    })


def _make_gateway(fake: FakeLLMBackend):
    from compliance_agent.llm.gateway import LLMGateway
    return LLMGateway(
        primary=fake,
        fallback=None,
        llm_config=_LLM_CFG,
        gateway_config=_GW_CFG,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_mapper_returns_process_mappings():
    _, collection = _make_collection()
    change = _make_change()
    summary = _make_summary(change.change_id)
    fake = FakeLLMBackend(responses=[_valid_mapping_response()])
    gw = _make_gateway(fake)
    mapper = Mapper(gateway=gw, collection=collection)

    results = mapper.map(change, summary)

    assert len(results) == 1
    assert results[0].change_id == change.change_id
    assert results[0].process_id == "aml"
    assert results[0].process_section_id == _CHUNK_ID
    assert results[0].impact_type == "modify_control"
    assert results[0].confidence == pytest.approx(0.78)


def test_mapper_drops_mappings_below_min_confidence():
    _, collection = _make_collection()
    change = _make_change()
    summary = _make_summary(change.change_id)
    low_conf_resp = json.dumps({
        "mappings": [
            {
                "process_id": "aml",
                "process_section_id": _CHUNK_ID,
                "impact_type": "no_impact",
                "confidence": 0.10,
                "rationale": "Low confidence.",
                "citation_quote": "aml",
            }
        ]
    })
    fake = FakeLLMBackend(responses=[low_conf_resp])
    gw = _make_gateway(fake)
    mapper = Mapper(gateway=gw, collection=collection)

    results = mapper.map(change, summary)

    assert results == []


def test_mapper_drops_mappings_with_invalid_impact_type():
    _, collection = _make_collection()
    change = _make_change()
    summary = _make_summary(change.change_id)
    bad_impact_resp = json.dumps({
        "mappings": [
            {
                "process_id": "aml",
                "process_section_id": _CHUNK_ID,
                "impact_type": "INVALID_TYPE",
                "confidence": 0.90,
                "rationale": "Bad impact type.",
                "citation_quote": "aml",
            }
        ]
    })
    fake = FakeLLMBackend(responses=[bad_impact_resp])
    gw = _make_gateway(fake)
    mapper = Mapper(gateway=gw, collection=collection)

    results = mapper.map(change, summary)

    assert results == []


def test_mapper_drops_mappings_with_unknown_section_id():
    _, collection = _make_collection()
    change = _make_change()
    summary = _make_summary(change.change_id)
    unknown_id_resp = json.dumps({
        "mappings": [
            {
                "process_id": "aml",
                "process_section_id": "nonexistent_chunk:99",
                "impact_type": "add_control",
                "confidence": 0.80,
                "rationale": "Unknown section.",
                "citation_quote": "aml",
            }
        ]
    })
    fake = FakeLLMBackend(responses=[unknown_id_resp])
    gw = _make_gateway(fake)
    mapper = Mapper(gateway=gw, collection=collection)

    results = mapper.map(change, summary)

    assert results == []


def test_mapper_result_persists_to_storage():
    _, collection = _make_collection()
    change = _make_change()
    summary = _make_summary(change.change_id)
    fake = FakeLLMBackend(responses=[_valid_mapping_response()])
    gw = _make_gateway(fake)
    mapper = Mapper(gateway=gw, collection=collection)

    mappings = mapper.map(change, summary)
    assert len(mappings) == 1

    conn = get_connection(":memory:")
    migrate(conn)
    # Insert prerequisite doc + change to satisfy FK constraints
    doc_repo = DocumentRepository(conn)
    change_repo = ChangeRepository(conn)
    import hashlib
    from datetime import datetime, timezone
    dummy_content = "dummy"
    dummy_doc = RegulatoryDocument(
        doc_id=change.doc_id,
        source=change.source,
        stable_id=change.stable_id,
        title="Dummy",
        content=dummy_content,
        content_hash=hashlib.sha256(dummy_content.encode()).hexdigest(),
        source_url="https://example.com",
        fetched_at=datetime.now(timezone.utc),
    )
    doc_repo.upsert(dummy_doc)
    change_repo.insert(change)

    repo = ProcessMappingRepository(conn)
    repo.insert(mappings[0])

    retrieved = repo.get_by_change_id(change.change_id)
    assert len(retrieved) == 1
    assert retrieved[0].mapping_id == mappings[0].mapping_id
    assert retrieved[0].prompt_version == "map_v1"
