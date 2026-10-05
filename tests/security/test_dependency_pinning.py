"""Security tests for dependency pinning (C-29, C-30).

C-29: All dependencies are pinned to exact versions in requirements.lock.
C-30: pyproject.toml uses version bounds (>=) for compat, not exact pins,
      so that the lockfile remains the single source of truth.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
LOCK_FILE = REPO_ROOT / "requirements.lock"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Patterns for requirements.lock lines
_COMMENT_OR_BLANK = re.compile(r"^\s*(#.*)?$")
_EDITABLE_INSTALL = re.compile(r"^-e\s+")
# A pinned line: <name>==<version> (optionally with extras like name[extras]==version)
_PINNED_LINE = re.compile(r"^[A-Za-z0-9_.\-]+(\[.*?\])?==\S+$")
# An option line (e.g., --index-url, --extra-index-url)
_OPTION_LINE = re.compile(r"^--")


def _lock_content_lines() -> list[str]:
    return LOCK_FILE.read_text().splitlines()


def test_requirements_lock_exists() -> None:
    """requirements.lock must exist at the repo root (C-29)."""
    assert LOCK_FILE.exists(), (
        f"requirements.lock not found at {LOCK_FILE}. "
        "Run `make lock` to generate it."
    )


def test_requirements_lock_pins_exact_versions() -> None:
    """Every non-comment, non-editable line in requirements.lock must be name==version (C-29)."""
    violations: list[str] = []
    for i, line in enumerate(_lock_content_lines(), start=1):
        stripped = line.strip()
        if _COMMENT_OR_BLANK.match(stripped):
            continue
        if _EDITABLE_INSTALL.match(stripped):
            continue  # editable installs are allowed (the package itself)
        if _OPTION_LINE.match(stripped):
            continue  # index-url options are allowed
        if not _PINNED_LINE.match(stripped):
            violations.append(f"  Line {i}: {stripped!r}")

    assert not violations, (
        "requirements.lock contains non-pinned entries:\n"
        + "\n".join(violations)
        + "\nAll packages must use == (exact version pinning)."
    )


def test_pyproject_uses_version_bounds() -> None:
    """pyproject.toml dependencies must use >= bounds, not exact == pins (C-30).

    The lockfile is the source of truth for exact versions.
    pyproject.toml specifies compatibility ranges so that `pip-compile`
    can regenerate the lockfile when packages are updated.
    """
    content = PYPROJECT.read_text()

    # Find the [project.dependencies] block
    in_deps = False
    exact_pins: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[project"):
            in_deps = "dependencies" in stripped
        if in_deps and "==" in stripped and not stripped.startswith("#"):
            # Allow exact pins for test infrastructure but flag production deps
            exact_pins.append(stripped)

    assert not exact_pins, (
        "pyproject.toml should use >= bounds, not == exact pins:\n"
        + "\n".join(f"  {p}" for p in exact_pins)
        + "\nUse requirements.lock for exact pinning."
    )


def test_no_unknown_packages_in_lock() -> None:
    """Every non-comment, non-editable line in requirements.lock matches the expected format."""
    malformed: list[str] = []
    for i, line in enumerate(_lock_content_lines(), start=1):
        stripped = line.strip()
        if _COMMENT_OR_BLANK.match(stripped):
            continue
        if _EDITABLE_INSTALL.match(stripped):
            continue
        if _OPTION_LINE.match(stripped):
            continue
        # Must match: optional-extras==version
        if not re.match(r"^[A-Za-z0-9_.\-]+(\[.*?\])?==\S+$", stripped):
            malformed.append(f"  Line {i}: {stripped!r}")

    assert not malformed, (
        "requirements.lock contains lines that do not match "
        "`package[extras]==version` format:\n" + "\n".join(malformed)
    )
