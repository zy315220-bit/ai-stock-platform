from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.backtest.engine import backtest_stock

from .final_holdout import (
    FINAL_HOLDOUT_MAX_DRAWDOWN_PERCENT,
    FINAL_HOLDOUT_MIN_COMPLETED_TRADES,
)
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
    min_completed_trades: int = FINAL_HOLDOUT_MIN_COMPLETED_TRADES,
    max_drawdown_percent: float = FINAL_HOLDOUT_MAX_DRAWDOWN_PERCENT,
) -> PromotionResult:
    """Evaluate untouched holdout with the same pre-registered quality rubric.

    Production automation uses the durable one-shot ledger in final_holdout.py.
    This lower-level helper remains for deterministic evaluation and tests. It
    deliberately avoids an extra post-hoc "score degradation" threshold because
    adding a new threshold only after model selection would create another
    discretionary degree of freedom. Final holdout therefore reuses the fixed
    completed-trade, return, Sharpe, drawdown and research-score rubric.
    """
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
    # Hansen SPA is a set-level diagnostic: rejecting the global null only
    # establishes that at least one finalist is superior to the benchmark.
    # It must not be interpreted as proof that this selected candidate is the
    # superior model, so SPA is intentionally not an individual hard gate.

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
    holdout_result = evaluate_candidate(
        candidate,
        metrics,
        min_trades=max(1, int(min_completed_trades)),
        max_drawdown_percent=float(max_drawdown_percent),
    )

    reasons: list[str] = []
    if holdout_result.decision is not ExperimentDecision.HOLDOUT_READY:
        reasons.append("holdout_quality_gate_failed")

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
