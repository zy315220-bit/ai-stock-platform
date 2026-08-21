from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.backtest.engine import backtest_stock

from .models import ExperimentDecision, ExperimentResult, ResearchSplit
from .scoring import evaluate_candidate
from .runner import _validation_metrics

BacktestFn = Callable[..., dict[str, Any]]
_ALLOWED_PARAMETERS = {"entry_score", "exit_score", "initial_capital"}


@dataclass(frozen=True)
class PromotionResult:
    candidate_id: str
    promoted: bool
    validation_score: float
    holdout_score: float
    holdout_metrics: dict[str, Any]
    reasons: tuple[str, ...]


def run_holdout_gate(
    stock_code: str,
    split: ResearchSplit,
    validation_result: ExperimentResult,
    *,
    backtest_fn: BacktestFn = backtest_stock,
    max_score_degradation: float = 20.0,
) -> PromotionResult:
    """Touch final holdout exactly once, only after validation qualification."""
    if validation_result.decision is not ExperimentDecision.HOLDOUT_READY:
        raise ValueError("Candidate must be HOLDOUT_READY before final holdout evaluation")

    candidate = validation_result.candidate
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")

    report = backtest_fn(
        stock_code=stock_code,
        start_date=split.holdout_start,
        end_date=split.holdout_end,
        **candidate.parameters,
    )
    metrics = _validation_metrics(report)
    holdout_result = evaluate_candidate(candidate, metrics)

    reasons: list[str] = []
    if holdout_result.decision is not ExperimentDecision.HOLDOUT_READY:
        reasons.append("holdout_quality_gate_failed")
    degradation = validation_result.research_score - holdout_result.research_score
    if degradation > max_score_degradation:
        reasons.append("holdout_score_degraded")

    return PromotionResult(
        candidate_id=candidate.candidate_id,
        promoted=not reasons,
        validation_score=validation_result.research_score,
        holdout_score=holdout_result.research_score,
        holdout_metrics=metrics,
        reasons=tuple(reasons),
    )
