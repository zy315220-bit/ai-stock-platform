from __future__ import annotations

import numpy as np

from app.services.research_lab.statistical_evidence import (
    build_statistical_evidence,
    cscv_probability_of_backtest_overfitting,
    deflated_sharpe_evidence,
    hansen_spa_test,
    minimum_track_record_length,
    probabilistic_sharpe_ratio,
    stationary_bootstrap_mean_interval,
)


def test_psr_and_minimum_track_record_reward_persistent_returns() -> None:
    probability = probabilistic_sharpe_ratio(
        observed_sharpe=0.12,
        benchmark_sharpe=0.0,
        observations=500,
        skewness=0.0,
        kurtosis=3.0,
    )
    required = minimum_track_record_length(
        observed_sharpe=0.12,
        benchmark_sharpe=0.0,
        skewness=0.0,
        kurtosis=3.0,
    )
    assert probability > 0.99
    assert required is not None
    assert required < 500


def test_statistical_evidence_preserves_time_dependence_with_bootstrap() -> None:
    rng = np.random.default_rng(7)
    innovations = rng.normal(0.0008, 0.003, 500)
    returns = np.empty_like(innovations)
    returns[0] = innovations[0]
    for index in range(1, len(returns)):
        returns[index] = 0.45 * returns[index - 1] + innovations[index]

    first = stationary_bootstrap_mean_interval(returns, samples=200)
    second = stationary_bootstrap_mean_interval(returns, samples=200)
    evidence = build_statistical_evidence(returns, np.zeros(len(returns)))

    assert first == second
    assert first["available"] is True
    assert evidence["available"] is True
    assert evidence["probabilistic_sharpe_ratio"] > 0.95
    assert evidence["minimum_track_record_observations"] is not None
    assert len(evidence["_daily_excess_returns"]) == len(returns)


def test_deflated_sharpe_penalizes_a_larger_search() -> None:
    candidate = {
        "available": True,
        "period_sharpe_ratio": 0.12,
        "observations": 500,
        "skewness": 0.0,
        "kurtosis": 3.0,
    }
    few_trials = deflated_sharpe_evidence(candidate, [0.01, 0.02, 0.03])
    many_trials = deflated_sharpe_evidence(
        candidate,
        np.linspace(-0.02, 0.10, 100),
    )
    assert few_trials["available"] is True
    assert many_trials["expected_maximum_period_sharpe"] > few_trials[
        "expected_maximum_period_sharpe"
    ]
    assert many_trials["deflated_sharpe_probability"] < few_trials[
        "deflated_sharpe_probability"
    ]


def test_cscv_reports_low_pbo_for_a_stable_winner() -> None:
    rng = np.random.default_rng(11)
    common = rng.normal(0.0, 0.001, 320)
    result = cscv_probability_of_backtest_overfitting(
        {
            "stable": common + 0.002,
            "middle": common + 0.0005,
            "weak": common - 0.0005,
        },
        slice_count=8,
    )
    assert result["available"] is True
    assert result["combination_count"] == 70
    assert result["pbo_probability"] == 0.0
    assert result["overfitting_risk_pass"] is True


def test_hansen_spa_uses_common_stationary_bootstrap() -> None:
    rng = np.random.default_rng(19)
    result = hansen_spa_test(
        {
            "strong": rng.normal(0.002, 0.003, 400),
            "noise": rng.normal(0.0, 0.003, 400),
            "weak": rng.normal(-0.001, 0.003, 400),
        },
        bootstrap_samples=300,
    )
    assert result["available"] is True
    assert result["spa_p_value"] < 0.05
    assert result["superior_predictive_ability_pass"] is True
