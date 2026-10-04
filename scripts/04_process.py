"""Phase 4: Process unhandled changes — summarize and map each one.

Usage:
    python scripts/04_process.py [--limit N]

Connects to the production SQLite database, finds Change records that
have no corresponding Summary, summarizes them with the LLM gateway,
maps them to internal processes via the KB, and stores the results.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import chromadb
import structlog

from compliance_agent.config.loader import load_agent_config
from compliance_agent.intelligence.kb import index_knowledge_base
from compliance_agent.intelligence.mapper import Mapper
from compliance_agent.intelligence.summarizer import Summarizer
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.llm.ollama import OllamaBackend
from compliance_agent.llm.openrouter import OpenRouterBackend
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.mappings import ProcessMappingRepository
from compliance_agent.storage.summaries import SummaryRepository
from compliance_agent.utils.logging import configure_logging

log = structlog.get_logger(__name__)

_KB_DIR = Path("data/kb/processes")
_CHROMA_PATH = Path("data/chroma")


@dataclass
class ProcessReport:
    """Summary of one processing run."""

    total_changes: int = 0
    summarized: int = 0
    mapped: int = 0
    skipped_already_processed: int = 0
    errors: int = 0


def process(limit: int = 100) -> ProcessReport:
    """Process unhandled changes: summarize and map each one."""
    configure_logging()
    cfg = load_agent_config()
    report = ProcessReport()

    conn = get_connection()
    migrate(conn)

    change_repo = ChangeRepository(conn)
    doc_repo = DocumentRepository(conn)
    summary_repo = SummaryRepository(conn)
    mapping_repo = ProcessMappingRepository(conn)

    primary = OpenRouterBackend()
    fallback = OllamaBackend()
    gateway = LLMGateway(
        primary=primary,
        fallback=fallback,
        llm_config=cfg.llm,
        gateway_config=cfg.gateway,
    )
    summarizer = Summarizer(gateway=gateway)

    chroma_client = chromadb.PersistentClient(path=str(_CHROMA_PATH))
    collection = chroma_client.get_or_create_collection("knowledge_base")
    if _KB_DIR.exists():
        indexed = index_knowledge_base(_KB_DIR, collection)
        log.info("kb_ready", chunks=indexed)

    mapper = Mapper(gateway=gateway, collection=collection)

    changes = change_repo.list_recent(limit=limit)
    report.total_changes = len(changes)

    for change in changes:
        existing = summary_repo.get_by_change_id(change.change_id)
        if existing is not None:
            report.skipped_already_processed += 1
            continue

        doc = doc_repo.get_by_id(change.doc_id)
        if doc is None:
            log.warning("process_doc_missing", change_id=change.change_id)
            report.errors += 1
            continue

        try:
            summary = summarizer.summarize(change, doc)
            summary_repo.insert(summary)
            report.summarized += 1
            log.info("summarized", change_id=change.change_id, summary_id=summary.summary_id)
        except Exception as exc:
            log.error("summarize_failed", change_id=change.change_id, error=str(exc))
            report.errors += 1
            continue

        try:
            mappings = mapper.map(change, summary)
            for m in mappings:
                mapping_repo.insert(m)
            report.mapped += len(mappings)
            log.info("mapped", change_id=change.change_id, count=len(mappings))
        except Exception as exc:
            log.error("map_failed", change_id=change.change_id, error=str(exc))
            report.errors += 1

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Process regulatory changes.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    report = process(limit=args.limit)
    print(f"Process report:")
    print(f"  total changes examined : {report.total_changes}")
    print(f"  already processed      : {report.skipped_already_processed}")
    print(f"  summaries created      : {report.summarized}")
    print(f"  mappings created       : {report.mapped}")
    print(f"  errors                 : {report.errors}")

    return 0 if report.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
