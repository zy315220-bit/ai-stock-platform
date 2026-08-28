from __future__ import annotations

import math
from itertools import combinations
from statistics import NormalDist
from typing import Any, Iterable

import numpy as np

_NORMAL = NormalDist()
_EULER_MASCHERONI = 0.5772156649015329
_DEFAULT_BLOCK_LENGTH = 10


def _clean(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def _deduplicate_return_paths(candidates: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    unique: dict[bytes, tuple[str, np.ndarray]] = {}
    for name, values in candidates.items():
        signature = np.round(values, 12).tobytes()
        unique.setdefault(signature, (name, values))
    return {name: values for name, values in unique.values()}


def _moments(returns: np.ndarray) -> tuple[float, float, float]:
    if len(returns) < 3:
        return 0.0, 0.0, 3.0
    mean = float(np.mean(returns))
    centered = returns - mean
    second = float(np.mean(centered**2))
    if second <= 0:
        return 0.0, 0.0, 3.0
    skewness = float(np.mean(centered**3) / second**1.5)
    kurtosis = float(np.mean(centered**4) / second**2)
    sample_std = float(np.std(returns, ddof=1))
    sharpe = mean / sample_std if sample_std > 0 else 0.0
    return sharpe, skewness, max(1.0, kurtosis)


def probabilistic_sharpe_ratio(observed_sharpe: float, benchmark_sharpe: float, observations: int, skewness: float, kurtosis: float) -> float:
    if observations < 3:
        return 0.0
    variance_term = 1.0 - skewness * observed_sharpe + ((kurtosis - 1.0) / 4.0) * observed_sharpe**2
    if not math.isfinite(variance_term) or variance_term <= 0:
        return 0.0
    statistic = (observed_sharpe - benchmark_sharpe) * math.sqrt(observations - 1) / math.sqrt(variance_term)
    return max(0.0, min(1.0, _NORMAL.cdf(statistic)))


def minimum_track_record_length(observed_sharpe: float, benchmark_sharpe: float, skewness: float, kurtosis: float, *, confidence: float = 0.95) -> int | None:
    difference = observed_sharpe - benchmark_sharpe
    if difference <= 0 or not 0.5 < confidence < 1.0:
        return None
    variance_term = 1.0 - skewness * observed_sharpe + ((kurtosis - 1.0) / 4.0) * observed_sharpe**2
    if not math.isfinite(variance_term) or variance_term <= 0:
        return None
    required = 1.0 + variance_term * (_NORMAL.inv_cdf(confidence) / difference) ** 2
    return max(3, int(math.ceil(required)))


def estimate_stationary_block_length(returns: Iterable[float], *, fallback: int = _DEFAULT_BLOCK_LENGTH) -> dict[str, Any]:
    """Train/data-only dependence estimate with a fixed fail-safe fallback.

    We use a truncated integrated-autocorrelation-time estimate. The truncation
    stops at the first non-positive autocorrelation, preventing noisy distant
    lags from inflating the block length. This is deterministic and never uses
    validation or holdout feedback.
    """
    values = _clean(returns)
    if len(values) < 20 or float(np.std(values, ddof=1)) <= 0.0:
        return {"average_block_length": int(fallback), "method": "fixed_fallback", "fallback_used": True, "reason": "insufficient_dependence_data"}
    centered = values - float(np.mean(values))
    variance = float(np.dot(centered, centered))
    if variance <= 0.0:
        return {"average_block_length": int(fallback), "method": "fixed_fallback", "fallback_used": True, "reason": "zero_variance"}
    max_lag = min(len(values) // 4, max(5, int(math.sqrt(len(values)) * 2)))
    positive_acf: list[float] = []
    for lag in range(1, max_lag + 1):
        rho = float(np.dot(centered[:-lag], centered[lag:]) / variance)
        if not math.isfinite(rho) or rho <= 0.0:
            break
        positive_acf.append(min(rho, 0.99))
    integrated_time = 1.0 + 2.0 * sum(positive_acf)
    estimate = int(round(max(1.0, min(float(len(values) // 3), integrated_time))))
    return {"average_block_length": estimate, "method": "positive_sequence_integrated_autocorrelation_time", "fallback_used": False, "positive_acf_lags": len(positive_acf), "integrated_autocorrelation_time": round(integrated_time, 6)}


def _stationary_bootstrap_indices(observations: int, samples: int, *, average_block_length: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    indices = np.empty((samples, observations), dtype=np.int64)
    indices[:, 0] = rng.integers(0, observations, size=samples)
    restart_probability = 1.0 / max(1, average_block_length)
    for position in range(1, observations):
        restart = rng.random(samples) < restart_probability
        continuation = (indices[:, position - 1] + 1) % observations
        fresh = rng.integers(0, observations, size=samples)
        indices[:, position] = np.where(restart, fresh, continuation)
    return indices


def stationary_bootstrap_mean_interval(returns: Iterable[float], *, confidence: float = 0.95, samples: int = 400, average_block_length: int | None = None, seed: int = 20260825) -> dict[str, Any]:
    values = _clean(returns)
    if len(values) < 10:
        return {"available": False, "reason": "insufficient_dependent_return_observations", "observations": int(len(values))}
    block = estimate_stationary_block_length(values) if average_block_length is None else {"average_block_length": int(average_block_length), "method": "explicit_override", "fallback_used": False}
    chosen = int(block["average_block_length"])
    indices = _stationary_bootstrap_indices(len(values), samples, average_block_length=chosen, seed=seed)
    means = values[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(means, [alpha, 1.0 - alpha])
    return {"available": True, "method": "Politis-Romano stationary bootstrap", "observations": int(len(values)), "samples": samples, "average_block_length": chosen, "block_length_estimator": block, "confidence": confidence, "mean_daily_return_percent": round(float(values.mean()) * 100.0, 6), "mean_daily_return_ci_percent": [round(float(lower) * 100.0, 6), round(float(upper) * 100.0, 6)], "annualized_arithmetic_return_ci_percent": [round(float(lower) * 252.0 * 100.0, 4), round(float(upper) * 252.0 * 100.0, 4)]}


def build_statistical_evidence(strategy_returns: Iterable[float], benchmark_returns: Iterable[float] | None = None, *, benchmark_sharpe: float = 0.0, confidence: float = 0.95) -> dict[str, Any]:
    strategy = _clean(strategy_returns)
    benchmark = _clean(benchmark_returns) if benchmark_returns is not None else np.asarray([], dtype=float)
    if len(strategy) < 3:
        return {"available": False, "reason": "insufficient_daily_return_observations", "observations": int(len(strategy))}
    sharpe, skewness, kurtosis = _moments(strategy)
    psr = probabilistic_sharpe_ratio(sharpe, benchmark_sharpe, len(strategy), skewness, kurtosis)
    min_track = minimum_track_record_length(sharpe, benchmark_sharpe, skewness, kurtosis, confidence=confidence)
    bootstrap = stationary_bootstrap_mean_interval(strategy, confidence=confidence)
    lower_bootstrap = float(bootstrap["mean_daily_return_ci_percent"][0]) if bootstrap.get("available") else float("-inf")
    comparable = min(len(strategy), len(benchmark))
    excess = strategy[-comparable:] - benchmark[-comparable:] if comparable > 0 else np.asarray([], dtype=float)
    return {"available": True, "method": "PSR_MinTRL_and_stationary_bootstrap_v2_adaptive_block", "observations": int(len(strategy)), "period_sharpe_ratio": round(sharpe, 8), "annualized_sharpe_ratio": round(sharpe * math.sqrt(252.0), 4), "skewness": round(skewness, 6), "kurtosis": round(kurtosis, 6), "probabilistic_sharpe_ratio": round(psr, 6), "probabilistic_sharpe_ratio_percent": round(psr * 100.0, 4), "minimum_track_record_observations": min_track, "track_record_sufficient": bool(min_track is not None and len(strategy) >= min_track), "stationary_bootstrap": bootstrap, "statistical_quality_pass": bool(psr >= confidence and min_track is not None and len(strategy) >= min_track and lower_bootstrap > 0.0), "benchmark_return_basis": "same_stock_split_adjusted_buy_and_hold_total_return" if comparable > 0 else None, "_daily_excess_returns": excess.tolist()}


def _effective_trial_count(trial_return_paths: dict[str, Iterable[float]] | None, raw_count: int) -> dict[str, Any]:
    if raw_count <= 1:
        return {"effective_trial_count": float(raw_count), "average_pairwise_correlation": None, "method": "raw_count_fallback", "fallback_used": True}
    if not trial_return_paths:
        return {"effective_trial_count": float(raw_count), "average_pairwise_correlation": None, "method": "raw_count_fallback", "fallback_used": True, "reason": "trial_return_paths_not_supplied"}
    cleaned = _deduplicate_return_paths({name: _clean(values) for name, values in trial_return_paths.items() if len(_clean(values)) >= 3})
    if len(cleaned) < 2:
        return {"effective_trial_count": 1.0, "average_pairwise_correlation": 1.0, "method": "behavior_path_effective_trials", "fallback_used": False, "unique_behavior_count": len(cleaned)}
    length = min(len(values) for values in cleaned.values())
    matrix = np.vstack([values[-length:] for values in cleaned.values()])
    corr = np.corrcoef(matrix)
    upper = corr[np.triu_indices_from(corr, k=1)]
    finite = upper[np.isfinite(upper)]
    if not len(finite):
        return {"effective_trial_count": float(len(cleaned)), "average_pairwise_correlation": None, "method": "unique_behavior_count_fallback", "fallback_used": True}
    rho = max(0.0, min(0.999999, float(np.mean(finite))))
    unique_count = len(cleaned)
    effective = unique_count / (1.0 + (unique_count - 1.0) * rho)
    return {"effective_trial_count": max(1.0, min(float(raw_count), effective)), "average_pairwise_correlation": round(rho, 8), "method": "equicorrelation_effective_independent_trials", "fallback_used": False, "unique_behavior_count": unique_count}


def deflated_sharpe_evidence(candidate_evidence: dict[str, Any], trial_period_sharpes: Iterable[float], trial_return_paths: dict[str, Iterable[float]] | None = None) -> dict[str, Any]:
    trials = _clean(trial_period_sharpes)
    raw_count = len(trials)
    if not candidate_evidence.get("available") or raw_count < 2:
        return {"available": False, "reason": "insufficient_strategy_trials", "trial_count": int(raw_count), "raw_trial_count": int(raw_count)}
    effective = _effective_trial_count(trial_return_paths, raw_count)
    effective_count = max(2.0, float(effective["effective_trial_count"]))
    mean_trial = float(np.mean(trials))
    trial_std = float(np.std(trials, ddof=1))
    quantile_a = _NORMAL.inv_cdf(1.0 - 1.0 / effective_count)
    quantile_b = _NORMAL.inv_cdf(1.0 - 1.0 / (effective_count * math.e))
    expected_maximum = mean_trial + trial_std * ((1.0 - _EULER_MASCHERONI) * quantile_a + _EULER_MASCHERONI * quantile_b)
    probability = probabilistic_sharpe_ratio(float(candidate_evidence.get("period_sharpe_ratio", 0.0)), expected_maximum, int(candidate_evidence.get("observations", 0)), float(candidate_evidence.get("skewness", 0.0)), float(candidate_evidence.get("kurtosis", 3.0)))
    return {"available": True, "method": "Bailey-Lopez_de_Prado_deflated_Sharpe_v2_effective_trials", "trial_count": int(raw_count), "raw_trial_count": int(raw_count), "effective_trial_count": round(float(effective["effective_trial_count"]), 6), "effective_trial_estimator": effective, "mean_trial_period_sharpe": round(mean_trial, 8), "trial_period_sharpe_std": round(trial_std, 8), "expected_maximum_period_sharpe": round(expected_maximum, 8), "deflated_sharpe_probability": round(probability, 6), "deflated_sharpe_probability_percent": round(probability * 100.0, 4), "multiple_testing_pass": probability >= 0.95}


def cscv_probability_of_backtest_overfitting(candidate_returns: dict[str, Iterable[float]], *, slice_count: int = 8) -> dict[str, Any]:
    cleaned = {candidate_id: _clean(returns) for candidate_id, returns in candidate_returns.items()}
    cleaned = {candidate_id: values for candidate_id, values in cleaned.items() if len(values) >= slice_count * 5}
    original_candidate_count = len(cleaned)
    cleaned = _deduplicate_return_paths(cleaned)
    if len(cleaned) < 3 or slice_count < 4 or slice_count % 2:
        return {"available": False, "reason": "CSCV_requires_three_candidates_and_even_slices", "candidate_count": len(cleaned), "original_candidate_count": original_candidate_count, "slice_count": slice_count}
    length = min(len(values) for values in cleaned.values())
    names = list(cleaned)
    matrix = np.vstack([cleaned[name][-length:] for name in names])
    blocks = np.array_split(np.arange(length), slice_count)
    logits: list[float] = []
    degradations: list[float] = []
    for in_sample_blocks in combinations(range(slice_count), slice_count // 2):
        in_set = set(in_sample_blocks)
        is_indices = np.concatenate([blocks[index] for index in in_set])
        oos_indices = np.concatenate([blocks[index] for index in range(slice_count) if index not in in_set])
        def sharpes(indices: np.ndarray) -> np.ndarray:
            selected = matrix[:, indices]
            means = selected.mean(axis=1)
            stds = selected.std(axis=1, ddof=1)
            return np.divide(means, stds, out=np.full_like(means, -np.inf), where=stds > 0)
        is_sharpes = sharpes(is_indices)
        oos_sharpes = sharpes(oos_indices)
        winner = int(np.argmax(is_sharpes))
        order = np.argsort(oos_sharpes)
        rank = int(np.where(order == winner)[0][0]) + 1
        percentile = min(max((rank - 0.5) / len(names), 1e-9), 1.0 - 1e-9)
        logits.append(math.log(percentile / (1.0 - percentile)))
        degradations.append(float(is_sharpes[winner] - oos_sharpes[winner]))
    pbo = sum(value <= 0.0 for value in logits) / len(logits)
    return {"available": True, "method": "Combinatorially_Symmetric_Cross_Validation_v1", "candidate_count": len(names), "original_candidate_count": original_candidate_count, "slice_count": slice_count, "combination_count": len(logits), "pbo_probability": round(pbo, 6), "pbo_probability_percent": round(pbo * 100.0, 4), "median_oos_rank_logit": round(float(np.median(logits)), 6), "median_sharpe_degradation": round(float(np.median(degradations)), 6), "overfitting_risk_pass": pbo <= 0.20}


def _stationary_long_run_variance(values: np.ndarray, *, average_block_length: int) -> float:
    observations = len(values)
    if observations < 2:
        return 0.0
    demeaned = values - float(np.mean(values))
    restart_probability = 1.0 / max(1, average_block_length)
    variance = float(np.sum(demeaned**2) / observations)
    for lag in range(1, observations):
        kappa = (1.0 - lag / observations) * (1.0 - restart_probability) ** lag + (lag / observations) * (1.0 - restart_probability) ** (observations - lag)
        covariance = float(np.sum(demeaned[: observations - lag] * demeaned[lag:]) / observations)
        variance += 2.0 * kappa * covariance
    return max(0.0, variance)


def hansen_spa_test(candidate_excess_returns: dict[str, Iterable[float]], *, bootstrap_samples: int = 600, average_block_length: int | None = None, seed: int = 20260825) -> dict[str, Any]:
    cleaned = {name: _clean(values) for name, values in candidate_excess_returns.items()}
    original_candidate_count = len(cleaned)
    cleaned = _deduplicate_return_paths(cleaned)
    if len(cleaned) < 2:
        return {"available": False, "reason": "SPA_requires_at_least_two_candidate_models", "candidate_count": len(cleaned), "original_candidate_count": original_candidate_count}
    observations = min(len(values) for values in cleaned.values())
    if observations < 30:
        return {"available": False, "reason": "SPA_requires_at_least_30_return_observations", "candidate_count": len(cleaned), "original_candidate_count": original_candidate_count, "observations": observations}
    names = list(cleaned)
    matrix = np.vstack([cleaned[name][-observations:] for name in names])
    aggregate = np.mean(matrix, axis=0)
    block = estimate_stationary_block_length(aggregate) if average_block_length is None else {"average_block_length": int(average_block_length), "method": "explicit_override", "fallback_used": False}
    chosen = int(block["average_block_length"])
    means = matrix.mean(axis=1)
    long_run_variances = np.asarray([_stationary_long_run_variance(values, average_block_length=chosen) for values in matrix], dtype=float)
    positive_variance = np.isfinite(long_run_variances) & (long_run_variances > 0.0)
    if not np.any(positive_variance):
        return {"available": False, "reason": "SPA_requires_positive_long_run_variance", "candidate_count": len(names), "original_candidate_count": original_candidate_count, "observations": observations}
    safe_stds = np.where(positive_variance, np.sqrt(long_run_variances), np.inf)
    observed_statistics = math.sqrt(observations) * means / safe_stds
    observed = max(0.0, float(np.max(observed_statistics)))
    best_index = int(np.argmax(observed_statistics))
    log_log_term = max(0.0, math.log(math.log(observations)))
    thresholds = -np.sqrt((long_run_variances / observations) * 2.0 * log_log_term)
    active = positive_variance & (means >= thresholds)
    if not np.any(active):
        active[best_index] = True
    lower_recentering = np.maximum(means, 0.0)
    consistent_recentering = means.copy()
    consistent_recentering[~active] = 0.0
    recentering = np.vstack([lower_recentering, consistent_recentering, means.copy()])
    indices = _stationary_bootstrap_indices(observations, bootstrap_samples, average_block_length=chosen, seed=seed)
    simulated = np.empty((bootstrap_samples, 3), dtype=float)
    root_n = math.sqrt(observations)
    for sample_number, sample_indices in enumerate(indices):
        bootstrap_means = matrix[:, sample_indices].mean(axis=1)
        for recenter_index in range(3):
            statistics = root_n * (bootstrap_means - recentering[recenter_index]) / safe_stds
            simulated[sample_number, recenter_index] = max(0.0, float(np.max(statistics)))
    exceedances = np.sum(simulated >= observed, axis=0)
    p_values = (exceedances + 1.0) / (bootstrap_samples + 1.0)
    critical_values = np.quantile(simulated, 0.95, axis=0)
    lower_p, consistent_p, upper_p = [float(value) for value in p_values]
    lower_critical, consistent_critical, upper_critical = [float(value) for value in critical_values]
    best_mean = float(means[best_index])
    best_lrv = float(long_run_variances[best_index])
    best_std = math.sqrt(best_lrv) if best_lrv > 0.0 else float("inf")
    required_mean = consistent_critical * best_std / root_n if math.isfinite(best_std) else float("inf")
    additional_mean = max(0.0, required_mean - best_mean) if math.isfinite(required_mean) else float("inf")
    return {"available": True, "method": "Hansen_SPA_consistent_stationary_bootstrap_v3_adaptive_lrv", "candidate_count": len(names), "original_candidate_count": original_candidate_count, "active_candidate_count": int(np.sum(active)), "observations": observations, "bootstrap_samples": bootstrap_samples, "average_block_length": chosen, "block_length_estimator": block, "studentization": "stationary_bootstrap_long_run_variance", "recentring_rule": "Hansen_log_log_consistent", "best_candidate_id": names[best_index], "best_mean_daily_excess_percent": round(best_mean * 100.0, 6), "best_annualized_arithmetic_excess_percent": round(best_mean * 252.0 * 100.0, 4), "best_long_run_variance": round(best_lrv, 12), "best_long_run_std": round(best_std, 10), "observed_max_studentized_statistic": round(observed, 6), "p_values": {"lower": round(lower_p, 6), "consistent": round(consistent_p, 6), "upper": round(upper_p, 6)}, "critical_values_5pct": {"lower": round(lower_critical, 6), "consistent": round(consistent_critical, 6), "upper": round(upper_critical, 6)}, "spa_p_value": round(consistent_p, 6), "required_mean_daily_excess_percent_at_5pct": round(required_mean * 100.0, 6) if math.isfinite(required_mean) else None, "additional_mean_daily_excess_percent_needed_at_5pct": round(additional_mean * 100.0, 6) if math.isfinite(additional_mean) else None, "superior_predictive_ability_pass": consistent_p < 0.05, "promotion_threshold": "consistent_spa_p_value_below_0.05", "benchmark": "same_stock_split_adjusted_buy_and_hold_total_return"}
