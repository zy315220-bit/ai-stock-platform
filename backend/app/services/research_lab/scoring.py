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


def evaluate_candidate(
    candidate: ResearchCandidate,
    validation_metrics: dict[str, Any],
    *,
    min_trades: int = 8,
    max_drawdown_percent: float = 30.0,
) -> ExperimentResult:
    """Score validation only; holdout data must not be supplied here.

    This is intentionally conservative. It prevents a high-return candidate
    with too few trades or extreme drawdown from automatically surviving.
    """
    sharpe = _number(validation_metrics, "sharpe_ratio")
    sortino = _number(validation_metrics, "sortino_ratio")
    calmar = _number(validation_metrics, "calmar_ratio")
    total_return = _number(validation_metrics, "total_return_percent")
    drawdown = abs(_number(validation_metrics, "max_drawdown_percent"))
    try:
        trades = int(validation_metrics.get("total_trades", 0))
    except (TypeError, ValueError):
        trades = 0

    reasons: list[str] = []
    if trades < min_trades:
        reasons.append("insufficient_validation_trades")
    if drawdown > max_drawdown_percent:
        reasons.append("validation_drawdown_too_high")
    if total_return <= 0:
        reasons.append("non_positive_validation_return")
    if sharpe <= 0:
        reasons.append("non_positive_validation_sharpe")

    score = (
        35.0 * max(-1.0, min(sharpe / 2.0, 1.0))
        + 20.0 * max(-1.0, min(sortino / 3.0, 1.0))
        + 20.0 * max(-1.0, min(calmar / 2.0, 1.0))
        + 25.0 * max(-1.0, min(total_return / 25.0, 1.0))
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
        validation_metrics=dict(validation_metrics),
        decision=decision,
        research_score=score,
        reasons=tuple(reasons),
    )
