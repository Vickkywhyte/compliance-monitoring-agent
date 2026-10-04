"""Tests for configuration loading and validation (Phase 1)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from compliance_agent.config.loader import (
    get_settings,
    load_agent_config,
    load_eval_config,
    load_routing_config,
    load_sources_config,
)
from compliance_agent.config.models import AppSettings
from compliance_agent.exceptions import ConfigError


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear the lru_cache on get_settings before each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── AppSettings ──────────────────────────────────────────────────────────────


def test_settings_defaults(monkeypatch):
    """Settings load with documented defaults when env vars are absent."""
    for key in ("OPENROUTER_API_KEY", "DATABASE_PATH", "LOG_DIR", "ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)

    settings = get_settings()
    assert settings.environment == "development"
    assert settings.database_path == "data/compliance.db"
    assert settings.log_dir == "logs"


def test_settings_from_env(monkeypatch):
    """Settings read values from environment variables."""
    monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
    monkeypatch.setenv("ENVIRONMENT", "production")

    settings = get_settings()
    assert settings.database_path == "/tmp/test.db"
    assert settings.environment == "production"


def test_settings_extra_field_forbidden():
    """AppSettings rejects unknown fields (extra='forbid')."""
    with pytest.raises(Exception):
        AppSettings(unknown_field="oops")


# ── YAML config loading ───────────────────────────────────────────────────────


CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_load_sources_config():
    """sources.yaml loads and validates to SourcesConfig."""
    cfg = load_sources_config(CONFIGS_DIR)
    assert len(cfg.sources) >= 1
    assert all(s.type in ("eurlex", "sanctions", "eba") for s in cfg.sources)


def test_load_agent_config():
    """agent.yaml loads and validates to AgentConfig."""
    cfg = load_agent_config(CONFIGS_DIR)
    assert cfg.llm.temperature == 0.0
    assert cfg.gateway.max_concurrent == 4
    assert cfg.summarizer.max_words == 200


def test_load_routing_config():
    """routing.yaml loads and validates to RoutingConfig."""
    cfg = load_routing_config(CONFIGS_DIR)
    assert len(cfg.rules) >= 1
    priorities = [r.priority for r in cfg.rules]
    assert sorted(priorities) == priorities  # rules are in priority order


def test_load_eval_config():
    """eval.yaml loads and validates to EvalConfig."""
    cfg = load_eval_config(CONFIGS_DIR)
    assert cfg.seed == 0
    assert cfg.bootstrap_samples == 1000
    assert "detection_recall" in cfg.metrics.coverage


def test_malformed_config_raises_config_error(tmp_path):
    """A deliberately malformed YAML config raises ConfigError."""
    bad_yaml = tmp_path / "agent.yaml"
    bad_yaml.write_text("llm:\n  unknown_field: oops\n  primary_model: x\n  fallback_model: y\n")

    with pytest.raises(ConfigError):
        load_agent_config(tmp_path)


def test_missing_config_file_raises_config_error(tmp_path):
    """A missing config file raises ConfigError."""
    with pytest.raises(ConfigError, match="not found"):
        load_sources_config(tmp_path)
