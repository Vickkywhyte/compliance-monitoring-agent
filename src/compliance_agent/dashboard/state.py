"""Session-state helpers and SQLite connection factory for the dashboard."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st

from compliance_agent.config.loader import get_settings, load_agent_config
from compliance_agent.storage.db import get_connection, migrate


@st.cache_resource
def get_db_connection() -> sqlite3.Connection:
    """Return a cached, migrated SQLite connection.

    Uses @st.cache_resource so the connection is shared across reruns
    within the same server process.
    """
    settings = get_settings()
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    migrate(conn)
    return conn


def init_session_state() -> None:
    """Initialise all required session-state keys with safe defaults."""
    defaults: dict[str, Any] = {
        "selected_change_id": None,
        "selected_proposal_id": None,
        "session_role": "officer",
        "actor_id": "dashboard_user",
        "feed_page": 0,
        "queue_page": 0,
        "return_to": "feed",  # "feed" or "queue" — for the back button in change_detail
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def get_config_summary() -> dict[str, Any]:
    """Return a lightweight summary of the active configuration for the sidebar."""
    try:
        settings = get_settings()
        cfg = load_agent_config()
        return {
            "database": settings.database_path,
            "environment": settings.environment,
            "llm_model": cfg.llm.primary_model,
            "log_level": settings.log_level,
        }
    except Exception:
        return {"error": "config unavailable"}
