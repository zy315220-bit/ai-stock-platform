from __future__ import annotations

from app.services.research_lab.market_regimes import (
    MarketRegime,
    build_pre_holdout_regime_slices,
    classify_market_regime,
    run_market_regime_validation,
)
from app.services.research_lab.models import ResearchCandidate, ResearchSplit


def _split() -> ResearchSplit:
    return ResearchSplit(
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-01",
        validation_end="2024-12-31",
        holdout_start="2025-01-01",
        holdout_end="2025-12-31",
    )


def _candidate(candidate_id: str = "candidate") -> ResearchCandidate:
    return ResearchCandidate(
        candidate_id=candidate_id,
        strategy_family="score_engine",
        parameters={
            "entry_score": 60,
            "exit_score": 40,
            "initial_capital": 100_000,
            "require_ema_trend": False,
            "ema_fast_column": "EMA20",
            "ema_slow_column": "EMA60",
            "exit_mode": "score_or_time",
            "max_holding_days": 40,
        },
    )


def test_regime_classifier_has_explicit_thresholds() -> None:
    assert classify_market_regime(5.0) is MarketRegime.BULL
    assert classify_market_regime(-5.0) is MarketRegime.BEAR
    assert classify_market_regime(4.99) is MarketRegime.SIDEWAYS


def test_regime_slices_never_cross_holdout() -> None:
    slices = build_pre_holdout_regime_slices(_split(), slice_count=6)
    assert len(slices) == 6
    assert slices[0].start_date == _split().train_start
    assert slices[-1].end_date == _split().validation_end
    assert all(item.end_date < _split().holdout_start for item in slices)


def test_bull_and_bear_evidence_can_pass_without_holdout() -> None:
    slices = build_pre_holdout_regime_slices(_split(), slice_count=6)
    benchmark_returns = {
        item.start_date: (10.0 if index % 2 == 0 else -10.0)
        for index, item in enumerate(slices)
    }
    regime_labels = {
        item.start_date: (
            MarketRegime.BULL if index % 2 == 0 else MarketRegime.BEAR
        )
        for index, item in enumerate(slices)
    }
    calls: list[dict[str, object]] = []

    def fake_backtest(**kwargs):
        calls.append(kwargs)
        benchmark_return = benchmark_returns[kwargs["start_date"]]
        if kwargs["stock_code"] == "0050":
            return {
                "buy_and_hold": {"return_percent": benchmark_return},
                "total_return_percent": benchmark_return,
            }
        strategy_return = (
            benchmark_return + 3.0 if benchmark_return > 0 else 3.0
        )
        return {
            "total_return_percent": strategy_return,
            "max_drawdown_percent": 8.0,
            "completed_trades": 2,
            "winning_trade_count": 2,
            "win_rate_percent": 100.0,
            "performance_metrics": {
                "sharpe_ratio": 1.2,
                "sortino_ratio": 1.5,
                "calmar_ratio": 1.0,
            },
        }

    matrix = run_market_regime_validation(
        "2330",
        _split(),
        _candidate(),
        backtest_fn=fake_backtest,
        benchmark_backtest_fn=fake_backtest,
        slice_count=6,
        min_completed_trades_per_regime=2,
        regime_label_fn=lambda item: (
            regime_labels[item.start_date],
            {
                "as_of_date": item.start_date,
                "method": "test_point_in_time_label",
                "confidence": 1.0,
                "future_observations_used": False,
            },
        ),
    )

    assert matrix.robustness["robust_across_required_regimes"] is True
    assert matrix.robustness["holdout_used"] is False
    assert matrix.by_regime["BULL"]["mean_alpha_percent"] == 3.0
    assert matrix.by_regime["BEAR"]["mean_alpha_percent"] == 13.0
    assert calls
    assert all(call["end_date"] < _split().holdout_start for call in calls)


def test_missing_bear_regime_fails_closed_and_benchmark_is_cached() -> None:
    benchmark_calls = 0

    def strategy_backtest(**kwargs):
        return {
            "total_return_percent": 12.0,
            "max_drawdown_percent": 5.0,
            "completed_trades": 2,
            "winning_trade_count": 1,
        }

    def benchmark_backtest(**kwargs):
        nonlocal benchmark_calls
        benchmark_calls += 1
        return {"buy_and_hold": {"return_percent": 10.0}}

    cache = {}
    first = run_market_regime_validation(
        "2330",
        _split(),
        _candidate("first"),
        backtest_fn=strategy_backtest,
        benchmark_backtest_fn=benchmark_backtest,
        slice_count=6,
        min_completed_trades_per_regime=1,
        benchmark_cache=cache,
        regime_label_fn=lambda item: (
            MarketRegime.BULL,
            {
                "as_of_date": item.start_date,
                "method": "test_point_in_time_label",
                "confidence": 1.0,
                "future_observations_used": False,
            },
        ),
    )
    run_market_regime_validation(
        "2330",
        _split(),
        _candidate("second"),
        backtest_fn=strategy_backtest,
        benchmark_backtest_fn=benchmark_backtest,
        slice_count=6,
        min_completed_trades_per_regime=1,
        benchmark_cache=cache,
        regime_label_fn=lambda item: (
            MarketRegime.BULL,
            {
                "as_of_date": item.start_date,
                "method": "test_point_in_time_label",
                "confidence": 1.0,
                "future_observations_used": False,
            },
        ),
    )

    assert first.robustness["robust_across_required_regimes"] is False
    assert "missing_bear_regime" in first.robustness["reasons"]
    assert benchmark_calls == 6
