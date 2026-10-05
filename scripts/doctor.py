"""Dependency and import health check (Lesson 1: make doctor).

Imports every public module in src/compliance_agent.
Reports missing packages by name and exits non-zero on any failure.
"""
from __future__ import annotations

import importlib
import sys

PUBLIC_MODULES = [
    "compliance_agent",
    "compliance_agent.exceptions",
    "compliance_agent.config",
    "compliance_agent.config.loader",
    "compliance_agent.config.models",
    "compliance_agent.utils",
    "compliance_agent.utils.logging",
    "compliance_agent.utils.ids",
    "compliance_agent.utils.ratelimit",
    "compliance_agent.storage",
    "compliance_agent.storage.db",
    "compliance_agent.storage.models",
    "compliance_agent.storage.audit",
    "compliance_agent.storage.documents",
    "compliance_agent.sources",
    "compliance_agent.sources.base",
    "compliance_agent.sources.eurlex",
    "compliance_agent.sources.sanctions",
    "compliance_agent.sources.eba",
    "compliance_agent.sources.registry",
    "compliance_agent.ingestion",
    "compliance_agent.ingestion.fetch",
    "compliance_agent.ingestion.normalize",
    "compliance_agent.ingestion.orchestrator",
    "compliance_agent.detection",
    "compliance_agent.detection.stable_id",
    "compliance_agent.detection.diff",
    "compliance_agent.detection.detector",
    "compliance_agent.storage.changes",
    "compliance_agent.storage.summaries",
    "compliance_agent.storage.mappings",
    "compliance_agent.llm",
    "compliance_agent.llm.backends",
    "compliance_agent.llm.gateway",
    "compliance_agent.llm.openrouter",
    "compliance_agent.llm.ollama",
    "compliance_agent.llm.prompts",
    "compliance_agent.intelligence",
    "compliance_agent.intelligence.fencing",
    "compliance_agent.intelligence.kb",
    "compliance_agent.intelligence.summarizer",
    "compliance_agent.intelligence.mapper",
    "compliance_agent.intelligence.proposer",
    "compliance_agent.routing",
    "compliance_agent.routing.rules",
    "compliance_agent.routing.router",
    "compliance_agent.approval",
    "compliance_agent.approval.service",
    "compliance_agent.approval.state",
    "compliance_agent.audit",
    "compliance_agent.audit.recorder",
    "compliance_agent.audit.exporter",
    "compliance_agent.storage.proposals",
    "compliance_agent.storage.approvals",
    "compliance_agent.dashboard",
    "compliance_agent.dashboard.theme",
    "compliance_agent.dashboard.state",
    "compliance_agent.dashboard.app",
    "compliance_agent.dashboard.charts",
    "compliance_agent.dashboard.components",
    "compliance_agent.dashboard.components.severity_badge",
    "compliance_agent.dashboard.components.citation",
    "compliance_agent.dashboard.components.evidence_list",
    "compliance_agent.dashboard.components.header",
    "compliance_agent.dashboard.views",
    "compliance_agent.dashboard.views.feed",
    "compliance_agent.dashboard.views.queue",
    "compliance_agent.dashboard.views.change_detail",
    "compliance_agent.dashboard.views.audit_trail",
    "compliance_agent.dashboard.views.digest",
    # Phase 7: evaluation harness
    "compliance_agent.evaluation",
    "compliance_agent.evaluation.metrics",
    "compliance_agent.evaluation.metrics.base",
    "compliance_agent.evaluation.metrics.coverage",
    "compliance_agent.evaluation.metrics.mapping",
    "compliance_agent.evaluation.metrics.proposal",
    "compliance_agent.evaluation.metrics.routing",
    "compliance_agent.evaluation.metrics.operational",
    "compliance_agent.evaluation.metrics.summary",
    "compliance_agent.evaluation.stats",
    "compliance_agent.evaluation.judge",
    "compliance_agent.evaluation.golden",
    "compliance_agent.evaluation.runner",
    "compliance_agent.evaluation.report",
]


def main() -> int:
    """Import all public modules and report failures. Returns exit code."""
    failures: list[tuple[str, str]] = []

    print("Running doctor checks...")
    for module in PUBLIC_MODULES:
        try:
            importlib.import_module(module)
            print(f"  OK  {module}")
        except ModuleNotFoundError as exc:
            missing_pkg = exc.name or str(exc)
            print(f"  FAIL {module} — missing package: {missing_pkg}", file=sys.stderr)
            failures.append((module, missing_pkg))
        except Exception as exc:
            print(f"  FAIL {module} — {type(exc).__name__}: {exc}", file=sys.stderr)
            failures.append((module, str(exc)))

    if failures:
        print(f"\ndoctor: {len(failures)} failure(s):", file=sys.stderr)
        for mod, reason in failures:
            print(f"  {mod}: {reason}", file=sys.stderr)
        return 1

    print(f"\ndoctor: all {len(PUBLIC_MODULES)} imports OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
