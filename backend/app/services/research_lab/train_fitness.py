from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


TRAIN_FITNESS_SCHEMA = "train-active-robustness-v2"


def _clean(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def _information_ratio(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    std = float(np.std(values, ddof=1))
    mean = float(np.mean(values))
    if std <= 0.0:
        if mean > 0.0:
            return 10.0
        if mean < 0.0:
            return -10.0
        return 0.0
    return mean / std * math.sqrt(252.0)


def _bartlett_long_run_variance(
    values: np.ndarray,
    *,
    max_lag: int | None = None,
) -> tuple[float, int]:
    """Newey-West/Bartlett long-run variance using only Train observations."""
    observations = len(values)
    if observations < 2:
        return 0.0, 0
    lag = (
        min(20, max(1, int(round(4.0 * (observations / 100.0) ** (2.0 / 9.0)))))
        if max_lag is None
        else min(max(0, int(max_lag)), observations - 1)
    )
    demeaned = values - float(np.mean(values))
    variance = float(np.dot(demeaned, demeaned) / observations)
    for offset in range(1, lag + 1):
        covariance = float(
            np.dot(demeaned[offset:], demeaned[:-offset]) / observations
        )
        weight = 1.0 - offset / (lag + 1.0)
        variance += 2.0 * weight * covariance
    return max(0.0, variance), lag


def _dependence_adjusted_t_statistic(values: np.ndarray) -> tuple[float, float, int]:
    if len(values) < 2:
        return 0.0, 0.0, 0
    long_run_variance, lag = _bartlett_long_run_variance(values)
    if long_run_variance <= 0.0:
        mean = float(np.mean(values))
        if mean > 0.0:
            return 10.0, long_run_variance, lag
        if mean < 0.0:
            return -10.0, long_run_variance, lag
        return 0.0, long_run_variance, lag
    statistic = (
        math.sqrt(len(values))
        * float(np.mean(values))
        / math.sqrt(long_run_variance)
    )
    return float(statistic), long_run_variance, lag


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def build_train_active_robustness_proxy(
    daily_excess_returns: Iterable[float],
    *,
    slice_count: int = 6,
    min_observations: int = 120,
) -> dict[str, Any]:
    """Build a Train-only ranking proxy for persistent active performance.

    This is deliberately *not* a promotion gate and must never consume
    Validation or Final Holdout observations. It rewards candidates whose
    active return is persistent through time and whose mean remains credible
    after accounting for serial dependence in Train returns. Independent
    Validation/DSR/PBO/SPA/Regime gates remain unchanged.
    """
    values = _clean(daily_excess_returns)
    if slice_count < 3:
        raise ValueError("train robustness slice_count must be at least 3")
    required = max(int(min_observations), slice_count * 10)
    if len(values) < required:
        return {
            "available": False,
            "schema": TRAIN_FITNESS_SCHEMA,
            "reason": "insufficient_train_excess_return_observations",
            "observations": int(len(values)),
            "required_observations": required,
            "slice_count": slice_count,
            "score_adjustment": 0.0,
            "feeds_validation": False,
            "feeds_holdout": False,
        }

    blocks = np.array_split(values, slice_count)
    slice_rows: list[dict[str, float | int]] = []
    slice_information_ratios: list[float] = []
    positive_slice_count = 0
    for index, block in enumerate(blocks, start=1):
        mean = float(np.mean(block))
        information_ratio = _information_ratio(block)
        if mean > 0.0:
            positive_slice_count += 1
        slice_information_ratios.append(information_ratio)
        slice_rows.append(
            {
                "slice": index,
                "observations": int(len(block)),
                "mean_daily_excess_percent": round(mean * 100.0, 6),
                "annualized_mean_excess_percent": round(mean * 252.0 * 100.0, 4),
                "information_ratio": round(information_ratio, 4),
            }
        )

    positive_slice_ratio = positive_slice_count / slice_count
    overall_ir = _information_ratio(values)
    median_slice_ir = float(np.median(slice_information_ratios))
    worst_slice_ir = float(np.min(slice_information_ratios))
    active_t, long_run_variance, hac_lag = _dependence_adjusted_t_statistic(values)

    # Keep this subordinate to the established Train score. Dependence-adjusted
    # evidence adds only a small nudge; the multi-objective frontier uses the
    # raw diagnostics separately instead of turning this into a hidden gate.
    adjustment = (
        5.0 * (2.0 * positive_slice_ratio - 1.0)
        + 3.0 * _clamp(overall_ir / 1.0, -1.0, 1.0)
        + 2.5 * _clamp(median_slice_ir / 0.75, -1.0, 1.0)
        + 2.0 * _clamp(worst_slice_ir / 0.50, -1.0, 1.0)
        + 2.5 * _clamp(active_t / 2.0, -1.0, 1.0)
    )
    adjustment = _clamp(adjustment, -15.0, 15.0)

    return {
        "available": True,
        "schema": TRAIN_FITNESS_SCHEMA,
        "method": "chronological_active_return_stability_with_hac_v2",
        "observations": int(len(values)),
        "slice_count": slice_count,
        "positive_slice_count": positive_slice_count,
        "positive_slice_ratio": round(positive_slice_ratio, 4),
        "overall_information_ratio": round(overall_ir, 4),
        "median_slice_information_ratio": round(median_slice_ir, 4),
        "worst_slice_information_ratio": round(worst_slice_ir, 4),
        "mean_daily_excess_percent": round(float(np.mean(values)) * 100.0, 6),
        "annualized_mean_excess_percent": round(
            float(np.mean(values)) * 252.0 * 100.0,
            4,
        ),
        "dependence_adjusted_active_t_statistic": round(active_t, 6),
        "hac_long_run_variance": round(long_run_variance, 12),
        "hac_max_lag": hac_lag,
        "score_adjustment": round(adjustment, 3),
        "slices": slice_rows,
        "promotion_gate": False,
        "train_only": True,
        "feeds_validation": False,
        "feeds_holdout": False,
    }
