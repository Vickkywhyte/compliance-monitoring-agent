"""Pre-commit hook: fail if src/ or scripts/ changed but CHANGELOG.md is not."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    )
    changed = result.stdout.splitlines()

    touches_code = any(
        f.startswith("src/") or f.startswith("scripts/") for f in changed
    )
    touches_changelog = any(f == "CHANGELOG.md" for f in changed)

    if touches_code and not touches_changelog:
        print(
            "ERROR: commit touches src/ or scripts/ but CHANGELOG.md is not staged.\n"
            "Update CHANGELOG.md in the same commit (Lesson 7).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
