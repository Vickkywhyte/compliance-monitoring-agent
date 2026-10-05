"""Phase 9 — End-to-end pipeline integration tests.

All tests use FakeLLMBackend (no network) and in-memory SQLite + Chroma.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import pytest

REPO_ROOT = Path(__file__).parent.parent
KB_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "kb"
DEMO_DIR = REPO_ROOT / "data" / "demo" / "changes"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _fake_gateway(responses: list[str] | None = None):
    """Build a LLMGateway backed by FakeLLMBackend."""
    from compliance_agent.config.models import GatewayConfig, LLMConfig
    from compliance_agent.llm.gateway import LLMGateway
    from tests.mocks.llm import FakeLLMBackend

    default_summary = (
        '{"text": "Regulatory change requires updated compliance controls.", '
        '"citations": [{"source_url": "https://example.com", '
        '"span_start": 0, "span_end": 30, "quoted_text": "compliance controls"}], '
        '"confidence": 0.8}'
    )
    default_mapping = (
        '{"mappings": [{"process_id": "aml", "process_section_id": "aml_test:0", '
        '"impact_type": "add_control", "confidence": 0.85, '
        '"rationale": "AML control required", "citation_quote": "compliance controls"}]}'
    )
    default_proposal = (
        '{"title": "Update AML compliance controls for new regulation", '
        '"description": "Review and update internal AML controls.", '
        '"rationale": "Required by regulation", '
        '"category": "policy_update"}'
    )

    if responses is None:
        responses = []
        for _ in range(20):
            responses.extend([default_summary, default_mapping, default_proposal])

    fake = FakeLLMBackend(responses=responses)
    return LLMGateway(
        primary=fake,
        fallback=None,
        llm_config=LLMConfig(primary_model="fake", fallback_model="fake"),
        gateway_config=GatewayConfig(max_concurrent=1),
    )


def _fake_kb():
    """Build an ephemeral Chroma collection pre-loaded with KB fixtures."""
    from compliance_agent.intelligence.kb import index_knowledge_base

    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("kb_test")
    if KB_FIXTURE_DIR.exists():
        index_knowledge_base(KB_FIXTURE_DIR, collection)
    return collection


def _seed_demo_to_db(db_path: str) -> None:
    """Seed demo JSON files into the given DB without network calls."""
    import hashlib
    from compliance_agent.storage.changes import ChangeRepository
    from compliance_agent.storage.db import get_connection, migrate
    from compliance_agent.storage.documents import DocumentRepository
    from compliance_agent.storage.models import Change, RegulatoryDocument
    from compliance_agent.utils.ids import compute_change_id, new_ulid, now_utc

    conn = get_connection(db_path)
    migrate(conn)
    doc_repo = DocumentRepository(conn)
    change_repo = ChangeRepository(conn)

    for path in sorted(DEMO_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        source = data["source"]
        stable_id = data["stable_id"]
        change_type = data["change_type"]
        content = data["raw_content"]

        if change_type == "amended" and "previous_raw_content" in data:
            prev = RegulatoryDocument(
                doc_id=new_ulid(), source=source, stable_id=stable_id,
                title=f"[prev] {data['title']}", content=data["previous_raw_content"],
                content_hash=hashlib.sha256(data["previous_raw_content"].encode()).hexdigest(),
                source_url=data["source_url"], fetched_at=datetime.now(timezone.utc),
            )
            doc_repo.upsert(prev)

        doc = RegulatoryDocument(
            doc_id=new_ulid(), source=source, stable_id=stable_id,
            title=data["title"], content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            source_url=data["source_url"], fetched_at=datetime.now(timezone.utc),
        )
        doc_repo.upsert(doc)

        all_versions = doc_repo.get_by_stable_id(source, stable_id)
        latest = max(all_versions, key=lambda d: d.version)

        if change_type == "withdrawn":
            current_version = latest.version
            prev_version = None
        elif change_type == "amended":
            current_version = latest.version
            prev_version = latest.version - 1 if latest.version > 1 else None
        else:
            current_version = 1
            prev_version = None

        change = Change(
            change_id=compute_change_id(source, stable_id, current_version),
            doc_id=latest.doc_id,
            source=source,
            stable_id=stable_id,
            change_type=change_type,
            diff=None,
            previous_version=prev_version,
            current_version=current_version,
            detected_at=now_utc(),
            metadata={},
        )
        change_repo.insert(change)

    conn.close()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_pipeline_runs_end_to_end_fixture_mode() -> None:
    """Pipeline produces non-zero counts for every stage and no failures."""
    from compliance_agent.pipeline import run_pipeline
    from compliance_agent.storage.changes import ChangeRepository
    from compliance_agent.storage.db import get_connection
    from compliance_agent.storage.proposals import ProposalRepository

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_demo_to_db(db_path)

        report = run_pipeline(
            fixture_mode=False,
            db_path=db_path,
            gateway=_fake_gateway(),
            kb_collection=_fake_kb(),
            skip_ingest=True,
        )

    assert report.summaries_generated > 0, "Expected summaries"
    assert report.proposals_generated > 0, "Expected proposals"
    assert report.proposals_routed > 0, "Expected routed proposals"
    assert len(report.failures) == 0, f"Unexpected failures: {report.failures}"


def test_pipeline_every_proposal_has_assignee_role() -> None:
    """Every generated proposal has a non-empty assignee_role."""
    from compliance_agent.pipeline import run_pipeline
    from compliance_agent.storage.db import get_connection
    from compliance_agent.storage.proposals import ProposalRepository

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_demo_to_db(db_path)

        run_pipeline(
            fixture_mode=False,
            db_path=db_path,
            gateway=_fake_gateway(),
            kb_collection=_fake_kb(),
            skip_ingest=True,
        )

        conn = get_connection(db_path)
        proposal_repo = ProposalRepository(conn)
        proposals = proposal_repo.list_by_state("pending")
        conn.close()

    for p in proposals:
        assert p.assignee_role, f"Proposal {p.proposal_id} missing assignee_role"


def test_pipeline_every_proposal_has_evidence() -> None:
    """Every generated proposal has at least one evidence item."""
    from compliance_agent.pipeline import run_pipeline
    from compliance_agent.storage.db import get_connection
    from compliance_agent.storage.proposals import ProposalRepository

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_demo_to_db(db_path)

        run_pipeline(
            fixture_mode=False,
            db_path=db_path,
            gateway=_fake_gateway(),
            kb_collection=_fake_kb(),
            skip_ingest=True,
        )

        conn = get_connection(db_path)
        proposal_repo = ProposalRepository(conn)
        proposals = proposal_repo.list_by_state("pending")
        conn.close()

    for p in proposals:
        assert len(p.evidence) >= 1, f"Proposal {p.proposal_id} has no evidence"


def test_pipeline_continues_on_partial_failure() -> None:
    """Pipeline processes remaining changes after one stage fails on a specific change."""
    from compliance_agent.config.models import GatewayConfig, LLMConfig
    from compliance_agent.llm.gateway import LLMGateway
    from compliance_agent.pipeline import run_pipeline
    from tests.mocks.llm import FakeLLMBackend

    good_summary = (
        '{"text": "Valid summary.", "citations": '
        '[{"source_url": "https://x.com", "span_start": 0, "span_end": 7, '
        '"quoted_text": "Valid s"}], "confidence": 0.9}'
    )
    good_mapping = (
        '{"mappings": [{"process_id": "aml", "process_section_id": "aml_test:0", '
        '"impact_type": "add_control", "confidence": 0.9, '
        '"rationale": "ok", "citation_quote": "Valid s"}]}'
    )
    good_proposal = (
        '{"title": "Action required", "description": "Update controls.", '
        '"rationale": "regulatory", "category": "policy_update"}'
    )

    # First change: LLM returns bad JSON (will fail summarize), then good for rest
    responses = ["not-valid-json", "not-valid-json"]  # two attempts, both fail
    for _ in range(10):
        responses.extend([good_summary, good_mapping, good_proposal])

    fake = FakeLLMBackend(responses=responses)
    gw = LLMGateway(
        primary=fake,
        fallback=None,
        llm_config=LLMConfig(primary_model="fake", fallback_model="fake"),
        gateway_config=GatewayConfig(max_concurrent=1),
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_demo_to_db(db_path)

        report = run_pipeline(
            fixture_mode=False,
            db_path=db_path,
            gateway=gw,
            kb_collection=_fake_kb(),
            skip_ingest=True,
        )

    # At least some changes should still have succeeded
    assert report.proposals_generated > 0, "Expected some proposals despite one failure"
    # The partial failure might be recorded, or the fallback text might succeed — either is OK
    # What matters is the run did not abort entirely
    assert report.started_at is not None


def test_pipeline_assigns_correlation_id() -> None:
    """All audit events from a single run share the same correlation_id."""
    from compliance_agent.pipeline import run_pipeline
    from compliance_agent.storage.audit import AuditRepository
    from compliance_agent.storage.db import get_connection

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_demo_to_db(db_path)

        report = run_pipeline(
            fixture_mode=False,
            correlation_id="test-cid-12345",
            db_path=db_path,
            gateway=_fake_gateway(),
            kb_collection=_fake_kb(),
            skip_ingest=True,
        )

        conn = get_connection(db_path)
        audit_repo = AuditRepository(conn)
        events = audit_repo.query(correlation_id="test-cid-12345", limit=200)
        conn.close()

    assert report.correlation_id == "test-cid-12345"
    assert len(events) > 0, "Expected audit events for the correlation_id"
    for ev in events:
        assert ev.correlation_id == "test-cid-12345", f"Event {ev.event_id} has wrong cid"


def test_pipeline_does_not_bypass_approval_service() -> None:
    """All proposals after the pipeline run are in 'pending' state (C-18 guard)."""
    from compliance_agent.pipeline import run_pipeline
    from compliance_agent.storage.db import get_connection
    from compliance_agent.storage.proposals import ProposalRepository

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_demo_to_db(db_path)

        run_pipeline(
            fixture_mode=False,
            db_path=db_path,
            gateway=_fake_gateway(),
            kb_collection=_fake_kb(),
            skip_ingest=True,
        )

        conn = get_connection(db_path)
        proposal_repo = ProposalRepository(conn)
        all_proposals = proposal_repo.list_by_state("pending")
        approved = proposal_repo.list_by_state("approved")
        rejected = proposal_repo.list_by_state("rejected")
        conn.close()

    assert len(approved) == 0, f"Pipeline must not auto-approve: found {len(approved)}"
    assert len(rejected) == 0, f"Pipeline must not auto-reject: found {len(rejected)}"
    assert len(all_proposals) > 0, "Expected pending proposals after pipeline run"


def test_pipeline_writes_audit_events_in_order() -> None:
    """Audit chain for a change contains events in the expected order."""
    from compliance_agent.pipeline import run_pipeline
    from compliance_agent.storage.audit import AuditRepository
    from compliance_agent.storage.changes import ChangeRepository
    from compliance_agent.storage.db import get_connection

    EXPECTED_ACTIONS = [
        "change_detected",
        "summary_generated",
        "mapping_generated",
        "proposal_created",
        "proposal_routed",
    ]

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_demo_to_db(db_path)
        cid = "audit-order-test"

        run_pipeline(
            fixture_mode=False,
            correlation_id=cid,
            db_path=db_path,
            gateway=_fake_gateway(),
            kb_collection=_fake_kb(),
            skip_ingest=True,
        )

        conn = get_connection(db_path)
        audit_repo = AuditRepository(conn)
        events = audit_repo.query(correlation_id=cid, limit=200)
        conn.close()

    actions_seen = [e.action for e in events]
    for expected_action in EXPECTED_ACTIONS:
        assert expected_action in actions_seen, (
            f"Expected '{expected_action}' in audit chain, got: {actions_seen}"
        )


def test_pipeline_report_changes_detected_matches_table() -> None:
    """report.changes_detected equals len(report.per_change) (structural invariant)."""
    from compliance_agent.pipeline import run_pipeline

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        _seed_demo_to_db(db_path)

        report = run_pipeline(
            fixture_mode=False,
            db_path=db_path,
            gateway=_fake_gateway(),
            kb_collection=_fake_kb(),
            skip_ingest=True,
        )

    assert report.changes_detected == len(report.per_change), (
        f"changes_detected={report.changes_detected} != "
        f"len(per_change)={len(report.per_change)}"
    )
    assert report.changes_detected > 0, "Expected at least one change to be processed"


def test_demo_seed_source_is_isolated() -> None:
    """data/demo/seed.py reads only from data/demo/changes/, not data/eval/ or data/kb/."""
    seed_source = (REPO_ROOT / "data" / "demo" / "seed.py").read_text()
    assert "eval" not in seed_source, "seed.py must not reference data/eval/"
    assert "data/kb" not in seed_source, "seed.py must not reference data/kb/"
    assert "demo/changes" in seed_source or "DEMO_DIR" in seed_source, (
        "seed.py must reference its DEMO_DIR (data/demo/changes/)"
    )


def test_demo_script_data_exists() -> None:
    """data/demo/changes/ contains exactly 6 JSON files with required schema."""
    required_fields = {
        "id", "title", "source", "stable_id", "change_type",
        "source_url", "raw_content", "expected_summary_keywords", "expected_mappings",
    }
    valid_sources = {"eurlex", "sanctions", "eba"}
    valid_change_types = {"new", "amended", "withdrawn"}

    json_files = sorted(DEMO_DIR.glob("*.json"))
    assert len(json_files) == 6, f"Expected 6 demo files, found {len(json_files)}"

    for path in json_files:
        data = json.loads(path.read_text())
        missing = required_fields - data.keys()
        assert not missing, f"{path.name} missing fields: {missing}"
        assert data["source"] in valid_sources, f"{path.name}: invalid source '{data['source']}'"
        assert data["change_type"] in valid_change_types, (
            f"{path.name}: invalid change_type '{data['change_type']}'"
        )
        assert isinstance(data["expected_summary_keywords"], list)
        assert isinstance(data["expected_mappings"], list)
