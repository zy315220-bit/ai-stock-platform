from __future__ import annotations

import numpy as np

from app.services.research_lab.statistical_evidence import (
    build_statistical_evidence,
    cscv_probability_of_backtest_overfitting,
    deflated_sharpe_evidence,
    estimate_stationary_block_length,
    hansen_spa_test,
    minimum_track_record_length,
    probabilistic_sharpe_ratio,
    stationary_bootstrap_mean_interval,
)


def test_psr_and_minimum_track_record_reward_persistent_returns() -> None:
    probability = probabilistic_sharpe_ratio(0.12, 0.0, 500, 0.0, 3.0)
    required = minimum_track_record_length(0.12, 0.0, 0.0, 3.0)
    assert probability > 0.99
    assert required is not None
    assert required < 500


def test_statistical_evidence_preserves_time_dependence_with_adaptive_bootstrap() -> None:
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
    assert first["block_length_estimator"]["fallback_used"] is False
    assert first["average_block_length"] >= 1
    assert evidence["available"] is True
    assert evidence["probabilistic_sharpe_ratio"] > 0.95
    assert len(evidence["_daily_excess_returns"]) == len(returns)


def test_adaptive_block_length_keeps_fixed_fallback_for_short_data() -> None:
    estimate = estimate_stationary_block_length([0.01, -0.01, 0.02])
    assert estimate["fallback_used"] is True
    assert estimate["average_block_length"] == 10


def test_deflated_sharpe_penalizes_a_larger_independent_search() -> None:
    candidate = {"available": True, "period_sharpe_ratio": 0.12, "observations": 500, "skewness": 0.0, "kurtosis": 3.0}
    few_trials = deflated_sharpe_evidence(candidate, [0.01, 0.02, 0.03])
    many_trials = deflated_sharpe_evidence(candidate, np.linspace(-0.02, 0.10, 100))
    assert many_trials["expected_maximum_period_sharpe"] > few_trials["expected_maximum_period_sharpe"]
    assert many_trials["deflated_sharpe_probability"] < few_trials["deflated_sharpe_probability"]


def test_deflated_sharpe_uses_effective_independent_trial_count() -> None:
    rng = np.random.default_rng(71)
    common = rng.normal(0.0005, 0.003, 300)
    paths = {f"mutation-{i}": common + rng.normal(0.0, 0.00001, 300) for i in range(12)}
    candidate = {"available": True, "period_sharpe_ratio": 0.12, "observations": 500, "skewness": 0.0, "kurtosis": 3.0}
    evidence = deflated_sharpe_evidence(candidate, np.linspace(0.01, 0.08, 12), paths)
    assert evidence["raw_trial_count"] == 12
    assert 1.0 <= evidence["effective_trial_count"] < 12.0
    assert evidence["effective_trial_estimator"]["average_pairwise_correlation"] > 0.9


def test_cscv_reports_low_pbo_for_a_stable_winner() -> None:
    rng = np.random.default_rng(11)
    common = rng.normal(0.0, 0.001, 320)
    result = cscv_probability_of_backtest_overfitting({"stable": common + 0.002, "middle": common + 0.0005, "weak": common - 0.0005}, slice_count=8)
    assert result["available"] is True
    assert result["combination_count"] == 70
    assert result["pbo_probability"] == 0.0
    assert result["overfitting_risk_pass"] is True


def test_hansen_spa_uses_adaptive_lrv_studentization() -> None:
    rng = np.random.default_rng(19)
    result = hansen_spa_test({"strong": rng.normal(0.002, 0.003, 400), "noise": rng.normal(0.0, 0.003, 400), "weak": rng.normal(-0.001, 0.003, 400)}, bootstrap_samples=300)
    assert result["available"] is True
    assert result["method"] == "Hansen_SPA_consistent_stationary_bootstrap_v3_adaptive_lrv"
    assert result["block_length_estimator"]["method"] in {"positive_sequence_integrated_autocorrelation_time", "fixed_fallback"}
    assert result["studentization"] == "stationary_bootstrap_long_run_variance"
    assert result["best_candidate_id"] == "strong"
    assert result["spa_p_value"] == result["p_values"]["consistent"]
    assert result["p_values"]["lower"] <= result["p_values"]["consistent"] <= result["p_values"]["upper"]
    assert result["spa_p_value"] < 0.05


def test_hansen_spa_is_deterministic_for_serially_correlated_returns() -> None:
    rng = np.random.default_rng(43)
    innovations = rng.normal(0.0002, 0.003, (3, 420))
    paths = np.zeros_like(innovations)
    paths[:, 0] = innovations[:, 0]
    for index in range(1, paths.shape[1]):
        paths[:, index] = 0.65 * paths[:, index - 1] + innovations[:, index]
    candidates = {"a": paths[0] + 0.0002, "b": paths[1], "c": paths[2] - 0.0001}
    first = hansen_spa_test(candidates, bootstrap_samples=240, seed=17)
    second = hansen_spa_test(candidates, bootstrap_samples=240, seed=17)
    assert first == second
    assert first["available"] is True
    assert first["best_long_run_variance"] > 0.0
    assert first["additional_mean_daily_excess_percent_needed_at_5pct"] >= 0.0


def test_hansen_spa_does_not_pass_noise_only_candidates() -> None:
    rng = np.random.default_rng(1234)
    result = hansen_spa_test({"a": rng.normal(0.0, 0.004, 400), "b": rng.normal(0.0, 0.004, 400), "c": rng.normal(-0.0001, 0.004, 400)}, bootstrap_samples=400)
    assert result["available"] is True
    assert result["spa_p_value"] >= 0.05
    assert result["superior_predictive_ability_pass"] is False
