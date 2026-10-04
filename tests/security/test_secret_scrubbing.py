"""Secret scrubbing tests (C-06, C-07, C-08).

Verifies that secrets logged via structlog do NOT appear in logs/app.jsonl
and are replaced with [REDACTED].
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def log_dir(tmp_path):
    return tmp_path / "logs"


def _fresh_configure(log_dir: Path):
    import structlog
    import compliance_agent.utils.logging as log_mod

    log_mod._configured = False
    structlog.reset_defaults()
    log_mod.configure_logging(log_dir=str(log_dir))
    return log_mod


def _read_events(log_dir: Path) -> list[dict]:
    log_file = log_dir / "app.jsonl"
    if not log_file.exists():
        return []
    return [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]


# ── OpenRouter / Anthropic key patterns ─────────────────────────────────────


def test_openrouter_key_redacted(log_dir):
    """sk-or-* keys are redacted from log output."""
    fake_key = "sk-or-v1-abc123def456ghi789jkl012mno345pqr678stu901"  # pragma: allowlist secret
    log_mod = _fresh_configure(log_dir)
    log_mod.get_logger("sec.test").info("key_leak_test", api_key=fake_key)

    events = _read_events(log_dir)
    raw_text = (log_dir / "app.jsonl").read_text()
    assert fake_key not in raw_text, "raw key must not appear in log file"
    assert "[REDACTED]" in raw_text, "[REDACTED] marker must appear"


def test_anthropic_key_redacted(log_dir):
    """sk-ant-* keys are redacted from log output."""
    fake_key = "sk-ant-api03-abc123def456"
    log_mod = _fresh_configure(log_dir)
    log_mod.get_logger("sec.test").info("anthropic_key", value=fake_key)

    raw_text = (log_dir / "app.jsonl").read_text()
    assert fake_key not in raw_text
    assert "[REDACTED]" in raw_text


def test_bearer_token_redacted(log_dir):
    """Bearer tokens are redacted from log output."""
    fake_token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake.token"
    log_mod = _fresh_configure(log_dir)
    log_mod.get_logger("sec.test").info("bearer_test", auth_header=fake_token)

    raw_text = (log_dir / "app.jsonl").read_text()
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake.token" not in raw_text
    assert "[REDACTED]" in raw_text


def test_generic_sk_key_redacted(log_dir):
    """sk-* keys (generic) are redacted from log output."""
    fake_key = "sk-proj-abcdefghijklmnop1234567890"  # pragma: allowlist secret
    log_mod = _fresh_configure(log_dir)
    log_mod.get_logger("sec.test").info("generic_sk", token=fake_key)

    raw_text = (log_dir / "app.jsonl").read_text()
    assert fake_key not in raw_text
    assert "[REDACTED]" in raw_text


def test_env_var_secret_redacted(log_dir, monkeypatch):
    """Values of env vars with KEY/TOKEN/SECRET in the name are redacted."""
    secret_val = "super-secret-value-xyz789"  # pragma: allowlist secret
    monkeypatch.setenv("MY_API_KEY", secret_val)

    log_mod = _fresh_configure(log_dir)
    log_mod.get_logger("sec.test").info("env_secret", msg=f"using {secret_val}")

    raw_text = (log_dir / "app.jsonl").read_text()
    assert secret_val not in raw_text
    assert "[REDACTED]" in raw_text


def test_safe_value_not_redacted(log_dir):
    """Non-secret values pass through the scrubber unchanged."""
    safe_value = "ordinary log message without secrets"
    log_mod = _fresh_configure(log_dir)
    log_mod.get_logger("sec.test").info("safe_event", msg=safe_value)

    raw_text = (log_dir / "app.jsonl").read_text()
    assert safe_value in raw_text
