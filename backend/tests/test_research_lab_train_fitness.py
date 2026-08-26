from __future__ import annotations

import numpy as np

from app.services.research_lab.models import ResearchCandidate, ResearchSplit
from app.services.research_lab.runner import run_candidate_validation
from app.services.research_lab.train_fitness import (
    build_train_active_robustness_proxy,
)


def _split() -> ResearchSplit:
    return ResearchSplit(
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-01",
        validation_end="2024-12-31",
        holdout_start="2025-01-01",
        holdout_end="2025-12-31",
    )


def test_proxy_rewards_persistent_positive_excess_returns() -> None:
    rng = np.random.default_rng(123)
    persistent = rng.normal(0.0008, 0.002, 600)
    concentrated = np.concatenate(
        [
            rng.normal(-0.0002, 0.002, 500),
            rng.normal(0.005, 0.002, 100),
        ]
    )

    stable = build_train_active_robustness_proxy(persistent)
    lucky = build_train_active_robustness_proxy(concentrated)

    assert stable["available"] is True
    assert lucky["available"] is True
    assert stable["positive_slice_ratio"] > lucky["positive_slice_ratio"]
    assert stable["score_adjustment"] > lucky["score_adjustment"]
    assert stable["train_only"] is True
    assert stable["promotion_gate"] is False


def test_runner_applies_proxy_only_during_train() -> None:
    candidate = ResearchCandidate(
        "stable",
        "score_engine",
        {"entry_score": 70, "exit_score": 35},
    )

    def fake_backtest(**kwargs):
        observations = 500
        strategy = np.full(observations, 0.0015)
        benchmark = np.full(observations, 0.0003)
        return {
            "total_return_percent": 25.0,
            "max_drawdown_percent": 5.0,
            "completed_trades": 12,
            "winning_trade_count": 9,
            "win_rate_percent": 75.0,
            "alpha_percent": 10.0,
            "performance_metrics": {
                "sharpe_ratio": 1.5,
                "sortino_ratio": 2.0,
                "calmar_ratio": 1.5,
            },
            "research_return_series": {
                "strategy_daily_returns": strategy.tolist(),
                "benchmark_daily_returns": benchmark.tolist(),
            },
        }

    train = run_candidate_validation(
        "2330",
        _split(),
        candidate,
        backtest_fn=fake_backtest,
        evaluation_phase="train",
        min_validation_trades=4,
    )
    validation = run_candidate_validation(
        "2330",
        _split(),
        candidate,
        backtest_fn=fake_backtest,
        evaluation_phase="validation",
        min_validation_trades=4,
    )

    assert train.validation_metrics["train_active_robustness_proxy"]["available"] is True
    assert train.validation_metrics["train_fitness_validation_feedback_used"] is False
    assert train.validation_metrics["train_fitness_holdout_feedback_used"] is False
    assert "train_active_robustness_proxy" not in validation.validation_metrics
    assert train.research_score > validation.research_score
