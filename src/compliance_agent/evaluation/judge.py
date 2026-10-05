"""LLM judge for summary evaluation — entailment and rubric scoring (06_EVAL_SPEC.md §4.1, §4.6).

Reuses LLMGateway from Phase 4 and fence() for security (C-01/C-02).
All judge calls are cached by hash(prompt + model + version + inputs).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import structlog

from compliance_agent.exceptions import LLMError, ValidationError
from compliance_agent.intelligence.fencing import fence
from compliance_agent.llm.gateway import LLMGateway
from compliance_agent.llm.prompts import PromptRegistry

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "judge_prompts"
_PROMPT_VERSION = 1


class EvalJudge:
    """LLM judge for claim entailment and rubric scoring.

    Caches responses by a deterministic key to avoid re-running identical
    evaluations across multiple eval runs (ADR-015).
    """

    def __init__(
        self,
        gateway: LLMGateway,
        cache_dir: Path | None = None,
        prompt_version: int = _PROMPT_VERSION,
    ) -> None:
        self._gateway = gateway
        self._registry = PromptRegistry(
            _PROMPTS_DIR,
            cache_dir=cache_dir or Path("data/cache/llm"),
        )
        self._prompt_version = prompt_version

    def entailment(
        self,
        claim: str,
        source_content: str,
    ) -> Literal["yes", "partial", "no"]:
        """Return whether *claim* is entailed by *source_content*.

        Fences *source_content* before injection (C-01/C-02).
        """
        template = self._registry.load("entailment", version=self._prompt_version)
        prompt = (
            template
            .replace("{{CLAIM}}", claim)
            .replace("{{SOURCE_CONTENT}}", fence(source_content))
        )
        model_name = _gateway_model(self._gateway)
        cache_key = self._registry.cache_key(
            prompt, model_name, f"entailment_v{self._prompt_version}"
        )
        cached = self._registry.read_cache(cache_key)
        if cached:
            try:
                return _parse_verdict(cached)
            except (ValueError, KeyError):
                pass

        try:
            resp = self._gateway.complete(prompt)
            self._registry.write_cache(cache_key, resp.text)
            log.debug(
                "judge_entailment",
                prompt_version=self._prompt_version,
                model=resp.model,
            )
            return _parse_verdict(resp.text)
        except LLMError as exc:
            log.warning("judge_entailment_llm_error", error=str(exc))
            return "no"

    def rubric(
        self,
        summary_text: str,
        rubric: str,
        source_content: str,
    ) -> int:
        """Return a rubric score 1–5 for *summary_text* against *rubric*.

        Fences *source_content* before injection (C-01/C-02).
        """
        template = self._registry.load("rubric", version=self._prompt_version)
        prompt = (
            template
            .replace("{{SUMMARY}}", summary_text)
            .replace("{{RUBRIC}}", rubric)
            .replace("{{SOURCE_CONTENT}}", fence(source_content))
        )
        model_name = _gateway_model(self._gateway)
        cache_key = self._registry.cache_key(
            prompt, model_name, f"rubric_v{self._prompt_version}"
        )
        cached = self._registry.read_cache(cache_key)
        if cached:
            try:
                return _parse_score(cached)
            except (ValueError, KeyError):
                pass

        try:
            resp = self._gateway.complete(prompt)
            self._registry.write_cache(cache_key, resp.text)
            log.debug(
                "judge_rubric",
                prompt_version=self._prompt_version,
                model=resp.model,
            )
            return _parse_score(resp.text)
        except LLMError as exc:
            log.warning("judge_rubric_llm_error", error=str(exc))
            return 1


def _gateway_model(gateway: LLMGateway) -> str:
    """Best-effort model name from gateway config."""
    try:
        return gateway._llm_config.primary_model  # type: ignore[attr-defined]
    except AttributeError:
        return "unknown"


def _parse_verdict(text: str) -> Literal["yes", "partial", "no"]:
    """Parse {"verdict": "yes"|"partial"|"no"} from *text*."""
    data = json.loads(text)
    verdict = data["verdict"]
    if verdict not in ("yes", "partial", "no"):
        raise ValueError(f"Invalid verdict: {verdict!r}")
    return verdict  # type: ignore[return-value]


def _parse_score(text: str) -> int:
    """Parse {"score": 1-5} from *text*."""
    data = json.loads(text)
    score = int(data["score"])
    if not 1 <= score <= 5:
        raise ValueError(f"Score out of range: {score}")
    return score
