"""Phase 2 ingestion entry point.

Usage:
    python scripts/02_ingest.py [--fixture] [--config-dir PATH] [--db PATH]

Options:
    --fixture       Load from tests/fixtures/raw/ instead of live URLs
    --config-dir    Path to configs/ directory (default: configs/)
    --db            Path to SQLite database (default: from settings)

Exits 0 on success, 1 if any source failed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from compliance_agent.ingestion.orchestrator import run_ingest
from compliance_agent.utils.logging import configure_logging, get_logger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest regulatory sources (Phase 2)")
    parser.add_argument("--fixture", action="store_true", help="Use fixture files instead of live HTTP")
    parser.add_argument("--config-dir", default=None, help="Path to configs/ directory")
    parser.add_argument("--db", default=None, help="Path to SQLite database file")
    args = parser.parse_args(argv)

    configure_logging()
    log = get_logger("scripts.02_ingest")

    log.info("ingest_start", fixture_mode=args.fixture)
    report = run_ingest(
        config_dir=args.config_dir,
        fixture_mode=args.fixture,
        db_path=args.db,
    )

    print(f"\n{'─' * 50}")
    print(f"Ingestion complete — {len(report.sources)} source(s)")
    print(f"{'─' * 50}")
    for sr in report.sources:
        status = f"ERROR: {sr.error}" if sr.error else "OK"
        print(
            f"  {sr.source:<20} fetched={sr.fetched}  new={sr.new}  "
            f"unchanged={sr.unchanged}  updated={sr.updated}  "
            f"failed={sr.failed}  {sr.latency_ms:.0f}ms  [{status}]"
        )
    print(f"{'─' * 50}")
    print(
        f"  TOTAL  fetched={report.total_fetched}  new={report.total_new}  "
        f"unchanged={report.total_unchanged}  updated={report.total_updated}  "
        f"failed={report.total_failed}"
    )
    print(f"{'─' * 50}\n")

    return 1 if report.total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
