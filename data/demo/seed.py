"""Demo data seeder — loads pre-scripted demo changes into storage.

Reads the 6 JSON files from data/demo/changes/, constructs RegulatoryDocument
and Change records, and writes them to the database without making any network
calls.  Idempotent: safe to run multiple times.

Usage:
    python data/demo/seed.py [--db PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from compliance_agent.storage.changes import ChangeRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.documents import DocumentRepository
from compliance_agent.storage.models import Change, RegulatoryDocument
from compliance_agent.utils.ids import compute_change_id, new_ulid, now_utc

DEMO_DIR = Path(__file__).parent / "changes"
DEFAULT_DB = REPO_ROOT / "data" / "compliance.db"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def seed(db_path: str | Path | None = None) -> int:
    """Seed all demo change files into storage. Returns number of items seeded."""
    resolved = str(db_path or DEFAULT_DB)
    conn = get_connection(resolved)
    migrate(conn)
    doc_repo = DocumentRepository(conn)
    change_repo = ChangeRepository(conn)

    seeded = 0
    change_files = sorted(DEMO_DIR.glob("*.json"))

    for path in change_files:
        data = json.loads(path.read_text())
        source = data["source"]
        stable_id = data["stable_id"]
        change_type = data["change_type"]
        content = data["raw_content"]

        # Insert previous version for amended changes first
        if change_type == "amended" and "previous_raw_content" in data:
            prev_content = data["previous_raw_content"]
            prev_doc = RegulatoryDocument(
                doc_id=new_ulid(),
                source=source,
                stable_id=stable_id,
                title=f"[previous] {data['title']}",
                content=prev_content,
                content_hash=_content_hash(prev_content),
                source_url=data["source_url"],
                fetched_at=datetime.now(timezone.utc),
                version=1,
            )
            doc_repo.upsert(prev_doc)

        doc = RegulatoryDocument(
            doc_id=new_ulid(),
            source=source,
            stable_id=stable_id,
            title=data["title"],
            content=content,
            content_hash=_content_hash(content),
            source_url=data["source_url"],
            fetched_at=datetime.now(timezone.utc),
        )
        result = doc_repo.upsert(doc)

        # Determine the version that was written
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

        change_id = compute_change_id(source, stable_id, current_version)

        if change_type == "withdrawn":
            change = Change(
                change_id=change_id,
                doc_id=latest.doc_id,
                source=source,
                stable_id=stable_id,
                change_type="withdrawn",
                diff=None,
                previous_version=prev_version,
                current_version=current_version,
                detected_at=now_utc(),
                metadata={},
            )
        else:
            change = Change(
                change_id=change_id,
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

        inserted = change_repo.insert(change)
        if inserted:
            seeded += 1
            print(f"  seeded  {data['id']}  {source}/{stable_id}  [{change_type}]")
        else:
            print(f"  exists  {data['id']}  {source}/{stable_id}  [{change_type}]")

    conn.close()
    return seeded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data into storage")
    parser.add_argument("--db", default=None, help="SQLite DB path (default: data/compliance.db)")
    args = parser.parse_args()
    n = seed(db_path=args.db)
    print(f"\nSeeded {n} new demo changes.")
