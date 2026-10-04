"""Unified diff computation for regulatory document content (Phase 3).

compute_diff(previous, current) → unified diff string.
Returns empty string when content is identical.
Raises DiffError for binary or oversized inputs.
"""
from __future__ import annotations

import difflib

from compliance_agent.exceptions import DiffError

_MAX_CONTENT_BYTES = 10 * 1024 * 1024  # 10 MB per side


def compute_diff(previous_content: str, current_content: str) -> str:
    """Return a unified diff of two normalized text strings.

    Only call this on the `content` field of RegulatoryDocument (normalized plain
    text), never on raw XML or HTML.

    Returns an empty string when previous_content == current_content.
    Raises DiffError when either input contains NUL bytes or exceeds 10 MB.
    """
    for label, text in (("previous", previous_content), ("current", current_content)):
        if "\x00" in text:
            raise DiffError(f"Binary content (NUL byte) detected in {label} document")
        if len(text.encode("utf-8", errors="replace")) > _MAX_CONTENT_BYTES:
            raise DiffError(
                f"Content too large to diff: {label} exceeds {_MAX_CONTENT_BYTES} bytes"
            )

    if previous_content == current_content:
        return ""

    diff_lines = list(
        difflib.unified_diff(
            previous_content.splitlines(keepends=True),
            current_content.splitlines(keepends=True),
            fromfile="previous",
            tofile="current",
            lineterm="",
        )
    )
    return "\n".join(diff_lines)


if __name__ == "__main__":
    print("=== detection/diff self-test ===")

    result = compute_diff("line 1\nline 2\n", "line 1\nline 2\n")
    assert result == "", f"identical content must yield empty string, got: {result!r}"
    print("  identical → empty: OK")

    result = compute_diff("old text\nother\n", "new text\nother\n")
    assert "---" in result and "+++" in result
    assert "-old text" in result
    assert "+new text" in result
    print(f"  diff generated ({len(result)} chars): OK")

    try:
        compute_diff("hello\x00world", "hi")
        raise AssertionError("should have raised DiffError")
    except DiffError as exc:
        print(f"  binary → DiffError: OK ({exc!s:.40s}...)")

    print("PASS")
