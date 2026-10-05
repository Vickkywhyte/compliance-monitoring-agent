"""Statistical utilities — bootstrap confidence intervals (06_EVAL_SPEC.md §8)."""
from __future__ import annotations

import numpy as np


def bootstrap_ci(
    values: list[float] | np.ndarray,
    n_samples: int = 1000,
    seed: int = 0,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Compute a bootstrap confidence interval for the mean of *values*.

    Parameters
    ----------
    values:
        Observed metric scores (list or numpy array).
    n_samples:
        Number of bootstrap resamples. Default 1,000 (§8).
    seed:
        Fixed RNG seed for deterministic output (§8).
    confidence:
        Interval width. Default 0.95 (95%).

    Returns
    -------
    (lower, upper):
        Percentile-based confidence interval.

    Raises
    ------
    ValueError:
        When *values* is empty.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("bootstrap_ci requires at least one value")

    rng = np.random.default_rng(seed)
    means = np.array([
        rng.choice(arr, size=len(arr), replace=True).mean()
        for _ in range(n_samples)
    ])
    alpha = (1.0 - confidence) / 2.0
    lower = float(np.percentile(means, 100 * alpha))
    upper = float(np.percentile(means, 100 * (1.0 - alpha)))
    return lower, upper
