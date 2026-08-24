from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.backtest.engine import backtest_stock

from .models import ExperimentDecision, ExperimentResult, ResearchSplit
from .scoring import evaluate_candidate
from .runner import _ALLOWED_PARAMETERS, _validation_metrics

BacktestFn = Callable[..., dict[str, Any]]
@dataclass(frozen=True)
class PromotionResult:
    candidate_id: str
    promoted: bool
    validation_score: float
    regime_robustness_score: float
    holdout_score: float
    holdout_metrics: dict[str, Any]
    reasons: tuple[str, ...]


def run_holdout_gate(
    stock_code: str,
    split: ResearchSplit,
    validation_result: ExperimentResult,
    *,
    regime_robustness: dict[str, Any] | None,
    model_selection_evidence: dict[str, Any] | None,
    backtest_fn: BacktestFn = backtest_stock,
    max_score_degradation: float = 20.0,
) -> PromotionResult:
    """Touch holdout once, after validation and market-regime qualification."""
    if validation_result.decision is not ExperimentDecision.HOLDOUT_READY:
        raise ValueError("Candidate must be HOLDOUT_READY before final holdout evaluation")
    if not regime_robustness or not regime_robustness.get(
        "robust_across_required_regimes"
    ):
        raise ValueError(
            "Candidate must pass bull/bear robustness before holdout evaluation"
        )
    if regime_robustness.get("holdout_used") is not False:
        raise ValueError(
            "Regime evidence must explicitly prove that holdout was not used"
        )
    statistical_evidence = validation_result.validation_metrics.get(
        "statistical_evidence",
        {},
    )
    deflated_sharpe = validation_result.validation_metrics.get(
        "deflated_sharpe",
        {},
    )
    if not statistical_evidence.get("statistical_quality_pass"):
        raise ValueError(
            "Candidate must pass PSR, MinTRL and stationary bootstrap gates"
        )
    if not deflated_sharpe.get("multiple_testing_pass"):
        raise ValueError("Candidate must pass the Deflated Sharpe Ratio gate")
    if not model_selection_evidence:
        raise ValueError("Model-selection evidence is required before holdout")
    if not model_selection_evidence.get("cscv_pbo", {}).get(
        "overfitting_risk_pass"
    ):
        raise ValueError("Candidate must pass the CSCV/PBO gate")
    if not model_selection_evidence.get("hansen_spa", {}).get(
        "superior_predictive_ability_pass"
    ):
        raise ValueError("Candidate must pass the Hansen SPA gate")

    candidate = validation_result.candidate
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")

    report = backtest_fn(
        stock_code=stock_code,
        start_date=split.holdout_start,
        end_date=split.holdout_end,
        liquidate_at_end=False,
        include_research_series=True,
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
        regime_robustness_score=float(
            regime_robustness.get("robustness_score", 0.0) or 0.0
        ),
        holdout_score=holdout_result.research_score,
        holdout_metrics=metrics,
        reasons=tuple(reasons),
    )
