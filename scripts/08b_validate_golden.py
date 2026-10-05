#!/usr/bin/env python3
"""Quality gate runner for the golden evaluation set.

Loads data/eval/golden.jsonl, runs all 8 validate_golden checks,
verifies composition targets, checks raw_content_path files exist,
validates all process_ids and impact_types against controlled vocabularies,
and prints a summary table.

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.

Usage:
    python scripts/08b_validate_golden.py [--golden PATH] [--no-file-checks]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from compliance_agent.evaluation.golden import GoldenEntry, load_golden, validate_golden

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

COMPOSITION_TARGETS = {
    "new": 18,
    "amended": 18,
    "withdrawn": 8,
    "total": 46,
}


def _check_mark(ok: bool) -> str:
    return "  PASS" if ok else "  FAIL"


def run_checks(golden_path: Path, check_files: bool = True) -> bool:
    all_passed = True
    checks: list[tuple[str, bool, str]] = []

    # 1 — file exists
    file_exists = golden_path.exists()
    checks.append(("golden.jsonl exists", file_exists, str(golden_path)))
    if not file_exists:
        _print_table(checks)
        return False

    # 2 — load
    try:
        entries: list[GoldenEntry] = load_golden(golden_path)
        load_ok = True
        load_msg = f"{len(entries)} entries loaded"
    except Exception as exc:
        entries = []
        load_ok = False
        load_msg = str(exc)
    checks.append(("Load (no malformed JSON)", load_ok, load_msg))

    if not load_ok:
        _print_table(checks)
        return False

    # 3 — total count
    total_ok = len(entries) >= COMPOSITION_TARGETS["total"]
    checks.append((f"Total entries ≥ {COMPOSITION_TARGETS['total']}", total_ok, f"{len(entries)} found"))

    # 4 — composition split
    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e.change_type] = by_type.get(e.change_type, 0) + 1
    for ct, minimum in [("new", COMPOSITION_TARGETS["new"]), ("amended", COMPOSITION_TARGETS["amended"]), ("withdrawn", COMPOSITION_TARGETS["withdrawn"])]:
        count = by_type.get(ct, 0)
        ok = count >= minimum
        checks.append((f"  {ct} ≥ {minimum}", ok, f"{count} found"))

    # 5 — no duplicate IDs
    ids = [e.id for e in entries]
    seen: set[str] = set()
    dupes = [i for i in ids if i in seen or seen.add(i)]  # type: ignore[func-returns-value]
    no_dupes = len(dupes) == 0
    checks.append(("No duplicate IDs", no_dupes, f"duplicates: {dupes}" if dupes else "all unique"))

    # 6 — raw_content_path files exist
    if check_files:
        missing_paths: list[str] = []
        for e in entries:
            p = REPO_ROOT / e.raw_content_path
            if not p.exists():
                missing_paths.append(e.raw_content_path)
            if e.previous_content_path:
                pp = REPO_ROOT / e.previous_content_path
                if not pp.exists():
                    missing_paths.append(e.previous_content_path)
        paths_ok = len(missing_paths) == 0
        checks.append((
            "All raw_content_path files exist",
            paths_ok,
            f"missing: {missing_paths[:5]}" if missing_paths else f"all {len(entries)} paths verified",
        ))

    # 7 — valid process IDs in KB
    bad_pids: list[str] = []
    for e in entries:
        for m in e.expected_mappings:
            pid = m.get("process_id", "")
            if pid and pid not in VALID_PROCESS_IDS:
                bad_pids.append(f"{e.id}/{pid}")
    pids_ok = len(bad_pids) == 0
    checks.append((
        "All process_ids in KB",
        pids_ok,
        f"unknown: {bad_pids[:5]}" if bad_pids else "all valid",
    ))

    # 8 — valid impact_types
    bad_impacts: list[str] = []
    for e in entries:
        for m in e.expected_mappings:
            it = m.get("impact_type", "")
            if it and it not in VALID_IMPACT_TYPES:
                bad_impacts.append(f"{e.id}/{it}")
    impacts_ok = len(bad_impacts) == 0
    checks.append((
        "All impact_types in controlled vocab",
        impacts_ok,
        f"unknown: {bad_impacts[:5]}" if bad_impacts else "all valid",
    ))

    # 9 — quality gate (validate_golden — all 8 internal checks)
    try:
        validate_golden(entries, check_files=check_files)
        gate_ok = True
        gate_msg = "all 8 checks passed"
    except Exception as exc:
        gate_ok = False
        gate_msg = str(exc)[:120]
    checks.append(("Quality gate (validate_golden)", gate_ok, gate_msg))

    _print_table(checks)

    all_passed = all(ok for _, ok, _ in checks)
    return all_passed


def _print_table(checks: list[tuple[str, bool, str]]) -> None:
    print()
    print(f"{'Check':<45}  {'Result':<6}  {'Detail'}")
    print("-" * 90)
    for label, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"  {label:<43}  {mark:<6}  {detail}")
    print()
    failed = sum(1 for _, ok, _ in checks if not ok)
    total = len(checks)
    if failed == 0:
        print(f"All {total} checks passed.")
    else:
        print(f"{failed}/{total} checks FAILED.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden set quality gate runner")
    parser.add_argument("--golden", default=str(REPO_ROOT / "data" / "eval" / "golden.jsonl"))
    parser.add_argument("--no-file-checks", action="store_true", help="Skip raw path existence checks")
    args = parser.parse_args()

    golden_path = Path(args.golden)
    check_files = not args.no_file_checks

    print(f"Validating golden set: {golden_path}")
    ok = run_checks(golden_path, check_files=check_files)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
