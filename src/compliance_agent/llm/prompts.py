"""Prompt versioning and LLM response caching (ADR-015).

Prompt files live in intelligence/prompts/{name}_v{N}.txt.
Cache files live in data/cache/llm/{sha256}.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import structlog

from compliance_agent.exceptions import ConfigError

log = structlog.get_logger(__name__)

_DEFAULT_CACHE_DIR = Path("data/cache/llm")


class PromptRegistry:
    """Load versioned prompt templates and cache LLM responses to disk."""

    def __init__(
        self,
        prompts_dir: Path,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
    ) -> None:
        self._dir = prompts_dir
        self._cache_dir = cache_dir

    def load(self, name: str, version: int = 1) -> str:
        """Return the text of {name}_v{version}.txt from the prompts directory."""
        path = self._dir / f"{name}_v{version}.txt"
        if not path.exists():
            raise ConfigError(f"Prompt template not found: {path}")
        return path.read_text(encoding="utf-8")

    def cache_key(self, prompt_text: str, model: str, version: str) -> str:
        """Deterministic cache key for a (prompt, model, version) triple."""
        raw = f"{prompt_text}\x00{model}\x00{version}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def read_cache(self, key: str) -> str | None:
        """Return cached LLM response text, or None on miss/error."""
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("text")
        except Exception:
            return None

    def write_cache(self, key: str, text: str) -> None:
        """Persist LLM response text to the disk cache."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / f"{key}.json"
        path.write_text(json.dumps({"text": text}), encoding="utf-8")
        log.debug("llm_cache_hit_write", key=key[:16])
