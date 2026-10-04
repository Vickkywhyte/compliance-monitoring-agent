"""Untrusted content fencing (C-01, C-02, ADR-016).

All external document content MUST pass through fence() before insertion
into a prompt. This prevents prompt injection by:
  1. Escaping any existing UNTRUSTED_SOURCE_CONTENT tags in the input
  2. Wrapping the result in a clearly labelled boundary

The system prompt preamble tells the LLM to treat fenced content as data,
never as instructions.
"""
from __future__ import annotations

OPEN_TAG = "<UNTRUSTED_SOURCE_CONTENT>"
CLOSE_TAG = "</UNTRUSTED_SOURCE_CONTENT>"
ESCAPE_OPEN = "[ESCAPED_OPEN_TAG]"
ESCAPE_CLOSE = "[ESCAPED_CLOSE_TAG]"


def fence(text: str) -> str:
    """Escape internal tags then wrap text in UNTRUSTED_SOURCE_CONTENT tags."""
    text = text.replace(OPEN_TAG, ESCAPE_OPEN)
    text = text.replace(CLOSE_TAG, ESCAPE_CLOSE)
    return f"{OPEN_TAG}\n{text}\n{CLOSE_TAG}"
