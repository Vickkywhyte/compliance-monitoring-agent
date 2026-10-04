"""Tests for the structured logging subsystem (Lesson 5: every write has a read-back)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def log_dir(tmp_path):
    """Provide a fresh temporary log directory for each test."""
    return tmp_path / "logs"


def _fresh_configure(log_dir: Path):
    """Configure logging with a fresh state (resets the _configured guard)."""
    import compliance_agent.utils.logging as log_mod

    # Reset the module-level guard so configure_logging() runs fresh
    log_mod._configured = False
    # Also clear structlog's cache to avoid processor chain conflicts
    import structlog
    structlog.reset_defaults()

    log_mod.configure_logging(log_dir=str(log_dir))
    return log_mod


def test_configure_logging_creates_log_file(log_dir):
    """configure_logging() creates logs/app.jsonl on first log write."""
    log_mod = _fresh_configure(log_dir)
    logger = log_mod.get_logger("test.create")
    logger.info("probe_event", marker="create_test")

    log_file = log_dir / "app.jsonl"
    assert log_file.exists(), "app.jsonl was not created"


def test_log_event_is_valid_json(log_dir):
    """Emitted log events are valid JSON lines (Lesson 5 read-back)."""
    log_mod = _fresh_configure(log_dir)
    logger = log_mod.get_logger("test.json")
    logger.info("json_check_event", payload="hello")

    log_file = log_dir / "app.jsonl"
    lines = [l for l in log_file.read_text().splitlines() if l.strip()]
    assert lines, "log file is empty after writing"

    for line in lines:
        event = json.loads(line)  # raises if not valid JSON
        assert isinstance(event, dict)


def test_log_event_contains_expected_fields(log_dir):
    """Log events include event, level, and timestamp fields."""
    log_mod = _fresh_configure(log_dir)
    logger = log_mod.get_logger("test.fields")
    logger.info("field_check_event", custom_key="custom_val")

    log_file = log_dir / "app.jsonl"
    lines = [l for l in log_file.read_text().splitlines() if l.strip()]
    events = [json.loads(l) for l in lines]

    matching = [e for e in events if e.get("event") == "field_check_event"]
    assert matching, "event not found in log file"
    event = matching[-1]
    assert "level" in event, "event missing 'level' field"
    assert "timestamp" in event, "event missing 'timestamp' field"
    assert event.get("custom_key") == "custom_val"


def test_env_key_secret_scrubbed_via_loader(log_dir, monkeypatch):
    """Env var values (via get_secret_env_values) are redacted in log output (Lesson 8)."""
    import os
    monkeypatch.setenv("MY_TEST_KEY", "sk-test-1234")

    log_mod = _fresh_configure(log_dir)
    log_mod.get_logger("test.lesson8").info("secret_test", val="sk-test-1234")

    raw_text = (log_dir / "app.jsonl").read_text()
    assert "sk-test-1234" not in raw_text, "secret must not appear in log file"
    assert "[REDACTED]" in raw_text, "[REDACTED] marker must appear"


def test_idempotent_configure(log_dir):
    """Calling configure_logging() twice does not double-add handlers."""
    log_mod = _fresh_configure(log_dir)
    import logging as stdlib_logging
    handler_count_before = len(stdlib_logging.getLogger().handlers)
    # Second call should be a no-op
    log_mod.configure_logging(log_dir=str(log_dir))
    handler_count_after = len(stdlib_logging.getLogger().handlers)
    assert handler_count_after == handler_count_before
