"""Unit tests for the golden-set quality gate (Phase 7)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from compliance_agent.evaluation.golden import GoldenEntry, load_golden, validate_golden
from compliance_agent.exceptions import GoldenValidationError


def _make_entry(**overrides) -> GoldenEntry:
    base = dict(
        id="e-001",
        source="EUR-Lex",
        source_url="https://eur-lex.europa.eu/test",
        raw_content_path="/tmp/test_raw.txt",
        change_type="new_requirement",
        expected_mappings=[{"process_id": "aml", "impact_type": "new_obligation"}],
        expected_proposals=[{"assignee_role": "compliance_officer", "severity": "high"}],
        expected_severity="high",
        annotated_at="2026-10-01",
    )
    base.update(overrides)
    return GoldenEntry(**base)


def test_duplicate_ids_rejected():
    e1 = _make_entry(id="dup-1")
    e2 = _make_entry(id="dup-1")
    with pytest.raises(GoldenValidationError, match="Duplicate id"):
        validate_golden([e1, e2], check_files=False)


def test_empty_mappings_for_non_withdrawn():
    e = _make_entry(change_type="new_requirement", expected_mappings=[])
    with pytest.raises(GoldenValidationError, match="expected_mappings is empty"):
        validate_golden([e], check_files=False)


def test_withdrawn_change_type_allows_empty_mappings():
    e = _make_entry(change_type="withdrawn", expected_mappings=[])
    # Should not raise
    validate_golden([e], check_files=False)


def test_unknown_process_id_rejected():
    e = _make_entry(
        expected_mappings=[{"process_id": "not_a_real_process", "impact_type": "new_obligation"}]
    )
    with pytest.raises(GoldenValidationError, match="Unknown process_id"):
        validate_golden([e], check_files=False)


def test_valid_entry_passes():
    e = _make_entry()
    validate_golden([e], check_files=False)


def test_load_golden_malformed_json(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "e-1", "source": "EUR-Lex"\n', encoding="utf-8")
    with pytest.raises(GoldenValidationError, match="Malformed JSON"):
        load_golden(bad)


def test_load_golden_missing_file():
    with pytest.raises(GoldenValidationError, match="not found"):
        load_golden("/nonexistent/golden.jsonl")


def test_load_golden_valid(tmp_path):
    line = json.dumps({
        "id": "e-1",
        "source": "EUR-Lex",
        "source_url": "https://example.com",
        "raw_content_path": "/tmp/raw.txt",
        "change_type": "new_requirement",
        "expected_mappings": [{"process_id": "aml", "impact_type": "new_obligation"}],
        "expected_severity": "low",
    })
    f = tmp_path / "golden.jsonl"
    f.write_text(line + "\n", encoding="utf-8")
    entries = load_golden(f)
    assert len(entries) == 1
    assert entries[0].id == "e-1"
