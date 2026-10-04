"""Configuration loader — the ONLY module that calls os.getenv.

All other modules obtain runtime settings by importing from here.
This enforces Lesson 8: one config source per concern.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

from compliance_agent.exceptions import ConfigError

from .models import AgentConfig, AppSettings, EvalConfig, RoutingConfig, SourcesConfig

# Load .env file once at import time (safe to call repeatedly)
load_dotenv()


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return application settings loaded from environment variables.

    Cached after first call — call get_settings.cache_clear() in tests.
    """
    try:
        return AppSettings(
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            database_path=os.getenv("DATABASE_PATH", "data/compliance.db"),
            log_dir=os.getenv("LOG_DIR", "logs"),
            config_dir=os.getenv("CONFIG_DIR", "configs"),
            environment=os.getenv("ENVIRONMENT", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
    except Exception as exc:
        raise ConfigError(f"Failed to load application settings: {exc}") from exc


def get_secret_env_values() -> list[str]:
    """Return the values of env vars whose names contain KEY, TOKEN, or SECRET.

    Called by utils/logging.py's secret scrubber to redact live secrets from
    log output. This is the only place os.environ is iterated (Lesson 8).
    """
    return [
        val
        for key, val in os.environ.items()
        if val and any(marker in key.upper() for marker in ("KEY", "TOKEN", "SECRET"))
    ]


def _load_yaml(path: Path) -> dict:
    """Load and parse a YAML file, raising ConfigError on failure."""
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parse error in {path}: {exc}") from exc


def _config_dir() -> Path:
    """Resolve config directory from settings."""
    return Path(get_settings().config_dir)


def load_sources_config(config_dir: Path | None = None) -> SourcesConfig:
    """Load and validate configs/sources.yaml."""
    path = (config_dir or _config_dir()) / "sources.yaml"
    data = _load_yaml(path)
    try:
        return SourcesConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Invalid sources.yaml: {exc}") from exc


def load_agent_config(config_dir: Path | None = None) -> AgentConfig:
    """Load and validate configs/agent.yaml."""
    path = (config_dir or _config_dir()) / "agent.yaml"
    data = _load_yaml(path)
    try:
        return AgentConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Invalid agent.yaml: {exc}") from exc


def load_routing_config(config_dir: Path | None = None) -> RoutingConfig:
    """Load and validate configs/routing.yaml."""
    path = (config_dir or _config_dir()) / "routing.yaml"
    data = _load_yaml(path)
    try:
        return RoutingConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Invalid routing.yaml: {exc}") from exc


def load_eval_config(config_dir: Path | None = None) -> EvalConfig:
    """Load and validate configs/eval.yaml."""
    path = (config_dir or _config_dir()) / "eval.yaml"
    data = _load_yaml(path)
    try:
        return EvalConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Invalid eval.yaml: {exc}") from exc


if __name__ == "__main__":
    print("=== config/loader self-test ===")
    s = get_settings()
    print(f"  environment : {s.environment}")
    print(f"  config_dir  : {s.config_dir}")
    print(f"  database    : {s.database_path}")

    for name, loader in [
        ("sources.yaml", load_sources_config),
        ("agent.yaml", load_agent_config),
        ("routing.yaml", load_routing_config),
        ("eval.yaml", load_eval_config),
    ]:
        try:
            loader()
            print(f"  {name}: OK")
        except ConfigError as exc:
            print(f"  {name}: FAIL — {exc}")

    print("PASS")
