from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Iterable

from app.services.backtest.engine import backtest_stock
from .evidence import assess_validation_evidence
from .models import ExperimentResult, ResearchCandidate, ResearchSplit
from .scoring import evaluate_candidate

BacktestFn = Callable[..., dict[str, Any]]
_ALLOWED_PARAMETERS = {"entry_score", "exit_score", "initial_capital", "require_ema_trend", "ema_fast_column", "ema_slow_column"}


def _validation_metrics(report: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(report.get("performance_metrics") or {})
    completed_trades = report.get("completed_trades", report.get("total_trades", len(report.get("trades") or [])))
    open_position_count = report.get("open_position_count", 1 if report.get("open_position") else 0)
    metrics.update({
        "total_return_percent": report.get("total_return_percent", report.get("total_return", 0.0)),
        "max_drawdown_percent": report.get("max_drawdown_percent", report.get("max_drawdown", 0.0)),
        "total_trades": completed_trades,
        "completed_trades": completed_trades,
        "open_position_count": open_position_count,
        "has_open_position": bool(open_position_count),
        "open_position_unrealized_return_percent": (report.get("open_position") or {}).get("unrealized_return_percent", 0.0),
    })
    return metrics


def run_candidate_validation(stock_code: str, split: ResearchSplit, candidate: ResearchCandidate, *, backtest_fn: BacktestFn = backtest_stock, min_validation_trades: int = 8) -> ExperimentResult:
    """Run exactly validation; holdout is never touched."""
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")
    report = backtest_fn(stock_code=stock_code, start_date=split.validation_start, end_date=split.validation_end, **candidate.parameters)
    metrics = _validation_metrics(report)
    evidence = assess_validation_evidence(metrics, min_trades=min_validation_trades)
    metrics["evidence_quality"] = asdict(evidence)
    return evaluate_candidate(candidate, metrics, min_trades=min_validation_trades)


def run_research_batch(stock_code: str, split: ResearchSplit, candidates: Iterable[ResearchCandidate], *, backtest_fn: BacktestFn = backtest_stock, min_validation_trades: int = 8) -> list[ExperimentResult]:
    results = [run_candidate_validation(stock_code, split, candidate, backtest_fn=backtest_fn, min_validation_trades=min_validation_trades) for candidate in candidates]
    return sorted(results, key=lambda result: result.research_score, reverse=True)


def serialize_result(result: ExperimentResult) -> dict[str, Any]:
    payload = asdict(result); payload["decision"] = result.decision.value; return payload
