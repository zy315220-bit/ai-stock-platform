from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CausalRegimeEstimate:
    regime: str
    as_of_date: str
    method: str
    confidence: float
    state_probabilities: dict[str, float]
    state_annualized_mean_returns: dict[str, float]
    observation_count: int
    future_observations_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _emissions(
    observations: np.ndarray,
    means: np.ndarray,
    variances: np.ndarray,
) -> np.ndarray:
    differences = observations[:, None] - means[None, :]
    density = np.exp(-0.5 * differences**2 / variances[None, :])
    density /= np.sqrt(2.0 * np.pi * variances[None, :])
    return np.clip(density, 1e-300, None)


def _forward_backward(
    emissions: np.ndarray,
    initial: np.ndarray,
    transition: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    observations, states = emissions.shape
    alpha = np.empty((observations, states), dtype=float)
    scales = np.empty(observations, dtype=float)
    alpha[0] = initial * emissions[0]
    scales[0] = max(float(alpha[0].sum()), 1e-300)
    alpha[0] /= scales[0]
    for index in range(1, observations):
        alpha[index] = alpha[index - 1] @ transition
        alpha[index] *= emissions[index]
        scales[index] = max(float(alpha[index].sum()), 1e-300)
        alpha[index] /= scales[index]

    beta = np.ones((observations, states), dtype=float)
    for index in range(observations - 2, -1, -1):
        beta[index] = transition @ (
            emissions[index + 1] * beta[index + 1]
        )
        beta[index] /= max(scales[index + 1], 1e-300)
    gamma = alpha * beta
    gamma /= np.clip(gamma.sum(axis=1, keepdims=True), 1e-300, None)
    log_likelihood = float(np.log(scales).sum())
    return alpha, beta, gamma, log_likelihood


def _fit_three_state_hamilton_model(
    observations: np.ndarray,
    *,
    max_iterations: int = 80,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit a three-state Gaussian Markov-switching mean model by EM."""
    states = 3
    means = np.quantile(observations, [0.2, 0.5, 0.8]).astype(float)
    overall_variance = max(float(np.var(observations)), 1e-8)
    variances = np.full(states, overall_variance, dtype=float)
    transition = np.full((states, states), 0.03, dtype=float)
    np.fill_diagonal(transition, 0.94)
    transition /= transition.sum(axis=1, keepdims=True)
    initial = np.full(states, 1.0 / states, dtype=float)
    previous_likelihood = float("-inf")

    for _ in range(max_iterations):
        emissions = _emissions(observations, means, variances)
        alpha, beta, gamma, likelihood = _forward_backward(
            emissions,
            initial,
            transition,
        )
        xi_sum = np.zeros((states, states), dtype=float)
        for index in range(len(observations) - 1):
            joint = (
                alpha[index, :, None]
                * transition
                * emissions[index + 1, None, :]
                * beta[index + 1, None, :]
            )
            total = float(joint.sum())
            if total > 0:
                xi_sum += joint / total

        weights = np.clip(gamma.sum(axis=0), 1e-8, None)
        initial = gamma[0]
        transition = xi_sum / np.clip(
            gamma[:-1].sum(axis=0)[:, None],
            1e-8,
            None,
        )
        transition = np.clip(transition, 1e-6, None)
        transition /= transition.sum(axis=1, keepdims=True)
        means = (gamma * observations[:, None]).sum(axis=0) / weights
        differences = observations[:, None] - means[None, :]
        variances = (gamma * differences**2).sum(axis=0) / weights
        variances = np.clip(variances, 1e-8, None)
        if abs(likelihood - previous_likelihood) < 1e-8:
            break
        previous_likelihood = likelihood

    emissions = _emissions(observations, means, variances)
    alpha, _, _, _ = _forward_backward(emissions, initial, transition)
    return means, alpha[-1]


def _weekly_returns(daily_returns: pd.Series) -> pd.Series:
    wealth = (1.0 + daily_returns).cumprod()
    weekly_wealth = wealth.resample("W-FRI").last().dropna()
    return weekly_wealth.pct_change().dropna()


def _fallback_estimate(
    daily_returns: pd.Series,
    as_of_date: pd.Timestamp,
) -> CausalRegimeEstimate:
    trailing = daily_returns.tail(126)
    cumulative = float((1.0 + trailing).prod() - 1.0)
    if cumulative >= 0.05:
        regime = "BULL"
    elif cumulative <= -0.05:
        regime = "BEAR"
    else:
        regime = "SIDEWAYS"
    confidence = min(0.8, 0.45 + abs(cumulative) * 2.0)
    return CausalRegimeEstimate(
        regime=regime,
        as_of_date=as_of_date.strftime("%Y-%m-%d"),
        method="causal_trailing_126_session_fallback",
        confidence=round(confidence, 6),
        state_probabilities={regime: round(confidence, 6)},
        state_annualized_mean_returns={},
        observation_count=int(len(daily_returns)),
    )


def estimate_hamilton_regime_as_of(
    benchmark_daily_returns: pd.Series,
    as_of_date: str | pd.Timestamp,
) -> CausalRegimeEstimate:
    """Estimate a regime using only benchmark returns known by ``as_of_date``."""
    as_of = pd.Timestamp(as_of_date).normalize()
    series = pd.Series(benchmark_daily_returns, copy=True)
    series.index = pd.to_datetime(series.index).normalize()
    series = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    series = series.loc[series.index <= as_of]
    series = series.loc[np.isfinite(series.to_numpy(dtype=float))]
    if len(series) < 126:
        raise ValueError(
            "At least 126 point-in-time benchmark observations are required "
            "for market-regime estimation"
        )
    weekly = _weekly_returns(series)
    if len(weekly) < 78:
        return _fallback_estimate(series, as_of)

    lower, upper = weekly.quantile([0.01, 0.99])
    observations = weekly.clip(lower=lower, upper=upper).to_numpy(dtype=float)
    try:
        means, probabilities = _fit_three_state_hamilton_model(observations)
    except (FloatingPointError, ValueError, np.linalg.LinAlgError):
        return _fallback_estimate(series, as_of)
    order = np.argsort(means)
    labels = {
        int(order[0]): "BEAR",
        int(order[1]): "SIDEWAYS",
        int(order[2]): "BULL",
    }
    selected_state = int(np.argmax(probabilities))
    state_probabilities = {
        labels[index]: round(float(probabilities[index]), 6)
        for index in range(3)
    }
    annualized_means = {
        labels[index]: round(float(means[index]) * 52.0 * 100.0, 4)
        for index in range(3)
    }
    return CausalRegimeEstimate(
        regime=labels[selected_state],
        as_of_date=as_of.strftime("%Y-%m-%d"),
        method="Hamilton_three_state_Gaussian_Markov_switching_weekly_v1",
        confidence=round(float(probabilities[selected_state]), 6),
        state_probabilities=state_probabilities,
        state_annualized_mean_returns=annualized_means,
        observation_count=int(len(weekly)),
    )
