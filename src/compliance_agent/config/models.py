"""Pydantic v2 models for all YAML config schemas (05_DATA_SPEC §5).

Config models use extra="forbid" so unknown keys raise at load time.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    """Settings loaded from environment variables via config/loader.py."""

    model_config = {"extra": "forbid"}

    openrouter_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    database_path: str = "data/compliance.db"
    log_dir: str = "logs"
    config_dir: str = "configs"
    environment: str = "development"
    log_level: str = "INFO"


class SourceConfig(BaseModel):
    """Single regulatory source configuration (05_DATA_SPEC §5.1)."""

    model_config = {"extra": "forbid"}

    name: str
    type: str
    url: str
    schedule_cron: str
    enabled: bool = True


class SourcesConfig(BaseModel):
    """Top-level wrapper for configs/sources.yaml."""

    model_config = {"extra": "forbid"}

    sources: list[SourceConfig]
    fixture_mode: bool = False


class LLMConfig(BaseModel):
    """LLM provider settings (05_DATA_SPEC §5.2)."""

    model_config = {"extra": "forbid"}

    primary_model: str
    fallback_model: str
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_seconds: int = 30


class GatewayConfig(BaseModel):
    """LLM gateway concurrency and retry settings (05_DATA_SPEC §5.2)."""

    model_config = {"extra": "forbid"}

    max_concurrent: int = 4
    queue_max_size: int = 100
    backoff_initial_ms: int = 500
    backoff_max_ms: int = 30000
    fallback_after_consecutive_429: int = 3


class SummarizerConfig(BaseModel):
    """Summarizer quality constraints (05_DATA_SPEC §5.2)."""

    model_config = {"extra": "forbid"}

    max_words: int = 200
    min_citations: int = 1
    hallucination_gate: float = 0.05


class MapperConfig(BaseModel):
    """Process mapper retrieval settings (05_DATA_SPEC §5.2)."""

    model_config = {"extra": "forbid"}

    top_k: int = 8
    min_confidence: float = 0.30


class ProposerConfig(BaseModel):
    """Proposal generation limits (05_DATA_SPEC §5.2)."""

    model_config = {"extra": "forbid"}

    max_proposals_per_change: int = 5
    default_deadline_days: int = 30


class AgentConfig(BaseModel):
    """Top-level wrapper for configs/agent.yaml."""

    model_config = {"extra": "forbid"}

    llm: LLMConfig
    gateway: GatewayConfig
    summarizer: SummarizerConfig
    mapper: MapperConfig
    proposer: ProposerConfig


class RoutingCondition(BaseModel):
    """Matching condition for a routing rule."""

    model_config = {"extra": "forbid"}

    severity: str | None = None
    category: str | None = None


class RoutingRule(BaseModel):
    """Single routing rule (05_DATA_SPEC §5.3)."""

    model_config = {"extra": "forbid"}

    priority: int
    when: RoutingCondition
    assign_to: str


class RoutingDefault(BaseModel):
    """Default routing behaviour when no rule matches."""

    model_config = {"extra": "forbid"}

    assign_to: str
    flag_unmatched: bool = True


class RoutingConfig(BaseModel):
    """Top-level wrapper for configs/routing.yaml."""

    model_config = {"extra": "forbid"}

    rules: list[RoutingRule]
    default: RoutingDefault


class MetricsConfig(BaseModel):
    """Metric categories for the evaluation harness (05_DATA_SPEC §5.4)."""

    model_config = {"extra": "forbid"}

    coverage: list[str] = Field(default_factory=list)
    accuracy: list[str] = Field(default_factory=list)
    action_quality: list[str] = Field(default_factory=list)


class EvalConfig(BaseModel):
    """Top-level wrapper for configs/eval.yaml."""

    model_config = {"extra": "forbid"}

    golden_set_path: str
    metrics: MetricsConfig
    bootstrap_samples: int = 1000
    seed: int = 0
