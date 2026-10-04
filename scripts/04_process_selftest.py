"""Phase 4 self-test: summarize and map using FakeLLMBackend.

Assertion 1: A new Change produces one Summary and one ProcessMapping.
Assertion 2: Re-processing the same Change is idempotent (no duplicates).
Assertion 3: Low-confidence output (bad JSON) marks Summary.low_confidence=True.
Assertion 4: Mapping confidence below threshold produces zero ProcessMappings.

All tests use in-memory SQLite and ephemeral Chroma — no real LLM calls,
no network, no disk I/O outside the test's temporary directory.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import chromadb

# Allow importing tests/mocks/ from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from compliance_agent.config.models import GatewayConfig, LLMConfig
from compliance_agent.intelligence.mapper import Mapper
from compliance_agent.intelligence.summarizer import Summarizer
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.mappings import ProcessMappingRepository
from compliance_agent.storage.models import Change, RegulatoryDocument
from compliance_agent.storage.summaries import SummaryRepository
from compliance_agent.utils.ids import new_ulid
from tests.mocks.llm import FakeLLMBackend

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
    backoff_initial_ms=1,
    backoff_max_ms=5,
    fallback_after_consecutive_429=3,
)
_CONTENT = (
    "Article 1: Credit institutions must conduct annual AML risk assessments. "
    "Article 2: Transaction monitoring thresholds must be reviewed quarterly."
)
_CHUNK_ID = "aml_selftest:0"
_CHUNK_TEXT = "AML risk assessment identifies exposure across products and customers."

_SUMMARY_RESP = json.dumps({
    "text": "Credit institutions must perform annual AML risk assessments.",
    "citations": [{"span_start": 0, "span_end": 40}],
    "confidence": 0.88,
})
_MAPPING_RESP = json.dumps({
    "mappings": [
        {
            "process_id": "aml",
            "process_section_id": _CHUNK_ID,
            "impact_type": "modify_control",
            "confidence": 0.75,
            "rationale": "Requires update to AML risk assessment procedure.",
            "citation_quote": "annual AML risk assessments",
        }
    ]
})


def _repos():
    conn = get_connection(":memory:")
    migrate(conn)
    return (
        DocumentRepository(conn),
        ChangeRepository(conn),
        SummaryRepository(conn),
        ProcessMappingRepository(conn),
    )


def _collection():
    import uuid
    client = chromadb.EphemeralClient()
    col = client.get_or_create_collection(f"selftest_kb_{uuid.uuid4().hex[:8]}")
    col.upsert(ids=[_CHUNK_ID], documents=[_CHUNK_TEXT], metadatas=[{"source": "aml.md", "chunk_index": 0}])
    return col


def _make_doc() -> RegulatoryDocument:
    return RegulatoryDocument(
        doc_id=new_ulid(),
        source="eurlex",
        stable_id="32024R0001",
        title="AML Regulation 2024",
        content=_CONTENT,
        content_hash=hashlib.sha256(_CONTENT.encode()).hexdigest(),
        source_url="https://eur-lex.europa.eu/test",
        fetched_at=datetime.now(timezone.utc),
    )


def _make_change(doc: RegulatoryDocument) -> Change:
    return Change(
        change_id=new_ulid(),
        doc_id=doc.doc_id,
        source="eurlex",
        stable_id=doc.stable_id,
        change_type="new",
        current_version=1,
        detected_at=datetime.now(timezone.utc),
    )


def _gw(responses: list[str]) -> LLMGateway:
    return LLMGateway(
        primary=FakeLLMBackend(responses=responses),
        fallback=None,
        llm_config=_LLM_CFG,
        gateway_config=_GW_CFG,
    )


def test_assertion_1_new_change_produces_summary_and_mapping():
    print("Assertion 1: new Change → 1 Summary + 1 ProcessMapping")
    doc_repo, change_repo, summary_repo, mapping_repo = _repos()
    col = _collection()

    doc = _make_doc()
    change = _make_change(doc)
    doc_repo.upsert(doc)
    change_repo.insert(change)

    gw = _gw([_SUMMARY_RESP, _MAPPING_RESP])
    summarizer = Summarizer(gateway=gw)
    mapper = Mapper(gateway=gw, collection=col)

    summary = summarizer.summarize(change, doc)
    summary_repo.insert(summary)
    mappings = mapper.map(change, summary)
    for m in mappings:
        mapping_repo.insert(m)

    assert summary_repo.get_by_change_id(change.change_id) is not None, "No summary stored"
    assert len(mapping_repo.get_by_change_id(change.change_id)) == 1, "No mapping stored"
    print("  PASS")


def test_assertion_2_reprocessing_is_idempotent():
    print("Assertion 2: re-inserting the same Summary is idempotent")
    doc_repo, change_repo, summary_repo, mapping_repo = _repos()
    col = _collection()

    doc = _make_doc()
    change = _make_change(doc)
    doc_repo.upsert(doc)
    change_repo.insert(change)

    gw = _gw([_SUMMARY_RESP, _MAPPING_RESP])
    summarizer = Summarizer(gateway=gw)
    mapper = Mapper(gateway=gw, collection=col)

    summary = summarizer.summarize(change, doc)
    inserted_first = summary_repo.insert(summary)
    for m in mapper.map(change, summary):
        mapping_repo.insert(m)

    # Re-insert the SAME summary: should return False (already exists by summary_id)
    inserted_second = summary_repo.insert(summary)

    assert inserted_first is True, "First insert should return True"
    assert inserted_second is False, "Second insert of same summary should return False"
    all_summaries = summary_repo.list_recent(100)
    assert len([s for s in all_summaries if s.change_id == change.change_id]) == 1
    print("  PASS")


def test_assertion_3_bad_json_produces_low_confidence_summary():
    print("Assertion 3: invalid LLM JSON → Summary.low_confidence=True")
    doc_repo, change_repo, summary_repo, mapping_repo = _repos()

    doc = _make_doc()
    change = _make_change(doc)

    gw = _gw(["NOT JSON", "STILL NOT JSON"])
    summarizer = Summarizer(gateway=gw)
    summary = summarizer.summarize(change, doc)

    assert summary.low_confidence is True, "Expected low_confidence=True"
    assert summary.citations == []
    print("  PASS")


def test_assertion_4_low_confidence_mapping_is_filtered():
    print("Assertion 4: confidence < 0.30 → 0 ProcessMappings returned")
    col = _collection()
    change = _make_change(_make_doc())

    from compliance_agent.storage.models import Summary as SummaryModel
    summary = SummaryModel(
        summary_id=new_ulid(),
        change_id=change.change_id,
        text="Some AML text for retrieval.",
        citations=[],
        prompt_version="summarize_v1",
        model="fake",
        confidence=0.5,
        low_confidence=False,
        generated_at=datetime.now(timezone.utc),
    )
    low_conf_resp = json.dumps({
        "mappings": [
            {
                "process_id": "aml",
                "process_section_id": _CHUNK_ID,
                "impact_type": "add_control",
                "confidence": 0.15,
                "rationale": "Low confidence.",
                "citation_quote": "aml",
            }
        ]
    })
    gw = _gw([low_conf_resp])
    mapper = Mapper(gateway=gw, collection=col)
    mappings = mapper.map(change, summary)

    assert mappings == [], f"Expected 0 mappings, got {len(mappings)}"
    print("  PASS")


if __name__ == "__main__":
    print("=== Phase 4 self-test ===")
    try:
        test_assertion_1_new_change_produces_summary_and_mapping()
        test_assertion_2_reprocessing_is_idempotent()
        test_assertion_3_bad_json_produces_low_confidence_summary()
        test_assertion_4_low_confidence_mapping_is_filtered()
        print("\nPASS — all 4 assertions passed")
        sys.exit(0)
    except AssertionError as e:
        print(f"\nFAIL — {e}")
        sys.exit(1)
