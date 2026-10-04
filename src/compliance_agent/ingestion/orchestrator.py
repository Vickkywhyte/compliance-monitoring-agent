"""Ingestion orchestrator — runs all sources in parallel (asyncio, semaphore=3).

Entry point: run_ingest() — synchronous wrapper suitable for scripts.
Internal: ingest_all() — async, called via asyncio.run().

Per-source errors are caught and surfaced in the SourceReport; one source
failing does not abort the others (rule: fail soft in prod, log everything).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from compliance_agent.config.loader import get_settings, load_sources_config
from compliance_agent.ingestion.fetch import Fetcher
from compliance_agent.ingestion.normalize import normalize
from compliance_agent.sources.base import Source
from compliance_agent.sources.registry import build_sources
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.utils.logging import get_logger

_log = get_logger(__name__)

_SEMAPHORE_LIMIT = 3


@dataclass
class SourceReport:
    """Per-source summary from a single ingestion run."""

    source: str
    fetched: int = 0
    parsed: int = 0
    new: int = 0
    unchanged: int = 0
    updated: int = 0
    failed: int = 0
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class IngestReport:
    """Aggregate report for a full ingestion run across all sources."""

    sources: list[SourceReport] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime = field(default_factory=datetime.now)

    @property
    def total_fetched(self) -> int:
        return sum(r.fetched for r in self.sources)

    @property
    def total_new(self) -> int:
        return sum(r.new for r in self.sources)

    @property
    def total_unchanged(self) -> int:
        return sum(r.unchanged for r in self.sources)

    @property
    def total_updated(self) -> int:
        return sum(r.updated for r in self.sources)

    @property
    def total_failed(self) -> int:
        return sum(r.failed for r in self.sources)


async def _run_source(
    source: Source,
    repo: DocumentRepository,
    semaphore: asyncio.Semaphore,
) -> SourceReport:
    """Run one source inside the semaphore and return its SourceReport."""
    report = SourceReport(source=source._config.name)
    t0 = time.monotonic()

    async with semaphore:
        try:
            loop = asyncio.get_running_loop()
            raw_docs = await loop.run_in_executor(None, source.fetch)
            report.fetched = len(raw_docs)
            report.parsed = len(raw_docs)

            for raw in raw_docs:
                try:
                    doc = normalize(raw)
                    result = repo.upsert(doc)
                    if result == "new":
                        report.new += 1
                    elif result == "unchanged":
                        report.unchanged += 1
                    else:
                        report.updated += 1
                except Exception as exc:
                    report.failed += 1
                    _log.warning(
                        "doc_upsert_failed",
                        source=source._config.name,
                        stable_id=getattr(raw, "stable_id", "?"),
                        error=str(exc),
                    )

        except Exception as exc:
            report.error = str(exc)
            report.failed = report.fetched or 1
            _log.error(
                "source_fetch_failed",
                source=source._config.name,
                error=str(exc),
            )

    report.latency_ms = (time.monotonic() - t0) * 1000
    _log.info(
        "source_complete",
        source=report.source,
        fetched=report.fetched,
        new=report.new,
        unchanged=report.unchanged,
        updated=report.updated,
        failed=report.failed,
        latency_ms=round(report.latency_ms, 1),
    )
    return report


async def ingest_all(
    sources: list[Source],
    repo: DocumentRepository,
) -> IngestReport:
    """Run all sources concurrently (up to _SEMAPHORE_LIMIT at a time)."""
    report = IngestReport(started_at=datetime.now())
    semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)

    tasks = [_run_source(s, repo, semaphore) for s in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            _log.error("orchestrator_task_exception", error=str(result))
            report.sources.append(SourceReport(source="unknown", error=str(result)))
        else:
            report.sources.append(result)  # type: ignore[arg-type]

    report.completed_at = datetime.now()
    _log.info(
        "ingest_complete",
        sources=len(report.sources),
        total_fetched=report.total_fetched,
        total_new=report.total_new,
        total_unchanged=report.total_unchanged,
        total_updated=report.total_updated,
        total_failed=report.total_failed,
    )
    return report


def run_ingest(
    config_dir: Path | str | None = None,
    fixture_mode: bool = False,
    db_path: str | None = None,
) -> IngestReport:
    """Synchronous entry point for scripts and tests.

    Loads sources config, builds Fetcher (fixture or live), runs all enabled
    sources with ingest_all(), and returns the aggregate IngestReport.
    """
    cfg_dir = Path(config_dir) if config_dir else None
    settings = get_settings()
    sources_cfg = load_sources_config(cfg_dir)

    effective_fixture = fixture_mode or getattr(sources_cfg, "fixture_mode", False)
    fixture_dir: Path | None = None
    if effective_fixture:
        fixture_dir = Path("tests/fixtures/raw")

    fetcher = Fetcher(fixture_dir=fixture_dir)
    sources = build_sources(sources_cfg.sources, fetcher)

    resolved_db = db_path or settings.database_path
    conn = get_connection(resolved_db)
    try:
        migrate(conn)
        repo = DocumentRepository(conn)
        return asyncio.run(ingest_all(sources, repo))
    finally:
        conn.close()
