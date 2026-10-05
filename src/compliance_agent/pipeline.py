"""End-to-end pipeline orchestrator (Phase 9).

Wires ingest → detect → summarize → map → propose → route into a single
callable that returns a PipelineReport.

Every stage logs with the same correlation_id.  Per-change failures are
caught, logged, and added to the failures list; the run continues (fail-soft
per ADR-015).  The pipeline NEVER calls ApprovalService — all proposals are
left in "pending" state for human review (C-18).
"""
from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
import structlog

from compliance_agent.audit.recorder import AuditRecorder
from compliance_agent.config.loader import get_settings, load_agent_config, load_sources_config
from compliance_agent.detection.detector import detect
from compliance_agent.ingestion.fetch import Fetcher
from compliance_agent.ingestion.orchestrator import ingest_all
from compliance_agent.intelligence.kb import index_knowledge_base
from compliance_agent.intelligence.mapper import Mapper
from compliance_agent.intelligence.proposer import Proposer
from compliance_agent.intelligence.summarizer import Summarizer
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.llm.ollama import OllamaBackend
from compliance_agent.llm.openrouter import OpenRouterBackend
from compliance_agent.routing.router import Router
from compliance_agent.sources.registry import build_sources
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.mappings import ProcessMappingRepository
from compliance_agent.storage.models import Change, RegulatoryDocument
from compliance_agent.storage.proposals import ProposalRepository
from compliance_agent.storage.summaries import SummaryRepository
from compliance_agent.utils.ids import new_ulid, now_utc
from compliance_agent.utils.logging import configure_logging

_log = structlog.get_logger(__name__)

_KB_DIR = Path("data/kb/processes")
_CHROMA_PATH = Path("data/chroma")

# ── Report models ────────────────────────────────────────────────────────────


@dataclass
class StageFailure:
    """One per-change stage failure recorded during a pipeline run."""

    stage: str
    entity_id: str
    error: str


