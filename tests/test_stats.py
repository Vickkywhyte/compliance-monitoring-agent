"""Unit tests for bootstrap_ci in evaluation.stats (Phase 7)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from compliance_agent.evaluation.stats import bootstrap_ci


def test_empty_raises():
    with pytest.raises(ValueError, match="at least one value"):
        bootstrap_ci([])


def test_single_value_returns_value():
    lo, hi = bootstrap_ci([0.8])
    assert lo == pytest.approx(0.8)
    assert hi == pytest.approx(0.8)


def test_identical_values_tight_ci():
    lo, hi = bootstrap_ci([0.5] * 20)
    assert lo == pytest.approx(0.5)
    assert hi == pytest.approx(0.5)


def test_ci_ordering():
    values = [0.1, 0.9, 0.5, 0.3, 0.7]
    lo, hi = bootstrap_ci(values)
    assert lo <= hi


def test_ci_contains_mean():
    values = list(np.linspace(0.0, 1.0, 50))
    lo, hi = bootstrap_ci(values)
    mean = sum(values) / len(values)
    assert lo <= mean <= hi


def test_reproducible_with_seed():
    values = [0.1, 0.4, 0.6, 0.8, 0.9]
    lo1, hi1 = bootstrap_ci(values, seed=42)
    lo2, hi2 = bootstrap_ci(values, seed=42)
    assert lo1 == lo2
    assert hi1 == hi2
