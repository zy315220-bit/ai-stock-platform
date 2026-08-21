from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Iterable

from app.services.backtest.engine import backtest_stock

from .models import ExperimentResult, ResearchCandidate, ResearchSplit
from .scoring import evaluate_candidate

BacktestFn = Callable[..., dict[str, Any]]

_ALLOWED_PARAMETERS = {"entry_score", "exit_score", "initial_capital"}


def _validation_metrics(report: dict[str, Any]) -> dict[str, Any]:
    """Normalize the existing backtest report into Research Lab metrics."""
    metrics = dict(report.get("performance_metrics") or {})
    metrics.update(
        {
            "total_return_percent": report.get("total_return_percent", report.get("total_return", 0.0)),
            "max_drawdown_percent": report.get("max_drawdown_percent", report.get("max_drawdown", 0.0)),
            "total_trades": report.get("total_trades", len(report.get("trades") or [])),
        }
    )
    return metrics


def run_candidate_validation(
    stock_code: str,
    split: ResearchSplit,
    candidate: ResearchCandidate,
    *,
    backtest_fn: BacktestFn = backtest_stock,
) -> ExperimentResult:
    """Run exactly the validation window; the final holdout is never touched."""
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")

    report = backtest_fn(
        stock_code=stock_code,
        start_date=split.validation_start,
        end_date=split.validation_end,
        **candidate.parameters,
    )
    return evaluate_candidate(candidate, _validation_metrics(report))


def run_research_batch(
    stock_code: str,
    split: ResearchSplit,
    candidates: Iterable[ResearchCandidate],
    *,
    backtest_fn: BacktestFn = backtest_stock,
) -> list[ExperimentResult]:
    """Evaluate a deterministic candidate batch and rank strongest first."""
    results = [
        run_candidate_validation(
            stock_code,
            split,
            candidate,
            backtest_fn=backtest_fn,
        )
        for candidate in candidates
    ]
    return sorted(results, key=lambda result: result.research_score, reverse=True)


def serialize_result(result: ExperimentResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["decision"] = result.decision.value
    return payload
