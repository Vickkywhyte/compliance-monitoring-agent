"""Process mapper: links regulatory changes to internal business processes.

Retrieves the top-K KB chunks from Chroma, builds a fenced prompt,
calls the LLM, and returns ranked ProcessMappings.

Filtering rules (09_AGENT_DESIGN.md §4):
  - Drop mappings with confidence < min_confidence (from agent.yaml)
  - Drop mappings with process_section_id not in the retrieved chunk IDs
  - Drop mappings with invalid impact_type
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import structlog

from compliance_agent.config.loader import load_agent_config
from compliance_agent.exceptions import LLMError
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.llm.prompts import PromptRegistry
from compliance_agent.storage.models import Change, ImpactType, ProcessMapping, Summary
from compliance_agent.utils.ids import new_ulid

from .fencing import fence

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_VALID_IMPACT_TYPES: frozenset[str] = frozenset(get_args(ImpactType))


class Mapper:
    """Map a regulatory change to internal business processes via KB + LLM."""

    def __init__(
        self,
        gateway: LLMGateway,
        collection,
        registry: PromptRegistry | None = None,
        prompt_version: int = 1,
    ) -> None:
        self._gateway = gateway
        self._collection = collection
        self._registry = registry or PromptRegistry(_PROMPTS_DIR)
        self._prompt_version = prompt_version
        self._cfg = load_agent_config().mapper

    def map(self, change: Change, summary: Summary) -> list[ProcessMapping]:
        """Return a filtered, ranked list of ProcessMappings for this change."""
        chunks = self._retrieve(summary.text)
        if not chunks:
            log.warning("mapper_no_chunks_retrieved", change_id=change.change_id)
            return []

        valid_chunk_ids = {c["id"] for c in chunks}
        prompt = self._build_prompt(summary, chunks)
        version_str = f"map_v{self._prompt_version}"

        last_resp = None
        raw_mappings: list[dict] = []

        for attempt in range(2):
            try:
                resp = self._gateway.complete(prompt)
            except LLMError as exc:
                log.warning("mapper_llm_error", attempt=attempt, error=str(exc))
                if attempt == 1:
                    raise
                continue
            last_resp = resp
            raw_mappings = _parse_mappings(resp.text)
            if raw_mappings:
                break
            log.warning("mapper_invalid_output", attempt=attempt, text=resp.text[:200])

        model = last_resp.model if last_resp else "unknown"
        results: list[ProcessMapping] = []

        for m in raw_mappings:
            confidence = _safe_float(m.get("confidence"))
            if confidence is None or confidence < self._cfg.min_confidence:
                continue
            impact = m.get("impact_type", "")
            if impact not in _VALID_IMPACT_TYPES:
                log.warning("mapper_invalid_impact_type", impact=impact)
                continue
            section_id = m.get("process_section_id", "")
            if not section_id or section_id not in valid_chunk_ids:
                log.warning("mapper_unknown_section_id", section_id=section_id)
                continue
            results.append(
                ProcessMapping(
                    mapping_id=new_ulid(),
                    change_id=change.change_id,
                    process_id=m.get("process_id", "unknown"),
                    process_section_id=section_id,
                    impact_type=impact,
                    confidence=confidence,
                    rationale=m.get("rationale", ""),
                    citation_quote=m.get("citation_quote", ""),
                    prompt_version=version_str,
                    model=model,
                    generated_at=datetime.now(timezone.utc),
                )
            )

        return results

    def _retrieve(self, query: str) -> list[dict]:
        """Query Chroma for the top-K relevant process chunks."""
        try:
            n = self._cfg.top_k
            results = self._collection.query(query_texts=[query], n_results=n)
            chunks = []
            for doc_id, document, meta in zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
            ):
                chunks.append({"id": doc_id, "document": document, "meta": meta})
            return chunks
        except Exception as exc:
            log.error("mapper_retrieval_error", error=str(exc))
            return []

    def _build_prompt(self, summary: Summary, chunks: list[dict]) -> str:
        template = self._registry.load("map", self._prompt_version)
        fenced_summary = fence(summary.text)
        chunks_block = "\n\n".join(
            f"[CHUNK {c['id']}]\n{c['document']}" for c in chunks
        )
        return (
            template
            .replace("{{SUMMARY}}", fenced_summary)
            .replace("{{PROCESS_CHUNKS}}", chunks_block)
        )


def _parse_mappings(raw: str) -> list[dict]:
    """Parse LLM JSON; return list of mapping dicts or empty list on failure."""
    try:
        data = json.loads(raw)
        mappings = data.get("mappings", [])
        return mappings if isinstance(mappings, list) else []
    except (json.JSONDecodeError, AttributeError):
        return []


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
