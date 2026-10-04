"""LLM-powered change summarizer with citation grounding (09_AGENT_DESIGN.md §3).

Output schema validation:
  - Retry once if JSON is invalid or required keys are missing
  - After two failures, mark low_confidence=True and use raw text as summary
  - quoted_text in each Citation is always extracted from doc.content using
    span_start:span_end — never taken directly from LLM output (C-03)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

from compliance_agent.exceptions import LLMError
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.llm.prompts import PromptRegistry
from compliance_agent.storage.models import Change, Citation, RegulatoryDocument, Summary
from compliance_agent.utils.ids import new_ulid

from .fencing import fence

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_INSUFFICIENT = "insufficient_information"


class Summarizer:
    """Summarize a regulatory change using LLM; ground citations in the source doc."""

    def __init__(
        self,
        gateway: LLMGateway,
        registry: PromptRegistry | None = None,
        prompt_version: int = 1,
    ) -> None:
        self._gateway = gateway
        self._registry = registry or PromptRegistry(_PROMPTS_DIR)
        self._prompt_version = prompt_version

    def summarize(self, change: Change, doc: RegulatoryDocument) -> Summary:
        """Return a Summary for the given Change, grounded in doc.content."""
        prompt = self._build_prompt(doc)
        version_str = f"summarize_v{self._prompt_version}"

        last_resp = None
        parsed = None

        for attempt in range(2):
            try:
                resp = self._gateway.complete(prompt)
            except LLMError as exc:
                log.warning("summarizer_llm_error", attempt=attempt, error=str(exc))
                if attempt == 1:
                    raise
                continue
            last_resp = resp
            parsed = _try_parse(resp.text, doc)
            if parsed is not None:
                break
            log.warning("summarizer_invalid_output", attempt=attempt, text=resp.text[:200])

        low_confidence = parsed is None
        if parsed is None:
            parsed = {
                "text": last_resp.text if last_resp else _INSUFFICIENT,
                "citations": [],
                "confidence": 0.1,
            }

        return Summary(
            summary_id=new_ulid(),
            change_id=change.change_id,
            text=parsed["text"],
            citations=parsed["citations"],
            prompt_version=version_str,
            model=last_resp.model if last_resp else "unknown",
            confidence=float(parsed.get("confidence", 0.5)),
            low_confidence=low_confidence,
            generated_at=datetime.now(timezone.utc),
            tokens_in=last_resp.tokens_in if last_resp else 0,
            tokens_out=last_resp.tokens_out if last_resp else 0,
            cost_usd=last_resp.cost_usd if last_resp else 0.0,
        )

    def _build_prompt(self, doc: RegulatoryDocument) -> str:
        template = self._registry.load("summarize", self._prompt_version)
        fenced = fence(doc.content)
        return (
            template
            .replace("{{DOCUMENT}}", fenced)
            .replace("{{SOURCE_URL}}", doc.source_url)
        )


def _try_parse(raw: str, doc: RegulatoryDocument) -> dict | None:
    """Parse and validate LLM JSON; return None if it fails validation."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    text = data.get("text", "")
    if not isinstance(text, str) or not text:
        return None

    citations: list[Citation] = []
    for cit in data.get("citations", []):
        try:
            span_start = int(cit["span_start"])
            span_end = int(cit["span_end"])
            if span_start < 0 or span_end > len(doc.content) or span_start >= span_end:
                continue
            citations.append(
                Citation(
                    source_url=doc.source_url,
                    span_start=span_start,
                    span_end=span_end,
                    quoted_text=doc.content[span_start:span_end],
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    return {
        "text": text,
        "citations": citations,
        "confidence": float(data.get("confidence", 0.5)),
    }
