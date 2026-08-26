from __future__ import annotations

import numpy as np
import pytest

from app.services.research_lab.statistical_evidence import hansen_spa_test

arch_bootstrap = pytest.importorskip("arch.bootstrap")
SPA = arch_bootstrap.SPA


def _arch_consistent_pvalue(
    candidates: dict[str, np.ndarray],
    *,
    block_size: int,
    reps: int,
    seed: int,
) -> float:
    names = list(candidates)
    matrix = np.column_stack([candidates[name] for name in names])
    # arch.SPA is formulated on losses. Zero benchmark loss and negative
    # excess-return losses make a positive strategy excess return equivalent to
    # superior predictive ability versus the benchmark.
    benchmark_losses = np.zeros(matrix.shape[0], dtype=float)
    model_losses = -matrix
    spa = SPA(
        benchmark_losses,
        model_losses,
        block_size=block_size,
        reps=reps,
        bootstrap="stationary",
        studentize=True,
        seed=seed,
    )
    spa.compute()
    return float(spa.pvalues["consistent"])


def _ar1_noise(rng: np.random.Generator, n: int, rho: float = 0.45) -> np.ndarray:
    shocks = rng.normal(0.0, 0.01, n)
    out = np.empty(n, dtype=float)
    out[0] = shocks[0]
    for index in range(1, n):
        out[index] = rho * out[index - 1] + shocks[index]
    return out


def test_spa_agrees_with_arch_on_strong_serially_correlated_signal() -> None:
    rng = np.random.default_rng(20260826)
    n = 360
    candidates = {
        "noise_a": _ar1_noise(rng, n),
        "noise_b": _ar1_noise(rng, n),
        "strong_alpha": _ar1_noise(rng, n) + 0.0035,
    }
    reps = 1200
    block = 10
    seed = 99173

    ours = hansen_spa_test(
        candidates,
        bootstrap_samples=reps,
        average_block_length=block,
        seed=seed,
    )
    reference = _arch_consistent_pvalue(
        candidates,
        block_size=block,
        reps=reps,
        seed=seed,
    )

    assert ours["available"] is True
    assert float(ours["p_value_consistent"]) < 0.05
    assert reference < 0.05


def test_spa_does_not_manufacture_significance_from_correlated_noise() -> None:
    rng = np.random.default_rng(71003)
    n = 420
    shared = _ar1_noise(rng, n, rho=0.55)
    candidates = {
        "noise_a": 0.75 * shared + 0.25 * _ar1_noise(rng, n, rho=0.30),
        "noise_b": 0.70 * shared + 0.30 * _ar1_noise(rng, n, rho=0.40),
        "noise_c": 0.65 * shared + 0.35 * _ar1_noise(rng, n, rho=0.50),
    }
    reps = 1200
    block = 12
    seed = 44117

    ours = hansen_spa_test(
        candidates,
        bootstrap_samples=reps,
        average_block_length=block,
        seed=seed,
    )
    reference = _arch_consistent_pvalue(
        candidates,
        block_size=block,
        reps=reps,
        seed=seed,
    )

    assert ours["available"] is True
    assert float(ours["p_value_consistent"]) >= 0.05
    assert reference >= 0.05


def test_hansen_pvalue_bounds_remain_ordered() -> None:
    rng = np.random.default_rng(18181)
    candidates = {
        f"candidate_{index}": _ar1_noise(rng, 320) + (index - 2) * 0.00025
        for index in range(5)
    }
    result = hansen_spa_test(
        candidates,
        bootstrap_samples=800,
        average_block_length=10,
        seed=3001,
    )

    assert result["available"] is True
    lower = float(result["p_value_lower"])
    consistent = float(result["p_value_consistent"])
    upper = float(result["p_value_upper"])
    assert 0.0 <= lower <= consistent <= upper <= 1.0
