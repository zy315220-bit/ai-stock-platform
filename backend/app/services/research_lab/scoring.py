from __future__ import annotations

import math
from typing import Any

from .models import ExperimentDecision, ExperimentResult, ResearchCandidate


def _number(metrics: dict[str, Any], key: str) -> float:
    try:
        value = float(metrics.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def wilson_lower_bound(
    winning_trades: int,
    completed_trades: int,
    *,
    z: float = 1.959963984540054,
) -> float:
    """Return the conservative 95% lower bound for a trade win rate."""
    if completed_trades <= 0:
        return 0.0
    wins = max(0, min(int(winning_trades), int(completed_trades)))
    n = float(completed_trades)
    probability = wins / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = probability + z2 / (2.0 * n)
    margin = z * math.sqrt(
        (probability * (1.0 - probability) + z2 / (4.0 * n)) / n
    )
    return max(0.0, (center - margin) / denominator)


def evaluate_candidate(
    candidate: ResearchCandidate,
    validation_metrics: dict[str, Any],
    *,
    min_trades: int = 8,
    max_drawdown_percent: float = 30.0,
) -> ExperimentResult:
    """Score validation only; holdout data must not be supplied here.

    Mark-to-market performance is useful audit evidence, but it must not award
    research fitness when there are no completed trades. Otherwise a candidate
    that buys once and never exits can rank highly despite having zero realized
    validation evidence.
    """
    sharpe = _number(validation_metrics, "sharpe_ratio")
    sortino = _number(validation_metrics, "sortino_ratio")
    calmar = _number(validation_metrics, "calmar_ratio")
    total_return = _number(validation_metrics, "total_return_percent")
    alpha = _number(validation_metrics, "alpha_percent")
    drawdown = abs(_number(validation_metrics, "max_drawdown_percent"))
    try:
        trades = max(0, int(validation_metrics.get("completed_trades", validation_metrics.get("total_trades", 0))))
    except (TypeError, ValueError):
        trades = 0
    try:
        wins = max(0, int(validation_metrics.get("winning_trades", 0)))
    except (TypeError, ValueError):
        wins = 0
    if wins == 0 and trades > 0:
        win_rate = _number(validation_metrics, "win_rate_percent")
        wins = round(trades * max(0.0, min(win_rate, 100.0)) / 100.0)
    wilson_lower = wilson_lower_bound(wins, trades)
    enriched_metrics = dict(validation_metrics)
    enriched_metrics["wilson_win_rate_lower_bound_percent"] = round(
        wilson_lower * 100.0,
        4,
    )

    reasons: list[str] = []
    if trades < min_trades:
        reasons.append("insufficient_validation_trades")
    if drawdown > max_drawdown_percent:
        reasons.append("validation_drawdown_too_high")

    # With zero completed trades, equity-curve metrics are mark-to-market only.
    # Preserve them in validation_metrics for audit/display, but do not let them
    # create a high research score or misleading positive-performance reasons.
    if trades == 0:
        score = 0.0
        reasons.append("no_realized_trade_evidence")
    else:
        if total_return <= 0:
            reasons.append("non_positive_validation_return")
        if sharpe <= 0:
            reasons.append("non_positive_validation_sharpe")
        # Profit and a conservative, sample-size-aware win rate carry the
        # largest weights. Risk-adjusted return and alpha break ties without
        # allowing a tiny lucky sample to become the research champion.
        score = (
            25.0 * max(0.0, min(wilson_lower / 0.60, 1.0))
            + 25.0 * max(-1.0, min(total_return / 25.0, 1.0))
            + 15.0 * max(-1.0, min(alpha / 15.0, 1.0))
            + 15.0 * max(-1.0, min(sharpe / 2.0, 1.0))
            + 10.0 * max(-1.0, min(sortino / 3.0, 1.0))
            + 10.0 * max(-1.0, min(calmar / 2.0, 1.0))
        )
        score -= min(drawdown, 50.0) * 0.5
        score = round(score, 3)

    if reasons:
        decision = ExperimentDecision.DISCARD
    elif score >= 45.0:
        decision = ExperimentDecision.HOLDOUT_READY
    else:
        decision = ExperimentDecision.KEEP
        reasons.append("needs_more_validation")

    return ExperimentResult(
        candidate=candidate,
        validation_metrics=enriched_metrics,
        decision=decision,
        research_score=score,
        reasons=tuple(dict.fromkeys(reasons)),
    )
