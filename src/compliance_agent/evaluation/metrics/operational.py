"""Operational metrics — latency, cost, fallback, audit (06_EVAL_SPEC.md §6)."""
from __future__ import annotations

from typing import Literal

import numpy as np

from compliance_agent.evaluation.metrics.base import Metric


class E2ELatencyP50(Metric):
    """Median end-to-end latency in milliseconds (§6).

    actual_output keys: {"latency_ms": float}
    """

    @property
    def name(self) -> str:
        return "e2e_latency_p50_ms"

    @property
    def direction(self) -> Literal["higher_better", "lower_better"]:
        return "lower_better"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return float(actual_output.get("latency_ms", 0.0))

    def compute_batch(
        self,
        golden_entries: list[dict],
        actual_outputs: list[dict],
    ) -> float:
        values = [float(a.get("latency_ms", 0.0)) for a in actual_outputs]
        return float(np.percentile(values, 50)) if values else 0.0


class E2ELatencyP95(Metric):
    """95th-percentile end-to-end latency in milliseconds (§6).

    actual_output keys: {"latency_ms": float}
    """

    @property
    def name(self) -> str:
        return "e2e_latency_p95_ms"

    @property
    def direction(self) -> Literal["higher_better", "lower_better"]:
        return "lower_better"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return float(actual_output.get("latency_ms", 0.0))

    def compute_batch(
        self,
        golden_entries: list[dict],
        actual_outputs: list[dict],
    ) -> float:
        values = [float(a.get("latency_ms", 0.0)) for a in actual_outputs]
        return float(np.percentile(values, 95)) if values else 0.0


class CostPer1kChanges(Metric):
    """Extrapolated LLM cost per 1,000 changes in USD (§6).

    actual_output keys: {"cost_usd": float}
    """

    @property
    def name(self) -> str:
        return "cost_per_1k_changes_usd"

    @property
    def direction(self) -> Literal["higher_better", "lower_better"]:
        return "lower_better"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return float(actual_output.get("cost_usd", 0.0))

    def compute_batch(
        self,
        golden_entries: list[dict],
        actual_outputs: list[dict],
    ) -> float:
        if not actual_outputs:
            return 0.0
        total_cost = sum(float(a.get("cost_usd", 0.0)) for a in actual_outputs)
        n = len(actual_outputs)
        return (total_cost / n) * 1000 if n > 0 else 0.0


class LLMFallbackRate(Metric):
    """Fraction of LLM calls falling back to Ollama (§6).

    actual_output keys: {"llm_calls": int, "fallback_calls": int}
    """

    @property
    def name(self) -> str:
        return "llm_fallback_rate"

    @property
    def direction(self) -> Literal["higher_better", "lower_better"]:
        return "lower_better"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        total = int(actual_output.get("llm_calls", 0))
        fallback = int(actual_output.get("fallback_calls", 0))
        return fallback / total if total > 0 else 0.0

    def compute_batch(
        self,
        golden_entries: list[dict],
        actual_outputs: list[dict],
    ) -> float:
        total = sum(int(a.get("llm_calls", 0)) for a in actual_outputs)
        fallback = sum(int(a.get("fallback_calls", 0)) for a in actual_outputs)
        return fallback / total if total > 0 else 0.0


class AuditCompleteness(Metric):
    """Fraction of proposals with a complete audit chain (§6).

    actual_output keys: {"audit_complete": bool}
    """

    @property
    def name(self) -> str:
        return "audit_completeness"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return 1.0 if actual_output.get("audit_complete", False) else 0.0


class ApprovalBypassRate(Metric):
    """Fraction of proposals executed without approval — must be 0.00 (§6).

    actual_output keys: {"bypassed": bool}
    """

    @property
    def name(self) -> str:
        return "approval_bypass_rate"

    @property
    def direction(self) -> Literal["higher_better", "lower_better"]:
        return "lower_better"

    def compute(self, golden_entry: dict, actual_output: dict) -> float:
        return 1.0 if actual_output.get("bypassed", False) else 0.0
