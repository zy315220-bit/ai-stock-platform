from __future__ import annotations

from dataclasses import asdict
from dataclasses import replace
from typing import Any, Callable, Iterable, Literal

from app.services.backtest.engine import backtest_stock
from .evidence import assess_validation_evidence
from .models import ExperimentResult, ResearchCandidate, ResearchSplit
from .scoring import evaluate_candidate
from .statistical_evidence import build_statistical_evidence

BacktestFn = Callable[..., dict[str, Any]]
EvaluationPhase = Literal["train", "validation"]
_ALLOWED_PARAMETERS = {
    "entry_score",
    "exit_score",
    "initial_capital",
    "require_ema_trend",
    "ema_fast_column",
    "ema_slow_column",
    "entry_mode",
    "exit_mode",
    "max_holding_days",
}


def _validation_metrics(report: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(report.get("performance_metrics") or {})
    completed_trades = report.get(
        "completed_trades",
        report.get(
            "total_trades",
            report.get("trade_count", len(report.get("trades") or [])),
        ),
    )
    open_position_count = report.get("open_position_count", 1 if report.get("open_position") else 0)
    winning_trades = report.get(
        "winning_trade_count",
        sum(
            1
            for trade in report.get("trades") or []
            if float(trade.get("profit", 0.0)) > 0
        ),
    )
    buy_and_hold = report.get("buy_and_hold") or {}
    metrics.update({
        "total_return_percent": report.get("total_return_percent", report.get("total_return", 0.0)),
        "max_drawdown_percent": report.get("max_drawdown_percent", report.get("max_drawdown", 0.0)),
        "total_trades": completed_trades,
        "completed_trades": completed_trades,
        "winning_trades": winning_trades,
        "win_rate_percent": report.get("win_rate_percent", 0.0),
        "alpha_percent": report.get("alpha_percent", 0.0),
        "benchmark_return_percent": buy_and_hold.get("return_percent", 0.0),
        "total_transaction_cost": report.get("total_transaction_cost", 0.0),
        "open_position_count": open_position_count,
        "has_open_position": bool(open_position_count),
        "open_position_unrealized_return_percent": (report.get("open_position") or {}).get("unrealized_return_percent", 0.0),
        "data_source": report.get("data_source"),
        "data_fingerprint": (
            report.get("score_series_cache") or {}
        ).get("fingerprint"),
        "score_cache_schema": (
            report.get("score_series_cache") or {}
        ).get("schema"),
        "history_coverage": report.get("history_coverage"),
        "history_recovery": report.get("history_recovery"),
        "corporate_action_audit": report.get("corporate_actions"),
        "actual_start_date": report.get("actual_start_date"),
        "actual_end_date": report.get("actual_end_date"),
    })
    research_series = report.get("research_return_series") or {}
    strategy_returns = research_series.get("strategy_daily_returns") or []
    benchmark_returns = research_series.get("benchmark_daily_returns") or []
    if strategy_returns:
        statistical_evidence = build_statistical_evidence(
            strategy_returns,
            benchmark_returns,
        )
        metrics["statistical_evidence"] = {
            key: value
            for key, value in statistical_evidence.items()
            if not key.startswith("_")
        }
        metrics["_daily_excess_returns"] = statistical_evidence.get(
            "_daily_excess_returns",
            [],
        )
    return metrics


def _phase_dates(
    split: ResearchSplit,
    evaluation_phase: EvaluationPhase,
) -> tuple[str, str]:
    if evaluation_phase == "train":
        return split.train_start, split.train_end
    if evaluation_phase == "validation":
        return split.validation_start, split.validation_end
    raise ValueError(f"Unsupported evaluation phase: {evaluation_phase}")


def run_candidate_validation(
    stock_code: str,
    split: ResearchSplit,
    candidate: ResearchCandidate,
    *,
    backtest_fn: BacktestFn = backtest_stock,
    min_validation_trades: int = 8,
    evaluation_phase: EvaluationPhase = "validation",
) -> ExperimentResult:
    """Evaluate one chronological phase while never touching holdout."""
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")
    phase_start, phase_end = _phase_dates(split, evaluation_phase)
    report = backtest_fn(
        stock_code=stock_code,
        start_date=phase_start,
        end_date=phase_end,
        liquidate_at_end=False,
        include_research_series=True,
        **candidate.parameters,
    )
    metrics = _validation_metrics(report)
    evidence = assess_validation_evidence(metrics, min_trades=min_validation_trades)
    metrics["evidence_quality"] = asdict(evidence)
    result = evaluate_candidate(
        candidate,
        metrics,
        min_trades=min_validation_trades,
    )
    return replace(result, evaluation_phase=evaluation_phase)


def run_research_batch(
    stock_code: str,
    split: ResearchSplit,
    candidates: Iterable[ResearchCandidate],
    *,
    backtest_fn: BacktestFn = backtest_stock,
    min_validation_trades: int = 8,
    evaluation_phase: EvaluationPhase = "validation",
) -> list[ExperimentResult]:
    results = [
        run_candidate_validation(
            stock_code,
            split,
            candidate,
            backtest_fn=backtest_fn,
            min_validation_trades=min_validation_trades,
            evaluation_phase=evaluation_phase,
        )
        for candidate in candidates
    ]
    return sorted(
        results,
        key=lambda result: result.research_score,
        reverse=True,
    )


def serialize_result(result: ExperimentResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["decision"] = result.decision.value
    payload["validation_metrics"] = {
        key: value
        for key, value in payload["validation_metrics"].items()
        if not key.startswith("_")
    }
    return payload
