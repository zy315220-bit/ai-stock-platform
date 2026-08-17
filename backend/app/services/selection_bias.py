from __future__ import annotations

import math
from typing import Iterable


def probability_at_least_one_false_positive(strategy_count: int, alpha: float = 0.05) -> float:
    """Family-wise false-positive probability under independent null tests."""
    if strategy_count < 0:
        raise ValueError("strategy_count must be non-negative")
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be between 0 and 1")
    return 1.0 - (1.0 - alpha) ** strategy_count


def sidak_per_strategy_alpha(strategy_count: int, family_alpha: float = 0.05) -> float:
    """Sidak-adjusted per-strategy alpha for a target family-wise error rate."""
    if strategy_count <= 0:
        raise ValueError("strategy_count must be positive")
    if not 0.0 < family_alpha < 1.0:
        raise ValueError("family_alpha must be between 0 and 1")
    return 1.0 - (1.0 - family_alpha) ** (1.0 / strategy_count)


def selection_bias_diagnostics(
    strategy_count: int,
    *,
    family_alpha: float = 0.05,
    observed_trade_counts: Iterable[int] = (),
) -> dict[str, object]:
    """Expose transparent multiple-comparison diagnostics without pretending to be PBO.

    This is deliberately a warning/qualification layer. Correlated trading strategies
    violate the independence assumption behind the simple family-wise calculation, so
    the result must not be interpreted as a calibrated probability that the leader is false.
    """
    counts = [int(value) for value in observed_trade_counts]
    if any(value < 0 for value in counts):
        raise ValueError("trade counts must be non-negative")
    raw_fwer = probability_at_least_one_false_positive(strategy_count, family_alpha)
    adjusted_alpha = sidak_per_strategy_alpha(strategy_count, family_alpha)
    return {
        "strategy_count": strategy_count,
        "family_alpha": round(family_alpha, 6),
        "independence_fwer_percent": round(raw_fwer * 100.0, 2),
        "sidak_per_strategy_alpha": round(adjusted_alpha, 6),
        "sidak_confidence_percent": round((1.0 - adjusted_alpha) * 100.0, 4),
        "minimum_observed_trades": min(counts) if counts else None,
        "maximum_observed_trades": max(counts) if counts else None,
        "interpretation": "diagnostic_only_not_pbo",
        "assumption": "independent_strategy_tests",
        "warning": "策略報酬與訊號通常相關；此數字只顯示多策略挑冠軍的選拔偏誤風險，不是 PBO，也不是冠軍為假的機率。",
    }
