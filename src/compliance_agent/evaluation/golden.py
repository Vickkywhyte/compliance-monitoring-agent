"""Golden-set loader and quality gate (06_EVAL_SPEC.md §2).

load_golden(path) → list[GoldenEntry]
validate_golden(entries) → None   (raises GoldenValidationError on any violation)
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from compliance_agent.exceptions import GoldenValidationError

# Known process IDs (from data/kb/processes/)
_VALID_PROCESS_IDS: frozenset[str] = frozenset({
    "aml",
    "customer_due_diligence",
    "kyc",
    "regulatory_reporting",
    "sanctions_screening",
    "transaction_monitoring",
})


class GoldenEntry(BaseModel):
    """One labeled entry in the golden evaluation set (§2.1)."""

    model_config = {"extra": "ignore"}

    id: str
    source: str
    source_url: str
    raw_content_path: str
    change_type: str
    previous_content_path: str | None = None
    expected_change_id_components: dict[str, Any] = Field(default_factory=dict)
    expected_summary_keywords: list[str] = Field(default_factory=list)
    expected_summary_rubric: str = ""
    expected_mappings: list[dict[str, Any]] = Field(default_factory=list)
    expected_proposals: list[dict[str, Any]] = Field(default_factory=list)
    expected_deadline: str | None = None
    expected_severity: str = "low"
    annotator: str = ""
    annotated_at: str = ""
    notes: str = ""


def load_golden(path: str | Path) -> list[GoldenEntry]:
    """Load and parse *path* as a JSON Lines golden set file.

    Raises:
        GoldenValidationError: on malformed JSON or missing required fields.
    """
    p = Path(path)
    if not p.exists():
        raise GoldenValidationError(f"Golden set file not found: {p}")
    entries: list[GoldenEntry] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GoldenValidationError(f"Malformed JSON at line {lineno}: {exc}") from exc
        try:
            entries.append(GoldenEntry(**raw))
        except PydanticValidationError as exc:
            raise GoldenValidationError(
                f"Missing or invalid fields at line {lineno}: {exc}"
            ) from exc
    return entries


def validate_golden(entries: list[GoldenEntry], check_files: bool = True) -> None:
    """Run the quality gate on *entries*; raise GoldenValidationError on any failure.

    Quality gate rules (§2.4):
    1. Duplicate IDs
    2. Missing required fields (enforced by GoldenEntry model)
    3. expected_mappings empty when change_type != "withdrawn"
    4. expected_proposals empty when expected_severity != "low"
    5. References to non-existent process IDs
    6. raw_content_path missing or file not found (when check_files=True)
    7. Malformed JSON (handled in load_golden)
    8. expected_deadline inconsistent with deadline_offset_days
    """
    errors: list[str] = []

    # 1. Duplicate IDs
    seen_ids: set[str] = set()
    for e in entries:
        if e.id in seen_ids:
            errors.append(f"Duplicate id: {e.id!r}")
        seen_ids.add(e.id)

    for e in entries:
        # 3. expected_mappings empty when change_type != "withdrawn"
        if e.change_type != "withdrawn" and not e.expected_mappings:
            errors.append(
                f"[{e.id}] expected_mappings is empty for change_type={e.change_type!r}"
            )

        # 4. expected_proposals empty when expected_severity != "low"
        if e.expected_severity != "low" and not e.expected_proposals:
            errors.append(
                f"[{e.id}] expected_proposals is empty for expected_severity={e.expected_severity!r}"
            )

        # 5. Unknown process IDs in expected_mappings
        for m in e.expected_mappings:
            pid = m.get("process_id", "")
            if pid and pid not in _VALID_PROCESS_IDS:
                errors.append(
                    f"[{e.id}] Unknown process_id {pid!r} in expected_mappings"
                )

        # 6. raw_content_path file not found
        if check_files and not Path(e.raw_content_path).exists():
            errors.append(
                f"[{e.id}] raw_content_path not found: {e.raw_content_path!r}"
            )

        # 8. expected_deadline vs deadline_offset_days in first expected_proposal
        if e.expected_deadline and e.expected_proposals:
            first = e.expected_proposals[0]
            offset_days = first.get("deadline_offset_days")
            if offset_days is not None:
                # The deadline should be approximately today + offset_days
                # (we check within 7 days to allow for annotation date drift)
                try:
                    dl = date.fromisoformat(e.expected_deadline)
                    ann = date.fromisoformat(e.annotated_at[:10]) if e.annotated_at else date.today()
                    expected_dl = ann + timedelta(days=int(offset_days))
                    if abs((dl - expected_dl).days) > 7:
                        errors.append(
                            f"[{e.id}] expected_deadline {e.expected_deadline!r} inconsistent "
                            f"with deadline_offset_days={offset_days} (annotated {e.annotated_at[:10]})"
                        )
                except (ValueError, TypeError):
                    pass  # date parse errors handled elsewhere

    if errors:
        raise GoldenValidationError(
            f"Golden set quality gate failed ({len(errors)} error(s)):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
