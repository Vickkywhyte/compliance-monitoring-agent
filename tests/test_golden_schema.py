"""Phase 8 — Golden set schema and quality gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
GOLDEN_PATH = REPO_ROOT / "data" / "eval" / "golden.jsonl"
RAW_DIR = REPO_ROOT / "data" / "eval" / "raw"

VALID_PROCESS_IDS = {
    "aml",
    "customer_due_diligence",
    "kyc",
    "regulatory_reporting",
    "sanctions_screening",
    "transaction_monitoring",
}

VALID_IMPACT_TYPES = {
    "add_control",
    "modify_control",
    "add_screening",
    "modify_screening",
    "update_reporting",
    "no_impact",
}

REQUIRED_FIELDS = {
    "id",
    "source",
    "source_url",
    "raw_content_path",
    "change_type",
    "expected_change_id_components",
    "expected_summary_keywords",
    "expected_mappings",
    "expected_severity",
}


@pytest.fixture(scope="module")
def entries() -> list[dict]:
    assert GOLDEN_PATH.exists(), f"golden.jsonl not found at {GOLDEN_PATH}"
    result: list[dict] = []
    with GOLDEN_PATH.open() as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError as exc:
                pytest.fail(f"Line {i}: malformed JSON — {exc}")
    return result


def test_file_exists() -> None:
    assert GOLDEN_PATH.exists(), f"golden.jsonl not found at {GOLDEN_PATH}"


def test_minimum_50_entries(entries: list[dict]) -> None:
    assert len(entries) >= 50, f"Expected ≥ 50 entries, got {len(entries)}"


def test_composition_split(entries: list[dict]) -> None:
    by_type: dict[str, int] = {}
    for e in entries:
        ct = e.get("change_type", "")
        by_type[ct] = by_type.get(ct, 0) + 1
    assert by_type.get("new", 0) >= 18, f"Expected ≥ 18 new entries, got {by_type.get('new', 0)}"
    assert by_type.get("amended", 0) >= 18, f"Expected ≥ 18 amended entries, got {by_type.get('amended', 0)}"
    assert by_type.get("withdrawn", 0) >= 8, f"Expected ≥ 8 withdrawn entries, got {by_type.get('withdrawn', 0)}"


def test_required_fields_present(entries: list[dict]) -> None:
    for e in entries:
        missing = REQUIRED_FIELDS - e.keys()
        assert not missing, f"Entry {e.get('id', '?')} missing fields: {missing}"


def test_raw_paths_exist(entries: list[dict]) -> None:
    missing: list[str] = []
    for e in entries:
        p = REPO_ROOT / e["raw_content_path"]
        if not p.exists():
            missing.append(e["raw_content_path"])
        prev = e.get("previous_content_path")
        if prev:
            pp = REPO_ROOT / prev
            if not pp.exists():
                missing.append(prev)
    assert not missing, f"Missing raw fixture files:\n" + "\n".join(missing)


def test_process_ids_in_kb(entries: list[dict]) -> None:
    bad: list[str] = []
    for e in entries:
        for m in e.get("expected_mappings", []):
            pid = m.get("process_id", "")
            if pid and pid not in VALID_PROCESS_IDS:
                bad.append(f"{e['id']}: unknown process_id '{pid}'")
    assert not bad, "Invalid process IDs:\n" + "\n".join(bad)


def test_impact_types_controlled_vocab(entries: list[dict]) -> None:
    bad: list[str] = []
    for e in entries:
        for m in e.get("expected_mappings", []):
            it = m.get("impact_type", "")
            if it and it not in VALID_IMPACT_TYPES:
                bad.append(f"{e['id']}: unknown impact_type '{it}'")
    assert not bad, "Invalid impact types:\n" + "\n".join(bad)


def test_no_duplicate_ids(entries: list[dict]) -> None:
    ids = [e.get("id", "") for e in entries]
    seen: set[str] = set()
    dupes: list[str] = []
    for i in ids:
        if i in seen:
            dupes.append(i)
        seen.add(i)
    assert not dupes, f"Duplicate entry IDs: {dupes}"


def test_quality_gate_passes(entries: list[dict]) -> None:
    """validate_golden must pass without raising."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from compliance_agent.evaluation.golden import GoldenEntry, validate_golden

    golden_entries = [GoldenEntry(**e) for e in entries]
    validate_golden(golden_entries, check_files=True)
