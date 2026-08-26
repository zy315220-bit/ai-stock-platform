from __future__ import annotations

import numpy as np
import pytest

from app.services.research_lab.statistical_evidence import (
    _stationary_long_run_variance,
    hansen_spa_test,
)

arch_bootstrap = pytest.importorskip("arch.bootstrap")
SPA = arch_bootstrap.SPA


def _arch_spa(
    candidates: dict[str, np.ndarray],
    *,
    block_size: int,
    reps: int,
    seed: int,
) -> object:
    names = list(candidates)
    matrix = np.column_stack([candidates[name] for name in names])
    # arch.SPA is formulated on losses. Zero benchmark loss and negative
    # excess-return losses make positive excess return equivalent to superior
    # predictive ability versus the benchmark.
    benchmark_losses = np.zeros(matrix.shape[0], dtype=float)
    model_losses = -matrix
    return SPA(
        benchmark_losses,
        model_losses,
        block_size=block_size,
        reps=reps,
        bootstrap="stationary",
        studentize=True,
        seed=seed,
    )


def _arch_consistent_pvalue(
    candidates: dict[str, np.ndarray],
    *,
    block_size: int,
    reps: int,
    seed: int,
) -> float:
    spa = _arch_spa(
        candidates,
        block_size=block_size,
        reps=reps,
        seed=seed,
    )
    spa.compute()
    return float(spa.pvalues["consistent"])


def _ours_pvalue(result: dict[str, object], kind: str) -> float:
    p_values = result.get("p_values")
    if isinstance(p_values, dict) and kind in p_values:
        return float(p_values[kind])
    if kind == "consistent" and "spa_p_value" in result:
        return float(result["spa_p_value"])
    raise AssertionError(
        f"missing {kind} SPA p-value; keys={sorted(result)}"
    )


def _ar1_noise(
    rng: np.random.Generator,
    n: int,
    rho: float = 0.45,
) -> np.ndarray:
    shocks = rng.normal(0.0, 0.01, n)
    out = np.empty(n, dtype=float)
    out[0] = shocks[0]
    for index in range(1, n):
        out[index] = rho * out[index - 1] + shocks[index]
    return out


def test_stationary_lrv_matches_arch_reference() -> None:
    rng = np.random.default_rng(48017)
    n = 420
    block = 11
    candidates = {
        "ar1_low": _ar1_noise(rng, n, rho=0.20),
        "ar1_mid": _ar1_noise(rng, n, rho=0.50),
        "ar1_high": _ar1_noise(rng, n, rho=0.75),
    }
    spa = _arch_spa(candidates, block_size=block, reps=200, seed=9182)
    # Validation-only parity check against arch 8.0's asymptotic stationary
    # bootstrap variance implementation. This is deliberately private API use
    # in a pinned reference harness, never production runtime code.
    spa._compute_variance()
    reference = np.asarray(spa._loss_diff_var, dtype=float)
    ours = np.asarray(
        [
            _stationary_long_run_variance(
                values,
                average_block_length=block,
            )
            for values in candidates.values()
        ],
        dtype=float,
    )
    np.testing.assert_allclose(ours, reference, rtol=1e-11, atol=1e-14)


def test_spa_agrees_with_arch_on_unambiguous_dependent_alpha() -> None:
    rng = np.random.default_rng(20260826)
    n = 360
    candidates = {
        "noise_a": _ar1_noise(rng, n),
        "noise_b": _ar1_noise(rng, n),
        # Make the power fixture intentionally unambiguous. The previous
        # independent full-volatility AR(1)+0.35% draw happened to realize a
        # much weaker sample signal, so it was not a valid deterministic
        # strong-signal regression test.
        "strong_alpha": 0.006 + 0.30 * _ar1_noise(rng, n),
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
    ours_p = _ours_pvalue(ours, "consistent")
    assert ours_p < 0.05, f"ours failed strong-signal power check: p={ours_p}"
    assert reference < 0.05, f"arch failed strong-signal power check: p={reference}"


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
    ours_p = _ours_pvalue(ours, "consistent")
    assert ours_p >= 0.05, f"ours false-positive on correlated noise: p={ours_p}"
    assert reference >= 0.05, f"arch false-positive on correlated noise: p={reference}"


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
    lower = _ours_pvalue(result, "lower")
    consistent = _ours_pvalue(result, "consistent")
    upper = _ours_pvalue(result, "upper")
    assert 0.0 <= lower <= consistent <= upper <= 1.0
