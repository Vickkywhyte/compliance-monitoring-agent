"""Module self-test runner (Lesson 2: make selftest).

Runs `python -m compliance_agent.<module>` for every module that has a
__main__ block. Reports pass/fail per module and exits non-zero on any failure.
"""
from __future__ import annotations

import subprocess
import sys

# Modules known to have __main__ blocks (verified at Phase 1 build time)
SELFTEST_MODULES = [
    "compliance_agent.utils.ids",
    "compliance_agent.utils.ratelimit",
    "compliance_agent.storage.db",
    "compliance_agent.storage.audit",
    "compliance_agent.config.loader",
]


def run_module(module: str) -> tuple[bool, str]:
    """Run `python -m <module>` and return (passed, output)."""
    result = subprocess.run(
        [sys.executable, "-m", module],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def main() -> int:
    """Run all module self-tests. Returns exit code."""
    failures: list[str] = []

    print("Running module self-tests...")
    for module in SELFTEST_MODULES:
        passed, output = run_module(module)
        status = "PASS" if passed else "FAIL"
        print(f"  {status}  {module}")
        if not passed:
            failures.append(module)
            for line in output.splitlines():
                print(f"        {line}", file=sys.stderr)

    if failures:
        print(f"\nselftest: {len(failures)} failure(s):", file=sys.stderr)
        for mod in failures:
            print(f"  {mod}", file=sys.stderr)
        return 1

    # Note: utils/logging __main__ creates a temp dir and is covered by test_logging.py
    # It is excluded here to avoid polluting the logs/ directory during selftest runs.
    print(f"\nselftest: all {len(SELFTEST_MODULES)} module self-tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
