"""Structured logging configuration (C-06, C-07 — secret scrubbing at config level).

Writes JSON to stdout AND logs/app.jsonl (rotating 10 MB × 5 files).
The secret scrubber processor is wired into the shared processor chain so
every event is scrubbed before it reaches any handler.

Exports:
    configure_logging(log_dir) — call once at application startup
    get_logger(name)           — returns a structlog BoundLogger
"""
from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from pathlib import Path

import structlog

from compliance_agent.config.loader import get_secret_env_values

# Patterns for known secret formats (C-06)
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-ant-[A-Za-z0-9\-_]+"),
    re.compile(r"sk-or-[A-Za-z0-9\-_]+"),
    re.compile(r"sk-[A-Za-z0-9\-_]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/]+=*"),
]

_REDACTED = "[REDACTED]"

# Tracks whether configure_logging() has already run
_configured = False


def _scrub_string(value: str) -> str:
    """Replace secret patterns with [REDACTED] in a single string."""
    # Scrub env var values whose key names contain KEY, TOKEN, or SECRET.
    # The config loader (Lesson 8) supplies these values via get_secret_env_values().
    for env_val in get_secret_env_values():
        if env_val in value:
            value = value.replace(env_val, _REDACTED)

    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(_REDACTED, value)

    return value


def _secret_scrubber(
    logger: object,  # noqa: ARG001
    method: str,  # noqa: ARG001
    event_dict: dict,
) -> dict:
    """Structlog processor that redacts secrets from all string fields (C-07)."""
    for key in list(event_dict.keys()):
        val = event_dict[key]
        if isinstance(val, str):
            event_dict[key] = _scrub_string(val)
        elif isinstance(val, dict):
            event_dict[key] = {
                k: _scrub_string(v) if isinstance(v, str) else v for k, v in val.items()
            }
    return event_dict


def configure_logging(log_dir: str | Path = "logs") -> None:
    """Configure structlog with JSON output to stdout and a rotating file.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _configured  # noqa: PLW0603
    if _configured:
        return
    _configured = True

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _secret_scrubber,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path / "app.jsonl"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(file_handler)
    root.addHandler(stdout_handler)
    root.setLevel(logging.DEBUG)

    # Suppress noisy third-party loggers
    for noisy_logger in ("httpx", "httpcore", "kaleido"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger bound to the stdlib factory."""
    return structlog.get_logger(name)


if __name__ == "__main__":
    import json
    import tempfile

    print("=== utils/logging self-test ===")

    with tempfile.TemporaryDirectory() as tmp:
        configure_logging(log_dir=tmp)
        logger = get_logger("selftest")
        logger.info("selftest_event", payload="hello")

        log_file = Path(tmp) / "app.jsonl"
        assert log_file.exists(), "log file not created"
        lines = log_file.read_text().splitlines()
        assert lines, "log file is empty"
        event = json.loads(lines[-1])
        assert event.get("event") == "selftest_event", f"unexpected event: {event}"

    print("PASS")
