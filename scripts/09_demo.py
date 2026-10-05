"""Phase 9 demo script — seed, run pipeline, optionally open dashboard.

Usage:
    python scripts/09_demo.py [--reset] [--no-serve] [--db PATH]

Options:
    --reset     Clear the database before seeding (fresh run).
    --no-serve  Run the pipeline only; do not launch Streamlit.
    --db        SQLite path override (default: data/compliance.db).

Total time budget: ≤ 5 minutes on a laptop (fixture LLM, no network).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from compliance_agent.config.loader import get_settings
from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.proposals import ProposalRepository


def _build_fake_gateway():
    """Build an LLMGateway backed by FakeLLMBackend for no-network demo runs."""
    from compliance_agent.config.models import GatewayConfig, LLMConfig
    from compliance_agent.llm.gateway import LLMGateway
    from tests.mocks.llm import FakeLLMBackend

    summary_response = (
        '{"text": "This regulatory change introduces new compliance requirements '
        'affecting anti-money laundering and customer due diligence procedures. '
        'Institutions must update their internal controls accordingly.", '
        '"citations": [{"source_url": "https://example.com", "span_start": 0, '
        '"span_end": 50, "quoted_text": "compliance requirements"}], '
        '"confidence": 0.82}'
    )
    mapping_response = (
        '{"mappings": [{"process_id": "aml", "process_section_id": "aml_test:0", '
        '"impact_type": "add_control", "confidence": 0.85, '
        '"rationale": "New AML control required", '
        '"citation_quote": "compliance requirements"}]}'
    )
    proposal_response = (
        '{"title": "Update AML compliance controls", '
        '"description": "Review and update internal AML controls to comply with '
        'the new regulatory requirements.", '
        '"rationale": "Regulatory obligation", '
        '"category": "policy_update"}'
    )

    responses = []
    for _ in range(12):
        responses.extend([summary_response, mapping_response, proposal_response])

    fake = FakeLLMBackend(responses=responses)
    return LLMGateway(
        primary=fake,
        fallback=None,
        llm_config=LLMConfig(primary_model="fake", fallback_model="fake"),
        gateway_config=GatewayConfig(),
    )


def _build_fake_kb():
    """Build an in-memory Chroma collection pre-populated with KB fixtures."""
    import chromadb
    from compliance_agent.intelligence.kb import index_knowledge_base

    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("knowledge_base")
    kb_dir = REPO_ROOT / "tests" / "fixtures" / "kb"
    if kb_dir.exists():
        index_knowledge_base(kb_dir, collection)
    return collection


def reset_db(db_path: str) -> None:
    """Drop and re-create the database (--reset flag)."""
    p = Path(db_path)
    if p.exists():
        p.unlink()
        print(f"  reset   database removed: {p}")
    conn = get_connection(db_path)
    migrate(conn)
    conn.close()
    print(f"  reset   database re-created: {p}")


def seed_demo(db_path: str) -> int:
    """Seed demo data if storage is empty. Returns number of changes seeded."""
    conn = get_connection(db_path)
    migrate(conn)
    change_repo = ChangeRepository(conn)
    existing = change_repo.list_recent(limit=1)
    conn.close()

    if existing:
        print(f"  seed    storage already has data — skipping seed")
        return 0

    sys.path.insert(0, str(REPO_ROOT / "data" / "demo"))
    import importlib.util

    seed_path = REPO_ROOT / "data" / "demo" / "seed.py"
    spec = importlib.util.spec_from_file_location("demo_seed", seed_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.seed(db_path=db_path)


def run_pipeline(db_path: str) -> None:
    """Run the full pipeline in fixture/fake mode."""
    from compliance_agent.pipeline import run_pipeline as _run

    gateway = _build_fake_gateway()
    kb_collection = _build_fake_kb()

    print("\n  pipeline  starting...")
    t0 = time.monotonic()
    report = _run(
        fixture_mode=False,
        db_path=db_path,
        gateway=gateway,
        kb_collection=kb_collection,
        skip_ingest=True,
    )
    elapsed = time.monotonic() - t0

    print(f"\n  pipeline  complete in {elapsed:.1f}s")
    print(f"  changes detected    : {report.changes_detected}")
    print(f"  summaries generated : {report.summaries_generated}")
    print(f"  mappings generated  : {report.mappings_generated}")
    print(f"  proposals created   : {report.proposals_generated}")
    print(f"  proposals routed    : {report.proposals_routed}")
    print(f"  failures            : {len(report.failures)}")

    # Per-change detail
    conn = get_connection(db_path)
    proposal_repo = ProposalRepository(conn)
    change_repo = ChangeRepository(conn)
    changes = change_repo.list_recent(limit=20)
    print()
    print(f"  {'change_id':<20}  {'type':<10}  {'proposals':<10}  {'routed_to':<12}  severity")
    print(f"  {'-'*20}  {'-'*10}  {'-'*10}  {'-'*12}  --------")
    for ch in changes:
        proposals = proposal_repo.list_by_change(ch.change_id)
        proposal_count = len(proposals)
        if proposals:
            routed = proposals[0].assignee_role
            severity = proposals[0].severity
        else:
            routed = "—"
            severity = "—"
        print(f"  {ch.change_id:<20}  {ch.change_type:<10}  {proposal_count:<10}  {routed:<12}  {severity}")
    conn.close()

    if report.failures:
        print(f"\n  WARNING: {len(report.failures)} failure(s):")
        for f in report.failures:
            print(f"    stage={f.stage}  entity={f.entity_id}  error={f.error}")


def launch_dashboard() -> None:
    """Launch the Streamlit dashboard in a background process."""
    app_path = REPO_ROOT / "src" / "compliance_agent" / "dashboard" / "app.py"
    print("\n  dashboard  launching at http://localhost:8501 ...")
    subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(app_path),
         "--server.port", "8501", "--server.headless", "true"],
        cwd=str(REPO_ROOT),
    )
    time.sleep(3)
    print("  dashboard  open http://localhost:8501 in your browser")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compliance monitoring demo")
    parser.add_argument("--reset", action="store_true", help="Clear DB before seeding")
    parser.add_argument("--no-serve", action="store_true", help="Skip dashboard launch")
    parser.add_argument("--db", default=None, help="SQLite DB path override")
    args = parser.parse_args()

    t_start = time.monotonic()
    settings = get_settings()
    db_path = args.db or settings.database_path

    print("=== Compliance Monitoring Agent — Demo ===")
    print(f"  db: {db_path}")
    print()

    if args.reset:
        reset_db(db_path)

    print("  seeding demo data...")
    n_seeded = seed_demo(db_path)
    print(f"  seeded {n_seeded} change(s)")

    run_pipeline(db_path)

    if not args.no_serve:
        launch_dashboard()

    elapsed_total = time.monotonic() - t_start
    print(f"\n  total elapsed: {elapsed_total:.1f}s")
    if elapsed_total > 300:
        print("  WARNING: total time exceeded 5-minute budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
