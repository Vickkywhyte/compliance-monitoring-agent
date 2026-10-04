"""Source registry — maps config type strings to Source implementations.

Any new source adapter must be registered here. The orchestrator
calls build_sources() to instantiate all enabled sources.
"""
from __future__ import annotations

from typing import Any

from compliance_agent.config.models import SourceConfig
from compliance_agent.exceptions import ConfigError
from compliance_agent.sources.base import Source
from compliance_agent.sources.eba import EBASource
from compliance_agent.sources.eurlex import EurLexSource
from compliance_agent.sources.sanctions import SanctionsSource

_REGISTRY: dict[str, type[Source]] = {
    "eurlex": EurLexSource,
    "sanctions": SanctionsSource,
    "eba": EBASource,
}


def build_sources(
    configs: list[SourceConfig],
    fetcher: Any,
    *,
    enabled_only: bool = True,
) -> list[Source]:
    """Instantiate Source adapters from a list of SourceConfig entries.

    Raises ConfigError for unknown source type strings.
    """
    sources: list[Source] = []
    for cfg in configs:
        if enabled_only and not cfg.enabled:
            continue
        cls = _REGISTRY.get(cfg.type)
        if cls is None:
            raise ConfigError(
                f"Unknown source type: {cfg.type!r}. "
                f"Registered types: {sorted(_REGISTRY)}"
            )
        sources.append(cls(cfg, fetcher))
    return sources


if __name__ == "__main__":
    print("Source registry self-test")
    from compliance_agent.config.models import SourceConfig as SC

    dummy_cfgs = [
        SC(name="test_eurlex", type="eurlex", url="http://x", schedule_cron="0 0 * * *"),
        SC(name="test_sanctions", type="sanctions", url="http://x", schedule_cron="0 0 * * *"),
        SC(name="test_eba", type="eba", url="http://x", schedule_cron="0 0 * * *"),
    ]
    result = build_sources(dummy_cfgs, fetcher=None)
    assert len(result) == 3
    types = [s.source_type for s in result]
    assert set(types) == {"eurlex", "sanctions", "eba"}, types
    print(f"PASS — {len(result)} sources instantiated: {types}")