@dataclass
class PipelineReport:
    """Aggregate outcome of a full pipeline run."""

    correlation_id: str
    started_at: datetime
    ended_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    documents_ingested: int = 0
    changes_detected: int = 0
    summaries_generated: int = 0
    mappings_generated: int = 0
    proposals_generated: int = 0
    proposals_routed: int = 0
    per_change: list[str] = field(default_factory=list)
    failures: list[StageFailure] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True when every stage produced at least some output and no failures."""
        return len(self.failures) == 0


# ── Public API ───────────────────────────────────────────────────────────────


def run_pipeline(
    *,
    fixture_mode: bool = False,
    max_changes: int | None = None,
    correlation_id: str | None = None,
    db_path: str | None = None,
    gateway: LLMGateway | None = None,
    kb_collection=None,
    skip_ingest: bool = False,
) -> PipelineReport:
    """Run the full compliance pipeline and return a PipelineReport.

    Args:
        fixture_mode:    Use local fixture files instead of live network fetches.
        max_changes:     Process at most this many changes (None = all).
        correlation_id:  Caller-supplied run ID; a new ULID is generated if None.
        db_path:         SQLite path override (default from settings).
        gateway:         Pre-built LLMGateway (injected in tests; built from config otherwise).
        kb_collection:   Pre-built Chroma collection (injected in tests).
        skip_ingest:     If True, skip the ingest stage (use existing DB documents).
    """
    configure_logging()
    cid = correlation_id or new_ulid()
    report = PipelineReport(correlation_id=cid, started_at=now_utc())

    log = _log.bind(correlation_id=cid)
    log.info("pipeline_started", fixture_mode=fixture_mode, max_changes=max_changes)

    settings = get_settings()
    resolved_db = db_path or settings.database_path
    conn = get_connection(resolved_db)

    try:
        migrate(conn)
        _run(
            conn=conn,
            report=report,
            correlation_id=cid,
            fixture_mode=fixture_mode,
            max_changes=max_changes,
            gateway=gateway,
            kb_collection=kb_collection,
            skip_ingest=skip_ingest,
        )
    finally:
        conn.close()

    report.ended_at = now_utc()
    elapsed = (report.ended_at - report.started_at).total_seconds()
    log.info(
        "pipeline_complete",
        documents_ingested=report.documents_ingested,
        changes_detected=report.changes_detected,
        summaries_generated=report.summaries_generated,
        mappings_generated=report.mappings_generated,
        proposals_generated=report.proposals_generated,
        proposals_routed=report.proposals_routed,
        failures=len(report.failures),
        elapsed_s=round(elapsed, 2),
    )
    return report


# ── Internal ─────────────────────────────────────────────────────────────────


def _run(
    conn: sqlite3.Connection,
    report: PipelineReport,
    correlation_id: str,
    *,
    fixture_mode: bool,
    max_changes: int | None,
    gateway: LLMGateway | None,
    kb_collection,
    skip_ingest: bool,
) -> None:
    """Execute all pipeline stages against the open connection."""
    log = _log.bind(correlation_id=correlation_id)
    auditor = AuditRecorder(conn)

    doc_repo = DocumentRepository(conn)
    change_repo = ChangeRepository(conn)
    summary_repo = SummaryRepository(conn)
    mapping_repo = ProcessMappingRepository(conn)
    proposal_repo = ProposalRepository(conn)
    router = Router()

    # ── 1. Ingest ────────────────────────────────────────────────────────────
    if not skip_ingest:
        log.info("stage_start", stage="ingest")
        sources_cfg = load_sources_config()
        fixture_dir = Path("tests/fixtures/raw") if fixture_mode else None
        fetcher = Fetcher(fixture_dir=fixture_dir)
        sources = build_sources(sources_cfg.sources, fetcher)
        ingest_report = asyncio.run(ingest_all(sources, doc_repo))
        report.documents_ingested = ingest_report.total_new + ingest_report.total_updated
        log.info(
            "stage_complete",
            stage="ingest",
            ingested=report.documents_ingested,
            unchanged=ingest_report.total_unchanged,
        )

    # ── 2. Detect ────────────────────────────────────────────────────────────
    log.info("stage_start", stage="detect")
    for source_name in _source_names(conn):
        docs = doc_repo.list_latest_by_source(source_name)
        detect(docs, doc_repo, change_repo, source_name)

    all_changes = change_repo.list_recent(limit=max_changes or 10_000)
    if max_changes is not None:
        all_changes = all_changes[:max_changes]
    report.changes_detected = len(all_changes)
    log.info("stage_complete", stage="detect", changes=report.changes_detected)

    # ── Build LLM gateway and KB collection if not injected ──────────────────
    if gateway is None:
        cfg = load_agent_config()
        primary = OpenRouterBackend()
        fallback = OllamaBackend()
        gateway = LLMGateway(
            primary=primary,
            fallback=fallback,
            llm_config=cfg.llm,
            gateway_config=cfg.gateway,
        )

    if kb_collection is None:
        chroma_client = chromadb.PersistentClient(path=str(_CHROMA_PATH))
        kb_collection = chroma_client.get_or_create_collection("knowledge_base")
        if _KB_DIR.exists():
            indexed = index_knowledge_base(_KB_DIR, kb_collection)
            log.info("kb_ready", chunks=indexed)

    summarizer = Summarizer(gateway=gateway)
    mapper = Mapper(gateway=gateway, collection=kb_collection)
    cfg2 = load_agent_config()
    proposer = Proposer(
        gateway=gateway,
        default_deadline_days=cfg2.proposer.default_deadline_days,
    )

    # ── 3–6. Per-change: summarize → map → propose → route ───────────────────
    for change in all_changes:
        _process_change(
            change=change,
            conn=conn,
            doc_repo=doc_repo,
            summary_repo=summary_repo,
            mapping_repo=mapping_repo,
            proposal_repo=proposal_repo,
            summarizer=summarizer,
            mapper=mapper,
            proposer=proposer,
            router=router,
            auditor=auditor,
            report=report,
            correlation_id=correlation_id,
        )


def _process_change(
    *,
    change: Change,
    conn: sqlite3.Connection,
    doc_repo: DocumentRepository,
    summary_repo: SummaryRepository,
    mapping_repo: ProcessMappingRepository,
    proposal_repo: ProposalRepository,
    summarizer: Summarizer,
    mapper: Mapper,
    proposer: Proposer,
    router: Router,
    auditor: AuditRecorder,
    report: PipelineReport,
    correlation_id: str,
) -> None:
    """Process one change through summarize → map → propose → route.

    Failures are logged and appended to report.failures; processing continues.
    """
    log = _log.bind(correlation_id=correlation_id, change_id=change.change_id)
    report.per_change.append(change.change_id)

    # Audit: change detected
    try:
        auditor.record_change_detected(
            change_id=change.change_id,
            source=change.source,
            change_type=change.change_type,
            correlation_id=correlation_id,
        )
    except Exception as exc:
        log.warning("audit_change_detected_failed", error=str(exc))

    doc = doc_repo.get_by_id(change.doc_id)
    if doc is None:
        log.warning("pipeline_doc_missing", doc_id=change.doc_id)
        report.failures.append(StageFailure("ingest", change.change_id, "doc_missing"))
        return

    # ── Summarize ────────────────────────────────────────────────────────────
    existing_summary = summary_repo.get_by_change_id(change.change_id)
    if existing_summary is not None:
        summary = existing_summary
        log.debug("summary_skipped_existing", summary_id=summary.summary_id)
    else:
        try:
            summary = summarizer.summarize(change, doc)
            summary_repo.insert(summary)
            report.summaries_generated += 1
            log.info("summary_generated", summary_id=summary.summary_id)
            _audit_generic(auditor, "summary_generated", "summary", summary.summary_id, correlation_id)
        except Exception as exc:
            log.error("summarize_failed", error=str(exc))
            report.failures.append(StageFailure("summarize", change.change_id, str(exc)))
            return

    # ── Map ──────────────────────────────────────────────────────────────────
    try:
        mappings = mapper.map(change, summary)
        for m in mappings:
            mapping_repo.insert(m)
        report.mappings_generated += len(mappings)
        log.info("mappings_generated", count=len(mappings))
        if mappings:
            _audit_generic(auditor, "mapping_generated", "process_mapping", mappings[0].mapping_id, correlation_id)
    except Exception as exc:
        log.error("map_failed", error=str(exc))
        report.failures.append(StageFailure("map", change.change_id, str(exc)))
        return

    if not mappings:
        log.info("no_mappings_skip_propose", change_id=change.change_id)
        return

    # ── Propose ──────────────────────────────────────────────────────────────
    try:
        proposal = proposer.propose(change, mappings, summary, doc)
        # Route before persisting so the stored proposal already has the correct role
        proposal = router.route(proposal)
        proposal_repo.insert(proposal)
        report.proposals_generated += 1
        report.proposals_routed += 1
        log.info(
            "proposal_created_and_routed",
            proposal_id=proposal.proposal_id,
            severity=proposal.severity,
            assignee=proposal.assignee_role,
        )
        try:
            auditor.record_proposal_created(
                proposal_id=proposal.proposal_id,
                change_id=change.change_id,
                correlation_id=correlation_id,
            )
            _audit_generic(auditor, "proposal_routed", "proposal", proposal.proposal_id, correlation_id,
                           payload={"assignee_role": proposal.assignee_role})
        except Exception as exc:
            log.warning("audit_proposal_failed", error=str(exc))
    except Exception as exc:
        log.error("propose_failed", error=str(exc))
        report.failures.append(StageFailure("propose", change.change_id, str(exc)))


def _audit_generic(
    auditor: AuditRecorder,
    action: str,
    entity_type: str,
    entity_id: str,
    correlation_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Record a generic audit event via the lower-level _record helper."""
    from compliance_agent.storage.models import AuditEvent

    event = AuditEvent(
        event_id=new_ulid(),
        occurred_at=now_utc(),
        actor="system",
        action=action,
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity_id,
        correlation_id=correlation_id,
        payload=payload or {},
    )
    auditor.record(event)


def _source_names(conn: sqlite3.Connection) -> list[str]:
    """Return distinct source names from the documents table."""
    rows = conn.execute(
        "SELECT DISTINCT source FROM regulatory_documents"
    ).fetchall()
    return [row[0] for row in rows]
