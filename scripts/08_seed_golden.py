#!/usr/bin/env python3
"""Seed synthetic candidate entries for the golden evaluation set.

Reads the existing golden.jsonl to determine which IDs are taken, then
generates new synthetic candidates from templates for any raw fixture files
that do not yet have full coverage.  Candidates are written to
data/eval/golden_candidates.jsonl — they are NOT appended to golden.jsonl
automatically; a human reviewer must promote them.

Usage:
    python scripts/08_seed_golden.py [--golden PATH] [--out PATH] [--raw-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

GOLDEN_PATH = REPO_ROOT / "data" / "eval" / "golden.jsonl"
RAW_DIR = REPO_ROOT / "data" / "eval" / "raw"
CANDIDATES_PATH = REPO_ROOT / "data" / "eval" / "golden_candidates.jsonl"
ANNOTATED_AT = "2026-10-05T00:00:00Z"
TODAY = date(2026, 10, 5)

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

TEMPLATES: list[dict] = [
    # EUR-Lex new — second regulation
    {
        "source": "eurlex",
        "stable_id": "32024R1205",
        "version": 1,
        "change_type": "new",
        "summary_keywords": ["SIFI", "prudential", "financial stability", "capital"],
        "rubric": "Summarise the systemically-important institution scope and the prudential reporting obligations.",
        "mappings": [{"process_id": "regulatory_reporting", "impact_type": "add_control"}],
        "proposals": [{"assignee_role": "reporting_officer", "category": "reporting_update", "severity": "medium", "deadline_offset_days": 60}],
        "severity": "medium",
    },
    # EUR-Lex new — third regulation
    {
        "source": "eurlex",
        "stable_id": "32024R0444",
        "version": 1,
        "change_type": "new",
        "summary_keywords": ["VASP", "virtual asset", "AML", "travel rule"],
        "rubric": "Summarise the VASP KYC threshold and the travel rule obligations for virtual asset transfers.",
        "mappings": [{"process_id": "kyc", "impact_type": "add_control"}, {"process_id": "sanctions_screening", "impact_type": "add_screening"}],
        "proposals": [{"assignee_role": "mlro", "category": "regulatory_update", "severity": "high", "deadline_offset_days": 14}],
        "severity": "high",
    },
    # Sanctions new — first entity
    {
        "source": "sanctions",
        "stable_id": "EST-2024-0042",
        "version": 1,
        "change_type": "new",
        "summary_keywords": ["Synthetix", "Ukraine", "asset freeze", "immediate"],
        "rubric": "Identify the sanctioned entity and the immediate asset freeze obligation.",
        "mappings": [{"process_id": "sanctions_screening", "impact_type": "add_screening"}],
        "proposals": [{"assignee_role": "mlro", "category": "screening_update", "severity": "critical", "deadline_offset_days": 0}],
        "severity": "critical",
    },
    # Sanctions new — second individual
    {
        "source": "sanctions",
        "stable_id": "EST-2024-0117",
        "version": 1,
        "change_type": "new",
        "summary_keywords": ["Ahmad Karim", "ISIL", "Al-Qaeda", "UN", "travel ban"],
        "rubric": "Identify the individual and both measures (travel ban and asset freeze).",
        "mappings": [{"process_id": "sanctions_screening", "impact_type": "add_screening"}, {"process_id": "customer_due_diligence", "impact_type": "add_control"}],
        "proposals": [{"assignee_role": "mlro", "category": "screening_update", "severity": "critical", "deadline_offset_days": 0}],
        "severity": "critical",
    },
    # EBA new GL
    {
        "source": "eba",
        "stable_id": "GL-2024-07",
        "version": 1,
        "change_type": "new",
        "summary_keywords": ["AML", "CFT", "internal governance", "MLRO", "training"],
        "rubric": "Summarise MLRO appointment requirement and annual risk assessment obligation.",
        "mappings": [{"process_id": "aml", "impact_type": "add_control"}, {"process_id": "customer_due_diligence", "impact_type": "add_control"}],
        "proposals": [{"assignee_role": "mlro", "category": "regulatory_update", "severity": "high", "deadline_offset_days": 21}],
        "severity": "high",
    },
    # EBA new RTS
    {
        "source": "eba",
        "stable_id": "RTS-2024-03",
        "version": 1,
        "change_type": "new",
        "summary_keywords": ["beneficial ownership", "API", "OAuth", "register"],
        "rubric": "Summarise the API access requirement and annual verification obligation.",
        "mappings": [{"process_id": "kyc", "impact_type": "add_control"}, {"process_id": "customer_due_diligence", "impact_type": "add_control"}],
        "proposals": [{"assignee_role": "compliance_officer", "category": "regulatory_update", "severity": "medium", "deadline_offset_days": 45}],
        "severity": "medium",
    },
    # EUR-Lex amended
    {
        "source": "eurlex",
        "stable_id": "32023R0956",
        "version": 2,
        "previous_version": 1,
        "change_type": "amended",
        "summary_keywords": ["threshold", "EUR 5,000", "24 hours", "7 years"],
        "rubric": "Summarise all 5 amendments: thresholds, review frequency, SAR window, retention.",
        "mappings": [{"process_id": "transaction_monitoring", "impact_type": "modify_control"}, {"process_id": "aml", "impact_type": "modify_control"}],
        "proposals": [{"assignee_role": "mlro", "category": "regulatory_update", "severity": "high", "deadline_offset_days": 7}],
        "severity": "high",
    },
    # Sanctions amended
    {
        "source": "sanctions",
        "stable_id": "EST-2023-0891",
        "version": 2,
        "previous_version": 1,
        "change_type": "amended",
        "summary_keywords": ["Technograd", "alias", "TIH Group", "Brest", "IQe.891"],
        "rubric": "Describe the two new aliases, second address, and UN reference added.",
        "mappings": [{"process_id": "sanctions_screening", "impact_type": "modify_screening"}, {"process_id": "customer_due_diligence", "impact_type": "modify_control"}],
        "proposals": [{"assignee_role": "mlro", "category": "screening_update", "severity": "high", "deadline_offset_days": 1}],
        "severity": "high",
    },
    # EBA amended
    {
        "source": "eba",
        "stable_id": "GL-2022-11",
        "version": 2,
        "previous_version": 1,
        "change_type": "amended",
        "summary_keywords": ["crypto", "VASP", "privacy coin", "Section 2a", "EDD"],
        "rubric": "Describe Section 2a (crypto risk factors) and the two new EDD triggers added.",
        "mappings": [{"process_id": "kyc", "impact_type": "modify_control"}, {"process_id": "customer_due_diligence", "impact_type": "modify_control"}, {"process_id": "aml", "impact_type": "modify_control"}],
        "proposals": [{"assignee_role": "mlro", "category": "regulatory_update", "severity": "high", "deadline_offset_days": 21}],
        "severity": "high",
    },
    # Sanctions withdrawn
    {
        "source": "sanctions",
        "stable_id": "EST-2022-0333",
        "version": 1,
        "change_type": "withdrawn",
        "summary_keywords": ["Dmitri Volkov", "delisted", "asset freeze lifted", "October 2024"],
        "rubric": "Confirm all measures are lifted and screening systems must be updated.",
        "mappings": [],
        "proposals": [{"assignee_role": "mlro", "category": "screening_update", "severity": "high", "deadline_offset_days": 1}],
        "severity": "high",
    },
    # EBA withdrawn
    {
        "source": "eba",
        "stable_id": "CP-2021-05",
        "version": 1,
        "change_type": "withdrawn",
        "summary_keywords": ["withdrawn", "superseded", "EBA/ITS/2024/09"],
        "rubric": "Confirm the withdrawal and identify the superseding instrument.",
        "mappings": [],
        "proposals": [{"assignee_role": "reporting_officer", "category": "regulatory_update", "severity": "medium", "deadline_offset_days": 14}],
        "severity": "medium",
    },
]


def _ext_for_source(source: str) -> str:
    return "html" if source == "eba" else "xml"


def _raw_path(source: str, stable_id: str, version: int) -> str:
    ext = _ext_for_source(source)
    return f"data/eval/raw/{source}_{stable_id}_v{version}.{ext}"


def _url_for(source: str, stable_id: str) -> str:
    if source == "eurlex":
        return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{stable_id}"
    if source == "sanctions":
        return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L:{stable_id}:TOC"
    return f"https://www.eba.europa.eu/regulation-and-policy/{stable_id.lower().replace('/', '-')}"


def _deadline(offset_days: int) -> str | None:
    if offset_days < 0:
        return None
    return (TODAY + timedelta(days=offset_days)).isoformat()


def _load_existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


def _next_id(existing: set[str], start: int = 1) -> str:
    n = start
    while True:
        candidate = f"g{n:03d}"
        if candidate not in existing:
            return candidate
        n += 1


def build_candidate(template: dict, entry_id: str, suffix: int = 0) -> dict:
    source = template["source"]
    stable_id = template["stable_id"]
    version = template["version"]
    change_type = template["change_type"]
    raw_path = _raw_path(source, stable_id, version)
    prev_path = (
        _raw_path(source, stable_id, template["previous_version"])
        if "previous_version" in template
        else None
    )

    max_offset = max(
        (p.get("deadline_offset_days", -1) for p in template.get("proposals", [])),
        default=-1,
    )
    deadline = _deadline(max_offset) if max_offset >= 0 else None

    unique_suffix = f" (variant {suffix})" if suffix else ""

    return {
        "id": entry_id,
        "source": source,
        "source_url": _url_for(source, stable_id),
        "raw_content_path": raw_path,
        "change_type": change_type,
        "previous_content_path": prev_path,
        "expected_change_id_components": {
            "source": source,
            "stable_id": stable_id,
            "current_version": version,
        },
        "expected_summary_keywords": template["summary_keywords"],
        "expected_summary_rubric": template["rubric"] + unique_suffix,
        "expected_mappings": template["mappings"],
        "expected_proposals": [
            {
                "assignee_role": p["assignee_role"],
                "category": p["category"],
                "severity": p["severity"],
                "deadline_offset_days": p["deadline_offset_days"],
                "rationale_keywords": [],
            }
            for p in template.get("proposals", [])
        ],
        "expected_deadline": deadline,
        "expected_severity": template["severity"],
        "annotator": "synthetic",
        "annotated_at": ANNOTATED_AT,
        "notes": f"Seeded by 08_seed_golden.py from template for {source}/{stable_id} v{version}.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic golden candidates")
    parser.add_argument("--golden", default=str(GOLDEN_PATH))
    parser.add_argument("--out", default=str(CANDIDATES_PATH))
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    args = parser.parse_args()

    golden_path = Path(args.golden)
    out_path = Path(args.out)
    raw_dir = Path(args.raw_dir)

    existing_ids = _load_existing_ids(golden_path)
    if out_path.exists():
        existing_ids |= _load_existing_ids(out_path)

    candidates: list[dict] = []
    id_counter = 1

    for tmpl in TEMPLATES:
        source = tmpl["source"]
        stable_id = tmpl["stable_id"]
        version = tmpl["version"]
        raw_path = raw_dir / f"{source}_{stable_id}_v{version}.{_ext_for_source(source)}"
        if not raw_path.exists():
            print(f"  SKIP {raw_path.name} — fixture not found", file=sys.stderr)
            continue

        entry_id = _next_id(existing_ids, start=id_counter)
        existing_ids.add(entry_id)
        id_counter = int(entry_id[1:]) + 1

        entry = build_candidate(tmpl, entry_id)
        candidates.append(entry)
        print(f"  GEN  {entry_id}  {source}/{stable_id}/v{version}  [{tmpl['change_type']}]")

    if not candidates:
        print("No candidates generated.")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for c in candidates:
            f.write(json.dumps(c) + "\n")

    new_count = sum(1 for c in candidates if c["change_type"] == "new")
    amended_count = sum(1 for c in candidates if c["change_type"] == "amended")
    withdrawn_count = sum(1 for c in candidates if c["change_type"] == "withdrawn")

    print()
    print(f"Written {len(candidates)} candidate entries to {out_path}")
    print(f"  new={new_count}  amended={amended_count}  withdrawn={withdrawn_count}")
    print()
    print("Review and promote annotator='synthetic' → 'human' before use in eval runs.")
    print(f"Append to golden set: cat {out_path} >> {golden_path}")


if __name__ == "__main__":
    main()
