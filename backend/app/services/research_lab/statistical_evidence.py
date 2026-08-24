from __future__ import annotations

import math
from itertools import combinations
from statistics import NormalDist
from typing import Any, Iterable

import numpy as np

_NORMAL = NormalDist()
_EULER_MASCHERONI = 0.5772156649015329


def _clean(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def _deduplicate_return_paths(
    candidates: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
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


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    benchmark_sharpe: float,
    observations: int,
    skewness: float,
    kurtosis: float,
) -> float:
    """Bailey–López de Prado PSR under non-normal observed returns."""
    if observations < 3:
        return 0.0
    variance_term = (
        1.0
        - skewness * observed_sharpe
        + ((kurtosis - 1.0) / 4.0) * observed_sharpe**2
    )
    if not math.isfinite(variance_term) or variance_term <= 0:
        return 0.0
    statistic = (
        (observed_sharpe - benchmark_sharpe)
        * math.sqrt(observations - 1)
        / math.sqrt(variance_term)
    )
    return max(0.0, min(1.0, _NORMAL.cdf(statistic)))


def minimum_track_record_length(
    observed_sharpe: float,
    benchmark_sharpe: float,
    skewness: float,
    kurtosis: float,
    *,
    confidence: float = 0.95,
) -> int | None:
    """Minimum observations required to reject the benchmark Sharpe."""
    difference = observed_sharpe - benchmark_sharpe
    if difference <= 0 or not 0.5 < confidence < 1.0:
        return None
    variance_term = (
        1.0
        - skewness * observed_sharpe
        + ((kurtosis - 1.0) / 4.0) * observed_sharpe**2
    )
    if not math.isfinite(variance_term) or variance_term <= 0:
        return None
    z_score = _NORMAL.inv_cdf(confidence)
    required = 1.0 + variance_term * (z_score / difference) ** 2
    return max(3, int(math.ceil(required)))


def _stationary_bootstrap_indices(
    observations: int,
    samples: int,
    *,
    average_block_length: int,
    seed: int,
) -> np.ndarray:
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


def stationary_bootstrap_mean_interval(
    returns: Iterable[float],
    *,
    confidence: float = 0.95,
    samples: int = 400,
    average_block_length: int = 10,
    seed: int = 20260825,
) -> dict[str, Any]:
    values = _clean(returns)
    if len(values) < 10:
        return {
            "available": False,
            "reason": "insufficient_dependent_return_observations",
            "observations": int(len(values)),
        }
    indices = _stationary_bootstrap_indices(
        len(values),
        samples,
        average_block_length=average_block_length,
        seed=seed,
    )
    means = values[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(means, [alpha, 1.0 - alpha])
    return {
        "available": True,
        "method": "Politis-Romano stationary bootstrap",
        "observations": int(len(values)),
        "samples": samples,
        "average_block_length": average_block_length,
        "confidence": confidence,
        "mean_daily_return_percent": round(float(values.mean()) * 100.0, 6),
        "mean_daily_return_ci_percent": [
            round(float(lower) * 100.0, 6),
            round(float(upper) * 100.0, 6),
        ],
        "annualized_arithmetic_return_ci_percent": [
            round(float(lower) * 252.0 * 100.0, 4),
            round(float(upper) * 252.0 * 100.0, 4),
        ],
    }


def build_statistical_evidence(
    strategy_returns: Iterable[float],
    benchmark_returns: Iterable[float] | None = None,
    *,
    benchmark_sharpe: float = 0.0,
    confidence: float = 0.95,
) -> dict[str, Any]:
    strategy = _clean(strategy_returns)
    benchmark = (
        _clean(benchmark_returns)
        if benchmark_returns is not None
        else np.asarray([], dtype=float)
    )
    if len(strategy) < 3:
        return {
            "available": False,
            "reason": "insufficient_daily_return_observations",
            "observations": int(len(strategy)),
        }
    sharpe, skewness, kurtosis = _moments(strategy)
    psr = probabilistic_sharpe_ratio(
        sharpe,
        benchmark_sharpe,
        len(strategy),
        skewness,
        kurtosis,
    )
    min_track = minimum_track_record_length(
        sharpe,
        benchmark_sharpe,
        skewness,
        kurtosis,
        confidence=confidence,
    )
    bootstrap = stationary_bootstrap_mean_interval(
        strategy,
        confidence=confidence,
    )
    lower_bootstrap = (
        float(bootstrap["mean_daily_return_ci_percent"][0])
        if bootstrap.get("available")
        else float("-inf")
    )
    comparable = min(len(strategy), len(benchmark))
    excess = (
        strategy[-comparable:] - benchmark[-comparable:]
        if comparable > 0
        else np.asarray([], dtype=float)
    )
    return {
        "available": True,
        "method": "PSR_MinTRL_and_stationary_bootstrap_v1",
        "observations": int(len(strategy)),
        "period_sharpe_ratio": round(sharpe, 8),
        "annualized_sharpe_ratio": round(sharpe * math.sqrt(252.0), 4),
        "skewness": round(skewness, 6),
        "kurtosis": round(kurtosis, 6),
        "probabilistic_sharpe_ratio": round(psr, 6),
        "probabilistic_sharpe_ratio_percent": round(psr * 100.0, 4),
        "minimum_track_record_observations": min_track,
        "track_record_sufficient": bool(
            min_track is not None and len(strategy) >= min_track
        ),
        "stationary_bootstrap": bootstrap,
        "statistical_quality_pass": bool(
            psr >= confidence
            and min_track is not None
            and len(strategy) >= min_track
            and lower_bootstrap > 0.0
        ),
        "benchmark_return_basis": (
            "same_stock_split_adjusted_buy_and_hold_total_return"
            if comparable > 0
            else None
        ),
        "_daily_excess_returns": excess.tolist(),
    }


def deflated_sharpe_evidence(
    candidate_evidence: dict[str, Any],
    trial_period_sharpes: Iterable[float],
) -> dict[str, Any]:
    trials = _clean(trial_period_sharpes)
    if not candidate_evidence.get("available") or len(trials) < 2:
        return {
            "available": False,
            "reason": "insufficient_strategy_trials",
            "trial_count": int(len(trials)),
        }
    mean_trial = float(np.mean(trials))
    trial_std = float(np.std(trials, ddof=1))
    trial_count = len(trials)
    quantile_a = _NORMAL.inv_cdf(1.0 - 1.0 / trial_count)
    quantile_b = _NORMAL.inv_cdf(
        1.0 - 1.0 / (trial_count * math.e)
    )
    expected_maximum = mean_trial + trial_std * (
        (1.0 - _EULER_MASCHERONI) * quantile_a
        + _EULER_MASCHERONI * quantile_b
    )
    probability = probabilistic_sharpe_ratio(
        float(candidate_evidence.get("period_sharpe_ratio", 0.0)),
        expected_maximum,
        int(candidate_evidence.get("observations", 0)),
        float(candidate_evidence.get("skewness", 0.0)),
        float(candidate_evidence.get("kurtosis", 3.0)),
    )
    return {
        "available": True,
        "method": "Bailey-Lopez_de_Prado_deflated_Sharpe_v1",
        "trial_count": int(trial_count),
        "mean_trial_period_sharpe": round(mean_trial, 8),
        "trial_period_sharpe_std": round(trial_std, 8),
        "expected_maximum_period_sharpe": round(expected_maximum, 8),
        "deflated_sharpe_probability": round(probability, 6),
        "deflated_sharpe_probability_percent": round(
            probability * 100.0,
            4,
        ),
        "multiple_testing_pass": probability >= 0.95,
    }


def cscv_probability_of_backtest_overfitting(
    candidate_returns: dict[str, Iterable[float]],
    *,
    slice_count: int = 8,
) -> dict[str, Any]:
    cleaned = {
        candidate_id: _clean(returns)
        for candidate_id, returns in candidate_returns.items()
    }
    cleaned = {
        candidate_id: values
        for candidate_id, values in cleaned.items()
        if len(values) >= slice_count * 5
    }
    original_candidate_count = len(cleaned)
    cleaned = _deduplicate_return_paths(cleaned)
    if len(cleaned) < 3 or slice_count < 4 or slice_count % 2:
        return {
            "available": False,
            "reason": "CSCV_requires_three_candidates_and_even_slices",
            "candidate_count": len(cleaned),
            "original_candidate_count": original_candidate_count,
            "slice_count": slice_count,
        }
    length = min(len(values) for values in cleaned.values())
    names = list(cleaned)
    matrix = np.vstack([cleaned[name][-length:] for name in names])
    blocks = np.array_split(np.arange(length), slice_count)
    logits: list[float] = []
    degradations: list[float] = []

    for in_sample_blocks in combinations(range(slice_count), slice_count // 2):
        in_set = set(in_sample_blocks)
        is_indices = np.concatenate([blocks[index] for index in in_set])
        oos_indices = np.concatenate(
            [blocks[index] for index in range(slice_count) if index not in in_set]
        )

        def sharpes(indices: np.ndarray) -> np.ndarray:
            selected = matrix[:, indices]
            means = selected.mean(axis=1)
            stds = selected.std(axis=1, ddof=1)
            return np.divide(
                means,
                stds,
                out=np.full_like(means, -np.inf),
                where=stds > 0,
            )

        is_sharpes = sharpes(is_indices)
        oos_sharpes = sharpes(oos_indices)
        winner = int(np.argmax(is_sharpes))
        order = np.argsort(oos_sharpes)
        rank = int(np.where(order == winner)[0][0]) + 1
        percentile = (rank - 0.5) / len(names)
        percentile = min(max(percentile, 1e-9), 1.0 - 1e-9)
        logits.append(math.log(percentile / (1.0 - percentile)))
        degradations.append(float(is_sharpes[winner] - oos_sharpes[winner]))

    pbo = sum(value <= 0.0 for value in logits) / len(logits)
    return {
        "available": True,
        "method": "Combinatorially_Symmetric_Cross_Validation_v1",
        "candidate_count": len(names),
        "original_candidate_count": original_candidate_count,
        "slice_count": slice_count,
        "combination_count": len(logits),
        "pbo_probability": round(pbo, 6),
        "pbo_probability_percent": round(pbo * 100.0, 4),
        "median_oos_rank_logit": round(float(np.median(logits)), 6),
        "median_sharpe_degradation": round(
            float(np.median(degradations)),
            6,
        ),
        "overfitting_risk_pass": pbo <= 0.20,
    }


def hansen_spa_test(
    candidate_excess_returns: dict[str, Iterable[float]],
    *,
    bootstrap_samples: int = 600,
    average_block_length: int = 10,
    seed: int = 20260825,
) -> dict[str, Any]:
    cleaned = {
        name: _clean(values)
        for name, values in candidate_excess_returns.items()
    }
    original_candidate_count = len(cleaned)
    cleaned = _deduplicate_return_paths(cleaned)
    if len(cleaned) < 2:
        return {
            "available": False,
            "reason": "SPA_requires_at_least_two_candidate_models",
            "candidate_count": len(cleaned),
            "original_candidate_count": original_candidate_count,
        }
    observations = min(len(values) for values in cleaned.values())
    if observations < 30:
        return {
            "available": False,
            "reason": "SPA_requires_at_least_30_return_observations",
            "candidate_count": len(cleaned),
            "observations": observations,
        }
    names = list(cleaned)
    matrix = np.vstack(
        [cleaned[name][-observations:] for name in names]
    )
    means = matrix.mean(axis=1)
    stds = matrix.std(axis=1, ddof=1)
    safe_stds = np.where(stds > 0, stds, np.inf)
    observed_statistics = np.sqrt(observations) * means / safe_stds
    observed = max(0.0, float(np.max(observed_statistics)))

    # Hansen's consistent recentering drops very poor alternatives before the
    # common stationary bootstrap. This is the key power improvement over an
    # unstudentized Reality Check while preserving cross-model dependence.
    cutoff = -math.sqrt(
        max(0.0, 2.0 * math.log(max(math.log(observations), 1.0)))
    )
    active = observed_statistics >= cutoff
    if not np.any(active):
        active[np.argmax(observed_statistics)] = True
    centered = matrix - means[:, None]
    indices = _stationary_bootstrap_indices(
        observations,
        bootstrap_samples,
        average_block_length=average_block_length,
        seed=seed,
    )
    exceedances = 0
    for sample_indices in indices:
        bootstrap_means = centered[:, sample_indices].mean(axis=1)
        statistic = float(
            np.max(
                np.sqrt(observations)
                * bootstrap_means[active]
                / safe_stds[active]
            )
        )
        if statistic >= observed:
            exceedances += 1
    p_value = (exceedances + 1.0) / (bootstrap_samples + 1.0)
    return {
        "available": True,
        "method": "Hansen_SPA_consistent_stationary_bootstrap_v1",
        "candidate_count": len(names),
        "original_candidate_count": original_candidate_count,
        "active_candidate_count": int(np.sum(active)),
        "observations": observations,
        "bootstrap_samples": bootstrap_samples,
        "average_block_length": average_block_length,
        "observed_max_studentized_statistic": round(observed, 6),
        "spa_p_value": round(p_value, 6),
        "superior_predictive_ability_pass": p_value < 0.05,
        "benchmark": "same_stock_split_adjusted_buy_and_hold_total_return",
    }
